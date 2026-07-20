from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import hashlib
from io import StringIO
import json
import math
import numbers
import os
from pathlib import Path
import pickle
import re
from statistics import median
import sys
import threading
import time as time_module
from urllib.parse import quote
import xml.etree.ElementTree as ET

from flask import Flask, jsonify, make_response, redirect, render_template, request
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
NSE_NIFTY_500_API = (
    "https://www.nseindia.com/api/"
    "equity-stock-indices?index=NIFTY%20500"
)
NSE_ALL_INDICES_API = "https://www.nseindia.com/api/allIndices"
NSE_FII_DII_API = "https://www.nseindia.com/api/fiidiiTradeReact"
FII_DII_HISTORY_ARCHIVE_URL = "https://fii-diidata.mrchartist.com/api/history-full"
NSE_BULK_BLOCK_REPORT_URL = "https://www.nseindia.com/report-detail/display-bulk-and-block-deals"
NSE_BULK_BLOCK_HISTORY_API = "https://www.nseindia.com/api/historicalOR/bulk-block-short-deals"
NSE_HISTORICAL_DEAL_APIS = {
    "bulk": "bulk_deals",
    "block": "block_deals",
    "short": "short_selling",
}
BULK_BLOCK_DATA_DIR = Path(__file__).resolve().parent / "bulk block short data"
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
ARTICLE_POSTS_SOURCE = [
    {
        "title": "Trading Simplified Dashboard & Market Insights: A Smarter Way to Read Indian Markets",
        "url": "https://trading-simplified.com/2026/06/21/trading-simplified-dashboard-market-insights-indian-markets/",
        "date": "2026-06-21",
        "author": "rajista",
        "categories": ["Stocks"],
        "tags": ["market dashboard", "market insights", "nifty", "NSE", "stock analysis", "trading"],
        "excerpt": "Explore the Trading Simplified Indian Market Dashboard and Market Insights sections, including live NSE index snapshots, breadth indicators, top movers, sector performance, accumulation signals, deal-flow context and high-conviction watchlists.",
    },
    {
        "title": "Nasdaq Stock Analysis May 2026: NVDA, MSFT &amp; AppLovin — Data-Driven Breakdown",
        "url": "https://trading-simplified.com/2026/05/23/nasdaq-stock-analysis-may-2026-nvda-msft-applovin/",
        "date": "2026-05-23",
        "author": "rajista",
        "categories": ["US stocks"],
        "tags": ["ai", "AI stocks", "AppLovin", "finance", "investing", "May 2026", "Microsoft Azure", "MSFT", "Nasdaq", "NVDA", "NVIDIA earnings", "stock analysis", "technology"],
        "excerpt": "The Nasdaq Composite has staged a powerful recovery in Spring 2026 after a brutal 16% drawdown in Q1. Earnings season just closed, and three major Nasdaq stocks — NVIDIA (NVDA), Microsoft (MSFT), and AppLovin (APP) — are telling three very&hellip;",
    },
    {
        "title": "Nippon India Small Cap Fund SWP Simulator v2: Flexible Inputs, 5 Scenarios &amp; Crash-Year Stress Testing",
        "url": "https://trading-simplified.com/2026/05/17/nippon-india-small-cap-fund-swp-simulator-v2-flexible-inputs-5-scenarios-crash-year-stress-testing/",
        "date": "2026-05-17",
        "author": "rajista",
        "categories": ["Mutual Funds", "Uncategorized"],
        "tags": ["CAGR", "finance", "investing", "Mutual Fund", "NAV", "Nippon Small Cap", "passive-income", "personal-finance", "Portfolio Simulation", "Small Cap", "Small Cap Fund", "Stocks", "SWP", "Systematic Withdrawal Plan"],
        "excerpt": "This post is a major update to our earlier SWP projection analysis. The new simulator lets you change the initial investment amount and withdrawal percentages — and models all five market scenarios with exactly 3 negative return years each, reflecting&hellip;",
    },
    {
        "title": "Nippon India Small Cap Fund SWP Projection: Monthly Withdrawal, CAGR &amp; Portfolio Survival Analysis",
        "url": "https://trading-simplified.com/2026/05/09/nippon-india-small-cap-fund-swp-projection-monthly-withdrawal-cagr-portfolio-survival-analysis/",
        "date": "2026-05-09",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": ["finance", "investing", "investment", "personal-finance", "Stocks"],
        "excerpt": "This post documents a systematic withdrawal plan (SWP) simulation on a ₹70 lakh lump-sum investment in Nippon India Small Cap Fund — Direct Growth, started in April 2024. The analysis covers 24 months of actual NAV data, a month-by-month capital&hellip;",
    },
    {
        "title": "Mastering IV Inversions for Profitable Trading Tips",
        "url": "https://trading-simplified.com/2025/08/24/mastering-iv-inversions-for-profitable-trading-tips/",
        "date": "2025-08-24",
        "author": "rajista",
        "categories": ["Stocks"],
        "tags": ["ai", "algotrading", "data-science", "machine-learning", "nifty", "python", "technology", "trading", "tradingview"],
        "excerpt": "Find IV Inversions and Calendar Spread Opportunities Like a Pro 🚀 🔍 Introduction Trading is all about identifying hidden edges where risk and reward align in your favor. One such edge comes from Implied Volatility (IV) inversions of option contracts between near&hellip;",
    },
    {
        "title": "📈 Covered Call Strategy Backtest in Python (NSE Data + Breeze API)",
        "url": "https://trading-simplified.com/2025/08/24/%f0%9f%93%88-covered-call-strategy-backtest-in-python-nse-data-breeze-api/",
        "date": "2025-08-24",
        "author": "rajista",
        "categories": ["Stocks"],
        "tags": ["algotrading", "breezeapi", "icicidirect", "nifty", "NSE", "nsepython"],
        "excerpt": "Intro. Covered calls are one of the most popular options trading strategies among retail and professional traders. The idea is simple: 👉 You own a stock (or take it synthetically in backtest) and sell call options against it every month.This&hellip;",
    },
    {
        "title": "Home Depot Stock: Weathering Short-Term Challenges for Long-Term Potential",
        "url": "https://trading-simplified.com/2023/04/23/home-depot-stock-weathering-short-term-challenges-for-long-term-potential/",
        "date": "2023-04-23",
        "author": "rajista",
        "categories": ["Stocks"],
        "tags": ["dowjones", "homedepot", "stocktrading", "trading"],
        "excerpt": "After experiencing a 10% decline year-to-date, Home Depot stock (NYSE: HD), the world's largest home improvement retailer, is currently priced at around $285 per share. This decline has been attributed to challenges in the housing market and rising inflation, as&hellip;",
    },
    {
        "title": "Get historical option charts",
        "url": "https://trading-simplified.com/2022/12/21/get-historical-option-charts/",
        "date": "2022-12-21",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": ["algotrading", "breezeapi", "icicidirect", "kite", "trading"],
        "excerpt": "As historical option charts are not easily available on broker terminals. I thought about writing a program to get one with the help of ICICI Direct Breeze api. This code will work only if you have the following: Python 3.xx&hellip;",
    },
    {
        "title": "Zerodha PnL summary",
        "url": "https://trading-simplified.com/2021/09/21/zerodha-pnl-summary/",
        "date": "2021-09-21",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": [],
        "excerpt": "We will use the Kiteconnect module in python for this tutorial You will need to have zerodha API subscription and python setup for this The following code will give the Profit and loss summary for trades taken throughout the day:&hellip;",
    },
    {
        "title": "NSE Freak trade",
        "url": "https://trading-simplified.com/2021/08/22/nse-freaktrade/",
        "date": "2021-08-22",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": ["algotrading", "freak trade", "kite", "NSE", "python", "trading", "tradingview"],
        "excerpt": "Recently there has been few instances of \"freak trades\" happening in the derivates segment of NSE exchange. In case you are wondering what is a Freak trade and how you can avoid such trades, then you’re in the right place.&hellip;",
    },
    {
        "title": "Get Atm strike price of any stock",
        "url": "https://trading-simplified.com/2021/08/16/get-atm-strike-price-of-any-stock/",
        "date": "2021-08-16",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": [],
        "excerpt": "To get the at the money (ATM) strikes of a stock we will use the NSEpython module in python. Please make sure that you have the nsepython module installed, else: Type this in the terminal: $pip install nsepython We will&hellip;",
    },
    {
        "title": "Getting current weekly expiry details for Banknifty",
        "url": "https://trading-simplified.com/2021/08/15/getting-current-weekly-expiry-details-for-banknifty/",
        "date": "2021-08-15",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": [],
        "excerpt": "To run any options based trading system we need the tradingsymbol for the latest expiring call and put options. The format for weekly expiring options is: BANKNIFTY&lt;YY&gt;&lt;M&gt;&lt;DD&gt;strike&lt;PE/CE&gt; Where M is given as 1 for JAN, 2 for FEB, 3, 4,&hellip;",
    },
    {
        "title": "Vwap rejection strategy with ATR based stop",
        "url": "https://trading-simplified.com/2021/08/14/vwap-rejection-strategy-with-atr-based-stop/",
        "date": "2021-08-14",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": [],
        "excerpt": "The strategy is based on vwap (volume weighted average price) and ATR (average true range). The strategy takes a long trade when the asset is gapping up and subsequently price goes into a consolidation phase and finally if we get&hellip;",
    },
    {
        "title": "Trading Journal simplified",
        "url": "https://trading-simplified.com/2021/07/31/trading-journal-simplified/",
        "date": "2021-07-31",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": [],
        "excerpt": "I had used the following trading journal in my initial trading days when i used to do intraday trading. One of the most important things to have when you're trading is a Trading journal, to constantly review your performance and&hellip;",
    },
    {
        "title": "How to get ATM strikes of Banknifty",
        "url": "https://trading-simplified.com/2021/07/25/how-to-get-atm-strikes-of-banknifty/",
        "date": "2021-07-25",
        "author": "rajista",
        "categories": ["nsepy"],
        "tags": ["banknifty", "nifty", "nsepy"],
        "excerpt": "To get the at the money (ATM) strikes of Banknifty index we will use the NSEpython module in python. Please make sure that you have the nsepython module installed, else: Type this in the terminal: $pip install nsepython First we&hellip;",
    },
    {
        "title": "Nsepython: Getting Nifty/Banknifty Ltp",
        "url": "https://trading-simplified.com/2021/07/25/nsepython-getting-nifty-banknifty-ltp/",
        "date": "2021-07-25",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": ["kite", "nsepython", "python"],
        "excerpt": "We can use the nsepython library to fetch data from the NSE website. Steps to install NSEPython: In any Python ide, for ex- pycharm type the following code in the terminal: $pip install nsepythonTo upgrade to the latest version,pip install&hellip;",
    },
    {
        "title": "Pine script Tutorial",
        "url": "https://trading-simplified.com/2021/02/02/pine-script-tutorial/",
        "date": "2021-02-02",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": ["algotrading", "bitcoin", "pine", "pinescript", "trading", "tradingview"],
        "excerpt": "Trading strategies&nbsp;are one of the best ways to avoid behavioral biases and ensure consistent results. Strategies employ indicators in an objective manner to determine entry, exit and/or trade management rules. They include the detailed use of indicators or, multiple indicators, to&hellip;",
    },
    {
        "title": "About me",
        "url": "https://trading-simplified.com/2021/02/02/example-post-3/",
        "date": "2021-02-02",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": [],
        "excerpt": "Founder of Simplytrading. Trading analyst and derivatives trader. Expert in the field of algorithmic trading and a rich experience of trading different asset classes. Tutoring new traders on deploying fully automated trading strategies and other aspects of Trade automation and&hellip;",
    },
    {
        "title": "Site description",
        "url": "https://trading-simplified.com/2021/02/02/example-post-2/",
        "date": "2021-02-02",
        "author": "rajista",
        "categories": ["Uncategorized"],
        "tags": [],
        "excerpt": "Simplifying the process of trading through regular market insights, new trading strategies and backtesting for various asset classes",
    },
]
MARKET_CACHE_TTL = int(os.getenv("MARKET_CACHE_TTL_SECONDS", "1200"))
MARKET_HARD_REFRESH_AFTER = int(
    os.getenv("MARKET_HARD_REFRESH_AFTER_SECONDS", str(max(3600, MARKET_CACHE_TTL * 3)))
)
HISTORY_CACHE_TTL = int(os.getenv("HISTORY_CACHE_TTL_SECONDS", "21600"))
NEWS_CACHE_TTL = 900
CALENDAR_CACHE_TTL = 21600
CONSTITUENT_CACHE_TTL = 86400
BULK_BLOCK_CACHE_TTL = 24 * 60 * 60
FII_DII_HISTORY_CACHE_TTL = 6 * 60 * 60
STOCK_DETAIL_CACHE_TTL = 24 * 60 * 60
STOCK_AI_CACHE_TTL = 12 * 60 * 60
INSIGHTS_SNAPSHOT_TTL = 7 * 24 * 60 * 60
CACHE_DIR = Path(os.getenv("APP_CACHE_DIR", Path(__file__).resolve().parent / ".runtime_cache"))
PERSISTENT_CACHE_ENABLED = (
    os.getenv("DISABLE_PERSISTENT_CACHE") != "1"
    and not any("unittest" in arg or "pytest" in arg for arg in sys.argv)
)
STOCK_POPUP_DETAILS_LATEST_KEY = "stock_popup_details:latest"
INSIGHTS_SNAPSHOT_KEY = "insights_snapshot:latest"
MARKET_BREADTH_HISTORY_KEY = "market_breadth_history"
FII_DII_HISTORY_KEY = "fii_dii_history"
MAX_ASYNC_POPUP_DETAIL_PREFETCH = 75
STOCK_DETAIL_WORKERS = int(os.getenv("STOCK_DETAIL_WORKERS", "3"))
STARTUP_MARKET_REFRESH_DELAY = int(os.getenv("STARTUP_MARKET_REFRESH_DELAY_SECONDS", "10"))
STARTUP_STOCK_DETAIL_REFRESH_DELAY = int(os.getenv("STARTUP_STOCK_DETAIL_REFRESH_DELAY_SECONDS", "300"))
STARTUP_INSIGHTS_SNAPSHOT_REFRESH_DELAY = int(
    os.getenv("STARTUP_INSIGHTS_SNAPSHOT_REFRESH_DELAY_SECONDS", "45")
)
REPORTED_FINANCIAL_OVERRIDES = {
    "INFY": {
        "period": "2026-03-31",
        "revenue_inr": 178_650 * 10_000_000,
        "net_income_inr": 29_440 * 10_000_000,
    }
}
_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_REFRESHING = set()
_BULK_BLOCK_REFRESH_STARTED = False
_STOCK_DETAIL_REFRESH_STARTED = False
_MARKET_REFRESH_STARTED = False
_INSIGHTS_SNAPSHOT_REFRESH_STARTED = False


def _cache_file_path(key):
    digest = hashlib.sha256(key.encode("utf-8", errors="ignore")).hexdigest()
    return CACHE_DIR / f"{digest}.pickle"


def _read_persistent_cache(key):
    if not PERSISTENT_CACHE_ENABLED:
        return None
    path = _cache_file_path(key)
    try:
        if not path.exists():
            return None
        with path.open("rb") as handle:
            entry = pickle.load(handle)
        if not isinstance(entry, dict) or "data" not in entry or "expires" not in entry:
            return None
        return entry
    except Exception:
        return None


def _write_persistent_cache(key, data, ttl):
    if not PERSISTENT_CACHE_ENABLED:
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "data": data,
            "expires": time_module.time() + ttl,
            "written_at": datetime.now(IST).isoformat(),
        }
        tmp_path = _cache_file_path(key).with_suffix(f".{threading.get_ident()}.tmp")
        with tmp_path.open("wb") as handle:
            pickle.dump(entry, handle, protocol=pickle.HIGHEST_PROTOCOL)
        tmp_path.replace(_cache_file_path(key))
    except Exception:
        pass


def article_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "articles"


def article_image_url(url, width=1200):
    return f"https://s0.wp.com/mshots/v1/{quote(url, safe='')}?w={width}"


def clean_article_text(value):
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def format_article_date(value):
    published = date.fromisoformat(value)
    return published.strftime("%b %d, %Y")


def build_article_posts():
    posts = []
    for source in ARTICLE_POSTS_SOURCE:
        categories = source.get("categories") or ["Articles"]
        primary_category = next(
            (category for category in categories if category.lower() != "uncategorized"),
            categories[0],
        )
        title = clean_article_text(source["title"])
        excerpt = clean_article_text(source.get("excerpt", ""))
        tags = [clean_article_text(tag) for tag in source.get("tags", [])]
        search_text = " ".join([title, excerpt, primary_category, *categories, *tags]).lower()
        posts.append(
            {
                **source,
                "title": title,
                "excerpt": excerpt,
                "tags": tags,
                "primary_category": primary_category,
                "primary_category_slug": article_slug(primary_category),
                "category_slugs": {article_slug(category) for category in categories},
                "date_label": format_article_date(source["date"]),
                "image_url": article_image_url(source["url"]),
                "search_text": search_text,
            }
        )
    return posts


ARTICLE_POSTS = build_article_posts()
ARTICLE_CATEGORY_ORDER = {
    "Stocks": 0,
    "US stocks": 1,
    "Mutual Funds": 2,
    "nsepy": 3,
    "Uncategorized": 4,
}
ARTICLE_CATEGORIES = sorted(
    {
        category
        for post in ARTICLE_POSTS_SOURCE
        for category in post.get("categories", [])
    },
    key=lambda category: (ARTICLE_CATEGORY_ORDER.get(category, 99), category.lower()),
)


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


