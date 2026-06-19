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
from urllib.parse import quote
import xml.etree.ElementTree as ET

from flask import Flask, jsonify, redirect, render_template, request
import pandas as pd
import requests
import yfinance as yf

from stocks import STOCKS

app = Flask(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
NIFTY_50_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv"
NIFTY_500_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
NSE_HOME_URL = (
    "https://www.nseindia.com/market-data/"
    "live-equity-market?symbol=NIFTY%2050"
)
NSE_NIFTY_50_API = (
    "https://www.nseindia.com/api/"
    "equity-stock-indices?index=NIFTY%2050"
)
NSE_FII_DII_API = "https://www.nseindia.com/api/fiidiiTradeReact"
NSE_INDEX_CARD_SYMBOLS = {
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "NIFTY BANK",
    "^CNXIT": "NIFTY IT",
}
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
    "articles": "https://trading-simplified.com/blog/",
    "swp-calculator": "https://trading-simplified.com/swp-calculator/",
    "option-chain-analysis": "https://trading-simplified.com/option-chain-analysis/",
    "option-builder": "https://trading-simplified.com/option-builder/",
    "market-performance": "https://trading-simplified.com/market-performance/",
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


def fetch_index_constituents(url, minimum_count=None):
    response = requests.get(
        url,
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
    if minimum_count and len(rows) < minimum_count:
        raise ValueError(f"Expected at least {minimum_count} constituents, received {len(rows)}")
    return rows


def fetch_nifty50_constituents():
    return fetch_index_constituents(NIFTY_50_URL, 50)


def fetch_nifty500_constituents():
    return fetch_index_constituents(NIFTY_500_URL, 500)


def fetch_nse_nifty50_snapshot():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": (
            "https://www.nseindia.com/market-data/"
            "live-equity-market?symbol=NIFTY%2050"
        ),
    }
    with requests.Session() as session:
        session.headers.update(headers)
        session.get(NSE_HOME_URL, timeout=10).raise_for_status()
        response = session.get(NSE_NIFTY_50_API, timeout=12)
        response.raise_for_status()
        payload = response.json()
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("NSE NIFTY 50 response has no data rows")
    return rows


def parse_nse_index_card(symbol, index_name, payload):
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return None
    normalized_name = index_name.upper().replace(" ", "")
    aggregate = None
    for item in rows:
        item_symbol = str(item.get("symbol") or item.get("identifier") or "").upper().replace(" ", "")
        if item_symbol == normalized_name:
            aggregate = item
            break
    if aggregate is None and rows:
        aggregate = rows[0]
    if not aggregate:
        return None
    price = _parse_number(aggregate.get("lastPrice"))
    change = _parse_number(aggregate.get("change"))
    percent = _parse_number(aggregate.get("pChange"))
    if price is None or change is None or percent is None:
        return None
    return {
        "symbol": symbol,
        "name": INDEX_SYMBOLS.get(symbol, index_name),
        "available": True,
        "price": price,
        "change": change,
        "percent": percent,
        "date": datetime.now(IST).strftime("%b %d"),
    }


def fetch_nse_index_cards():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": NSE_HOME_URL,
    }
    cards = {}
    nifty50_rows = None
    with requests.Session() as session:
        session.headers.update(headers)
        try:
            session.get(NSE_HOME_URL, timeout=10)
        except requests.RequestException:
            pass
        for symbol, index_name in NSE_INDEX_CARD_SYMBOLS.items():
            url = (
                "https://www.nseindia.com/api/equity-stock-indices?"
                f"index={quote(index_name)}"
            )
            try:
                response = session.get(url, timeout=12)
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError):
                continue
            card = parse_nse_index_card(symbol, index_name, payload)
            if card:
                cards[symbol] = card
            if symbol == "^NSEI":
                rows = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(rows, list):
                    nifty50_rows = rows
    return cards, nifty50_rows


