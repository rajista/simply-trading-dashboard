import unittest
from datetime import datetime
import time
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
    build_sector_performance,
    apply_nifty_impact,
    apply_nse_quote_snapshot,
    fetch_nse_nifty50_snapshot,
    fetch_nifty50_constituents,
    fetch_nifty500_constituents,
    format_crore_value,
    format_volume,
    get_cached,
    get_cached_swr,
    get_market_status,
    normalize_fii_dii_activity,
    parse_nse_index_card,
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
    "nifty50_rows": [],
    "breadth": [],
    "gainers": [],
    "losers": [],
    "active": [],
    "signals": [],
    "sectors": [{
        "name": "Technology",
        "stocks": 1,
        "advancers": 1,
        "percent": 1.0,
        "volume": 100_000,
        "leader": {"display_symbol": "TCS", "percent": 1.0},
        "laggard": {"display_symbol": "TCS", "percent": 1.0},
        "members": [{
            "display_symbol": "TCS",
            "name": "Tata Consultancy Services",
            "price": 3200.0,
            "percent": 1.0,
            "volume": 100_000,
            "signal": "Uptrend",
        }],
    }],
    "heatmap": [],
    "hover_data": {},
    "impact_available": False,
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

    def test_nifty_impact_weights_and_heatmap_sizing(self):
        rows = [
            {"sector": "Energy", "display_symbol": "AAA", "percent": 2.0,
             "market_cap": 10, "volume": 1},
            {"sector": "Tech", "display_symbol": "BBB", "percent": -1.0,
             "market_cap": 10, "volume": 1},
            {"sector": "Tech", "display_symbol": "CCC", "percent": 0.0,
             "market_cap": 10, "volume": 1},
        ]
        snapshot = [
            {"symbol": "NIFTY 50", "ffmc": 9999},
            {"symbol": "AAA", "ffmc": "600"},
            {"symbol": "BBB", "ffmc": 300},
            {"symbol": "CCC", "ffmc": 100},
            {"symbol": "UNKNOWN", "ffmc": "bad"},
        ]
        apply_nifty_impact(rows, snapshot)
        self.assertAlmostEqual(sum(row["index_weight"] for row in rows), 1.0)
        self.assertAlmostEqual(rows[0]["nifty_impact"], 1.2)
        self.assertAlmostEqual(rows[1]["nifty_impact"], -0.3)
        self.assertEqual(rows[2]["nifty_impact"], 0)
        heatmap = build_heatmap(rows)
        self.assertGreater(heatmap[0]["impact"], heatmap[1]["impact"])
        self.assertGreater(
            heatmap[0]["width"] * heatmap[0]["height"],
            heatmap[1]["width"] * heatmap[1]["height"],
        )
        self.assertAlmostEqual(
            sum(group["width"] * group["height"] for group in heatmap),
            10000,
            places=1,
        )
        self.assertTrue(
            all(cell["width"] > 0 and cell["height"] > 0 for group in heatmap for cell in group["cells"])
        )

    def test_nse_snapshot_hydrates_live_quote_fields(self):
        rows = [{"display_symbol": "RELIANCE", "price": None, "change": None, "percent": None, "volume": None}]
        apply_nse_quote_snapshot(
            rows,
            [{"symbol": "RELIANCE", "lastPrice": "1,450.5", "change": "12.3", "pChange": "0.85", "totalTradedVolume": "123456"}],
        )
        self.assertEqual(rows[0]["price"], 1450.5)
        self.assertEqual(rows[0]["change"], 12.3)
        self.assertEqual(rows[0]["percent"], 0.85)
        self.assertEqual(rows[0]["volume"], 123456)

    def test_nse_index_card_parser_uses_ltp_change_and_previous_close_basis(self):
        card = parse_nse_index_card(
            "^NSEI",
            "NIFTY 50",
            {"data": [{"symbol": "NIFTY 50", "lastPrice": "24013.10", "change": "-154.90", "pChange": "-0.64"}]},
        )
        self.assertEqual(card["price"], 24013.10)
        self.assertEqual(card["change"], -154.90)
        self.assertEqual(card["percent"], -0.64)

    def test_fii_dii_activity_normalization(self):
        rows = normalize_fii_dii_activity([
            {"category": "DII", "date": "16-Jun-2026", "buyValue": "13,553.36", "sellValue": "13553.30", "netValue": "0.06"},
            {"category": "FII/FPI", "date": "16-Jun-2026", "buyValue": "13887.15", "sellValue": "14636.33", "netValue": "-749.18"},
        ])
        self.assertEqual(rows[0]["category"], "DII")
        self.assertEqual(rows[1]["category"], "FII/FPI")
        self.assertEqual(format_crore_value(rows[1]["net"]), "Rs -749.18 Cr")

    def test_sector_performance_includes_expandable_members(self):
        rows = [
            {"sector": "Tech", "display_symbol": "AAA", "name": "AAA Ltd", "price": 10, "percent": 2, "volume": 100, "signal": "Uptrend"},
            {"sector": "Tech", "display_symbol": "BBB", "name": "BBB Ltd", "price": 20, "percent": -1, "volume": 200, "signal": "Downtrend"},
        ]
        sectors = build_sector_performance(rows)
        self.assertEqual(sectors[0]["stocks"], 2)
        self.assertEqual(len(sectors[0]["members"]), 2)
        self.assertEqual(sectors[0]["members"][0]["display_symbol"], "AAA")

    @patch("app.requests.Session")
    def test_nse_snapshot_fetch_uses_session_and_returns_rows(self, session_class):
        session = session_class.return_value.__enter__.return_value
        session.get.return_value.raise_for_status.return_value = None
        session.get.return_value.json.return_value = {
            "data": [{"symbol": "RELIANCE", "ffmc": 100}]
        }
        self.assertEqual(fetch_nse_nifty50_snapshot()[0]["symbol"], "RELIANCE")
        self.assertEqual(session.get.call_count, 2)

    def test_cache_returns_stale_data_after_failure(self):
        _CACHE.clear()
        self.assertEqual(get_cached("x", 5, lambda: {"ok": True}, now=10), ({"ok": True}, False))
        data, stale = get_cached("x", 5, lambda: (_ for _ in ()).throw(RuntimeError()), now=20)
        self.assertEqual(data, {"ok": True})
        self.assertTrue(stale)

    def test_cold_async_cache_returns_immediately_and_refreshes_once(self):
        _CACHE.clear()
        result, stale = get_cached_swr(
            "cold",
            60,
            lambda: {"ready": True},
            cold_async=True,
        )
        self.assertIsNone(result)
        self.assertFalse(stale)
        for _ in range(50):
            if "cold" in _CACHE:
                break
            time.sleep(0.01)
        self.assertEqual(_CACHE["cold"]["data"], {"ready": True})

    def test_calendar_panels_include_corporate_events_without_routine_sessions(self):
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
        self.assertFalse(any(event["type"] == "Market" for event in panels["events"]))
        self.assertFalse(any("regular trading session" in event["title"] for event in panels["events"]))

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

    @patch("app.requests.get")
    def test_official_nifty500_feed_requires_five_hundred_stocks(self, get):
        lines = ["Company Name,Industry,Symbol,Series,ISIN Code"]
        lines.extend(
            f"Company {index},Sector {index % 12},N500{index},EQ,ISIN{index}"
            for index in range(504)
        )
        get.return_value.text = "\n".join(lines)
        get.return_value.raise_for_status.return_value = None
        stocks = fetch_nifty500_constituents()
        self.assertEqual(len(stocks), 504)
        self.assertEqual(stocks[0]["symbol"], "N5000.NS")