def fetch_nse_index_snapshot(api_url, index_name):
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
            f"live-equity-market?symbol={quote(index_name)}"
        ),
    }
    last_error = None
    timeout = 30 if "NIFTY%20500" in api_url or "NIFTY%2050" in api_url else 15
    for attempt in range(3):
        try:
            with requests.Session() as session:
                session.headers.update(headers)
                session.get(NSE_HOME_URL, timeout=12).raise_for_status()
                response = session.get(api_url, timeout=timeout)
                response.raise_for_status()
                payload = response.json()
            break
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time_module.sleep(0.8 * (attempt + 1))
    else:
        raise last_error or RuntimeError(f"NSE {index_name} snapshot failed")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError(f"NSE {index_name} response has no data rows")
    return rows


def fetch_nse_nifty50_snapshot():
    return fetch_nse_index_snapshot(NSE_NIFTY_50_API, "NIFTY 50")


def fetch_nse_nifty500_snapshot():
    rows = fetch_nse_index_snapshot(NSE_NIFTY_500_API, "NIFTY 500")
    constituent_rows = [
        row
        for row in rows
        if str(row.get("symbol") or row.get("identifier") or "").strip().upper()
        not in {"NIFTY 500", "NIFTY500"}
    ]
    if len(constituent_rows) < 450:
        raise ValueError(
            f"NSE NIFTY 500 response has only {len(constituent_rows)} constituent rows"
        )
    return rows


def fetch_nse_market_gauges():
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
    with requests.Session() as session:
        session.headers.update(headers)
        try:
            session.get("https://www.nseindia.com/", timeout=8)
        except requests.RequestException:
            pass
        response = session.get(NSE_ALL_INDICES_API, timeout=15)
        response.raise_for_status()
        payload = response.json()
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("NSE all-indices response has no data rows")
    wanted = (
        "INDIA VIX",
        "NIFTY NEXT 50",
        "NIFTY MIDCAP 100",
        "NIFTY SMALLCAP 100",
    )
    by_name = {str(row.get("index") or "").upper(): row for row in rows}
    gauges = []
    for name in wanted:
        item = by_name.get(name)
        if not item:
            continue
        gauges.append(
            {
                "name": name,
                "price": _parse_number(item.get("last")),
                "change": _parse_number(item.get("variation")),
                "percent": _parse_number(item.get("percentChange")),
                "advances": int(_parse_number(item.get("advances")) or 0),
                "declines": int(_parse_number(item.get("declines")) or 0),
                "unchanged": int(_parse_number(item.get("unchanged")) or 0),
                "month_change": _parse_number(item.get("perChange30d")),
                "year_change": _parse_number(item.get("perChange365d")),
                "pe": _parse_number(item.get("pe")),
                "pb": _parse_number(item.get("pb")),
                "dividend_yield": _parse_number(item.get("dy")),
            }
        )
    return gauges


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


def _flow_date_iso(value):
    text = str(value or "").strip()
    parsed = pd.to_datetime(
        text,
        errors="coerce",
        format="%Y-%m-%d" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else "%d-%b-%Y",
    )
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def normalize_fii_dii_history(payload):
    """Normalize compact historical cash-flow rows without trusting missing fields."""
    if not isinstance(payload, list):
        raise ValueError("FII/DII history response has no rows")
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        flow_date = _flow_date_iso(item.get("d") or item.get("date"))
        if not flow_date:
            continue
        rows.append(
            {
                "date": flow_date,
                "fii": _first_number(item.get("fn"), item.get("fii_net")),
                "dii": _first_number(item.get("dn"), item.get("dii_net")),
                "fii_buy": _first_number(item.get("fb"), item.get("fii_buy")),
                "fii_sell": _first_number(item.get("fs"), item.get("fii_sell")),
                "dii_buy": _first_number(item.get("db"), item.get("dii_buy")),
                "dii_sell": _first_number(item.get("ds"), item.get("dii_sell")),
            }
        )
    if not rows:
        raise ValueError("FII/DII history response has no usable rows")
    return sorted(rows, key=lambda row: row["date"])


def fetch_fii_dii_history_archive():
    response = requests.get(
        FII_DII_HISTORY_ARCHIVE_URL,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0 SimplyTrading/1.0", "Accept": "application/json"},
    )
    response.raise_for_status()
    return normalize_fii_dii_history(response.json())


def get_stock_universe():
    universe, stale = get_cached_swr(
        "nifty50_constituents",
        CONSTITUENT_CACHE_TTL,
        fetch_nifty50_constituents,
        cold_async=True,
    )
    return (universe or STOCKS), stale


def get_nifty500_universe():
    universe, stale = get_cached_swr(
        "nifty500_constituents",
        CONSTITUENT_CACHE_TTL,
        fetch_nifty500_constituents,
        cold_async=True,
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
    if not cached:
        cached = _read_persistent_cache(key)
        if cached:
            with _CACHE_LOCK:
                _CACHE[key] = cached
            if cached["expires"] > current:
                return cached["data"], False
    try:
        data = loader()
        if data is None:
            raise ValueError("Loader returned no data")
        with _CACHE_LOCK:
            _CACHE[key] = {"data": data, "expires": current + ttl}
        _write_persistent_cache(key, data, ttl)
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
        _write_persistent_cache(key, data, ttl)
    except Exception as exc:
        print(f"Cache refresh failed for {key}: {exc}", file=sys.stderr)
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
    if not cached:
        cached = _read_persistent_cache(key)
        if cached:
            with _CACHE_LOCK:
                _CACHE[key] = cached
            if cached["expires"] > current:
                return cached["data"], False
            current = time_module.time() if now is None else now
    with _CACHE_LOCK:
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


def _parse_ist_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M IST", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M:%S"):
        try:
            parsed = datetime.strptime(text.removesuffix(" IST").strip(), fmt.removesuffix(" IST"))
            return parsed.replace(tzinfo=IST)
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        if parsed.tzinfo is None:
            return parsed.to_pydatetime().replace(tzinfo=IST)
        return parsed.to_pydatetime().astimezone(IST)
    except Exception:
        return None


def market_cache_age_seconds(market, now=None):
    if not isinstance(market, dict):
        return None
    stamp = _parse_ist_timestamp(market.get("refreshed_at")) or _parse_ist_timestamp(
        market.get("data_timestamp")
    )
    if stamp is None:
        return None
    now = now or datetime.now(IST)
    return max(0, (now - stamp).total_seconds())


def should_force_market_refresh(market, stale, now=None):
    if not stale:
        return False
    age = market_cache_age_seconds(market, now=now)
    if age is None:
        return True
    return age >= MARKET_HARD_REFRESH_AFTER


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


def _first_number(*values):
    for value in values:
        number = _parse_number(value)
        if number is not None:
            return number
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
        day_open = _parse_number(item.get("open"))
        day_high = _parse_number(item.get("dayHigh"))
        day_low = _parse_number(item.get("dayLow"))
        previous_close = _parse_number(item.get("previousClose"))
        traded_value = _parse_number(item.get("totalTradedValue"))
        free_float_market_cap = _parse_number(item.get("ffmc"))
        month_change = _parse_number(item.get("perChange30d"))
        year_change = _parse_number(item.get("perChange365d"))
        year_high = _parse_number(item.get("yearHigh"))
        year_low = _parse_number(item.get("yearLow"))
        delivery_percent = _parse_number(
            item.get("deliveryToTradedQuantity")
            or item.get("deliveryQuantityToTradedQuantity")
            or item.get("deliveryToTradedQty")
        )
        if price is not None:
            row["price"] = price
        if change is not None:
            row["change"] = change
        if percent is not None:
            row["percent"] = percent
        if volume is not None:
            row["volume"] = volume
        if day_open is not None:
            row["day_open"] = day_open
        if day_high is not None:
            row["day_high"] = day_high
        if day_low is not None:
            row["day_low"] = day_low
        if previous_close is not None:
            row["previous_close"] = previous_close
        if traded_value is not None:
            row["traded_value"] = traded_value
        if free_float_market_cap is not None:
            row["free_float_market_cap"] = free_float_market_cap
        if month_change is not None:
            row["month_change"] = month_change
        if year_change is not None:
            row["year_change"] = year_change
        if year_high is not None:
            row["high52"] = year_high
        if year_low is not None:
            row["low52"] = year_low
        if item.get("lastUpdateTime"):
            row["last_update_time"] = str(item.get("lastUpdateTime"))
        if delivery_percent is not None:
            row["delivery_percent"] = delivery_percent
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


def _aligned_close_volume(closes, volumes):
    try:
        data = pd.concat(
            [
                pd.to_numeric(closes, errors="coerce").rename("close"),
                pd.to_numeric(volumes, errors="coerce").rename("volume"),
            ],
            axis=1,
        ).dropna()
    except Exception:
        return pd.DataFrame(columns=["close", "volume"])
    return data[data["volume"] > 0]


def compute_obv_divergence(closes, volumes):
    """Return True when volume accumulates while price is mostly flat."""
    data = _aligned_close_volume(closes, volumes)
    if len(data) < 16:
        return False
    try:
        direction = data["close"].diff().fillna(0).apply(lambda value: 1 if value > 0 else -1 if value < 0 else 0)
        obv = (direction * data["volume"]).cumsum()
        window = 15 if len(data) >= 20 else 10
        price_start = float(data["close"].iloc[-window])
        if not price_start:
            return False
        price_change = (float(data["close"].iloc[-1]) - price_start) / price_start * 100
        obv_window = obv.tail(window)
        obv_trending_up = float(obv_window.iloc[-1]) > float(obv_window.iloc[0])
        return obv_trending_up and abs(price_change) < 3
    except Exception:
        return False


def compute_quiet_pullback(closes, volumes):
    """Return True for a recent spike followed by quiet flat/down sessions."""
    data = _aligned_close_volume(closes, volumes)
    if len(data) < 24:
        return False
    try:
        for spike_pos in range(max(20, len(data) - 8), len(data) - 1):
            prior_avg = float(data["volume"].iloc[spike_pos - 20:spike_pos].mean())
            if prior_avg <= 0 or float(data["volume"].iloc[spike_pos]) <= prior_avg * 1.5:
                continue
            follow = data.iloc[spike_pos + 1:min(spike_pos + 4, len(data))]
            if follow.empty:
                continue
            below_avg_volume = all(float(value) < prior_avg for value in follow["volume"])
            quiet_closes = all(
                float(follow["close"].iloc[index]) <= float(data["close"].iloc[spike_pos + index]) * 1.005
                for index in range(len(follow))
            )
            if below_avg_volume and quiet_closes:
                return True
        return False
    except Exception:
        return False


def compute_volume_range_signal(closes, volumes):
    data = _aligned_close_volume(closes, volumes)
    if len(data) < 20:
        return False
    try:
        avg5 = float(data["volume"].tail(5).mean())
        avg20 = float(data["volume"].tail(20).mean())
        if avg20 <= 0 or avg5 / avg20 <= 1.1:
            return False
        current = data["close"].tail(10)
        previous = data["close"].iloc[-20:-10]
        current_range = float(current.max() - current.min())
        previous_range = float(previous.max() - previous.min())
        return previous_range > 0 and current_range < previous_range
    except Exception:
        return False


def market_session_progress(now=None):
    now = now or datetime.now(IST)
    if now.weekday() >= 5:
        return 1.0
    session_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    session_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now <= session_start or now >= session_end:
        return 1.0
    elapsed = (now - session_start).total_seconds()
    duration = (session_end - session_start).total_seconds()
    return max(0.08, min(elapsed / duration, 1.0))