def fetch_fii_dii_activity():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }
    with requests.Session() as session:
        session.headers.update(headers)
        try:
            session.get("https://www.nseindia.com/", timeout=8)
        except requests.RequestException:
            pass
        response = session.get(NSE_FII_DII_API, timeout=12)
        response.raise_for_status()
        payload = response.json()
    return normalize_fii_dii_activity(payload)


def normalize_fii_dii_activity(payload):
    if not isinstance(payload, list):
        raise ValueError("NSE FII/DII response has no rows")
    rows = []
    for item in payload:
        category = str(item.get("category") or "").strip()
        if not category:
            continue
        rows.append(
            {
                "category": "FII/FPI" if "FII" in category.upper() else category,
                "date": str(item.get("date") or "").strip(),
                "buy": _parse_number(item.get("buyValue")),
                "sell": _parse_number(item.get("sellValue")),
                "net": _parse_number(item.get("netValue")),
            }
        )
    if not rows:
        raise ValueError("NSE FII/DII response has no usable rows")
    return rows


def get_stock_universe():
    universe, stale = get_cached_swr(
        "nifty50_constituents",
        CONSTITUENT_CACHE_TTL,
        fetch_nifty50_constituents,
    )
    return (universe or STOCKS), stale


def get_nifty500_universe():
    universe, stale = get_cached_swr(
        "nifty500_constituents",
        CONSTITUENT_CACHE_TTL,
        fetch_nifty500_constituents,
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


def format_crore_value(value):
    if value is None:
        return "-"
    return f"Rs {float(value):,.2f} Cr"


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


def get_cached_swr(key, ttl, loader, now=None, cold_async=False):
    """Serve expired data immediately while one background refresh runs."""
    current = time_module.time() if now is None else now
    should_refresh = False
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and cached["expires"] > current:
            return cached["data"], False
        refreshing = key in _CACHE_REFRESHING
        if (cached or cold_async) and not refreshing:
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
    if cold_async:
        if should_refresh:
            threading.Thread(
                target=_refresh_cached_value,
                args=(key, ttl, loader),
                daemon=True,
                name=f"cache-refresh-{key[:32]}",
            ).start()
        return None, False
    return get_cached(key, ttl, loader, now=now)


def _parse_number(value):
    if value is None:
        return None
    try:
        cleaned = str(value).replace(",", "").strip()
        if cleaned in {"", "-", "None", "nan"}:
            return None
        number = float(cleaned)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


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


def apply_nse_quote_snapshot(rows, snapshot):
    by_symbol = {}
    for item in snapshot:
        symbol = str(item.get("symbol") or item.get("identifier") or "").strip().upper()
        if not symbol or symbol in {"NIFTY 50", "NIFTY50"}:
            continue
        by_symbol[symbol] = item

    for row in rows:
        item = by_symbol.get(row["display_symbol"].upper())
        if not item:
            continue
        price = _parse_number(item.get("lastPrice"))
        change = _parse_number(item.get("change"))
        percent = _parse_number(item.get("pChange"))
        volume = _parse_number(item.get("totalTradedVolume"))
        if price is not None:
            row["price"] = price
        if change is not None:
            row["change"] = change
        if percent is not None:
            row["percent"] = percent
        if volume is not None:
            row["volume"] = volume
    return rows


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
    symbols = [stock["symbol"] for stock in stocks]
    frames = []
    for start in range(0, len(symbols), 250):
        chunk = symbols[start:start + 250]
        frame = yf.download(
            chunk,
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
            timeout=20,
        )
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, axis=1)


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


