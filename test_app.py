import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

from stocks import STOCKS
from app import (
    IST,
    _CACHE,
    app,
    build_breadth,
    build_candles,
    build_calendar_panels,
    build_heatmap,
    fetch_nifty50_constituents,
    format_volume,
    get_cached,
    get_cached_swr,
    get_market_status,
)


SAMPLE_QUOTES = {
    "RELIANCE.NS": {
        "price": 1500.0, "change": 15.0, "percent": 1.0,
        "volume": 12_500_000, "market_cap": 20_000_000,
    },
    "TCS.NS": {
        "price": 3200.0, "change": -32.0, "percent": -1.0,
        "volume": 250_000, "market_cap": 15_000_000,
    },
}

SAMPLE_MARKET = {
    "indices": [
        {"name": "NIFTY 50", "symbol": "^NSEI", "available": True, "price": 24000,
         "change": 120, "percent": 0.5, "date": "Jun 12", "candles": []}
    ],
    "rows": [],
    "breadth": [],
    "gainers": [],
    "losers": [],
    "active": [],
    "signals": [],
    "sectors": [],
    "heatmap": [],
    "market_stats": {
        "tracked": 0, "priced": 0, "advance_ratio": 0,
        "average_change": None, "total_volume": 0, "total_market_cap": 0,
    },
    "internals": {
        "above_sma50": 0, "above_sma200": 0, "near_high": 0, "volume_surge": 0,
    },
}


class MarketStatusTests(unittest.TestCase):
    def test_market_states(self):
        self.assertEqual(get_market_status(datetime(2026, 6, 15, 8, 30, tzinfo=IST))["label"], "Pre-Market")
        self.assertEqual(get_market_status(datetime(2026, 6, 15, 9, 15, tzinfo=IST))["label"], "Open")
        self.assertEqual(get_market_status(datetime(2026, 6, 15, 15, 31, tzinfo=IST))["label"], "Closed")
        self.assertEqual(get_market_status(datetime(2026, 6, 13, 10, 0, tzinfo=IST))["label"], "Closed")


class DataModelTests(unittest.TestCase):
    def test_volume_and_candles(self):
        self.assertEqual(format_volume(12_500_000), "1.25 Cr")
        frame = pd.DataFrame(
            {"Open": [10, 12], "High": [13, 14], "Low": [9, 11], "Close": [12, 11]}
        )
        candles = build_candles(frame)
        self.assertEqual(len(candles), 2)
        self.assertTrue(candles[0]["up"])
        self.assertFalse(candles[1]["up"])

    def test_breadth_and_heatmap(self):
        rows = [
            {"sector": "Tech", "display_symbol": "AAA", "price": 100, "percent": 2,
             "market_cap": 10_000_000, "sma50": 90, "sma200": 80, "high52": 101, "low52": 50},
            {"sector": "Tech", "display_symbol": "BBB", "price": 80, "percent": -1,
             "market_cap": 5_000_000, "sma50": 85, "sma200": 90, "high52": 120, "low52": 70},
        ]
        breadth = build_breadth(rows)
        self.assertEqual(breadth[0]["left_count"], 1)
        self.assertEqual(len(build_heatmap(rows)[0]["cells"]), 2)

    def test_cache_returns_stale_data_after_failure(self):
        _CACHE.clear()
        self.assertEqual(get_cached("x", 5, lambda: {"ok": True}, now=10), ({"ok": True}, False))
        data, stale = get_cached("x", 5, lambda: (_ for _ in ()).throw(RuntimeError()), now=20)
        self.assertEqual(data, {"ok": True})
        self.assertTrue(stale)

    def test_calendar_panels_include_sessions_and_earnings(self):
        panels = build_calendar_panels(
            [{
                "symbol": "TCS", "name": "Tata Consultancy Services",
                "earnings_dates": [datetime(2026, 7, 9).date()],
                "ex_dividend": datetime(2026, 6, 18).date(),
            }],
            today=datetime(2026, 6, 14).date(),
        )
        self.assertEqual(panels["earnings"][0]["symbol"], "TCS")
        self.assertTrue(any(event["type"] == "Corporate" for event in panels["events"]))
        self.assertTrue(any(event["type"] == "Market" for event in panels["events"]))

    @patch("app.requests.get")
    def test_official_constituent_feed_requires_fifty_stocks(self, get):
        lines = ["Company Name,Industry,Symbol,Series,ISIN Code"]
        lines.extend(
            f"Company {index},Sector {index % 5},SYM{index},EQ,ISIN{index}"
            for index in range(50)
        )
        get.return_value.text = "\n".join(lines)
        get.return_value.raise_for_status.return_value = None
        stocks = fetch_nifty50_constituents()
        self.assertEqual(len(stocks), 50)
        self.assertEqual(stocks[0]["symbol"], "SYM0.NS")