def update_live_row_metrics(rows, now=None):
    progress = market_session_progress(now)
    for row in rows:
        price = row.get("price")
        volume = row.get("volume")
        average_volume = row.get("average_volume_20d")
        if row.get("traded_value") is None and price is not None and volume is not None:
            row["traded_value"] = price * volume
        expected_volume = average_volume * progress if average_volume else None
        relative_volume = (
            volume / expected_volume
            if volume is not None and expected_volume and expected_volume > 0
            else None
        )
        row["relative_volume"] = relative_volume
        row["volume_change"] = (
            (relative_volume - 1) * 100
            if relative_volume is not None
            else None
        )
        high52 = row.get("high52")
        low52 = row.get("low52")
        row["high52_distance"] = (
            (price - high52) / high52 * 100
            if price is not None and high52
            else None
        )
        row["low52_distance"] = (
            (price - low52) / low52 * 100
            if price is not None and low52
            else None
        )
        prior20_high = row.get("prior20_high")
        row["price_volume_breakout"] = bool(
            price is not None
            and prior20_high
            and price > prior20_high
            and (relative_volume or 0) >= 1.1
        )
    return rows


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
        day_open = float(frame["Open"].dropna().iloc[-1]) if not frame.empty and "Open" in frame and not frame["Open"].dropna().empty else None
        day_high = float(frame["High"].dropna().iloc[-1]) if not frame.empty and "High" in frame and not frame["High"].dropna().empty else None
        day_low = float(frame["Low"].dropna().iloc[-1]) if not frame.empty and "Low" in frame and not frame["Low"].dropna().empty else None
        current_volume = quote.get("volume")
        if current_volume is None and not volumes.empty:
            current_volume = float(volumes.iloc[-1])
        previous_volume = float(volumes.iloc[-2]) if len(volumes) > 1 else None
        average_volume_20d = float(volumes.tail(20).mean()) if len(volumes) >= 5 else None
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
        obv_divergence = compute_obv_divergence(closes, volumes)
        quiet_pullback = compute_quiet_pullback(closes, volumes)
        volume_range_signal = compute_volume_range_signal(closes, volumes)
        accumulation_score = sum([obv_divergence, quiet_pullback, volume_range_signal])
        prior20_high = (
            float(closes.iloc[-21:-1].max())
            if len(closes) >= 21
            else float(closes.iloc[:-1].max()) if len(closes) > 1 else None
        )
        rows.append(
            {
                **stock,
                "display_symbol": symbol.removesuffix(".NS"),
                "price": current,
                "change": change,
                "percent": percent,
                "volume": current_volume,
                "volume_change": volume_change,
                "average_volume_20d": average_volume_20d,
                "relative_volume": None,
                "traded_value": (
                    current_volume * current
                    if current_volume is not None and current is not None
                    else None
                ),
                "delivery_percent": quote.get("delivery_percent"),
                "five_day_change": five_day_change,
                "day_open": day_open,
                "day_high": day_high,
                "day_low": day_low,
                "high52_distance": (
                    (current - high52) / high52 * 100
                    if current is not None and high52
                    else None
                ),
                "low52_distance": (
                    (current - low52) / low52 * 100
                    if current is not None and low52
                    else None
                ),
                "chart_series": [
                    round(float(value), 2)
                    for value in closes.tail(60).tolist()
                    if not pd.isna(value)
                ],
                "market_cap": quote.get("market_cap"),
                "free_float_market_cap": None,
                "month_change": None,
                "year_change": None,
                "previous_close": previous_close,
                "prior20_high": prior20_high,
                "price_volume_breakout": False,
                "sma50": sma50,
                "sma200": sma200,
                "high52": high52,
                "low52": low52,
                "signal": signal,
                "obv_divergence": obv_divergence,
                "quiet_pullback": quiet_pullback,
                "volume_range_signal": volume_range_signal,
                "accumulation_score": accumulation_score,
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


def _with_readable_impact_weights(items, impact_key, unit_key=None, readability=0.4):
    """Blend impact with an equal/readability allocation so labels remain usable."""
    if not items:
        return []
    impact_total = sum(max(float(item.get(impact_key) or 0), 0) for item in items)
    units = [max(float(item.get(unit_key) or 0), 1) if unit_key else 1.0 for item in items]
    unit_total = sum(units) or float(len(items))
    if impact_total <= 0:
        return [
            {**item, "layout_weight": units[index] / unit_total}
            for index, item in enumerate(items)
        ]
    impact_share = max(0.0, min(float(readability), 0.8))
    return [
        {
            **item,
            "layout_weight": (
                (1 - impact_share) * max(float(item.get(impact_key) or 0), 0) / impact_total
                + impact_share * units[index] / unit_total
            ),
        }
        for index, item in enumerate(items)
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
        metric("52 Week Range", "Near High", "Near Low", len(high_rows), 0, len(low_rows)),
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
            "traded_value": row.get("traded_value"),
            "relative_volume": row.get("relative_volume"),
            "month_change": row.get("month_change"),
            "sector_rank": row.get("sector_rank"),
            "signal": row.get("signal"),
        }

    results = []
    for sector, values in sectors.items():
        priced = [row for row in values if row.get("percent") is not None]
        daily_changes = [row["percent"] for row in priced]
        month_changes = [
            row["month_change"]
            for row in values
            if row.get("month_change") is not None
        ]
        weighted_rows = [
            row for row in priced
            if row.get("free_float_market_cap")
        ]
        weight_total = sum(row["free_float_market_cap"] for row in weighted_rows)
        weighted_percent = (
            sum(row["percent"] * row["free_float_market_cap"] for row in weighted_rows)
            / weight_total
            if weight_total
            else None
        )
        sector_average = sum(daily_changes) / len(daily_changes) if daily_changes else 0
        ranked_values = sorted(
            values,
            key=lambda row: row["percent"] if row.get("percent") is not None else -math.inf,
            reverse=True,
        )
        for rank, row in enumerate(ranked_values, start=1):
            row["sector_rank"] = rank
            row["sector_stock_count"] = len(values)
            row["sector_average_change"] = sector_average
            row["sector_relative_change"] = (
                row["percent"] - sector_average
                if row.get("percent") is not None
                else None
            )
        results.append(
            {
                "name": sector,
                "percent": sector_average,
                "median_percent": median(daily_changes) if daily_changes else 0,
                "weighted_percent": weighted_percent,
                "month_change": sum(month_changes) / len(month_changes) if month_changes else None,
                "stocks": len(values),
                "advancers": sum((row.get("percent") or 0) > 0 for row in values),
                "volume": sum(row.get("volume") or 0 for row in values),
                "traded_value": sum(row.get("traded_value") or 0 for row in values),
                "leader": max(
                    values,
                    key=lambda row: row["percent"] if row.get("percent") is not None else -math.inf,
                ),
                "laggard": min(
                    values,
                    key=lambda row: row["percent"] if row.get("percent") is not None else math.inf,
                ),
                "members": [
                    member(row)
                    for row in ranked_values
                ],
            }
        )
    return sorted(
        results,
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
            "stock_count": len(items),
            "impact": impact,
            "market_cap": sum(item.get("market_cap") or 0 for item in items),
            "raw_weight": impact if impact_available else fallback,
        })

    groups = []
    sector_rectangles = _binary_treemap(
        _with_readable_impact_weights(
            sector_items,
            "impact",
            unit_key="stock_count",
            readability=0.58,
        )
        if impact_available
        else _with_minimum_layout_weights(sector_items, 0.055)
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
        cell_layout = (
            _with_readable_impact_weights(
                cell_items,
                "raw_weight",
                readability=0.64,
            )
            if impact_available
            else _with_minimum_layout_weights(cell_items, 0.055)
        )
        for item in _binary_treemap(cell_layout):
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


def _standardize_columns(frame):
    frame = frame.copy()
    frame.columns = [
        str(column).replace("\ufeff", "").replace("\xef\xbb\xbf", "").strip().strip('"').strip()
        for column in frame.columns
    ]
    return frame


def _parse_deal_date(value):
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.to_datetime(value, errors="coerce")
    return pd.to_datetime(str(value).strip(), format="%d-%b-%Y", errors="coerce")


def _normalize_symbol(value):
    return re.sub(r"[^A-Z0-9&-]", "", str(value or "").upper().removesuffix(".NS"))


def normalize_deal_frame(frame, kind):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "symbol", "security_name", "client_name", "side", "quantity", "price", "value"])
    frame = _standardize_columns(frame)
    if kind == "short" and {"SS_DATE", "SS_SYMBOL", "SS_QTY"}.issubset(frame.columns):
        normalized = pd.DataFrame(
            {
                "date": frame.get("SS_DATE", pd.Series(dtype=object)).map(_parse_deal_date),
                "symbol": frame.get("SS_SYMBOL", pd.Series(dtype=object)).map(_normalize_symbol),
                "security_name": frame.get("SS_NAME", pd.Series(dtype=object)).fillna("").astype(str),
                "quantity": frame.get("SS_QTY", pd.Series(dtype=object)).map(_parse_number),
            }
        )
        normalized["quantity"] = normalized["quantity"].fillna(0)
        return normalized.dropna(subset=["date"]).query("symbol != ''").reset_index(drop=True)
    if kind != "short" and {"BD_DT_DATE", "BD_SYMBOL", "BD_QTY_TRD"}.issubset(frame.columns):
        price_column = "BD_TP_WATP"
        normalized = pd.DataFrame(
            {
                "date": frame.get("BD_DT_DATE", pd.Series(dtype=object)).map(_parse_deal_date),
                "symbol": frame.get("BD_SYMBOL", pd.Series(dtype=object)).map(_normalize_symbol),
                "security_name": frame.get("BD_SCRIP_NAME", pd.Series(dtype=object)).fillna("").astype(str),
                "client_name": frame.get("BD_CLIENT_NAME", pd.Series(dtype=object)).fillna("").astype(str),
                "side": frame.get("BD_BUY_SELL", pd.Series(dtype=object)).fillna("").astype(str).str.upper().str.strip(),
                "quantity": frame.get("BD_QTY_TRD", pd.Series(dtype=object)).map(_parse_number),
                "price": frame.get(price_column, pd.Series(dtype=object)).map(_parse_number),
            }
        )
        normalized["quantity"] = normalized["quantity"].fillna(0)
        normalized["price"] = normalized["price"].fillna(0)
        normalized["value"] = normalized["quantity"] * normalized["price"]
        return normalized.dropna(subset=["date"]).query("symbol != ''").reset_index(drop=True)
    if {"date", "symbol", "quantity"}.issubset(frame.columns):
        normalized = frame.copy()
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized["symbol"] = normalized["symbol"].map(_normalize_symbol)
        normalized["quantity"] = normalized["quantity"].map(_parse_number).fillna(0)
        if kind != "short":
            if "side" not in normalized:
                normalized["side"] = ""
            normalized["side"] = normalized["side"].astype(str).str.upper().str.strip()
            if "price" not in normalized:
                normalized["price"] = 0
            normalized["price"] = normalized["price"].map(_parse_number).fillna(0)
            if "value" not in normalized:
                normalized["value"] = normalized["quantity"] * normalized["price"]
            normalized["value"] = normalized["value"].map(_parse_number).fillna(0)
            if "client_name" not in normalized:
                normalized["client_name"] = ""
            normalized["client_name"] = normalized["client_name"].fillna("").astype(str)
        if "security_name" not in normalized:
            normalized["security_name"] = ""
        normalized["security_name"] = normalized["security_name"].fillna("").astype(str)
        return normalized.dropna(subset=["date"]).query("symbol != ''").reset_index(drop=True)
    if kind == "short":
        normalized = pd.DataFrame(
            {
                "date": frame.get("Date", pd.Series(dtype=object)).map(_parse_deal_date),
                "symbol": frame.get("Symbol", pd.Series(dtype=object)).map(_normalize_symbol),
                "security_name": frame.get("Security Name", pd.Series(dtype=object)).fillna("").astype(str),
                "quantity": frame.get("Quantity", pd.Series(dtype=object)).map(_parse_number),
            }
        )
        normalized["quantity"] = normalized["quantity"].fillna(0)
        return normalized.dropna(subset=["date"]).query("symbol != ''").reset_index(drop=True)

    price_column = "Trade Price / Wght. Avg. Price"
    normalized = pd.DataFrame(
        {
            "date": frame.get("Date", pd.Series(dtype=object)).map(_parse_deal_date),
            "symbol": frame.get("Symbol", pd.Series(dtype=object)).map(_normalize_symbol),
            "security_name": frame.get("Security Name", pd.Series(dtype=object)).fillna("").astype(str),
            "client_name": frame.get("Client Name", pd.Series(dtype=object)).fillna("").astype(str),
            "side": frame.get("Buy / Sell", pd.Series(dtype=object)).fillna("").astype(str).str.upper().str.strip(),
            "quantity": frame.get("Quantity Traded", pd.Series(dtype=object)).map(_parse_number),
            "price": frame.get(price_column, pd.Series(dtype=object)).map(_parse_number),
        }
    )
    normalized["quantity"] = normalized["quantity"].fillna(0)
    normalized["price"] = normalized["price"].fillna(0)
    normalized["value"] = normalized["quantity"] * normalized["price"]
    return normalized.dropna(subset=["date"]).query("symbol != ''").reset_index(drop=True)


def _latest_matching_csv(data_dir, pattern):
    matches = sorted(data_dir.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def read_bulk_block_short_files(data_dir=BULK_BLOCK_DATA_DIR):
    paths = {
        "bulk": _latest_matching_csv(data_dir, "Bulk-Deals-*.csv"),
        "block": _latest_matching_csv(data_dir, "Block-Deals-*.csv"),
        "short": _latest_matching_csv(data_dir, "Short-Selling-*.csv"),
    }
    frames = {}
    for kind, path in paths.items():
        if not path:
            frames[kind] = normalize_deal_frame(pd.DataFrame(), kind)
            continue
        frames[kind] = normalize_deal_frame(pd.read_csv(path), kind)
    latest_dates = [
        frame["date"].max()
        for frame in frames.values()
        if frame is not None and not frame.empty and "date" in frame
    ]
    latest_date = max(latest_dates).date().isoformat() if latest_dates else None
    return {
        **frames,
        "source": "local CSV seed",
        "latest_date": latest_date,
        "refreshed_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
    }


def _frame_from_nse_payload(payload):
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        for key in ("data", "rows", "records"):
            if isinstance(payload.get(key), list):
                return pd.DataFrame(payload[key])
    return pd.DataFrame()


def _fetch_nse_history_frame(session, kind, from_date, to_date):
    response = session.get(
        NSE_BULK_BLOCK_HISTORY_API,
        params={
            "optionType": NSE_HISTORICAL_DEAL_APIS[kind],
            "from": from_date,
            "to": to_date,
            "csv": "true",
        },
        timeout=20,
        headers={"Referer": NSE_BULK_BLOCK_REPORT_URL},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        return _frame_from_nse_payload(response.json())
    text = response.text.strip()
    if text.startswith("{") or text.startswith("["):
        return _frame_from_nse_payload(response.json())
    return pd.read_csv(StringIO(text)) if text else pd.DataFrame()


def fetch_bulk_block_short_from_nse(today=None):
    today = today or datetime.now(IST).date()
    from_day = today - timedelta(days=365)
    from_date = from_day.strftime("%d-%m-%Y")
    to_date = today.strftime("%d-%m-%Y")
    frames = {}
    with requests.Session() as session:
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/csv,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": NSE_BULK_BLOCK_REPORT_URL,
            "X-Requested-With": "XMLHttpRequest",
        })
        session.get(NSE_BULK_BLOCK_REPORT_URL, timeout=12)
        for kind in ("bulk", "block", "short"):
            frames[kind] = normalize_deal_frame(
                _fetch_nse_history_frame(session, kind, from_date, to_date),
                kind,
            )
    if all(frame.empty for frame in frames.values()):
        raise ValueError("NSE bulk/block/short response returned no rows")
    latest_dates = [frame["date"].max() for frame in frames.values() if not frame.empty]
    return {
        **frames,
        "source": "NSE archive refresh",
        "latest_date": max(latest_dates).date().isoformat() if latest_dates else None,
        "refreshed_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
    }


def _save_bulk_block_short_files(data, data_dir=BULK_BLOCK_DATA_DIR):
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).date().strftime("%d-%m-%Y")
    file_map = {
        "bulk": f"Bulk-Deals-latest-{stamp}.csv",
        "block": f"Block-Deals-latest-{stamp}.csv",
        "short": f"Short-Selling-latest-{stamp}.csv",
    }
    for kind, filename in file_map.items():
        frame = data.get(kind)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frame.to_csv(data_dir / filename, index=False)


def refresh_bulk_block_short_cache_from_nse():
    data = fetch_bulk_block_short_from_nse()
    _save_bulk_block_short_files(data)
    with _CACHE_LOCK:
        _CACHE["bulk_block_short_data"] = {
            "data": data,
            "expires": time_module.time() + BULK_BLOCK_CACHE_TTL,
        }
    _write_persistent_cache("bulk_block_short_data", data, BULK_BLOCK_CACHE_TTL)
    return data


def empty_insights_data():
    return {
        "accumulation_count": 0,
        "uptrend_count": 0,
        "near_high_count": 0,
        "institutional_accumulation_count": 0,
        "high_conviction_count": 0,
        "rising_short_count": 0,
        "ranked": [],
        "high_conviction": [],
        "bulk_buy_leaders": [],
        "bulk_sell_leaders": [],
        "short_pressure": [],
        "sector_deal_flow": [],
        "sector_stock_tables": [],
        "sectors": [],
        "top_lines": [
            "Insights snapshot is warming. The latest precomputed analysis will appear automatically."
        ],
        "deal_meta": {
            "source": "warming",
            "latest_date": None,
            "refreshed_at": None,
            "row_count": 0,
        },
    }


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Series):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, pd.DataFrame):
        return [_json_safe(item) for item in value.to_dict(orient="records")]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if type(value).__module__.startswith("numpy"):
        try:
            return _json_safe(value.item())
        except (AttributeError, TypeError, ValueError):
            try:
                return _json_safe(value.tolist())
            except (AttributeError, TypeError, ValueError):
                return str(value)
    if isinstance(value, bool) or type(value).__name__ == "bool_":
        return bool(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, numbers.Integral) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        value = float(value)
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return value


def get_cached_insights_snapshot():
    with _CACHE_LOCK:
        cached = _CACHE.get(INSIGHTS_SNAPSHOT_KEY)
    if cached and isinstance(cached.get("data"), dict):
        return cached["data"]
    cached = _read_persistent_cache(INSIGHTS_SNAPSHOT_KEY)
    if cached and isinstance(cached.get("data"), dict):
        with _CACHE_LOCK:
            _CACHE[INSIGHTS_SNAPSHOT_KEY] = cached
        return cached["data"]
    return None


def insights_snapshot_needs_nse_refresh(snapshot):
    if not isinstance(snapshot, dict):
        return True
    insights = snapshot.get("insights") or {}
    deal_meta = insights.get("deal_meta") or snapshot.get("deal_meta") or {}
    source = str(deal_meta.get("source") or "").strip().lower()
    return source in {"", "warming", "local csv seed", "refresh failed"}


def store_insights_snapshot(snapshot):
    snapshot = _json_safe({
        "status": snapshot.get("status", "ready"),
        **snapshot,
    })
    with _CACHE_LOCK:
        _CACHE[INSIGHTS_SNAPSHOT_KEY] = {
            "data": snapshot,
            "expires": time_module.time() + INSIGHTS_SNAPSHOT_TTL,
        }
    _write_persistent_cache(INSIGHTS_SNAPSHOT_KEY, snapshot, INSIGHTS_SNAPSHOT_TTL)
    return snapshot


def store_insights_error_snapshot(error):
    created_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    insights = empty_insights_data()
    insights["top_lines"] = [
        "Insights snapshot could not be fully refreshed. The system will retry automatically.",
        f"Last refresh error: {error}",
    ]
    insights["deal_meta"] = {
        **insights["deal_meta"],
        "source": "refresh failed",
        "refreshed_at": created_at,
    }
    return store_insights_snapshot(
        {
            "status": "ready",
            "insights": insights,
            "hover_data": {},
            "deal_meta": insights["deal_meta"],
            "created_at": created_at,
            "refreshed_at": created_at,
            "stale": True,
            "error": str(error),
            "market_stale": True,
            "deal_data_stale": True,
            "constituents_stale": True,
        }
    )


def _market_for_insights_snapshot():
    try:
        return refresh_market_dashboard_cache(), False, False, None
    except Exception as refresh_error:
        try:
            context = load_cached_market_context()
            market = context.get("market") or empty_market_dashboard()
            return (
                market,
                True,
                bool(context.get("constituents_stale")),
                str(refresh_error),
            )
        except Exception as cache_error:
            return (
                empty_market_dashboard(),
                True,
                True,
                f"{refresh_error}; cached market fallback failed: {cache_error}",
            )


def refresh_insights_snapshot(deal_data=None, market=None, stale=False, error=None):
    if deal_data is None:
        deal_data = read_bulk_block_short_files()
    market_error = None
    market_stale = False
    constituents_stale = False
    if market is None:
        market, market_stale, constituents_stale, market_error = _market_for_insights_snapshot()
    rows = market.get("rows", []) if isinstance(market, dict) else []
    popup_details = get_cached_stock_popup_details_snapshot(rows)
    insight_data = build_insights(rows, deal_data or {}, popup_details)
    created_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    combined_error = "; ".join(str(item) for item in (error, market_error) if item)
    snapshot = {
        "status": "ready",
        "insights": insight_data,
        "hover_data": build_stock_hover_data_with_details(rows, popup_details),
        "deal_meta": insight_data.get("deal_meta", {}),
        "created_at": created_at,
        "refreshed_at": created_at,
        "stale": bool(stale or market_stale or combined_error),
        "error": combined_error or None,
        "market_stale": bool(market_stale),
        "deal_data_stale": bool(stale),
        "constituents_stale": bool(constituents_stale),
    }
    return store_insights_snapshot(snapshot)


def refresh_daily_insights_snapshot():
    try:
        deal_data = refresh_bulk_block_short_cache_from_nse()
        return refresh_insights_snapshot(deal_data=deal_data)
    except Exception as exc:
        previous = get_cached_insights_snapshot()
        if previous:
            return store_insights_snapshot(
                {
                    **previous,
                    "status": "ready",
                    "stale": True,
                    "deal_data_stale": True,
                    "error": str(exc),
                }
            )
        try:
            return refresh_insights_snapshot(stale=True, error=f"NSE refresh failed: {exc}")
        except Exception as fallback_exc:
            return store_insights_error_snapshot(f"{exc}; snapshot fallback failed: {fallback_exc}")


def _insights_snapshot_refresh_worker(delay=0):
    if delay:
        time_module.sleep(delay)
    try:
        refresh_daily_insights_snapshot()
    except Exception as exc:
        store_insights_error_snapshot(exc)
    finally:
        with _CACHE_LOCK:
            _CACHE_REFRESHING.discard(INSIGHTS_SNAPSHOT_KEY)


def ensure_insights_snapshot_refresh_async(delay=0):
    with _CACHE_LOCK:
        if INSIGHTS_SNAPSHOT_KEY in _CACHE_REFRESHING:
            return False
        _CACHE_REFRESHING.add(INSIGHTS_SNAPSHOT_KEY)
    threading.Thread(
        target=_insights_snapshot_refresh_worker,
        kwargs={"delay": delay},
        daemon=True,
        name="insights-snapshot-refresh",
    ).start()
    return True


def seconds_until_next_ist_midnight(now=None):
    current = now or datetime.now(IST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=IST)
    current = current.astimezone(IST)
    next_midnight = datetime.combine(current.date() + timedelta(days=1), time.min, tzinfo=IST)
    return max(1, int((next_midnight - current).total_seconds()))


def _bulk_block_refresh_loop():
    while True:
        time_module.sleep(seconds_until_next_ist_midnight())
        try:
            refresh_daily_insights_snapshot()
        except Exception:
            pass


