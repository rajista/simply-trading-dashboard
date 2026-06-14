from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from io import StringIO
import math
import os
import re
import threading
import time as time_module
import xml.etree.ElementTree as ET

from flask import Flask, redirect, render_template, request
import pandas as pd
import requests
import yfinance as yf

from stocks import STOCKS

app = Flask(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
NIFTY_50_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv"
INDEX_SYMBOLS = {
    "^NSEI": "NIFTY 50",
    "^BSESN": "SENSEX",
    "^NSEBANK": "NIFTY BANK",
    "^CNXIT": "NIFTY IT",
}
NEWS_FEEDS = (
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
)
PAGE_REDIRECTS = {
    "articles": "https://articles.trading-simplified.com/blog/",
    "swp-calculator": "https://swp-nifty-v2.netlify.app/",
    "option-chain-analysis": "https://articles.trading-simplified.com/option-chain-analysis/",
    "market-performance": "https://market-performace-v1.streamlit.app/",
}
MARKET_CACHE_TTL = int(os.getenv("MARKET_CACHE_TTL_SECONDS", "1200"))
NEWS_CACHE_TTL = 900
CALENDAR_CACHE_TTL = 21600
CONSTITUENT_CACHE_TTL = 86400
_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_REFRESHING = set()


def fetch_price_data(symbols):
    quotes = {}
    try:
        tickers = yf.Tickers(" ".join(symbols))
        for symbol in symbols:
            ticker = tickers.tickers.get(symbol)
            if ticker is None:
                continue
            info = ticker.info
            current = info.get("regularMarketPrice")
            prev_close = info.get("regularMarketPreviousClose")
            change = None
            percent = None
            if current is not None and prev_close is not None:
                change = current - prev_close
                percent = (change / prev_close) * 100 if prev_close != 0 else 0
            quotes[symbol] = {
                "price": current,
                "change": change,
                "percent": percent,
                "volume": info.get("volume"),
                "market_cap": info.get("marketCap"),
            }
    except Exception:
        pass
    return quotes


def fetch_nifty50_constituents():
    response = requests.get(
        NIFTY_50_URL,
        timeout=12,
        headers={"User-Agent": "Mozilla/5.0 SimplyTrading/1.0"},
    )
    response.raise_for_status()
    rows = []
    for item in csv.DictReader(StringIO(response.text.lstrip("\ufeff"))):
        symbol = (item.get("Symbol") or "").strip()
        company = (item.get("Company Name") or "").strip()
        industry = (item.get("Industry") or "Other").strip()
        if symbol and company:
            rows.append(
                {
                    "symbol": f"{symbol}.NS",
                    "name": company.removesuffix(" Ltd.").removesuffix(" Limited"),
                    "sector": industry,
                    "industry": industry,
                    "isin": (item.get("ISIN Code") or "").strip(),
                }
            )
    if len(rows) != 50:
        raise ValueError(f"Expected 50 NIFTY constituents, received {len(rows)}")
    return rows


def get_stock_universe():
    universe, stale = get_cached_swr(
        "nifty50_constituents",
        CONSTITUENT_CACHE_TTL,
        fetch_nifty50_constituents,
    )
    return (universe or STOCKS), stale


def format_market_cap(value):
    if not value:
        return "-"
    value = float(value)
    if value >= 1e7:
        return f"{value / 1e7:.2f} Cr"
    if value >= 1e5:
        return f"{value / 1e5:.2f} L"
    return f"{value:,.0f}"


def format_volume(value):
    if not value:
        return "-"
    value = float(value)
    if value >= 1e7:
        return f"{value / 1e7:.2f} Cr"
    if value >= 1e5:
        return f"{value / 1e5:.2f} L"
    return f"{value:,.0f}"


def get_market_status(now=None):
    current = now or datetime.now(IST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=IST)
    else:
        current = current.astimezone(IST)
    if current.weekday() >= 5:
        return {"label": "Closed", "class_name": "closed"}
    current_time = current.time().replace(tzinfo=None)
    if current_time < time(9, 15):
        return {"label": "Pre-Market", "class_name": "pre-market"}
    if current_time <= time(15, 30):
        return {"label": "Open", "class_name": "open"}
    return {"label": "Closed", "class_name": "closed"}


def get_cached(key, ttl, loader, now=None):
    current = time_module.time() if now is None else now
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and cached["expires"] > current:
            return cached["data"], False
    try:
        data = loader()
        if data is None:
            raise ValueError("Loader returned no data")
        with _CACHE_LOCK:
            _CACHE[key] = {"data": data, "expires": current + ttl}
        return data, False
    except Exception:
        if cached:
            return cached["data"], True
        return None, False


def _refresh_cached_value(key, ttl, loader):
    try:
        data = loader()
        if data is None:
            raise ValueError("Loader returned no data")
        with _CACHE_LOCK:
            _CACHE[key] = {
                "data": data,
                "expires": time_module.time() + ttl,
            }
    except Exception:
        pass
    finally:
        with _CACHE_LOCK:
            _CACHE_REFRESHING.discard(key)


def get_cached_swr(key, ttl, loader, now=None):
    """Serve expired data immediately while one background refresh runs."""
    current = time_module.time() if now is None else now
    should_refresh = False
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and cached["expires"] > current:
            return cached["data"], False
        if cached and key not in _CACHE_REFRESHING:
            _CACHE_REFRESHING.add(key)
            should_refresh = True
    if cached:
        if should_refresh:
            threading.Thread(
                target=_refresh_cached_value,
                args=(key, ttl, loader),
                daemon=True,
                name=f"cache-refresh-{key[:32]}",
            ).start()
        return cached["data"], True
    return get_cached(key, ttl, loader, now=now)


def get_market_quotes(stocks):
    symbols = [stock["symbol"] for stock in stocks]
    key = f"quotes:{','.join(symbols)}"
    return get_cached_swr(
        key,
        MARKET_CACHE_TTL,
        lambda: fetch_price_data(symbols),
    )


def _ticker_frame(download, symbol):
    if download is None or download.empty:
        return pd.DataFrame()
    if not isinstance(download.columns, pd.MultiIndex):
        return download.copy()
    level_zero = download.columns.get_level_values(0)
    level_one = download.columns.get_level_values(1)
    if symbol in level_zero:
        return download[symbol].copy()
    if symbol in level_one:
        return download.xs(symbol, axis=1, level=1).copy()
    return pd.DataFrame()


def _clean_number(value):
    if value is None or pd.isna(value):
        return None
    return float(value)


def fetch_index_history():
    return yf.download(
        list(INDEX_SYMBOLS),
        period="5d",
        interval="15m",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=12,
    )


def fetch_stock_history(stocks):
    return yf.download(
        [stock["symbol"] for stock in stocks],
        period="1y",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=15,
    )


def build_candles(frame, limit=32):
    required = {"Open", "High", "Low", "Close"}
    if frame.empty or not required.issubset(frame.columns):
        return []
    clean = frame[list(required)].dropna().tail(limit)
    if clean.empty:
        return []
    low = float(clean["Low"].min())
    high = float(clean["High"].max())
    span = high - low or 1
    width, height, pad_x, pad_y = 300, 120, 8, 8
    step = (width - pad_x * 2) / max(len(clean), 1)

    def y_pos(value):
        return round(pad_y + (high - float(value)) / span * (height - pad_y * 2), 2)

    candles = []
    for index, (_, row) in enumerate(clean.iterrows()):
        open_y = y_pos(row["Open"])
        close_y = y_pos(row["Close"])
        candles.append(
            {
                "x": round(pad_x + index * step + step / 2, 2),
                "high_y": y_pos(row["High"]),
                "low_y": y_pos(row["Low"]),
                "body_y": min(open_y, close_y),
                "body_height": max(abs(open_y - close_y), 1.5),
                "body_width": max(min(step * 0.58, 6), 2.5),
                "up": row["Close"] >= row["Open"],
            }
        )
    return candles


def build_index_cards(download):
    cards = []
    for symbol, name in INDEX_SYMBOLS.items():
        frame = _ticker_frame(download, symbol)
        if frame.empty or "Close" not in frame:
            cards.append({"name": name, "symbol": symbol, "available": False})
            continue
        closes = frame["Close"].dropna()
        if closes.empty:
            cards.append({"name": name, "symbol": symbol, "available": False})
            continue
        current = float(closes.iloc[-1])
        daily_last = closes.groupby(closes.index.date).last()
        previous = float(daily_last.iloc[-2]) if len(daily_last) > 1 else float(closes.iloc[0])
        change = current - previous
        percent = change / previous * 100 if previous else 0
        cards.append(
            {
                "name": name,
                "symbol": symbol,
                "available": True,
                "price": current,
                "change": change,
                "percent": percent,
                "date": closes.index[-1].strftime("%b %d"),
                "candles": build_candles(frame),
            }
        )
    return cards


def build_stock_rows(quotes, history, stocks):
    rows = []
    for stock in stocks:
        symbol = stock["symbol"]
        quote = quotes.get(symbol, {})
        frame = _ticker_frame(history, symbol)
        closes = frame["Close"].dropna() if not frame.empty and "Close" in frame else pd.Series(dtype=float)
        current = quote.get("price")
        if current is None and not closes.empty:
            current = float(closes.iloc[-1])
        sma50 = float(closes.tail(50).mean()) if len(closes) >= 20 else None
        sma200 = float(closes.tail(200).mean()) if len(closes) >= 100 else None
        high52 = float(closes.max()) if not closes.empty else None
        low52 = float(closes.min()) if not closes.empty else None
        volumes = frame["Volume"].dropna() if not frame.empty and "Volume" in frame else pd.Series(dtype=float)
        current_volume = quote.get("volume")
        if current_volume is None and not volumes.empty:
            current_volume = float(volumes.iloc[-1])
        previous_volume = float(volumes.iloc[-2]) if len(volumes) > 1 else None
        volume_change = (
            (current_volume - previous_volume) / previous_volume * 100
            if current_volume is not None and previous_volume
            else None
        )
        five_day_change = (
            (float(closes.iloc[-1]) - float(closes.iloc[-6])) / float(closes.iloc[-6]) * 100
            if len(closes) >= 6 and closes.iloc[-6]
            else None
        )
        signal = "Neutral"
        if current is not None and sma50 is not None and sma200 is not None:
            if current > sma50 > sma200:
                signal = "Uptrend"
            elif current < sma50 < sma200:
                signal = "Downtrend"
            elif current > sma50:
                signal = "Above SMA50"
            else:
                signal = "Below SMA50"
        rows.append(
            {
                **stock,
                "display_symbol": symbol.removesuffix(".NS"),
                "price": current,
                "change": quote.get("change"),
                "percent": quote.get("percent"),
                "volume": current_volume,
                "volume_change": volume_change,
                "five_day_change": five_day_change,
                "market_cap": quote.get("market_cap"),
                "sma50": sma50,
                "sma200": sma200,
                "high52": high52,
                "low52": low52,
                "signal": signal,
            }
        )
    return rows


def build_breadth(rows):
    priced = [row for row in rows if row["percent"] is not None]
    count = len(priced)

    def metric(label, left_label, right_label, left_count, total, right_count=None):
        resolved_right = max(total - left_count, 0) if right_count is None else right_count
        measured_total = left_count + resolved_right if right_count is not None else total
        left_percent = left_count / measured_total * 100 if measured_total else 0
        return {
            "label": label,
            "left_label": left_label,
            "right_label": right_label,
            "left_count": left_count,
            "right_count": resolved_right,
            "left_percent": left_percent,
            "right_percent": resolved_right / measured_total * 100 if measured_total else 0,
        }

    gainers = sum(row["percent"] > 0 for row in priced)
    high_rows = [
        row for row in rows
        if row["price"] is not None and row["high52"] and row["price"] >= row["high52"] * 0.98
    ]
    low_rows = [
        row for row in rows
        if row["price"] is not None and row["low52"] and row["price"] <= row["low52"] * 1.02
    ]
    technical50 = [row for row in rows if row["price"] is not None and row["sma50"] is not None]
    technical200 = [row for row in rows if row["price"] is not None and row["sma200"] is not None]
    return [
        metric("Market Breadth", "Advancing", "Declining", gainers, count),
        metric("52 Week Range", "New High", "New Low", len(high_rows), 0, len(low_rows)),
        metric("SMA50", "Above", "Below", sum(r["price"] > r["sma50"] for r in technical50), len(technical50)),
        metric("SMA200", "Above", "Below", sum(r["price"] > r["sma200"] for r in technical200), len(technical200)),
    ]


def build_sector_performance(rows):
    sectors = defaultdict(list)
    for row in rows:
        sectors[row["sector"]].append(row)
    return sorted(
        (
            {
                "name": sector,
                "percent": (
                    sum(row["percent"] for row in values if row["percent"] is not None)
                    / len([row for row in values if row["percent"] is not None])
                    if any(row["percent"] is not None for row in values)
                    else 0
                ),
                "stocks": len(values),
                "advancers": sum((row["percent"] or 0) > 0 for row in values),
                "volume": sum(row["volume"] or 0 for row in values),
                "leader": max(values, key=lambda row: row["percent"] if row["percent"] is not None else -math.inf),
                "laggard": min(values, key=lambda row: row["percent"] if row["percent"] is not None else math.inf),
            }
            for sector, values in sectors.items()
        ),
        key=lambda item: item["percent"],
        reverse=True,
    )


def build_heatmap(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["sector"]].append(row)
    groups = []
    for sector, items in grouped.items():
        items = sorted(
            items,
            key=lambda item: item["market_cap"] or item["volume"] or 0,
            reverse=True,
        )
        total_weight = sum(math.sqrt(item["market_cap"] or item["volume"] or 1) for item in items) or 1
        cells = []
        for item in items:
            percent = item["percent"] or 0
            intensity = min(abs(percent) / 5, 1)
            cells.append(
                {
                    **item,
                    "weight": max(math.sqrt(item["market_cap"] or item["volume"] or 1) / total_weight * 100, 8),
                    "intensity": round(0.28 + intensity * 0.62, 2),
                }
            )
        groups.append({"sector": sector, "cells": cells, "market_cap": sum(i["market_cap"] or 0 for i in items)})
    return sorted(groups, key=lambda group: group["market_cap"], reverse=True)


def load_market_dashboard(stocks):
    quotes, _ = get_market_quotes(stocks)
    quotes = quotes or {}
    index_history = fetch_index_history()
    stock_history = fetch_stock_history(stocks)
    rows = build_stock_rows(quotes, stock_history, stocks)
    available = [row for row in rows if row["percent"] is not None]
    gainers = sorted(available, key=lambda row: row["percent"], reverse=True)
    losers = sorted(
        [row for row in available if row["percent"] < 0],
        key=lambda row: row["percent"],
    )
    active = sorted(
        [row for row in rows if row["volume"] is not None],
        key=lambda row: row["volume"],
        reverse=True,
    )
    return {
        "indices": build_index_cards(index_history),
        "rows": rows,
        "breadth": build_breadth(rows),
        "gainers": gainers[:8],
        "losers": losers[:8],
        "active": active[:8],
        "signals": sorted(rows, key=lambda row: abs(row["percent"] or 0), reverse=True)[:10],
        "sectors": build_sector_performance(rows),
        "heatmap": build_heatmap(rows),
        "market_stats": build_market_stats(rows),
        "internals": build_market_internals(rows),
    }


def build_market_stats(rows):
    priced = [row for row in rows if row["percent"] is not None]
    volumes = [row["volume"] for row in rows if row["volume"] is not None]
    market_caps = [row["market_cap"] for row in rows if row["market_cap"] is not None]
    positive = [row for row in priced if row["percent"] > 0]
    return {
        "tracked": len(rows),
        "priced": len(priced),
        "advance_ratio": len(positive) / len(priced) * 100 if priced else 0,
        "average_change": sum(row["percent"] for row in priced) / len(priced) if priced else None,
        "total_volume": sum(volumes),
        "total_market_cap": sum(market_caps),
    }


def build_market_internals(rows):
    technical50 = [row for row in rows if row["price"] is not None and row["sma50"] is not None]
    technical200 = [row for row in rows if row["price"] is not None and row["sma200"] is not None]
    near_high = [
        row for row in rows
        if row["price"] is not None and row["high52"] and row["price"] >= row["high52"] * 0.95
    ]
    volume_surge = [row for row in rows if row["volume_change"] is not None and row["volume_change"] > 25]
    return {
        "above_sma50": sum(row["price"] > row["sma50"] for row in technical50),
        "above_sma200": sum(row["price"] > row["sma200"] for row in technical200),
        "near_high": len(near_high),
        "volume_surge": len(volume_surge),
    }


def _strip_html(value):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", unescape(value or ""))).strip()


def fetch_headlines():
    headlines = []
    headers = {"User-Agent": "Mozilla/5.0 SimplyTrading/1.0"}
    for source, url in NEWS_FEEDS:
        try:
            response = requests.get(url, timeout=8, headers=headers)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for item in root.findall(".//item")[:6]:
                title = _strip_html(item.findtext("title"))
                link = (item.findtext("link") or "").strip()
                published = item.findtext("pubDate")
                timestamp = ""
                if published:
                    try:
                        timestamp = parsedate_to_datetime(published).astimezone(IST).strftime("%I:%M %p")
                    except (TypeError, ValueError, OverflowError):
                        timestamp = ""
                if title and link.startswith(("http://", "https://")):
                    headlines.append(
                        {"title": title, "url": link, "source": source, "time": timestamp}
                    )
        except (requests.RequestException, ET.ParseError):
            continue
    return headlines[:10]


def _fetch_symbol_calendar(stock):
    calendar = yf.Ticker(stock["symbol"]).calendar or {}
    earnings_dates = calendar.get("Earnings Date") or []
    if isinstance(earnings_dates, (date, datetime)):
        earnings_dates = [earnings_dates]
    normalized_earnings = []
    for value in earnings_dates:
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            normalized_earnings.append(value)
    ex_dividend = calendar.get("Ex-Dividend Date")
    if isinstance(ex_dividend, datetime):
        ex_dividend = ex_dividend.date()
    return {
        "symbol": stock["symbol"].removesuffix(".NS"),
        "name": stock["name"],
        "earnings_dates": normalized_earnings,
        "ex_dividend": ex_dividend if isinstance(ex_dividend, date) else None,
    }


def fetch_company_calendar(stocks):
    entries = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_fetch_symbol_calendar, stock): stock for stock in stocks}
        for future in as_completed(futures):
            try:
                entries.append(future.result())
            except Exception:
                continue
    return entries