class RouteTests(unittest.TestCase):
    TOOL_LINKS = {
        "Articles": "https://trading-simplified.com/blog/",
        "SWP Calculator": "https://trading-simplified.com/swp-calculator/",
        "Retirement Stress Test": "https://retirement.trading-simplified.com/",
        "Option Chain Analysis": "https://trading-simplified.com/option-chain-analysis/",
        "Market Performance": "https://trading-simplified.com/market-performance/",
    }

    def setUp(self):
        self.client = app.test_client()
        _CACHE.clear()

    def assert_tool_navigation(self, html):
        for label, url in self.TOOL_LINKS.items():
            self.assertIn(f'href="{url}"', html)
            self.assertIn(f">{label}</a>", html)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_public_tool_paths_redirect_to_existing_services(self):
        destinations = {
            "/blog/": "https://articles.trading-simplified.com/blog/",
            "/swp-calculator/": "https://swp-nifty-v2.netlify.app/",
            "/option-chain-analysis/": "https://articles.trading-simplified.com/option-chain-analysis/",
            "/market-performance/": "https://market-performace-v1.streamlit.app/",
        }
        for path, destination in destinations.items():
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], destination)

    @patch("app.get_stock_universe", return_value=([], False))
    @patch("app.get_cached_swr")
    def test_dashboard_structure_and_search_routing(self, cached, universe):
        cached.side_effect = [(SAMPLE_MARKET, False), ([], False), ([], False)]
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("NIFTY 50 Stocks - 1 Day Performance", html)
        self.assertIn("Nearby Events", html)
        self.assertIn("Upcoming Earnings Release", html)
        self.assertIn("Simply Trading", html)
        self.assertIn("/static/css/style.css?v=20260614-2", html)
        self.assertIn('action="/screener"', html)
        self.assertIn('class="active" href="/">Home</a>', html)
        self.assertEqual(html.count('name="search"'), 1)
        self.assertNotIn(">Charts<", html)
        self.assertNotIn(">Maps<", html)
        self.assert_tool_navigation(html)

    @patch("app.get_stock_universe", return_value=(STOCKS, False))
    @patch("app.get_market_quotes")
    def test_screener_filters_and_has_no_header_search(self, quotes, universe):
        quotes.return_value = (SAMPLE_QUOTES, False)
        html = self.client.get("/screener?search=tata&sector=Technology").get_data(as_text=True)
        self.assertIn("Tata Consultancy Services", html)
        self.assertNotIn("Reliance Industries", html)
        self.assertEqual(html.count('name="search"'), 1)
        self.assertEqual(html.count('name="sector"'), 1)
        self.assertIn('class="active" href="/screener">Screener</a>', html)
        self.assert_tool_navigation(html)

    @patch("app.get_stock_universe", return_value=(STOCKS, False))
    @patch("app.get_market_quotes", return_value=({}, False))
    def test_empty_screener(self, quotes, universe):
        html = self.client.get("/screener?search=missing").get_data(as_text=True)
        self.assertIn("No stocks found", html)


if __name__ == "__main__":
    unittest.main()