def start_bulk_block_refresh_scheduler():
    global _BULK_BLOCK_REFRESH_STARTED
    if _BULK_BLOCK_REFRESH_STARTED or os.getenv("DISABLE_BULK_BLOCK_REFRESH") == "1":
        return
    _BULK_BLOCK_REFRESH_STARTED = True
    threading.Thread(
        target=_bulk_block_refresh_loop,
        daemon=True,
        name="bulk-block-short-midnight-refresh",
    ).start()


def start_insights_snapshot_refresh_scheduler():
    global _INSIGHTS_SNAPSHOT_REFRESH_STARTED
    if (
        _INSIGHTS_SNAPSHOT_REFRESH_STARTED
        or os.getenv("DISABLE_INSIGHTS_SNAPSHOT_REFRESH") == "1"
    ):
        return
    _INSIGHTS_SNAPSHOT_REFRESH_STARTED = True
    snapshot = get_cached_insights_snapshot()
    if insights_snapshot_needs_nse_refresh(snapshot):
        ensure_insights_snapshot_refresh_async(
            delay=max(0, STARTUP_INSIGHTS_SNAPSHOT_REFRESH_DELAY)
        )


def get_bulk_block_short_data():
    return get_cached_swr(
        "bulk_block_short_data",
        BULK_BLOCK_CACHE_TTL,
        read_bulk_block_short_files,
    )


def build_stock_hover_data(rows):
    return build_stock_hover_data_with_details(rows, {})


def build_stock_hover_data_with_details(rows, details, headline_context=None, event_context=None):
    headline_context = headline_context or {}
    event_context = event_context or {}
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
            "traded_value": row.get("traded_value"),
            "relative_volume": row.get("relative_volume"),
            "market_cap": row.get("market_cap"),
            "free_float_market_cap": row.get("free_float_market_cap"),
            "signal": row.get("signal"),
            "month_change": row.get("month_change"),
            "year_change": row.get("year_change"),
            "sector_rank": row.get("sector_rank"),
            "sector_stock_count": row.get("sector_stock_count"),
            "sector_relative_change": row.get("sector_relative_change"),
            "series": row.get("chart_series", []),
            "day_open": row.get("day_open"),
            "day_high": row.get("day_high"),
            "day_low": row.get("day_low"),
            "high52_distance": row.get("high52_distance"),
            "low52_distance": row.get("low52_distance"),
            "accumulation_score": row.get("accumulation_score", 0),
            "obv_divergence": row.get("obv_divergence", False),
            "quiet_pullback": row.get("quiet_pullback", False),
            "volume_range_signal": row.get("volume_range_signal", False),
            "delivery_percent": row.get("delivery_percent"),
            "market_headlines": headline_context.get(row["display_symbol"], []),
            "next_event": event_context.get(row["display_symbol"]),
            "details": details.get(row["display_symbol"], {}),
        }
        for row in rows
    }


DETAIL_USEFUL_FIELDS = (
    "pe_ratio",
    "revenue",
    "operating_profit_margin",
    "roe",
    "price_to_book",
    "promoter_holding",
    "description",
    "news",
)


def _detail_has_useful_content(detail):
    if not isinstance(detail, dict) or not detail:
        return False
    for key in DETAIL_USEFUL_FIELDS:
        value = detail.get(key)
        if value not in (None, "", []):
            return True
    return False


def _cached_dashboard_row_for_symbol(symbol):
    symbol = _normalize_symbol(symbol)
    if not symbol:
        return {}
    with _CACHE_LOCK:
        cached_values = list(_CACHE.values())
    for entry in cached_values:
        data = entry.get("data") if isinstance(entry, dict) else None
        if not isinstance(data, dict):
            continue
        rows = data.get("rows")
        if isinstance(rows, list):
            for row in rows:
                if _normalize_symbol(row.get("display_symbol") or row.get("symbol")) == symbol:
                    return row
        market = data.get("market")
        if isinstance(market, dict):
            for row in market.get("rows", []) or []:
                if _normalize_symbol(row.get("display_symbol") or row.get("symbol")) == symbol:
                    return row
    return {}


def _known_stock_metadata(symbol):
    symbol = _normalize_symbol(symbol)
    for stock in STOCKS:
        if _normalize_symbol(stock.get("symbol")) == symbol:
            return stock
    return {}


def _fallback_stock_detail(symbol, detail=None):
    symbol = _normalize_symbol(symbol)
    detail = detail if isinstance(detail, dict) else {}
    row = _cached_dashboard_row_for_symbol(symbol)
    known = _known_stock_metadata(symbol)
    name = detail.get("name") or row.get("name") or known.get("name") or symbol
    sector = detail.get("sector") or row.get("sector") or known.get("sector") or ""
    industry = detail.get("industry") or row.get("industry") or known.get("industry") or ""
    news = detail.get("news")
    if news in (None, []):
        news = _fallback_stock_news_from_market_headlines(symbol, name)
    fallback = {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "industry": industry,
        "price": row.get("price"),
        "market_cap": row.get("market_cap"),
        "volume": row.get("volume"),
        "delivery_percent": detail.get("delivery_percent", row.get("delivery_percent")),
        "enterprise_value": None,
        "pe_ratio": None,
        "revenue": None,
        "pat_margin": None,
        "operating_profit_margin": None,
        "roe": None,
        "roce": None,
        "price_to_book": None,
        "profit_cagr_3y": None,
        "avg_pe_3y": None,
        "debt_equity": None,
        "total_debt": None,
        "promoter_holding": None,
        "promoter_trend": None,
        "fii_holding": None,
        "fii_trend": None,
        "dii_holding": None,
        "dii_trend": None,
        "retail_holding": None,
        "retail_trend": None,
        "fii_dii_holding": None,
        "fii_dii_trend": None,
        "dividend_yield": None,
        "description": detail.get("description") or (
            "Company fundamentals are temporarily unavailable in the popup cache. "
            "Price, volume and sector data are shown from the latest dashboard row when available."
        ),
        "growth": detail.get("growth") or {},
        "news": news or [],
        "unavailable_message": detail.get("unavailable_message")
        or "Some fundamentals are unavailable in the latest cache.",
    }
    return {**fallback, **{key: value for key, value in detail.items() if value not in (None, "")}}


def _latest_statement_column(frame):
    if frame is None or frame.empty:
        return None
    return frame.columns[0]


def _statement_value(frame, labels, column=None):
    if frame is None or frame.empty:
        return None
    column = column if column is not None else _latest_statement_column(frame)
    if column is None or column not in frame:
        return None
    for label in labels:
        if label in frame.index:
            value = _parse_number(frame.loc[label, column])
            if value is not None:
                return value
    return None


def _statement_series(frame, labels):
    if frame is None or frame.empty:
        return []
    values = []
    for column in frame.columns:
        value = _statement_value(frame, labels, column)
        if value is not None:
            values.append((column, value))
    return values


def _fx_average_to_inr(currency, end_date):
    currency = (currency or "INR").upper()
    if currency == "INR":
        return 1.0
    if currency not in {"USD"}:
        return None
    try:
        end = pd.Timestamp(end_date).date()
    except Exception:
        end = datetime.now(IST).date()
    start = end - timedelta(days=365)
    key = f"fx:{currency}:INR:{start.isoformat()}:{end.isoformat()}"
    rate, _ = get_cached(
        key,
        STOCK_DETAIL_CACHE_TTL * 7,
        lambda: float(yf.Ticker("USDINR=X").history(start=start, end=end + timedelta(days=1))["Close"].dropna().mean()),
    )
    return rate if rate and math.isfinite(rate) else None


def _financial_to_inr(value, financial_currency, period_end=None):
    if value is None:
        return None
    rate = _fx_average_to_inr(financial_currency, period_end or datetime.now(IST).date())
    return value * rate if rate else None


def _percent_from_info(info, key):
    value = _parse_number(info.get(key))
    if value is None:
        return None
    return value * 100 if abs(value) <= 1 else value


def _ratio_from_percent(value):
    value = _parse_number(value)
    if value is None:
        return None
    return value / 100 if abs(value) > 3 else value


def _profit_cagr_3y(financials):
    profits = _statement_series(
        financials,
        ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"],
    )
    if len(profits) < 4:
        return None
    latest = profits[0][1]
    base = profits[3][1]
    if latest <= 0 or base <= 0:
        return None
    return ((latest / base) ** (1 / 3) - 1) * 100


def _average_pe_3y(financials, info, financial_currency, history=None):
    shares = _parse_number(info.get("sharesOutstanding"))
    if not shares or history is None or history.empty or "Close" not in history:
        return None
    closes = history["Close"].dropna()
    if closes.empty:
        return None
    profits = _statement_series(
        financials,
        ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"],
    )[:3]
    pe_values = []
    for period_end, profit in profits:
        profit_inr = _financial_to_inr(profit, financial_currency, period_end)
        try:
            period_timestamp = pd.Timestamp(period_end)
            eligible_closes = closes[closes.index.tz_localize(None) <= period_timestamp.tz_localize(None)]
        except (TypeError, ValueError):
            eligible_closes = pd.Series(dtype=float)
        if profit_inr and profit_inr > 0 and not eligible_closes.empty:
            historical_market_cap = float(eligible_closes.iloc[-1]) * shares
            pe_values.append(historical_market_cap / profit_inr)
    return sum(pe_values) / len(pe_values) if pe_values else None


def _compute_roce(financials, balance_sheet):
    latest_income_col = _latest_statement_column(financials)
    latest_balance_col = _latest_statement_column(balance_sheet)
    ebit = _statement_value(financials, ["EBIT", "Operating Income"], latest_income_col)
    total_assets = _statement_value(balance_sheet, ["Total Assets"], latest_balance_col)
    current_liabilities = _statement_value(balance_sheet, ["Current Liabilities"], latest_balance_col)
    invested_capital = _statement_value(balance_sheet, ["Invested Capital"], latest_balance_col)
    capital_employed = invested_capital or (
        total_assets - current_liabilities
        if total_assets is not None and current_liabilities is not None
        else None
    )
    if ebit is None or not capital_employed:
        return None
    return ebit / capital_employed * 100


def _major_holder_value(frame, label):
    try:
        if frame is None or frame.empty or label not in frame.index:
            return None
        value = _parse_number(frame.loc[label, "Value"])
        return value * 100 if value is not None and abs(value) <= 1 else value
    except Exception:
        return None


def _holder_percent_from_info(info, *keys):
    for key in keys:
        value = _percent_from_info(info, key)
        if value is not None:
            return value
    return None


def _infer_retail_holding(promoter, fii, dii):
    known = [value for value in (promoter, fii, dii) if value is not None]
    if not known:
        return None
    retail = 100 - sum(known)
    return max(0, min(100, retail))


def _change_label(current, previous):
    if current is None or previous is None:
        return None
    change = current - previous
    if abs(change) < 0.05:
        return "flat"
    return f"{change:+.1f}pp"


def _build_stock_detail_from_ticker(stock, fx_warnings=None):
    symbol = stock["symbol"]
    display_symbol = symbol.removesuffix(".NS")
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    financials = ticker.financials
    balance_sheet = ticker.balance_sheet
    major_holders = ticker.major_holders
    history = ticker.history(period="5y", interval="1d", auto_adjust=False)
    closes = history["Close"].dropna() if history is not None and "Close" in history else pd.Series(dtype=float)
    financial_currency = (info.get("financialCurrency") or info.get("currency") or "INR").upper()
    latest_period = _latest_statement_column(financials)
    annual_revenue = _statement_value(financials, ["Total Revenue"], latest_period)
    annual_net_income = _statement_value(
        financials,
        ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operation Net Minority Interest"],
        latest_period,
    )
    revenue_inr = _financial_to_inr(annual_revenue, financial_currency, latest_period)
    net_income_inr = _financial_to_inr(annual_net_income, financial_currency, latest_period)
    override = REPORTED_FINANCIAL_OVERRIDES.get(display_symbol)
    if override and str(pd.Timestamp(latest_period).date()) == override["period"]:
        revenue_inr = override["revenue_inr"]
        net_income_inr = override["net_income_inr"]
    if fx_warnings is not None and financial_currency != "INR" and annual_revenue:
        fx_warnings[display_symbol] = {
            "financial_currency": financial_currency,
            "raw_revenue": annual_revenue,
            "converted_revenue": revenue_inr,
        }
    promoter_holding = _major_holder_value(major_holders, "insidersPercentHeld")
    institutional_holding = _major_holder_value(major_holders, "institutionsPercentHeld")
    fii_holding = _holder_percent_from_info(info, "heldPercentInstitutions", "institutionsPercentHeld")
    dii_holding = _holder_percent_from_info(info, "heldPercentMutualFunds", "fundsPercentHeld")
    retail_holding = _infer_retail_holding(promoter_holding, fii_holding, dii_holding)
    operating_income = _statement_value(financials, ["Operating Income", "EBIT"], latest_period)
    operating_income_inr = _financial_to_inr(operating_income, financial_currency, latest_period)
    total_debt = _first_number(info.get("totalDebt"))
    if total_debt is None:
        total_debt = _statement_value(
            balance_sheet,
            ["Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"],
            _latest_statement_column(balance_sheet),
        )
        total_debt = _financial_to_inr(total_debt, financial_currency, _latest_statement_column(balance_sheet))
    company_name = info.get("longName") or info.get("shortName") or stock.get("name") or display_symbol
    return {
        "symbol": display_symbol,
        "name": company_name,
        "market_cap": _parse_number(info.get("marketCap")),
        "enterprise_value": _parse_number(info.get("enterpriseValue")),
        "pe_ratio": _parse_number(info.get("trailingPE")) or _parse_number(info.get("forwardPE")),
        "revenue": revenue_inr,
        "revenue_currency": "INR" if revenue_inr is not None else None,
        "pat_margin": (net_income_inr / revenue_inr * 100) if revenue_inr and net_income_inr else _percent_from_info(info, "profitMargins"),
        "operating_profit_margin": (
            operating_income_inr / revenue_inr * 100
            if revenue_inr and operating_income_inr is not None
            else _percent_from_info(info, "operatingMargins")
        ),
        "roe": _percent_from_info(info, "returnOnEquity"),
        "roce": _compute_roce(financials, balance_sheet),
        "price_to_book": _parse_number(info.get("priceToBook")),
        "profit_cagr_3y": _profit_cagr_3y(financials),
        "avg_pe_3y": _average_pe_3y(financials, info, financial_currency, history),
        "debt_equity": _ratio_from_percent(info.get("debtToEquity")),
        "total_debt": total_debt,
        "promoter_holding": promoter_holding,
        "promoter_trend": _change_label(promoter_holding, None),
        "fii_holding": fii_holding,
        "fii_trend": None,
        "dii_holding": dii_holding,
        "dii_trend": None,
        "retail_holding": retail_holding,
        "retail_trend": None,
        "fii_dii_holding": institutional_holding,
        "fii_dii_trend": None,
        "dividend_yield": _parse_number(info.get("dividendYield")),
        "delivery_percent": None,
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "description": _strip_html(info.get("longBusinessSummary") or "")[:520],
        "news": fetch_stock_news(display_symbol, company_name),
        "growth": {
            "1m": _growth_from_closes(closes, 21),
            "3m": _growth_from_closes(closes, 63),
            "1y": _growth_from_closes(closes, 252),
            "5y": _growth_from_closes(closes, min(1260, max(len(closes) - 2, 0))),
        },
    }


def fetch_all_stock_popup_details(stocks):
    details = {}
    fx_warnings = {}
    if stocks:
        with ThreadPoolExecutor(max_workers=max(1, STOCK_DETAIL_WORKERS)) as executor:
            futures = {executor.submit(_build_stock_detail_from_ticker, stock, fx_warnings): stock for stock in stocks}
            for future in as_completed(futures):
                stock = futures[future]
                symbol = stock["symbol"].removesuffix(".NS")
                try:
                    details[symbol] = future.result()
                except Exception:
                    details[symbol] = {
                        "symbol": symbol,
                        "description": "Company details temporarily unavailable.",
                        "growth": {},
                        "news": _fallback_stock_news_from_market_headlines(symbol, stock.get("name", "")),
                    }
    return {
        "details": details,
        "refreshed_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "fx_warnings": fx_warnings,
    }


def get_stock_popup_details(stocks):
    symbols = [
        stock.get("symbol") or f"{stock.get('display_symbol', '')}.NS"
        for stock in stocks
        if stock.get("symbol") or stock.get("display_symbol")
    ]
    if len(symbols) > MAX_ASYNC_POPUP_DETAIL_PREFETCH:
        return {
            "details": get_cached_stock_popup_details_snapshot(stocks),
            "fx_warnings": {},
            "refreshed_at": None,
        }, False
    key = f"stock_popup_details:{','.join(symbols)}"
    data, stale = get_cached_swr(
        key,
        STOCK_DETAIL_CACHE_TTL,
        lambda: fetch_all_stock_popup_details([
            stock if stock.get("symbol") else {**stock, "symbol": f"{stock.get('display_symbol')}.NS"}
            for stock in stocks
        ]),
        cold_async=True,
    )
    return data or {"details": {}, "fx_warnings": {}, "refreshed_at": None}, stale


def get_cached_stock_popup_details_snapshot(stocks):
    """Return already-built popup details without starting a refresh."""
    popup_symbols = [
        stock.get("symbol") or f"{stock.get('display_symbol', '')}.NS"
        for stock in stocks or []
        if stock.get("symbol") or stock.get("display_symbol")
    ]
    symbols = {
        _normalize_symbol(stock.get("display_symbol") or stock.get("symbol"))
        for stock in stocks or []
        if stock.get("display_symbol") or stock.get("symbol")
    }
    if not symbols:
        return {}
    details = {}
    with _CACHE_LOCK:
        cached_details = [
            value.get("data", {}).get("details", {})
            for key, value in _CACHE.items()
            if key.startswith("stock_popup_details:")
        ]
        cached_single_details = {
            key.removeprefix("stock_detail:"): value.get("data")
            for key, value in _CACHE.items()
            if key.startswith("stock_detail:")
        }
    exact_cache = _read_persistent_cache(f"stock_popup_details:{','.join(popup_symbols)}")
    if exact_cache:
        cached_details.append(exact_cache.get("data", {}).get("details", {}))
    latest_cache = _read_persistent_cache(STOCK_POPUP_DETAILS_LATEST_KEY)
    if latest_cache:
        cached_details.append(latest_cache.get("data", {}).get("details", {}))
    for cached in cached_details:
        for symbol in symbols:
            if symbol in cached:
                details[symbol] = cached[symbol]
    for symbol in symbols:
        if symbol in cached_single_details and cached_single_details[symbol]:
            details[symbol] = cached_single_details[symbol]
    return details