def next_trading_sessions(today, count=3):
    sessions = []
    candidate = today + timedelta(days=1)
    while len(sessions) < count:
        if candidate.weekday() < 5:
            sessions.append(
                {
                    "date": candidate,
                    "date_label": candidate.strftime("%b %d"),
                    "time": "09:15",
                    "type": "Market",
                    "title": "NSE regular trading session",
                    "detail": "Pre-open 09:00; regular market 09:15-15:30 IST",
                }
            )
        candidate += timedelta(days=1)
    return sessions


def build_calendar_panels(entries, today=None):
    today = today or datetime.now(IST).date()
    earnings = []
    events = next_trading_sessions(today)
    for entry in entries:
        for earnings_date in entry["earnings_dates"]:
            if earnings_date >= today:
                earnings.append(
                    {
                        "date": earnings_date,
                        "date_label": earnings_date.strftime("%b %d"),
                        "symbol": entry["symbol"],
                        "name": entry["name"],
                    }
                )
        ex_date = entry["ex_dividend"]
        if ex_date and ex_date >= today:
            events.append(
                {
                    "date": ex_date,
                    "date_label": ex_date.strftime("%b %d"),
                    "time": "All day",
                    "type": "Corporate",
                    "title": f"{entry['symbol']} ex-dividend",
                    "detail": entry["name"],
                }
            )
    earnings.sort(key=lambda item: (item["date"], item["symbol"]))
    events.sort(key=lambda item: (item["date"], item["time"]))
    return {"earnings": earnings[:10], "events": events[:8]}