def build_index_cards(download, nse_cards=None):
    nse_cards = nse_cards or {}
    cards = []
    for symbol, name in INDEX_SYMBOLS.items():
        frame = _ticker_frame(download, symbol)
        candles = build_candles(frame) if not frame.empty else []
        if symbol in nse_cards:
            cards.append({**nse_cards[symbol], "candles": candles})
            continue
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
                "candles": candles,
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
        previous_close = float(closes.iloc[-2]) if len(closes) > 1 else None
        change = quote.get("change")
        percent = quote.get("percent")
        if change is None and current is not None and previous_close is not None:
            change = current - previous_close
        if percent is None and current is not None and previous_close:
            percent = change / previous_close * 100 if change is not None else None
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
                "change": change,
                "percent": percent,
                "volume": current_volume,
                "volume_change": volume_change,
                "five_day_change": five_day_change,
                "chart_series": [
                    round(float(value), 2)
                    for value in closes.tail(90).tolist()
                    if not pd.isna(value)
                ],
                "market_cap": quote.get("market_cap"),
                "sma50": sma50,
                "sma200": sma200,
                "high52": high52,
                "low52": low52,
                "signal": signal,
            }
        )
    return rows


def _with_minimum_layout_weights(items, minimum_share):
    raw_total = sum(max(float(item.get("raw_weight") or 0), 0) for item in items)
    if raw_total <= 0:
        raw_total = float(len(items) or 1)
        items = [{**item, "raw_weight": 1.0} for item in items]
    floor = raw_total * minimum_share
    return [
        {
            **item,
            "layout_weight": max(float(item.get("raw_weight") or 0), floor),
        }
        for item in items
    ]


def _binary_treemap(items, x=0.0, y=0.0, width=100.0, height=100.0):
    """Lay out weighted items in a stable mosaic without clipping small entries."""
    if not items:
        return []
    ordered = sorted(items, key=lambda item: item["layout_weight"], reverse=True)

    def layout(group, left, top, box_width, box_height):
        if len(group) == 1:
            return [{
                **group[0],
                "x": round(left, 4),
                "y": round(top, 4),
                "width": round(box_width, 4),
                "height": round(box_height, 4),
            }]

        total = sum(item["layout_weight"] for item in group)
        target = total / 2
        running = 0.0
        split_at = 1
        closest = float("inf")
        for index in range(1, len(group)):
            running += group[index - 1]["layout_weight"]
            distance = abs(target - running)
            if distance <= closest:
                closest = distance
                split_at = index
            else:
                break

        first = group[:split_at]
        second = group[split_at:]
        first_weight = sum(item["layout_weight"] for item in first)
        ratio = first_weight / total if total else 0.5
        if box_width >= box_height:
            first_width = box_width * ratio
            return layout(first, left, top, first_width, box_height) + layout(
                second,
                left + first_width,
                top,
                box_width - first_width,
                box_height,
            )
        first_height = box_height * ratio
        return layout(first, left, top, box_width, first_height) + layout(
            second,
            left,
            top + first_height,
            box_width,
            box_height - first_height,
        )

    return layout(ordered, x, y, width, height)


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
    def member(row):
        return {
            "display_symbol": row["display_symbol"],
            "name": row.get("name", row["display_symbol"]),
            "price": row.get("price"),
            "percent": row.get("percent"),
            "volume": row.get("volume"),
            "signal": row.get("signal"),
        }

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
                "members": [
                    member(row)
                    for row in sorted(
                        values,
                        key=lambda row: row["percent"] if row["percent"] is not None else -math.inf,
                        reverse=True,
                    )
                ],
            }
            for sector, values in sectors.items()
        ),
        key=lambda item: item["percent"],
        reverse=True,
    )


def heatmap_sector_name(sector):
    value = (sector or "Other").lower()
    if any(term in value for term in ("financial", "bank", "finance", "insurance")):
        return "Financial"
    if any(term in value for term in ("information technology", "technology", "software")):
        return "Technology"
    if any(term in value for term in ("oil", "gas", "power", "energy")):
        return "Energy"
    if any(term in value for term in ("automobile", "auto")):
        return "Auto"
    if any(term in value for term in ("consumer", "fmcg", "fast moving")):
        return "Consumer"
    if any(term in value for term in ("healthcare", "pharma", "pharmaceutical")):
        return "Healthcare"
    if any(term in value for term in ("metal", "mining", "cement", "material", "chemical")):
        return "Materials"
    if any(term in value for term in ("capital goods", "construction", "industrial")):
        return "Industrials"
    if any(term in value for term in ("telecom", "communication")):
        return "Communication"
    return "Other"