def get_latest_stock_popup_details_data():
    with _CACHE_LOCK:
        cached = _CACHE.get(STOCK_POPUP_DETAILS_LATEST_KEY)
    if not cached:
        cached = _read_persistent_cache(STOCK_POPUP_DETAILS_LATEST_KEY)
        if cached:
            with _CACHE_LOCK:
                _CACHE[STOCK_POPUP_DETAILS_LATEST_KEY] = cached
    data = cached.get("data") if isinstance(cached, dict) else None
    if not isinstance(data, dict):
        return {"details": {}, "refreshed_at": None}
    return {
        "details": data.get("details") or {},
        "refreshed_at": data.get("refreshed_at"),
    }


def _stock_detail_universe_keys():
    stocks, _ = get_stock_universe()
    broad_stocks, _ = get_nifty500_universe()
    all_stocks = merge_stock_lists(stocks, broad_stocks)
    return stocks, broad_stocks, all_stocks


def refresh_stock_popup_details_cache():
    _, _, stocks = _stock_detail_universe_keys()
    data = fetch_all_stock_popup_details(stocks)
    key = f"stock_popup_details:{','.join(stock['symbol'] for stock in stocks)}"
    with _CACHE_LOCK:
        _CACHE[key] = {
            "data": data,
            "expires": time_module.time() + STOCK_DETAIL_CACHE_TTL,
        }
        _CACHE[STOCK_POPUP_DETAILS_LATEST_KEY] = {
            "data": data,
            "expires": time_module.time() + STOCK_DETAIL_CACHE_TTL,
        }
    _write_persistent_cache(key, data, STOCK_DETAIL_CACHE_TTL)
    _write_persistent_cache(STOCK_POPUP_DETAILS_LATEST_KEY, data, STOCK_DETAIL_CACHE_TTL)
    return data


def _stock_detail_refresh_loop():
    if os.getenv("DISABLE_STARTUP_STOCK_DETAIL_REFRESH") != "1":
        time_module.sleep(max(0, STARTUP_STOCK_DETAIL_REFRESH_DELAY))
        try:
            refresh_stock_popup_details_cache()
        except Exception:
            pass
    while True:
        time_module.sleep(seconds_until_next_ist_midnight() + 900)
        try:
            refresh_stock_popup_details_cache()
        except Exception:
            pass


def start_stock_detail_refresh_scheduler():
    global _STOCK_DETAIL_REFRESH_STARTED
    if _STOCK_DETAIL_REFRESH_STARTED or os.getenv("DISABLE_STOCK_DETAIL_REFRESH") == "1":
        return
    _STOCK_DETAIL_REFRESH_STARTED = True
    threading.Thread(
        target=_stock_detail_refresh_loop,
        daemon=True,
        name="stock-detail-daily-refresh",
    ).start()


def _sum_side(frame, side, column="value"):
    if frame is None or frame.empty or column not in frame:
        return 0.0
    side_frame = frame[frame.get("side", "").eq(side)]
    return float(side_frame[column].sum()) if not side_frame.empty else 0.0


def _window(frame, end_date, days, offset=0):
    if frame is None or frame.empty or end_date is None:
        return frame.iloc[0:0] if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    end = pd.Timestamp(end_date) - pd.Timedelta(days=offset)
    start = end - pd.Timedelta(days=days)
    return frame[(frame["date"] > start) & (frame["date"] <= end)]


def _deal_data_latest_date(deal_data):
    latest = None
    for kind in ("bulk", "block", "short"):
        frame = deal_data.get(kind) if deal_data else None
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frame_latest = frame["date"].max()
            latest = frame_latest if latest is None or frame_latest > latest else latest
    return latest


def _deal_summary_for_symbol(symbol, deal_data, end_date):
    symbol = _normalize_symbol(symbol)
    bulk = deal_data.get("bulk", pd.DataFrame()) if deal_data else pd.DataFrame()
    block = deal_data.get("block", pd.DataFrame()) if deal_data else pd.DataFrame()
    short = deal_data.get("short", pd.DataFrame()) if deal_data else pd.DataFrame()
    bulk_symbol = bulk[bulk["symbol"].eq(symbol)] if not bulk.empty else bulk
    block_symbol = block[block["symbol"].eq(symbol)] if not block.empty else block
    short_symbol = short[short["symbol"].eq(symbol)] if not short.empty else short
    bulk30 = _window(bulk_symbol, end_date, 30)
    bulk_prev30 = _window(bulk_symbol, end_date, 30, offset=30)
    block90 = _window(block_symbol, end_date, 90)
    short30 = _window(short_symbol, end_date, 30)
    short_prev30 = _window(short_symbol, end_date, 30, offset=30)
    bulk_buy30 = _sum_side(bulk30, "BUY")
    bulk_sell30 = _sum_side(bulk30, "SELL")
    block_buy90 = _sum_side(block90, "BUY")
    block_sell90 = _sum_side(block90, "SELL")
    short_qty30 = float(short30["quantity"].sum()) if not short30.empty else 0.0
    short_prev_qty30 = float(short_prev30["quantity"].sum()) if not short_prev30.empty else 0.0
    short_change = (
        (short_qty30 - short_prev_qty30) / short_prev_qty30 * 100
        if short_prev_qty30
        else 100.0 if short_qty30 else 0.0
    )
    return {
        "bulk_buy30": bulk_buy30,
        "bulk_sell30": bulk_sell30,
        "bulk_net30": bulk_buy30 - bulk_sell30,
        "bulk_trades30": int(len(bulk30)),
        "bulk_prev_net30": _sum_side(bulk_prev30, "BUY") - _sum_side(bulk_prev30, "SELL"),
        "block_buy90": block_buy90,
        "block_sell90": block_sell90,
        "block_net90": block_buy90 - block_sell90,
        "block_trades90": int(len(block90)),
        "short_qty30": short_qty30,
        "short_prev_qty30": short_prev_qty30,
        "short_change": short_change,
        "short_latest": float(short_symbol[short_symbol["date"].eq(short_symbol["date"].max())]["quantity"].sum())
        if not short_symbol.empty else 0.0,
    }


def _format_driver_value(value):
    return format_market_cap(abs(value)) if value else "0"