def enrich_earnings(earnings, rows):
    row_by_symbol = {row["display_symbol"]: row for row in rows}
    enriched = []
    for item in earnings:
        row = row_by_symbol.get(item["symbol"], {})
        enriched.append(
            {
                **item,
                "trend": row.get("signal", "Unavailable"),
                "percent": row.get("percent"),
                "volume": row.get("volume"),
                "volume_change": row.get("volume_change"),
            }
        )
    return enriched


def common_context(active_page, show_header_search):
    now = datetime.now(IST)
    return {
        "active_page": active_page,
        "show_header_search": show_header_search,
        "market_status": get_market_status(now),
        "current_time": now.strftime("%a %b %d %Y %I:%M %p IST"),
    }


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/blog/")
def articles():
    return redirect(PAGE_REDIRECTS["articles"], code=302)


@app.route("/swp-calculator/")
def swp_calculator():
    return redirect(PAGE_REDIRECTS["swp-calculator"], code=302)


@app.route("/option-chain-analysis/")
def option_chain_analysis():
    return redirect(PAGE_REDIRECTS["option-chain-analysis"], code=302)


@app.route("/market-performance/")
def market_performance():
    return redirect(PAGE_REDIRECTS["market-performance"], code=302)


@app.route("/")
def dashboard():
    stocks, constituents_stale = get_stock_universe()
    universe_key = ",".join(stock["symbol"] for stock in stocks)
    market, market_stale = get_cached_swr(
        f"market:{universe_key}",
        MARKET_CACHE_TTL,
        lambda: load_market_dashboard(stocks),
    )
    headlines, news_stale = get_cached_swr("news", NEWS_CACHE_TTL, fetch_headlines)
    calendar_entries, calendar_stale = get_cached_swr(
        f"company_calendar:{universe_key}",
        CALENDAR_CACHE_TTL,
        lambda: fetch_company_calendar(stocks),
    )
    market = market or {
        "indices": [],
        "rows": [],
        "breadth": [],
        "gainers": [],
        "losers": [],
        "active": [],
        "signals": [],
        "sectors": [],
        "heatmap": [],
        "market_stats": build_market_stats([]),
        "internals": build_market_internals([]),
    }
    headlines = headlines or []
    calendar = build_calendar_panels(calendar_entries or [])
    earnings = enrich_earnings(calendar["earnings"], market["rows"])
    leading_index = next((card for card in market["indices"] if card.get("available")), None)
    brief = (
        f"Indian markets: {leading_index['name']} at {leading_index['price']:,.2f}, "
        f"{leading_index['percent']:+.2f}% in the latest session."
        if leading_index
        else "Indian market data is temporarily unavailable. Cached panels will return automatically."
    )
    return render_template(
        "dashboard.html",
        **common_context("home", True),
        market=market,
        headlines=headlines,
        market_stale=market_stale,
        news_stale=news_stale,
        calendar_stale=calendar_stale,
        constituents_stale=constituents_stale,
        nearby_events=calendar["events"],
        earnings=earnings,
        market_brief=brief,
        format_market_cap=format_market_cap,
        format_volume=format_volume,
    )


@app.route("/screener")
def screener():
    stocks, _ = get_stock_universe()
    filter_sectors = sorted({stock["sector"] for stock in stocks})
    sector = request.args.get("sector", "")
    search_term = request.args.get("search", "").strip()
    search = search_term.lower()
    filtered = [
        stock
        for stock in stocks
        if (not sector or stock["sector"] == sector)
        and (
            not search
            or search in stock["symbol"].lower()
            or search in stock["name"].lower()
        )
    ]
    quotes, _ = get_market_quotes(stocks)
    quotes = quotes or {}
    stock_rows = []
    for stock in filtered:
        quote = quotes.get(stock["symbol"], {})
        stock_rows.append(
            {
                **stock,
                "display_symbol": stock["symbol"].removesuffix(".NS"),
                **{key: quote.get(key) for key in ("price", "change", "percent", "volume", "market_cap")},
            }
        )
    return render_template(
        "index.html",
        **common_context("screener", False),
        stocks=stock_rows,
        sectors=filter_sectors,
        selected_sector=sector,
        search_term=search_term,
        format_market_cap=format_market_cap,
        format_volume=format_volume,
    )


if __name__ == "__main__":
    app.run(debug=True)