def build_heatmap(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[heatmap_sector_name(row["sector"])].append(row)
    impact_available = any(row.get("nifty_impact") is not None for row in rows)
    sector_items = []
    for sector, items in grouped.items():
        impact = sum(abs(item.get("nifty_impact") or 0) for item in items)
        fallback = sum(
            math.sqrt(item.get("market_cap") or item.get("volume") or 1)
            for item in items
        )
        sector_items.append({
            "sector": sector,
            "rows": items,
            "impact": impact,
            "market_cap": sum(item.get("market_cap") or 0 for item in items),
            "raw_weight": impact if impact_available else fallback,
        })

    groups = []
    sector_rectangles = _binary_treemap(
        _with_minimum_layout_weights(sector_items, 0.035)
    )
    for sector_rectangle in sector_rectangles:
        cell_items = []
        for item in sector_rectangle["rows"]:
            impact = abs(item.get("nifty_impact") or 0)
            fallback = math.sqrt(item.get("market_cap") or item.get("volume") or 1)
            cell_items.append({
                **item,
                "raw_weight": impact if impact_available else fallback,
            })

        cells = []
        for item in _binary_treemap(
            _with_minimum_layout_weights(cell_items, 0.038)
        ):
            percent = item["percent"] or 0
            intensity = min(abs(percent) / 5, 1)
            area = item["width"] * item["height"]
            if area >= 850:
                size_class = "heat-xl"
            elif area >= 420:
                size_class = "heat-lg"
            elif area >= 190:
                size_class = "heat-md"
            elif area >= 75:
                size_class = "heat-sm"
            else:
                size_class = "heat-xs"
            cells.append(
                {
                    **item,
                    "index_weight": item.get("index_weight"),
                    "nifty_impact": item.get("nifty_impact"),
                    "intensity": round(0.28 + intensity * 0.62, 2),
                    "size_class": size_class,
                }
            )
        groups.append(
            {
                "sector": sector_rectangle["sector"],
                "cells": cells,
                "impact": sector_rectangle["impact"],
                "market_cap": sector_rectangle["market_cap"],
                "x": sector_rectangle["x"],
                "y": sector_rectangle["y"],
                "width": sector_rectangle["width"],
                "height": sector_rectangle["height"],
            }
        )
    return groups


def build_stock_hover_data(rows):
    return {
        row["display_symbol"]: {
            "symbol": row["display_symbol"],
            "name": row.get("name", row["display_symbol"]),
            "sector": row.get("sector", ""),
            "price": row.get("price"),
            "change": row.get("change"),
            "percent": row.get("percent"),
            "five_day_change": row.get("five_day_change"),
            "volume": row.get("volume"),
            "market_cap": row.get("market_cap"),
            "signal": row.get("signal"),
            "series": row.get("chart_series", []),
        }
        for row in rows
    }


def _growth_from_closes(closes, sessions):
    if closes is None or len(closes) <= sessions:
        return None
    latest = float(closes.iloc[-1])
    previous = float(closes.iloc[-sessions - 1])
    return (latest - previous) / previous * 100 if previous else None


def fetch_stock_detail(display_symbol):
    clean_symbol = re.sub(r"[^A-Za-z0-9&.-]", "", display_symbol or "").upper()
    if not clean_symbol:
        raise ValueError("Missing stock symbol")
    yf_symbol = clean_symbol if clean_symbol.endswith(".NS") else f"{clean_symbol}.NS"
    ticker = yf.Ticker(yf_symbol)
    info = ticker.info or {}
    history = ticker.history(period="5y", interval="1d", auto_adjust=False)
    closes = history["Close"].dropna() if history is not None and "Close" in history else pd.Series(dtype=float)
    summary = _strip_html(info.get("longBusinessSummary") or "")
    return {
        "symbol": clean_symbol.removesuffix(".NS"),
        "pe_ratio": _parse_number(info.get("trailingPE")) or _parse_number(info.get("forwardPE")),
        "revenue": _parse_number(info.get("totalRevenue")),
        "pat_margin": (
            _parse_number(info.get("profitMargins")) * 100
            if _parse_number(info.get("profitMargins")) is not None
            else None
        ),
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "description": summary[:520],
        "growth": {
            "1m": _growth_from_closes(closes, 21),
            "3m": _growth_from_closes(closes, 63),
            "1y": _growth_from_closes(closes, 252),
            "5y": _growth_from_closes(closes, min(1260, max(len(closes) - 2, 0))),
        },
    }


def get_stock_detail(display_symbol):
    key = f"stock_detail:{display_symbol.upper()}"
    detail, _ = get_cached(
        key,
        86400,
        lambda: fetch_stock_detail(display_symbol),
    )
    return detail or {}


def apply_nifty_impact(rows, snapshot):
    ffmc_by_symbol = {}
    for item in snapshot:
        symbol = str(item.get("symbol") or item.get("identifier") or "").strip()
        if symbol.upper() in {"NIFTY 50", "NIFTY50"}:
            continue
        try:
            ffmc = float(str(item.get("ffmc", "")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        if symbol and math.isfinite(ffmc) and ffmc > 0:
            ffmc_by_symbol[symbol.upper()] = ffmc

    matched = [
        row for row in rows
        if row["display_symbol"].upper() in ffmc_by_symbol
    ]
    required_matches = min(40, len(rows))
    if len(matched) < required_matches:
        raise ValueError(
            f"NSE NIFTY 50 response matched only {len(matched)} "
            f"of {len(rows)} stocks"
        )
    total_ffmc = sum(ffmc_by_symbol[row["display_symbol"].upper()] for row in matched)
    if not total_ffmc:
        raise ValueError("NSE NIFTY 50 response has no matching FFMC values")

    for row in rows:
        ffmc = ffmc_by_symbol.get(row["display_symbol"].upper())
        if ffmc is None:
            row["index_weight"] = None
            row["nifty_impact"] = None
            continue
        index_weight = ffmc / total_ffmc
        row["index_weight"] = index_weight
        row["nifty_impact"] = (
            index_weight * row["percent"]
            if row["percent"] is not None
            else None
        )
    return rows


def merge_stock_lists(primary, secondary):
    merged = {}
    for stock in primary + secondary:
        merged[stock["symbol"]] = stock
    return list(merged.values())


def load_market_dashboard(stocks, broad_stocks=None, allow_impact_fallback=False):
    broad_stocks = broad_stocks or stocks
    all_stocks = merge_stock_lists(stocks, broad_stocks)
    quotes, _ = get_market_quotes(stocks)
    quotes = quotes or {}
    index_history = fetch_index_history()
    nse_index_cards = {}
    nse_snapshot = None
    try:
        nse_index_cards, nse_snapshot = fetch_nse_index_cards()
    except Exception:
        nse_index_cards, nse_snapshot = {}, None
    stock_history = fetch_stock_history(all_stocks)
    all_rows = build_stock_rows(quotes, stock_history, all_stocks)
    rows_by_symbol = {row["symbol"]: row for row in all_rows}
    rows = [rows_by_symbol[stock["symbol"]] for stock in stocks if stock["symbol"] in rows_by_symbol]
    broad_rows = [rows_by_symbol[stock["symbol"]] for stock in broad_stocks if stock["symbol"] in rows_by_symbol]
    impact_available = False
    try:
        nse_snapshot = nse_snapshot or fetch_nse_nifty50_snapshot()
        apply_nse_quote_snapshot(rows, nse_snapshot)
        apply_nifty_impact(rows, nse_snapshot)
        impact_available = any(row.get("nifty_impact") is not None for row in rows)
    except Exception:
        if not allow_impact_fallback:
            raise
    available = [row for row in broad_rows if row["percent"] is not None]
    gainers = sorted(available, key=lambda row: row["percent"], reverse=True)
    losers = sorted(
        [row for row in available if row["percent"] < 0],
        key=lambda row: row["percent"],
    )
    active = sorted(
        [row for row in broad_rows if row["volume"] is not None],
        key=lambda row: row["volume"],
        reverse=True,
    )
    return {
        "indices": build_index_cards(index_history, nse_index_cards),
        "rows": broad_rows,
        "nifty50_rows": rows,
        "breadth": build_breadth(broad_rows),
        "gainers": gainers[:14],
        "losers": losers[:14],
        "active": active[:14],
        "signals": sorted(broad_rows, key=lambda row: abs(row["percent"] or 0), reverse=True)[:18],
        "sectors": build_sector_performance(broad_rows),
        "heatmap": build_heatmap(rows),
        "hover_data": build_stock_hover_data(broad_rows),
        "impact_available": impact_available,
        "market_stats": build_market_stats(broad_rows),
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


def build_calendar_panels(entries, today=None):
    today = today or datetime.now(IST).date()
    earnings = []
    events = []
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


@app.route("/api/stocks/<symbol>")
def stock_detail_api(symbol):
    return jsonify(get_stock_detail(symbol))


@app.route("/blog/")
def articles():
    return redirect(PAGE_REDIRECTS["articles"], code=302)


@app.route("/swp-calculator/")
def swp_calculator():
    return redirect(PAGE_REDIRECTS["swp-calculator"], code=302)


@app.route("/option-chain-analysis/")
def option_chain_analysis():
    return redirect(PAGE_REDIRECTS["option-chain-analysis"], code=302)


@app.route("/option-builder/")
def option_builder():
    return redirect(PAGE_REDIRECTS["option-builder"], code=302)


@app.route("/market-performance/")
def market_performance():
    return redirect(PAGE_REDIRECTS["market-performance"], code=302)


@app.route("/")
def dashboard():
    stocks, constituents_stale = get_stock_universe()
    broad_stocks, broad_constituents_stale = get_nifty500_universe()
    universe_key = ",".join(stock["symbol"] for stock in stocks)
    broad_universe_key = ",".join(stock["symbol"] for stock in broad_stocks)
    market_key = f"market:{universe_key}|broad:{broad_universe_key}"
    with _CACHE_LOCK:
        has_cached_market = market_key in _CACHE
    market, market_stale = get_cached_swr(
        market_key,
        MARKET_CACHE_TTL,
        lambda: load_market_dashboard(
            stocks,
            broad_stocks,
            allow_impact_fallback=not has_cached_market,
        ),
        cold_async=True,
    )
    headlines, news_stale = get_cached_swr(
        "news",
        NEWS_CACHE_TTL,
        fetch_headlines,
        cold_async=True,
    )
    fii_dii, fii_dii_stale = get_cached_swr(
        "fii_dii",
        MARKET_CACHE_TTL,
        fetch_fii_dii_activity,
    )
    calendar_entries, calendar_stale = get_cached_swr(
        f"company_calendar:{universe_key}",
        CALENDAR_CACHE_TTL,
        lambda: fetch_company_calendar(stocks),
        cold_async=True,
    )
    market = market or {
        "indices": [],
        "rows": [],
        "nifty50_rows": [],
        "breadth": [],
        "gainers": [],
        "losers": [],
        "active": [],
        "signals": [],
        "sectors": [],
        "heatmap": [],
        "hover_data": {},
        "impact_available": False,
        "market_stats": build_market_stats([]),
        "internals": build_market_internals([]),
    }
    headlines = headlines or []
    fii_dii = fii_dii or []
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
        fii_dii=fii_dii,
        fii_dii_stale=fii_dii_stale,
        calendar_stale=calendar_stale,
        constituents_stale=constituents_stale or broad_constituents_stale,
        broad_universe_count=len(broad_stocks),
        nearby_events=calendar["events"],
        earnings=earnings,
        market_brief=brief,
        format_market_cap=format_market_cap,
        format_volume=format_volume,
        format_crore_value=format_crore_value,
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