def build_insights(rows, deal_data=None, details=None):
    rows = rows or []
    deal_data = deal_data or {}
    details = details or {}
    deal_end_date = _deal_data_latest_date(deal_data)
    enriched_rows = []
    for row in rows:
        detail = details.get(_normalize_symbol(row.get("display_symbol") or row.get("symbol")), {})
        deal = _deal_summary_for_symbol(row.get("display_symbol"), deal_data, deal_end_date)
        drivers = []
        conflicts = []
        deal_score = 0
        if deal["bulk_net30"] > 0:
            deal_score += 2
            drivers.append(f"30D bulk net buying Rs {_format_driver_value(deal['bulk_net30'])}")
        elif deal["bulk_net30"] < 0:
            conflicts.append(f"30D bulk net selling Rs {_format_driver_value(deal['bulk_net30'])}")
        if deal["block_net90"] > 0:
            deal_score += 2
            drivers.append(f"90D block net buying Rs {_format_driver_value(deal['block_net90'])}")
        elif deal["block_net90"] < 0:
            conflicts.append(f"90D block net selling Rs {_format_driver_value(deal['block_net90'])}")
        if deal["short_qty30"] and deal["short_change"] <= -20:
            deal_score += 1
            drivers.append("short-selling pressure cooling")
        elif deal["short_qty30"] and deal["short_change"] >= 40:
            conflicts.append("short-selling pressure rising")
        if (row.get("accumulation_score") or 0) >= 2:
            drivers.append(f"{row.get('accumulation_score')}/3 accumulation setup")
        if row.get("signal") == "Uptrend":
            drivers.append("uptrend structure")
        if row.get("price") is not None and row.get("high52") and row["price"] >= row["high52"] * 0.95:
            drivers.append("within 5% of 52W high")
        if (row.get("accumulation_score") or 0) >= 2 and deal["bulk_net30"] < 0:
            conflicts.append("accumulation signal conflicts with bulk selling")
        if row.get("signal") == "Uptrend" and deal["short_change"] >= 40:
            conflicts.append("uptrend has rising short interest")
        composite_score = (
            (row.get("accumulation_score") or 0) * 12
            + deal_score * 9
            + (12 if row.get("signal") == "Uptrend" else 0)
            + (6 if row.get("five_day_change") is not None and row["five_day_change"] > 0 else 0)
            + (5 if row.get("price") is not None and row.get("high52") and row["price"] >= row["high52"] * 0.95 else 0)
            - min(len(conflicts) * 5, 15)
        )
        enriched_rows.append(
            {
                **row,
                "deal": deal,
                "detail": detail,
                "drivers": drivers[:5],
                "conflicts": conflicts[:4],
                "composite_score": round(composite_score, 1),
                "analyst_view": "Aligned" if drivers and not conflicts else "Mixed" if drivers else "Watch",
            }
        )
    accumulation_rows = [row for row in rows if (row.get("accumulation_score") or 0) >= 2]
    uptrend_rows = [row for row in rows if row.get("signal") == "Uptrend"]
    near_high_rows = [
        row for row in rows
        if row.get("price") is not None and row.get("high52") and row["price"] >= row["high52"] * 0.95
    ]
    ranked = sorted(
        enriched_rows,
        key=lambda row: (
            row.get("accumulation_score") or 0,
            row.get("five_day_change") if row.get("five_day_change") is not None else -999,
        ),
        reverse=True,
    )[:15]
    high_conviction = sorted(enriched_rows, key=lambda row: row["composite_score"], reverse=True)[:18]
    sector_totals = defaultdict(lambda: {"sector": "", "total": 0, "accumulation": 0})
    sector_flow = defaultdict(lambda: {"sector": "", "bulk_net30": 0.0, "block_net90": 0.0, "short_qty30": 0.0, "stocks": 0, "aligned": 0, "conflicts": 0})
    sector_members = defaultdict(list)
    for row in enriched_rows:
        sector = row.get("sector") or "Other"
        sector_totals[sector]["sector"] = sector
        sector_totals[sector]["total"] += 1
        if (row.get("accumulation_score") or 0) >= 2:
            sector_totals[sector]["accumulation"] += 1
        sector_flow[sector]["sector"] = sector
        sector_flow[sector]["bulk_net30"] += row["deal"]["bulk_net30"]
        sector_flow[sector]["block_net90"] += row["deal"]["block_net90"]
        sector_flow[sector]["short_qty30"] += row["deal"]["short_qty30"]
        sector_flow[sector]["stocks"] += 1
        sector_flow[sector]["aligned"] += 1 if row["analyst_view"] == "Aligned" else 0
        sector_flow[sector]["conflicts"] += len(row["conflicts"])
        sector_members[sector].append(row)
    sectors = sorted(
        sector_totals.values(),
        key=lambda item: (item["accumulation"], item["total"]),
        reverse=True,
    )
    max_count = max([item["accumulation"] for item in sectors] or [1])
    for item in sectors:
        item["width"] = (item["accumulation"] / max_count * 100) if max_count else 0
        item["ratio"] = item["accumulation"] / item["total"] * 100 if item["total"] else 0
    top_lines = [
        (
            f"{item['accumulation']} of {item['total']} {item['sector']} stocks are showing "
            "accumulation signals today."
        )
        for item in sectors[:3]
        if item["accumulation"] > 0
    ]
    if not top_lines:
        top_lines = ["No sector has a broad accumulation cluster in the current cached market data."]
    sector_deal_flow = sorted(
        sector_flow.values(),
        key=lambda item: abs(item["bulk_net30"]) + abs(item["block_net90"]),
        reverse=True,
    )[:10]
    bulk_buy_leaders = sorted(enriched_rows, key=lambda row: row["deal"]["bulk_net30"], reverse=True)[:10]
    bulk_sell_leaders = sorted(enriched_rows, key=lambda row: row["deal"]["bulk_net30"])[:10]
    short_pressure = sorted(enriched_rows, key=lambda row: (row["deal"]["short_qty30"], row["deal"]["short_change"]), reverse=True)[:12]
    institutional_accumulation = [
        row for row in enriched_rows
        if row["deal"]["bulk_net30"] > 0 and row["deal"]["block_net90"] >= 0 and (row.get("accumulation_score") or 0) >= 1
    ]
    def _average_detail_metric(members, key):
        values = []
        for member in members:
            value = member.get("detail", {}).get(key)
            if value is not None:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value):
                    values.append(value)
        return sum(values) / len(values) if values else None

    sector_stock_tables = []
    for sector, members in sector_members.items():
        ordered_members = sorted(
            members,
            key=lambda row: (
                row.get("composite_score", 0),
                row.get("accumulation_score") or 0,
                row.get("five_day_change") if row.get("five_day_change") is not None else -999,
            ),
            reverse=True,
        )
        leader = max(
            members,
            key=lambda row: row.get("percent") if row.get("percent") is not None else -999,
        ) if members else None
        laggard = min(
            members,
            key=lambda row: row.get("percent") if row.get("percent") is not None else 999,
        ) if members else None
        sector_accumulation = len([row for row in members if (row.get("accumulation_score") or 0) >= 2])
        sector_uptrend = len([row for row in members if row.get("signal") == "Uptrend"])
        sector_bulk_net30 = sum(row["deal"]["bulk_net30"] for row in members)
        sector_block_net90 = sum(row["deal"]["block_net90"] for row in members)
        sector_short_qty30 = sum(row["deal"]["short_qty30"] for row in members)
        sector_conflicts = sum(len(row.get("conflicts", [])) for row in members)
        sector_score = (
            sector_accumulation * 12
            + sector_uptrend * 5
            + sum(max(row.get("five_day_change") or 0, 0) for row in members)
            + (4 if sector_bulk_net30 > 0 else -4 if sector_bulk_net30 < 0 else 0)
            + (4 if sector_block_net90 > 0 else -4 if sector_block_net90 < 0 else 0)
            - min(sector_conflicts * 2, 12)
        )
        sector_stock_tables.append(
            {
                "sector": sector,
                "stocks": len(members),
                "accumulation": sector_accumulation,
                "uptrend": sector_uptrend,
                "avg_change": (
                    sum(row.get("percent", 0) or 0 for row in members) / len(members)
                    if members else None
                ),
                "leader": leader,
                "laggard": laggard,
                "watchlist": ordered_members[:5],
                "bulk_net30": sector_bulk_net30,
                "block_net90": sector_block_net90,
                "short_qty30": sector_short_qty30,
                "conflicts": sector_conflicts,
                "sector_score": round(sector_score, 1),
                "accumulation_ratio": sector_accumulation / len(members) * 100 if members else 0,
                "uptrend_ratio": sector_uptrend / len(members) * 100 if members else 0,
                "avg_pe": _average_detail_metric(members, "pe_ratio"),
                "avg_roe": _average_detail_metric(members, "roe"),
                "avg_roce": _average_detail_metric(members, "roce"),
                "members": ordered_members,
            }
        )
    sector_stock_tables = sorted(
        sector_stock_tables,
        key=lambda item: (item["accumulation"], item["uptrend"], item["stocks"]),
        reverse=True,
    )
    high_conviction_count = len([row for row in enriched_rows if row["composite_score"] >= 40])
    rising_short_count = len([row for row in enriched_rows if row["deal"]["short_qty30"] > 0 and row["deal"]["short_change"] >= 40])
    if sector_deal_flow and (abs(sector_deal_flow[0]["bulk_net30"]) + abs(sector_deal_flow[0]["block_net90"])) > 0:
        strongest_sector = sector_deal_flow[0]
        top_lines.append(
            f"{strongest_sector['sector']} has the strongest tracked deal-flow footprint: "
            f"bulk net Rs {_format_driver_value(strongest_sector['bulk_net30'])} and "
            f"block net Rs {_format_driver_value(strongest_sector['block_net90'])}."
        )
    if rising_short_count:
        top_lines.append(
            f"{rising_short_count} tracked stocks show a sharp 30D short-selling build-up; treat matching uptrends as confirmation-pending."
        )
    if institutional_accumulation:
        top_lines.append(
            f"{len(institutional_accumulation)} stocks combine positive deal flow with at least one accumulation signal."
        )
    deal_frames = [deal_data.get(kind) for kind in ("bulk", "block", "short") if isinstance(deal_data.get(kind), pd.DataFrame)]
    deal_row_count = sum(len(frame) for frame in deal_frames)
    return {
        "accumulation_count": len(accumulation_rows),
        "uptrend_count": len(uptrend_rows),
        "near_high_count": len(near_high_rows),
        "institutional_accumulation_count": len(institutional_accumulation),
        "high_conviction_count": high_conviction_count,
        "rising_short_count": rising_short_count,
        "ranked": ranked,
        "high_conviction": high_conviction,
        "bulk_buy_leaders": [row for row in bulk_buy_leaders if row["deal"]["bulk_net30"] > 0],
        "bulk_sell_leaders": [row for row in bulk_sell_leaders if row["deal"]["bulk_net30"] < 0],
        "short_pressure": [row for row in short_pressure if row["deal"]["short_qty30"] > 0],
        "sector_deal_flow": sector_deal_flow,
        "sector_stock_tables": sector_stock_tables,
        "sectors": sectors,
        "top_lines": top_lines,
        "deal_meta": {
            "source": deal_data.get("source", "unavailable") if deal_data else "unavailable",
            "latest_date": deal_data.get("latest_date") if deal_data else None,
            "refreshed_at": deal_data.get("refreshed_at") if deal_data else None,
            "row_count": deal_row_count,
        },
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
    return _fallback_stock_detail(clean_symbol, _build_stock_detail_from_ticker({"symbol": yf_symbol}))


def get_stock_detail(display_symbol):
    clean_symbol = _normalize_symbol(display_symbol)

    def with_news(detail):
        resolved = _fallback_stock_detail(clean_symbol, detail)
        if len(resolved.get("news") or []) < 3:
            try:
                resolved["news"] = fetch_stock_news(clean_symbol, resolved.get("name") or clean_symbol)
            except (requests.RequestException, ET.ParseError, ValueError, TypeError):
                pass
        return resolved

    with _CACHE_LOCK:
        popup_caches = [
            value.get("data", {}).get("details", {})
            for key, value in _CACHE.items()
            if key.startswith("stock_popup_details:")
        ]
    for details in popup_caches:
        if clean_symbol in details and _detail_has_useful_content(details[clean_symbol]):
            return with_news(details[clean_symbol])
    latest_cache = _read_persistent_cache(STOCK_POPUP_DETAILS_LATEST_KEY)
    latest_details = latest_cache.get("data", {}).get("details", {}) if latest_cache else {}
    if clean_symbol in latest_details and _detail_has_useful_content(latest_details[clean_symbol]):
        return with_news(latest_details[clean_symbol])
    data, _ = get_cached(
        f"stock_detail:{clean_symbol}",
        STOCK_DETAIL_CACHE_TTL,
        lambda: fetch_stock_detail(clean_symbol),
    )
    return with_news(data)


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


def popup_priority_symbols(market, earnings=None, headlines=None):
    symbols = {
        row.get("display_symbol")
        for group in (
            market.get("gainers", [])[:8],
            market.get("losers", [])[:8],
            market.get("turnover", [])[:8],
            market.get("unusual_volume", [])[:8],
            market.get("nifty50_rows", []),
        )
        for row in group
        if row.get("display_symbol")
    }
    symbols.update(
        item.get("symbol")
        for item in earnings or []
        if item.get("symbol")
    )
    for headline in headlines or []:
        symbols.update(
            item.get("symbol")
            for item in headline.get("stocks", [])
            if item.get("symbol")
        )
    return symbols


def load_market_dashboard(stocks, broad_stocks=None, allow_impact_fallback=False):
    broad_stocks = broad_stocks or stocks
    all_stocks = merge_stock_lists(stocks, broad_stocks)
    quotes, _ = get_market_quotes(stocks)
    quotes = quotes or {}
    index_history, _ = get_cached_swr(
        "index_history:5d:15m",
        MARKET_CACHE_TTL,
        fetch_index_history,
    )
    index_history = index_history if isinstance(index_history, pd.DataFrame) else pd.DataFrame()
    nse_index_cards = {}
    nse_snapshot = None
    try:
        nse_index_cards, nse_snapshot = fetch_nse_index_cards()
    except Exception:
        nse_index_cards, nse_snapshot = {}, None
    history_key = "stock_history:1y:1d:" + ",".join(stock["symbol"] for stock in all_stocks)
    stock_history, _ = get_cached_swr(
        history_key,
        HISTORY_CACHE_TTL,
        lambda: fetch_stock_history(all_stocks),
    )
    stock_history = stock_history if isinstance(stock_history, pd.DataFrame) else pd.DataFrame()
    all_rows = build_stock_rows(quotes, stock_history, all_stocks)
    rows_by_symbol = {row["symbol"]: row for row in all_rows}
    rows = [rows_by_symbol[stock["symbol"]] for stock in stocks if stock["symbol"] in rows_by_symbol]
    broad_rows = [rows_by_symbol[stock["symbol"]] for stock in broad_stocks if stock["symbol"] in rows_by_symbol]
    broad_snapshot = []
    snapshot_timestamp = None
    nse_snapshot_error = None
    try:
        broad_snapshot = fetch_nse_nifty500_snapshot()
        snapshot_timestamp = next(
            (
                item.get("lastUpdateTime")
                for item in broad_snapshot
                if str(item.get("symbol") or "").upper() in {"NIFTY 500", "NIFTY500"}
            ),
            None,
        )
        apply_nse_quote_snapshot(broad_rows, broad_snapshot)
    except Exception as exc:
        nse_snapshot_error = f"NIFTY 500 snapshot unavailable: {exc}"
    update_live_row_metrics(broad_rows)
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
    turnover = sorted(
        [row for row in broad_rows if row.get("traded_value") is not None],
        key=lambda row: row["traded_value"],
        reverse=True,
    )
    unusual_volume = sorted(
        [row for row in broad_rows if row.get("relative_volume") is not None],
        key=lambda row: row["relative_volume"],
        reverse=True,
    )
    delivery_leaders = sorted(
        [row for row in broad_rows if row.get("delivery_percent") is not None],
        key=lambda row: row["delivery_percent"],
        reverse=True,
    )
    breakouts = sorted(
        [row for row in broad_rows if row.get("price_volume_breakout")],
        key=lambda row: (
            row.get("relative_volume") or 0,
            row.get("percent") or 0,
        ),
        reverse=True,
    )
    contribution_leaders = sorted(
        [row for row in rows if row.get("nifty_impact") is not None],
        key=lambda row: row["nifty_impact"],
        reverse=True,
    )
    contribution_drags = sorted(
        [row for row in rows if row.get("nifty_impact") is not None],
        key=lambda row: row["nifty_impact"],
    )
    market_gauges, _ = get_cached_swr(
        "nse_market_gauges",
        MARKET_CACHE_TTL,
        fetch_nse_market_gauges,
    )
    sectors = build_sector_performance(broad_rows)
    market_stats = build_market_stats(broad_rows)
    breadth = build_breadth(broad_rows)
    breadth_history = record_market_breadth_history(breadth, market_stats)
    return {
        "indices": build_index_cards(index_history, nse_index_cards),
        "market_gauges": market_gauges or [],
        "rows": broad_rows,
        "nifty50_rows": rows,
        "breadth": breadth,
        "breadth_history": breadth_history,
        "gainers": gainers[:14],
        "losers": losers[:14],
        "active": turnover[:14],
        "turnover": turnover[:14],
        "volume_leaders": active[:14],
        "unusual_volume": unusual_volume[:14],
        "delivery_leaders": delivery_leaders[:10],
        "breakouts": breakouts[:10],
        "contribution_leaders": contribution_leaders[:6],
        "contribution_drags": contribution_drags[:6],
        "signals": sorted(broad_rows, key=lambda row: abs(row["percent"] or 0), reverse=True)[:18],
        "sectors": sectors,
        "sector_rotation": sorted(
            [sector for sector in sectors if sector.get("month_change") is not None],
            key=lambda sector: sector["month_change"],
            reverse=True,
        ),
        "heatmap": build_heatmap(rows),
        "hover_data": build_stock_hover_data(broad_rows),
        "impact_available": impact_available,
        "market_stats": market_stats,
        "internals": build_market_internals(rows),
        "insights": build_dashboard_insights(broad_rows, rows),
        "dashboard_notes": build_dashboard_notes(broad_rows, rows),
        "breadth_divergence": build_breadth_divergence(broad_rows, rows),
        "data_timestamp": snapshot_timestamp,
        "refreshed_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "refresh_warning": nse_snapshot_error,
    }


def build_market_stats(rows):
    priced = [row for row in rows if row["percent"] is not None]
    volumes = [row["volume"] for row in rows if row["volume"] is not None]
    free_float_caps = [
        row["free_float_market_cap"]
        for row in rows
        if row.get("free_float_market_cap") is not None
    ]
    traded_values = [
        row["traded_value"]
        for row in rows
        if row.get("traded_value") is not None
    ]
    positive = [row for row in priced if row["percent"] > 0]
    return {
        "tracked": len(rows),
        "priced": len(priced),
        "advance_ratio": len(positive) / len(priced) * 100 if priced else 0,
        "average_change": sum(row["percent"] for row in priced) / len(priced) if priced else None,
        "total_volume": sum(volumes),
        "total_traded_value": sum(traded_values),
        "free_float_market_cap": sum(free_float_caps),
        "free_float_coverage": len(free_float_caps),
    }


def record_market_breadth_history(breadth, market_stats, now=None):
    now = now or datetime.now(IST)
    market_breadth = breadth[0] if breadth else {}
    snapshot = {
        "timestamp": now.isoformat(),
        "label": now.strftime("%I:%M %p"),
        "advancers": int(market_breadth.get("left_count") or 0),
        "decliners": int(market_breadth.get("right_count") or 0),
        "advance_ratio": round(float(market_stats.get("advance_ratio") or 0), 2),
        "average_change": market_stats.get("average_change"),
    }
    with _CACHE_LOCK:
        cached = _CACHE.get(MARKET_BREADTH_HISTORY_KEY)
    if not cached:
        cached = _read_persistent_cache(MARKET_BREADTH_HISTORY_KEY)
    history = list(cached.get("data") or []) if isinstance(cached, dict) else []
    if history:
        try:
            last_time = datetime.fromisoformat(history[-1]["timestamp"])
        except (KeyError, TypeError, ValueError):
            last_time = None
        if last_time and (now - last_time).total_seconds() < 10 * 60:
            history[-1] = snapshot
        else:
            history.append(snapshot)
    else:
        history.append(snapshot)
    history = history[-48:]
    with _CACHE_LOCK:
        _CACHE[MARKET_BREADTH_HISTORY_KEY] = {
            "data": history,
            "expires": time_module.time() + INSIGHTS_SNAPSHOT_TTL,
        }
    _write_persistent_cache(
        MARKET_BREADTH_HISTORY_KEY,
        history,
        INSIGHTS_SNAPSHOT_TTL,
    )
    return history


def record_fii_dii_history(rows):
    if not rows:
        return []
    with _CACHE_LOCK:
        cached = _CACHE.get(FII_DII_HISTORY_KEY)
    if not cached:
        cached = _read_persistent_cache(FII_DII_HISTORY_KEY)
    history = list(cached.get("data") or []) if isinstance(cached, dict) else []
    by_date = {}
    for item in history:
        if not isinstance(item, dict):
            continue
        flow_date = _flow_date_iso(item.get("date"))
        if flow_date:
            by_date[flow_date] = {**item, "date": flow_date}
    for row in rows:
        flow_date = _flow_date_iso(row.get("date"))
        if not flow_date:
            continue
        entry = by_date.setdefault(flow_date, {"date": flow_date, "fii": None, "dii": None})
        category = str(row.get("category") or "").upper()
        if category.startswith("FII"):
            entry["fii"] = row.get("net")
        elif category.startswith("DII"):
            entry["dii"] = row.get("net")
    history = sorted(by_date.values(), key=lambda item: item["date"])[-520:]
    with _CACHE_LOCK:
        _CACHE[FII_DII_HISTORY_KEY] = {
            "data": history,
            "expires": time_module.time() + INSIGHTS_SNAPSHOT_TTL,
        }
    _write_persistent_cache(FII_DII_HISTORY_KEY, history, INSIGHTS_SNAPSHOT_TTL)
    return history


def merge_fii_dii_history(*histories):
    by_date = {}
    for history in histories:
        for item in history or []:
            if not isinstance(item, dict):
                continue
            flow_date = _flow_date_iso(item.get("date"))
            if not flow_date:
                continue
            existing = by_date.setdefault(flow_date, {"date": flow_date})
            for key in ("fii", "dii", "fii_buy", "fii_sell", "dii_buy", "dii_sell"):
                value = _parse_number(item.get(key))
                if value is not None:
                    existing[key] = value
    return sorted(by_date.values(), key=lambda item: item["date"])[-520:]


_DII_CLIENT_TERMS = (
    "MUTUAL FUND",
    "LIFE INSURANCE",
    "GENERAL INSURANCE",
    "NATIONAL PENSION SYSTEM",
    "NPS TRUST",
)
_FII_CLIENT_TERMS = (
    "MAURITIUS",
    " PTE",
    " VCC",
    " PCC",
    " SICAV",
    " UCITS",
    "FUND LP",
    "INTERNATIONAL STOCK",
    "EMERGING MARKETS",
    "EMERGING MARKET",
    "NORGES BANK",
    "ABU DHABI INVESTMENT AUTHORITY",
    "VANGUARD",
    "FIDELITY",
    "T ROWE PRICE",
    "T. ROWE PRICE",
    "GOVERNMENT PENSION INVESTMENT",
    "PUBLIC SECTOR PENSION INVESTMENT",
    "WF ASIAN",
)


def classify_institutional_client(client_name):
    """Classify only explicit institutional names; ambiguous clients stay excluded."""
    name = re.sub(r"\s+", " ", str(client_name or "").upper()).strip()
    if not name:
        return None
    if any(term in name for term in _DII_CLIENT_TERMS):
        return "DII"
    if any(term in name for term in _FII_CLIENT_TERMS):
        return "FII/FPI"
    return None


def _institutional_deal_leaders(frame, category, side, limit=6):
    selected = frame[(frame["institution"] == category) & (frame["side"] == side)]
    if selected.empty:
        return []
    leaders = []
    for symbol, group in selected.groupby("symbol"):
        security_names = [name for name in group["security_name"].astype(str) if name.strip()]
        leaders.append(
            {
                "symbol": symbol,
                "name": security_names[0] if security_names else symbol,
                "value_crore": round(float(group["value"].sum()) / 10_000_000, 2),
                "quantity": int(group["quantity"].sum()),
                "deals": int(len(group)),
            }
        )
    return sorted(leaders, key=lambda row: row["value_crore"], reverse=True)[:limit]


def build_institutional_deal_trends(deal_data):
    frames = []
    for kind in ("bulk", "block"):
        frame = deal_data.get(kind) if isinstance(deal_data, dict) else None
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        usable = frame.copy()
        usable["deal_type"] = kind
        frames.append(usable)
    if not frames:
        return {"latest_date": None, "classified_deals": 0, "periods": {}}
    combined = pd.concat(frames, ignore_index=True)
    combined["institution"] = combined["client_name"].map(classify_institutional_client)
    combined = combined[combined["institution"].notna()].copy()
    if combined.empty:
        return {"latest_date": None, "classified_deals": 0, "periods": {}}
    combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    combined = combined.dropna(subset=["date"])
    end_date = combined["date"].max().normalize()
    definitions = (("latest", "Latest session", 0), ("1m", "Last 1 month", 30), ("6m", "Last 6 months", 183))
    periods = {}
    for key, label, days in definitions:
        period_frame = (
            combined[combined["date"].eq(end_date)]
            if days == 0
            else combined[combined["date"].ge(end_date - pd.Timedelta(days=days))]
        )
        categories = {}
        for category in ("FII/FPI", "DII"):
            categories[category] = {
                "buy": _institutional_deal_leaders(period_frame, category, "BUY"),
                "sell": _institutional_deal_leaders(period_frame, category, "SELL"),
            }
        periods[key] = {"label": label, "categories": categories}
    return {
        "latest_date": end_date.date().isoformat(),
        "classified_deals": int(len(combined)),
        "periods": periods,
    }


def build_fii_dii_flow_insights(history, deal_data=None):
    history = merge_fii_dii_history(history)
    if not history:
        return {
            "status": "warming",
            "history": [],
            "periods": [],
            "institutional_deals": build_institutional_deal_trends(deal_data or {}),
        }
    end_date = date.fromisoformat(history[-1]["date"])
    start_date = date.fromisoformat(history[0]["date"])
    recent = history[-7:]
    largest = max(
        [abs(float(row.get(key) or 0)) for row in recent for key in ("fii", "dii")] or [1]
    ) or 1
    chart_rows = [
        {
            **row,
            "date_label": date.fromisoformat(row["date"]).strftime("%d %b"),
            "fii_width": round(abs(float(row.get("fii") or 0)) / largest * 100, 1),
            "dii_width": round(abs(float(row.get("dii") or 0)) / largest * 100, 1),
        }
        for row in recent
    ]
    period_definitions = (("1m", "1 month", 30), ("6m", "6 months", 183), ("1y", "1 year", 365), ("2y", "2 years", 730))
    periods = []
    for key, label, days in period_definitions:
        cutoff = end_date - timedelta(days=days)
        selected = [row for row in history if date.fromisoformat(row["date"]) >= cutoff]
        complete = start_date <= cutoff + timedelta(days=7)
        periods.append(
            {
                "key": key,
                "label": label,
                "fii": round(sum(float(row.get("fii") or 0) for row in selected), 2),
                "dii": round(sum(float(row.get("dii") or 0) for row in selected), 2),
                "sessions": len(selected),
                "complete": complete,
                "coverage": f"{start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}",
            }
        )
    return {
        "status": "ready",
        "as_of": end_date.isoformat(),
        "history": chart_rows,
        "periods": periods,
        "institutional_deals": build_institutional_deal_trends(deal_data or {}),
        "source_note": (
            "Aggregate flows use NSE daily cash-market values with a cached historical archive. "
            "Stock leaders use disclosed NSE bulk/block transactions and explicit institution-name matching."
        ),
    }


def build_breadth_divergence(rows, nifty_rows):
    priced = [row for row in rows if row.get("percent") is not None]
    nifty_priced = [row for row in nifty_rows if row.get("percent") is not None]
    if not priced or not nifty_priced:
        return {"active": False, "label": "Breadth signal unavailable", "tone": "neutral"}
    advance_ratio = sum(row["percent"] > 0 for row in priced) / len(priced) * 100
    broad_average = sum(row["percent"] for row in priced) / len(priced)
    nifty_average = sum(row["percent"] for row in nifty_priced) / len(nifty_priced)
    if nifty_average > 0 and advance_ratio < 50:
        return {
            "active": True,
            "label": "Narrow rally",
            "detail": f"NIFTY stocks average {nifty_average:+.2f}% while only {advance_ratio:.1f}% of NIFTY 500 stocks advance.",
            "tone": "warning",
        }
    if nifty_average < 0 and advance_ratio > 50:
        return {
            "active": True,
            "label": "Positive underlying breadth",
            "detail": f"NIFTY stocks average {nifty_average:+.2f}% while {advance_ratio:.1f}% of NIFTY 500 stocks advance.",
            "tone": "positive",
        }
    return {
        "active": False,
        "label": "Breadth aligned",
        "detail": f"Broad participation is {advance_ratio:.1f}% with an average move of {broad_average:+.2f}%.",
        "tone": "neutral",
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


def build_dashboard_insights(rows, nifty_rows=None):
    priced = [row for row in rows if row.get("percent") is not None]
    if not priced:
        return {
            "momentum": [],
            "risk": [],
            "leadership": [],
            "participation": [],
        }
    advancers = [row for row in priced if row["percent"] > 0]
    decliners = [row for row in priced if row["percent"] < 0]
    uptrends = [row for row in priced if row.get("signal") == "Uptrend"]
    downtrends = [row for row in priced if row.get("signal") == "Downtrend"]
    accumulation = [row for row in priced if row.get("accumulation_score", 0) >= 2]
    volume_surges = [row for row in priced if row.get("volume_change") is not None and row["volume_change"] > 25]
    near_high = [
        row for row in priced
        if row.get("price") is not None and row.get("high52") and row["price"] >= row["high52"] * 0.95
    ]
    near_low = [
        row for row in priced
        if row.get("price") is not None and row.get("low52") and row["price"] <= row["low52"] * 1.08
    ]
    top_sector = None
    sectors = build_sector_performance(rows)
    if sectors:
        top_sector = sectors[0]
    nifty_priced = [row for row in (nifty_rows or []) if row.get("percent") is not None]
    nifty_avg = sum(row["percent"] for row in nifty_priced) / len(nifty_priced) if nifty_priced else None
    broad_avg = sum(row["percent"] for row in priced) / len(priced)
    strongest = max(priced, key=lambda row: row["percent"])
    weakest = min(priced, key=lambda row: row["percent"])
    return {
        "momentum": [
            {"label": "Uptrend Stocks", "value": len(uptrends), "tone": "good"},
            {"label": "Accumulation Setups", "value": len(accumulation), "tone": "accent"},
            {"label": "Volume Surge", "value": len(volume_surges), "tone": "warm"},
        ],
        "risk": [
            {"label": "Downtrends", "value": len(downtrends), "tone": "bad"},
            {"label": "Near 52W Low", "value": len(near_low), "tone": "bad"},
            {"label": "Decliners", "value": len(decliners), "tone": "bad"},
        ],
        "leadership": [
            {
                "label": "Strongest Stock",
                "value": strongest["display_symbol"],
                "detail": f"{strongest['percent']:+.2f}%",
                "tone": "good",
            },
            {
                "label": "Weakest Stock",
                "value": weakest["display_symbol"],
                "detail": f"{weakest['percent']:+.2f}%",
                "tone": "bad",
            },
            {
                "label": "Top Sector",
                "value": top_sector["name"] if top_sector else "-",
                "detail": f"{top_sector['percent']:+.2f}%" if top_sector else "-",
                "tone": "accent",
            },
        ],
        "participation": [
            {"label": "Advancers", "value": len(advancers), "detail": f"{len(advancers) / len(priced) * 100:.1f}%", "tone": "good"},
            {"label": "Near 52W High", "value": len(near_high), "tone": "good"},
            {"label": "NIFTY vs Broad", "value": f"{(nifty_avg - broad_avg):+.2f}%" if nifty_avg is not None else "-", "tone": "accent"},
        ],
    }


def build_dashboard_notes(rows, nifty_rows=None):
    priced = [row for row in rows if row.get("percent") is not None]
    if not priced:
        return ["Live market rows are still warming up. Cached panels will populate automatically."]
    advancers = [row for row in priced if row["percent"] > 0]
    decliners = [row for row in priced if row["percent"] < 0]
    uptrends = [row for row in priced if row.get("signal") == "Uptrend"]
    accumulation = [row for row in priced if row.get("accumulation_score", 0) >= 2]
    volume_surges = [row for row in priced if row.get("volume_change") is not None and row["volume_change"] > 25]
    sectors = build_sector_performance(rows)
    top_sector = sectors[0] if sectors else None
    weak_sector = sectors[-1] if sectors else None
    strongest = max(priced, key=lambda row: row["percent"])
    weakest = min(priced, key=lambda row: row["percent"])
    nifty_priced = [row for row in (nifty_rows or []) if row.get("percent") is not None]
    broad_avg = sum(row["percent"] for row in priced) / len(priced)
    nifty_avg = sum(row["percent"] for row in nifty_priced) / len(nifty_priced) if nifty_priced else None
    participation = len(advancers) / len(priced) * 100
    notes = [
        (
            f"Participation is {participation:.1f}% with {len(advancers)} advancers and "
            f"{len(decliners)} decliners across the tracked universe."
        ),
        (
            f"{len(uptrends)} stocks are in uptrend and {len(accumulation)} show 2/3 or 3/3 "
            "accumulation signals, useful for follow-through watchlists."
        ),
        (
            f"Leadership: {strongest['display_symbol']} is strongest at {strongest['percent']:+.2f}%, "
            f"while {weakest['display_symbol']} is weakest at {weakest['percent']:+.2f}%."
        ),
    ]
    if top_sector:
        notes.append(
            f"Sector tone: {top_sector['name']} leads at {top_sector['percent']:+.2f}% average move; "
            f"{weak_sector['name']} is the softest at {weak_sector['percent']:+.2f}%."
        )
    if volume_surges:
        leader = max(volume_surges, key=lambda row: row.get("volume_change") or 0)
        notes.append(
            f"Volume watch: {len(volume_surges)} stocks show volume expansion above 25%; "
            f"{leader['display_symbol']} has the strongest volume jump at {leader['volume_change']:+.1f}%."
        )
    if nifty_avg is not None:
        notes.append(
            f"NIFTY 50 average move is {nifty_avg:+.2f}% versus broad universe average {broad_avg:+.2f}%."
        )
    return notes


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


HEADLINE_MATCH_STOPWORDS = {
    "limited", "india", "indian", "industries", "industry", "company",
    "corporation", "enterprise", "enterprises", "services", "finance",
    "financial", "holdings", "energy", "power", "bank", "group",
}


def _headline_stock_score(title, row):
    normalized_title = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    if not normalized_title:
        return 0
    title_words = set(normalized_title.split())
    symbol = str(row.get("display_symbol") or "").lower()
    score = 0
    if len(symbol) >= 3 and symbol in title_words:
        score += 12
    name_words = [
        word
        for word in re.sub(r"[^a-z0-9]+", " ", str(row.get("name") or "").lower()).split()
        if len(word) >= 4 and word not in HEADLINE_MATCH_STOPWORDS
    ]
    unique_words = list(dict.fromkeys(name_words))
    matched = [word for word in unique_words if word in title_words]
    if len(unique_words) >= 2 and len(matched) >= 2:
        score += 10 + min(len(matched), 3)
    elif matched and len(matched[0]) >= 6:
        score += 6
    return score


def enrich_headlines_with_stocks(headlines, rows):
    enriched = []
    context = defaultdict(list)
    for headline_index, headline in enumerate(headlines):
        matches = []
        for row in rows:
            score = _headline_stock_score(headline.get("title"), row)
            if score < 6:
                continue
            matches.append(
                {
                    "score": score,
                    "symbol": row["display_symbol"],
                    "name": row.get("name") or row["display_symbol"],
                    "sector": row.get("sector") or "",
                    "price": row.get("price"),
                    "percent": row.get("percent"),
                    "five_day_change": row.get("five_day_change"),
                    "month_change": row.get("month_change"),
                    "relative_volume": row.get("relative_volume"),
                    "sector_relative_change": row.get("sector_relative_change"),
                }
            )
        matches.sort(key=lambda item: (item["score"], abs(item.get("percent") or 0)), reverse=True)
        matches = matches[:4]
        item = {**headline, "stocks": matches, "headline_index": headline_index}
        enriched.append(item)
        for match in matches:
            context[match["symbol"]].append(
                {
                    "title": headline.get("title") or "",
                    "url": headline.get("url") or "",
                    "source": headline.get("source") or "",
                    "time": headline.get("time") or "",
                    "headline_index": headline_index,
                }
            )
    return enriched, {symbol: items[:3] for symbol, items in context.items()}


def build_stock_event_context(earnings, events):
    context = {}
    for item in earnings:
        context[item["symbol"]] = {
            "type": "Earnings",
            "date": item.get("date_label"),
            "title": f"{item['symbol']} earnings release",
        }
    for event in events:
        match = re.match(r"([A-Z0-9&.-]+)\s", event.get("title") or "")
        if not match or match.group(1) in context:
            continue
        context[match.group(1)] = {
            "type": event.get("type"),
            "date": event.get("date_label"),
            "title": event.get("title"),
        }
    return context


def _format_news_timestamp(value):
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone(IST).strftime("%b %d, %I:%M %p")
    except (TypeError, ValueError, OverflowError):
        return ""


def _parse_stock_news_rss(content, limit=6):
    root = ET.fromstring(content)
    news = []
    for item in root.findall(".//item"):
        title = _strip_html(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        source = _strip_html(item.findtext("source") or "Yahoo Finance")
        published = _format_news_timestamp(item.findtext("pubDate"))
        if title and link.startswith(("http://", "https://")):
            news.append(
                {
                    "title": title,
                    "url": link,
                    "source": source or "Yahoo Finance",
                    "published": published,
                }
            )
        if len(news) >= limit:
            break
    return news


def _fallback_stock_news_from_market_headlines(symbol, company_name=""):
    symbol = _normalize_symbol(symbol)
    ignored = {"limited", "company", "industries", "india", "indian", "national", "corporation"}
    terms = set()
    for part in re.split(r"[^A-Za-z0-9]+", company_name or ""):
        if len(part) >= 5 and part.lower() not in ignored:
            terms.add(part.lower())
    headlines, _ = get_cached_swr("news", NEWS_CACHE_TTL, fetch_headlines, cold_async=True)
    matches = []
    for item in headlines or []:
        title = (item.get("title") or "").lower()
        symbol_match = bool(re.search(rf"(?<![a-z0-9]){re.escape(symbol.lower())}(?![a-z0-9])", title))
        if symbol_match or any(term in title for term in terms):
            matches.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", "Market Headlines"),
                    "published": item.get("time", ""),
                }
            )
        if len(matches) >= 6:
            break
    return matches


def _filter_company_news(items, symbol, company_name, limit=6):
    clean_symbol = _normalize_symbol(symbol).lower()
    ignored = {"limited", "company", "industries", "india", "indian", "national", "corporation"}
    company_terms = {
        part.lower()
        for part in re.split(r"[^A-Za-z0-9]+", company_name or "")
        if len(part) >= 5 and part.lower() not in ignored
    }
    matches = []
    for item in items:
        title = (item.get("title") or "").lower()
        if clean_symbol not in title and not any(term in title for term in company_terms):
            continue
        matches.append(item)
        if len(matches) >= limit:
            break
    return matches


def fetch_stock_news(symbol, company_name=""):
    clean_symbol = _normalize_symbol(symbol)
    if not clean_symbol:
        return []

    def loader():
        rss_symbol = clean_symbol if clean_symbol.endswith(".NS") else f"{clean_symbol}.NS"
        collected = []
        seen = set()

        def append_news(items):
            for item in items:
                identity = (
                    (item.get("url") or "").lower(),
                    (item.get("title") or "").lower(),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                collected.append(item)
                if len(collected) >= 6:
                    break

        try:
            url = (
                "https://feeds.finance.yahoo.com/rss/2.0/headline?"
                f"s={quote(rss_symbol)}&region=IN&lang=en-IN"
            )
            response = requests.get(
                url,
                timeout=6,
                headers={"User-Agent": "Mozilla/5.0 SimplyTrading/1.0"},
            )
            response.raise_for_status()
            yahoo_items = _parse_stock_news_rss(response.content, limit=24)
            append_news(_filter_company_news(yahoo_items, clean_symbol, company_name, limit=6))
        except (requests.RequestException, ET.ParseError, ValueError, TypeError):
            pass
        try:
            if len(collected) >= 6:
                return collected
            search_name = re.sub(
                r"\b(?:limited|ltd\.?|company|corporation)\b",
                "",
                company_name or clean_symbol,
                flags=re.IGNORECASE,
            )
            search_name = re.sub(r"\s+", " ", search_name).strip()
            query_text = f'"{search_name}" stock OR shares'
            response = requests.get(
                "https://news.google.com/rss/search",
                params={"q": query_text, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
                timeout=6,
                headers={"User-Agent": "Mozilla/5.0 SimplyTrading/1.0"},
            )
            response.raise_for_status()
            google_items = _parse_stock_news_rss(response.content, limit=24)
            append_news(_filter_company_news(google_items, clean_symbol, company_name, limit=6))
        except (requests.RequestException, ET.ParseError, ValueError, TypeError):
            pass
        if collected:
            return collected
        return _fallback_stock_news_from_market_headlines(clean_symbol, company_name)

    data, _ = get_cached(
        f"stock_news:v6:{clean_symbol}",
        STOCK_DETAIL_CACHE_TTL,
        loader,
    )
    return data or _fallback_stock_news_from_market_headlines(clean_symbol, company_name)


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


def build_stock_page_context(symbol):
    clean_symbol = _normalize_symbol(symbol)
    market_context = load_cached_market_context()
    market = market_context["market"]
    rows = market.get("rows") or []
    found_row = next(
        (
            item for item in rows
            if _normalize_symbol(item.get("display_symbol") or item.get("symbol")) == clean_symbol
        ),
        None,
    ) or _cached_dashboard_row_for_symbol(clean_symbol)
    popup_data = get_latest_stock_popup_details_data()
    raw_detail = (popup_data.get("details") or {}).get(clean_symbol, {})
    detail = _fallback_stock_detail(clean_symbol, raw_detail)
    if found_row:
        detail = {
            **detail,
            "delivery_percent": detail.get("delivery_percent") or found_row.get("delivery_percent"),
            "market_cap": detail.get("market_cap") or found_row.get("market_cap") or found_row.get("free_float_market_cap"),
        }
    row = {
        "display_symbol": clean_symbol,
        "name": detail.get("name") or clean_symbol,
        "sector": detail.get("sector") or "Unclassified",
        "price": detail.get("price"),
        "percent": None,
        "change": None,
        "volume": None,
        "traded_value": None,
        "relative_volume": None,
        "delivery_percent": detail.get("delivery_percent"),
        "day_open": None,
        "day_high": None,
        "day_low": None,
        "high52_distance": None,
        "low52_distance": None,
        "five_day_change": None,
        "month_change": None,
        "year_change": None,
        "signal": None,
        "accumulation_score": 0,
        "sector_rank": None,
        "sector_stock_count": None,
        "sector_relative_change": None,
        "chart_series": [],
        **(found_row or {}),
    }
    sector = row.get("sector") or detail.get("sector") or "Unclassified"
    peer_rows = [
        item for item in rows
        if item.get("sector") == sector
        and _normalize_symbol(item.get("display_symbol")) != clean_symbol
        and item.get("price") is not None
    ]
    peer_rows.sort(
        key=lambda item: (
            item.get("free_float_market_cap") or item.get("market_cap") or 0,
            item.get("traded_value") or 0,
        ),
        reverse=True,
    )
    peer_details = popup_data.get("details") or {}
    peers = []
    for peer in peer_rows[:8]:
        peer_symbol = peer["display_symbol"]
        peer_detail = peer_details.get(peer_symbol, {})
        peers.append(
            {
                "display_symbol": peer_symbol,
                "name": peer.get("name") or peer_symbol,
                "price": peer.get("price"),
                "percent": peer.get("percent"),
                "month_change": peer.get("month_change"),
                "year_change": peer.get("year_change"),
                "market_cap": peer_detail.get("market_cap") or peer.get("market_cap") or peer.get("free_float_market_cap"),
                "pe_ratio": peer_detail.get("pe_ratio"),
                "roe": peer_detail.get("roe"),
                "signal": peer.get("signal"),
            }
        )
    benchmark = next(
        (item for item in market.get("indices", []) if item.get("name") == "NIFTY 50"),
        {},
    )
    sector_summary = next(
        (item for item in market.get("sectors", []) if item.get("name") == sector),
        {},
    )
    growth = detail.get("growth") or {}
    performance = {
        "day": (row or {}).get("percent"),
        "five_day": (row or {}).get("five_day_change"),
        "month": growth.get("1m") if growth.get("1m") is not None else (row or {}).get("month_change"),
        "three_month": growth.get("3m"),
        "year": growth.get("1y") if growth.get("1y") is not None else (row or {}).get("year_change"),
        "five_year": growth.get("5y"),
    }
    return {
        "symbol": clean_symbol,
        "row": row,
        "detail": detail,
        "performance": performance,
        "peers": peers,
        "benchmark": benchmark,
        "sector_summary": sector_summary,
        "market_average": (market.get("market_stats") or {}).get("average_change"),
        "market_timestamp": market.get("data_timestamp") or market.get("refreshed_at"),
        "stale": bool(market_context.get("market_stale") or not raw_detail),
    }


def build_rules_stock_analysis(context, fallback_reason=None):
    row = context.get("row") or {}
    detail = context.get("detail") or {}
    performance = context.get("performance") or {}
    peers = context.get("peers") or []
    strengths = []
    risks = []
    score = 0
    if row.get("signal") == "Uptrend":
        score += 2
        strengths.append("Price is in an established uptrend on the cached technical snapshot.")
    elif row.get("signal") == "Downtrend":
        score -= 2
        risks.append("The cached technical snapshot classifies the stock as a downtrend.")
    accumulation = int(row.get("accumulation_score") or 0)
    if accumulation >= 2:
        score += 2
        strengths.append(f"{accumulation}/3 accumulation signals are active.")
    relative = row.get("sector_relative_change")
    if relative is not None:
        if relative > 0:
            score += 1
            strengths.append(f"The stock is outperforming its sector by {relative:+.2f} percentage points today.")
        elif relative < 0:
            score -= 1
            risks.append(f"The stock is lagging its sector by {relative:+.2f} percentage points today.")
    year_growth = performance.get("year")
    if year_growth is not None and year_growth > 10:
        score += 1
        strengths.append(f"One-year price performance is {year_growth:+.1f}%.")
    elif year_growth is not None and year_growth < -10:
        score -= 1
        risks.append(f"One-year price performance is {year_growth:+.1f}%.")
    roe = detail.get("roe")
    if roe is not None and roe >= 15:
        strengths.append(f"Reported return on equity is {roe:.1f}%.")
    debt_equity = detail.get("debt_equity")
    if debt_equity is not None and debt_equity > 1.5:
        score -= 1
        risks.append(f"Debt/equity is elevated at {debt_equity:.2f}x.")
    if not strengths:
        strengths.append("No strong positive confirmation is present in the current cached evidence.")
    if not risks:
        risks.append("Market, earnings and valuation conditions can change after the cached timestamp.")
    peer_pes = [peer["pe_ratio"] for peer in peers if peer.get("pe_ratio") is not None]
    peer_pe = median(peer_pes) if peer_pes else None
    stock_pe = detail.get("pe_ratio")
    valuation = "Valuation comparison is unavailable because current peer P/E coverage is incomplete."
    if stock_pe is not None and peer_pe is not None:
        valuation = (
            f"P/E is {stock_pe:.1f}x versus a cached peer median of {peer_pe:.1f}x, "
            f"a {(stock_pe / peer_pe - 1) * 100:+.1f}% premium/discount."
        )
    verdict = "Constructive" if score >= 3 else "Cautious" if score <= -2 else "Neutral"
    return {
        "symbol": context.get("symbol"),
        "verdict": verdict,
        "executive_summary": (
            f"{context.get('symbol')} has a {verdict.lower()} evidence mix based on cached price trend, "
            "relative performance, accumulation, fundamentals and peer data."
        ),
        "technical_view": (
            f"Signal: {row.get('signal') or 'Unavailable'}; accumulation {accumulation}/3; "
            f"5-day move {performance.get('five_day'):+.2f}%."
            if performance.get("five_day") is not None
            else f"Signal: {row.get('signal') or 'Unavailable'}; accumulation {accumulation}/3."
        ),
        "valuation_view": valuation,
        "peer_context": (
            f"Compared with {len(peers)} cached {row.get('sector') or detail.get('sector') or 'sector'} peers. "
            f"Current sector rank is {row.get('sector_rank') or '-'} of {row.get('sector_stock_count') or '-'} by daily move."
        ),
        "strengths": strengths[:5],
        "risks": risks[:5],
        "watch_items": [
            "Confirm the latest exchange price and volume before acting.",
            "Watch the next earnings or corporate event and any material company announcement.",
            "Reassess if the technical signal or sector-relative trend changes.",
        ],
        "generated_by": "rules",
        "fallback_reason": fallback_reason,
        "generated_at": datetime.now(IST).strftime("%d %b %Y %I:%M %p IST"),
        "disclaimer": "Educational analysis only. This is not investment advice or a recommendation to buy or sell.",
    }


def generate_stock_ai_analysis(context):
    baseline = build_rules_stock_analysis(context)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return build_rules_stock_analysis(context, "GEMINI_API_KEY is not configured; showing rules-based analysis.")
    model = os.getenv("GEMINI_STOCK_MODEL", os.getenv("GEMINI_FAST_MODEL", "gemini-2.5-flash-lite"))
    evidence = {
        "symbol": context.get("symbol"),
        "market_timestamp": context.get("market_timestamp"),
        "row": context.get("row"),
        "fundamentals": context.get("detail"),
        "performance": context.get("performance"),
        "benchmark": context.get("benchmark"),
        "sector": context.get("sector_summary"),
        "peers": context.get("peers"),
        "rules_baseline": baseline,
    }
    prompt = (
        "Act as a careful Indian equity research analyst. Use only the supplied cached evidence. "
        "Return JSON with keys verdict, executive_summary, technical_view, valuation_view, peer_context, "
        "strengths, risks and watch_items. strengths, risks and watch_items must be arrays of 3-5 concise strings. "
        "Use a verdict of Constructive, Neutral or Cautious. Explicitly identify missing/stale evidence, do not "
        "invent news or financial values, and do not give personalized investment advice.\n\n"
        + json.dumps(_json_safe(evidence), ensure_ascii=True)
    )
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2, "maxOutputTokens": 4096},
            },
            timeout=int(os.getenv("GEMINI_TIMEOUT_SECONDS", "90")),
        )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        generated = json.loads(text)
        verdict = generated.get("verdict")
        if verdict not in {"Constructive", "Neutral", "Cautious"}:
            raise ValueError("Invalid verdict")
        for key in ("strengths", "risks", "watch_items"):
            if not isinstance(generated.get(key), list):
                raise ValueError(f"Missing {key}")
        return {
            **baseline,
            **generated,
            "generated_by": "gemini",
            "fallback_reason": None,
            "generated_at": datetime.now(IST).strftime("%d %b %Y %I:%M %p IST"),
        }
    except (requests.RequestException, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return build_rules_stock_analysis(context, f"AI provider unavailable ({type(error).__name__}); showing rules-based analysis.")


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/api/stocks/<symbol>")
def stock_detail_api(symbol):
    response = jsonify(get_stock_detail(symbol))
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=86400"
    response.add_etag()
    return response.make_conditional(request)


@app.route("/api/stock-details")
def stock_details_snapshot_api():
    data = get_latest_stock_popup_details_data()
    response = jsonify(
        {
            "status": "ready" if data["details"] else "warming",
            **data,
        }
    )
    response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=86400"
    response.add_etag()
    return response.make_conditional(request)


@app.route("/api/fii-dii-insights")
def fii_dii_insights_api():
    current, current_stale = get_cached_swr(
        "fii_dii",
        MARKET_CACHE_TTL,
        fetch_fii_dii_activity,
    )
    stored_history = record_fii_dii_history(current or [])
    archive, archive_stale = get_cached_swr(
        "fii_dii_history_archive",
        FII_DII_HISTORY_CACHE_TTL,
        fetch_fii_dii_history_archive,
    )
    deal_data, deal_stale = get_bulk_block_short_data()
    history = merge_fii_dii_history(archive or [], stored_history)
    payload = build_fii_dii_flow_insights(history, deal_data or {})
    payload.update(
        {
            "stale": bool(current_stale or archive_stale or deal_stale),
            "aggregate_source": "NSE cash-market activity; historical values cached from a public NSE-data archive",
            "deal_source": (deal_data or {}).get("source", "unavailable"),
        }
    )
    response = jsonify(_json_safe(payload))
    response.headers["Cache-Control"] = "no-store"
    response.add_etag()
    return response.make_conditional(request)


@app.post("/api/stocks/<symbol>/analysis")
def stock_analysis_api(symbol):
    context = build_stock_page_context(symbol)
    clean_symbol = context["symbol"]
    stamp = str(context.get("market_timestamp") or datetime.now(IST).date())
    cache_stamp = hashlib.sha256(stamp.encode("utf-8", errors="ignore")).hexdigest()[:12]
    analysis, _ = get_cached(
        f"stock_ai_analysis:{clean_symbol}:{cache_stamp}",
        STOCK_AI_CACHE_TTL,
        lambda: generate_stock_ai_analysis(context),
    )
    response = jsonify(analysis)
    response.headers["Cache-Control"] = "private, max-age=300"
    return response


@app.route("/api/insights-data")
def insights_data_api():
    snapshot = _json_safe(get_cached_insights_snapshot())
    if not snapshot:
        ensure_insights_snapshot_refresh_async()
        return jsonify(
            {
                "status": "warming",
                "snapshot": None,
                "refreshed_at": None,
                "stale": False,
                "error": None,
            }
        )
    if insights_snapshot_needs_nse_refresh(snapshot):
        ensure_insights_snapshot_refresh_async()
    return jsonify(
        {
            "status": snapshot.get("status", "ready"),
            "snapshot": snapshot,
            "refreshed_at": snapshot.get("refreshed_at") or snapshot.get("created_at"),
            "stale": bool(snapshot.get("stale")),
            "error": snapshot.get("error"),
        }
    )


def empty_market_dashboard():
    return {
        "indices": [],
        "market_gauges": [],
        "rows": [],
        "nifty50_rows": [],
        "breadth": [],
        "gainers": [],
        "losers": [],
        "active": [],
        "turnover": [],
        "volume_leaders": [],
        "unusual_volume": [],
        "delivery_leaders": [],
        "breakouts": [],
        "contribution_leaders": [],
        "contribution_drags": [],
        "sector_rotation": [],
        "breadth_history": [],
        "signals": [],
        "sectors": [],
        "heatmap": [],
        "hover_data": {},
        "impact_available": False,
        "market_stats": build_market_stats([]),
        "internals": build_market_internals([]),
        "insights": build_dashboard_insights([]),
        "dashboard_notes": build_dashboard_notes([]),
        "breadth_divergence": {
            "active": False,
            "label": "Breadth signal unavailable",
            "tone": "neutral",
        },
        "data_timestamp": None,
        "refreshed_at": None,
    }


def market_dashboard_cache_key(stocks, broad_stocks):
    universe_key = ",".join(stock["symbol"] for stock in stocks)
    broad_universe_key = ",".join(stock["symbol"] for stock in broad_stocks)
    return f"market:{universe_key}|broad:{broad_universe_key}", universe_key


def refresh_market_dashboard_cache():
    stocks, _ = get_stock_universe()
    broad_stocks, _ = get_nifty500_universe()
    key, _ = market_dashboard_cache_key(stocks, broad_stocks)
    data = load_market_dashboard(stocks, broad_stocks, allow_impact_fallback=True)
    with _CACHE_LOCK:
        _CACHE[key] = {
            "data": data,
            "expires": time_module.time() + MARKET_CACHE_TTL,
        }
    _write_persistent_cache(key, data, MARKET_CACHE_TTL)
    return data


def _market_refresh_loop():
    time_module.sleep(max(0, STARTUP_MARKET_REFRESH_DELAY))
    while True:
        try:
            refresh_market_dashboard_cache()
        except Exception as exc:
            print(f"Market dashboard scheduled refresh failed: {exc}", file=sys.stderr)
        time_module.sleep(max(60, MARKET_CACHE_TTL))


def start_market_refresh_scheduler():
    global _MARKET_REFRESH_STARTED
    if _MARKET_REFRESH_STARTED or os.getenv("DISABLE_MARKET_REFRESH") == "1":
        return
    _MARKET_REFRESH_STARTED = True
    threading.Thread(
        target=_market_refresh_loop,
        daemon=True,
        name="market-dashboard-refresh",
    ).start()


def load_cached_market_context():
    stocks, constituents_stale = get_stock_universe()
    broad_stocks, broad_constituents_stale = get_nifty500_universe()
    market_key, universe_key = market_dashboard_cache_key(stocks, broad_stocks)
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
    market_refresh_error = None
    if should_force_market_refresh(market, market_stale):
        try:
            market = refresh_market_dashboard_cache()
            market_stale = False
        except Exception as exc:
            market_refresh_error = str(exc)
            print(f"Forced market dashboard refresh failed: {exc}", file=sys.stderr)
    return {
        "stocks": stocks,
        "broad_stocks": broad_stocks,
        "universe_key": universe_key,
        "market": market or empty_market_dashboard(),
        "market_stale": market_stale,
        "market_refresh_error": market_refresh_error,
        "constituents_stale": constituents_stale or broad_constituents_stale,
    }


@app.route("/blog/")
def blog_redirect():
    return redirect("/articles", code=302)


@app.route("/stock/<symbol>")
def stock_analysis_page(symbol):
    context = _json_safe(build_stock_page_context(symbol))
    return render_template(
        "stock_analysis.html",
        **common_context("stock", True),
        stock=context,
        stock_json=_json_safe(context),
        format_market_cap=format_market_cap,
        format_volume=format_volume,
    )


@app.route("/articles")
def articles():
    selected_category = request.args.get("category", "").strip()
    query = request.args.get("q", "").strip()
    search = query.lower()
    filtered_articles = [
        post
        for post in ARTICLE_POSTS
        if (not selected_category or selected_category in post["category_slugs"])
        and (not search or search in post["search_text"])
    ]
    featured = filtered_articles[0] if filtered_articles else None
    recent_articles = filtered_articles[1:6] if featured else []
    return render_template(
        "articles.html",
        **common_context("articles", False),
        articles=filtered_articles,
        featured_article=featured,
        recent_articles=recent_articles,
        categories=[
            {"name": category, "slug": article_slug(category)}
            for category in ARTICLE_CATEGORIES
        ],
        selected_category=selected_category,
        search_query=query,
    )


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
    market_context = load_cached_market_context()
    stocks = market_context["stocks"]
    broad_stocks = market_context["broad_stocks"]
    universe_key = market_context["universe_key"]
    market = market_context["market"]
    market_stale = market_context["market_stale"]
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
    headlines = headlines or []
    fii_dii = fii_dii or []
    calendar = build_calendar_panels(calendar_entries or [])
    earnings = enrich_earnings(calendar["earnings"], market["rows"])
    enriched_headlines, headline_context = enrich_headlines_with_stocks(
        headlines,
        market["rows"],
    )
    stock_event_context = build_stock_event_context(earnings, calendar["events"])
    popup_detail_data = get_latest_stock_popup_details_data()
    all_popup_details = popup_detail_data.get("details") or {}
    priority_symbols = popup_priority_symbols(market, earnings, enriched_headlines)
    initial_popup_details = {
        symbol: all_popup_details[symbol]
        for symbol in priority_symbols
        if symbol in all_popup_details
    }
    popup_details_stale = not bool(all_popup_details)
    market = {
        **market,
        "hover_data": build_stock_hover_data_with_details(
            market["rows"],
            initial_popup_details,
            headline_context,
            stock_event_context,
        ),
    }
    fii_dii_history = record_fii_dii_history(fii_dii)
    fii_dii_recent = fii_dii_history[-5:]
    fii_dii_summary = {
        "sessions": len(fii_dii_recent),
        "fii": sum(item.get("fii") or 0 for item in fii_dii_recent),
        "dii": sum(item.get("dii") or 0 for item in fii_dii_recent),
    }
    leading_index = next((card for card in market["indices"] if card.get("available")), None)
    brief = (
        f"Indian markets: {leading_index['name']} at {leading_index['price']:,.2f}, "
        f"{leading_index['percent']:+.2f}% in the latest session."
        if leading_index
        else "Indian market data is temporarily unavailable. Cached panels will return automatically."
    )
    response = make_response(render_template(
        "dashboard.html",
        **common_context("home", True),
        market=market,
        headlines=enriched_headlines,
        market_stale=market_stale,
        popup_details_stale=popup_details_stale,
        news_stale=news_stale,
        fii_dii=fii_dii,
        fii_dii_history=fii_dii_history,
        fii_dii_summary=fii_dii_summary,
        fii_dii_stale=fii_dii_stale,
        calendar_stale=calendar_stale,
        constituents_stale=market_context["constituents_stale"],
        broad_universe_count=len(broad_stocks),
        nearby_events=calendar["events"],
        earnings=earnings,
        market_brief=brief,
        format_market_cap=format_market_cap,
        format_volume=format_volume,
        format_crore_value=format_crore_value,
    ))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/insights")
def insights():
    snapshot = _json_safe(get_cached_insights_snapshot())
    if not snapshot:
        ensure_insights_snapshot_refresh_async()
    elif insights_snapshot_needs_nse_refresh(snapshot):
        ensure_insights_snapshot_refresh_async()
    insight_data = (snapshot.get("insights") if snapshot else None) or empty_insights_data()
    market = {"hover_data": snapshot.get("hover_data", {}) if snapshot else {}}
    snapshot_status = snapshot.get("status", "ready") if snapshot else "warming"
    response = make_response(render_template(
        "insights.html",
        **common_context("insights", False),
        market=market,
        insights=insight_data,
        snapshot_status=snapshot_status,
        insights_snapshot_created_at=snapshot.get("created_at") if snapshot else None,
        insights_snapshot_error=snapshot.get("error") if snapshot else None,
        market_stale=bool(snapshot.get("market_stale")) if snapshot else False,
        popup_details_stale=False,
        deal_data_stale=bool(snapshot.get("deal_data_stale") or snapshot.get("stale")) if snapshot else False,
        constituents_stale=bool(snapshot.get("constituents_stale")) if snapshot else False,
        format_market_cap=format_market_cap,
        format_volume=format_volume,
    ))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


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


def should_start_background_jobs():
    if os.getenv("DISABLE_BACKGROUND_REFRESH") == "1":
        return False
    return not any("unittest" in arg or "pytest" in arg for arg in sys.argv)


if should_start_background_jobs():
    start_bulk_block_refresh_scheduler()
    start_stock_detail_refresh_scheduler()
    start_market_refresh_scheduler()
    start_insights_snapshot_refresh_scheduler()


if __name__ == "__main__":
    app.run(debug=True)