class RouteTests(unittest.TestCase):
    TOOL_LINKS = {
        "Articles": "https://trading-simplified.com/blog/",
        "SWP Calculator": "https://trading-simplified.com/swp-calculator/",
        "Retirement Stress Test": "https://retirement.trading-simplified.com/",
        "Option Chain Analysis": "https://trading-simplified.com/option-chain-analysis/",
        "Option Builder": "https://trading-simplified.com/option-builder/",
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
            "/blog/": "https://trading-simplified.com/blog/",
            "/swp-calculator/": "https://trading-simplified.com/swp-calculator/",
            "/option-chain-analysis/": "https://trading-simplified.com/option-chain-analysis/",
            "/option-builder/": "https://trading-simplified.com/option-builder/",
            "/market-performance/": "https://trading-simplified.com/market-performance/",
        }
        for path, destination in destinations.items():
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], destination)

    @patch("app.get_nifty500_universe", return_value=([], False))
    @patch("app.get_stock_universe", return_value=([], False))
    @patch("app.get_cached_swr")
    def test_dashboard_structure_and_search_routing(self, cached, universe, broad_universe):
        cached.side_effect = [(SAMPLE_MARKET, False), ([], False), ([], False), ([], False)]
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("NIFTY 50 Stocks - 1 Day Performance", html)
        self.assertIn("Nearby Events", html)
        self.assertIn("Upcoming Earnings Release", html)
        self.assertIn("Simply Trading", html)
        self.assertIn("/static/css/style.css?v=20260619-1", html)
        self.assertIn("/static/js/dashboard.js?v=20260619-1", html)
        self.assertIn("AI Option Chain Analysis", html)
        self.assertIn("Analyse Options", html)
        self.assertIn("FII / DII Cash Activity", html)
        self.assertIn("NIFTY 500", html)
        self.assertIn("sector-toggle", html)
        self.assertIn('class="option-chain-promo" href="https://trading-simplified.com/option-chain-analysis/"', html)
        self.assertIn("Educational insights only", html)
        self.assertIn("Impact data unavailable", html)
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
        self.assertNotIn("AI Option Chain Analysis", html)
        self.assert_tool_navigation(html)

    @patch("app.get_stock_universe", return_value=(STOCKS, False))
    @patch("app.get_market_quotes", return_value=({}, False))
    def test_empty_screener(self, quotes, universe):
        html = self.client.get("/screener?search=missing").get_data(as_text=True)
        self.assertIn("No stocks found", html)

    @patch("app.get_stock_detail")
    def test_stock_detail_api(self, detail):
        detail.return_value = {"symbol": "TCS", "growth": {"1m": 1.2}, "pe_ratio": 30}
        response = self.client.get("/api/stocks/TCS")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["symbol"], "TCS")


if __name__ == "__main__":
    unittest.main()
