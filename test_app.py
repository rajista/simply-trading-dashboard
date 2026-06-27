import unittest
from datetime import datetime
import time
from unittest.mock import patch

import pandas as pd

from stocks import STOCKS
from app import (
    IST,
    _CACHE,
    _parse_stock_news_rss,
    app,
    build_breadth,
    build_candles,
    build_calendar_panels,
    build_dashboard_insights,
    build_dashboard_notes,
    build_heatmap,
    build_insights,
    build_sector_performance,
    build_stock_hover_data_with_details,
    build_stock_rows,
    compute_obv_divergence,
    compute_quiet_pullback,
    compute_volume_range_signal,
    empty_insights_data,
    apply_nifty_impact,
    apply_nse_quote_snapshot,
    fetch_nse_nifty50_snapshot,
    fetch_nifty50_constituents,
    fetch_nifty500_constituents,
    format_crore_value,
    format_volume,
    get_cached,
    get_cached_swr,
    get_cached_stock_popup_details_snapshot,
    get_market_status,
    _financial_to_inr,
    normalize_deal_frame,
    normalize_fii_dii_activity,
    parse_nse_index_card,
    refresh_daily_insights_snapshot,
    seconds_until_next_ist_midnight,
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
    "insights": {
        "momentum": [],
        "risk": [],
        "leadership": [],
        "participation": [],
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

    def test_accumulation_helpers_handle_positive_and_insufficient_cases(self):
        closes = pd.Series([100, 101, 100.5, 101.2, 100.8, 101.1, 100.9, 101.3, 101.0, 101.4,
                            101.1, 101.5, 101.2, 101.6, 101.3, 101.7, 101.4, 101.8, 101.5, 101.9])
        volumes = pd.Series([1000, 1600, 900, 1700, 950, 1800, 920, 1900, 940, 2000,
                             960, 2100, 980, 2200, 1000, 2300, 1020, 2400, 1040, 2500])
        self.assertTrue(compute_obv_divergence(closes, volumes))
        self.assertFalse(compute_obv_divergence(pd.Series([1, 2]), pd.Series([10, 20])))

    def test_quiet_pullback_and_volume_range_signal(self):
        quiet_closes = pd.Series([100 + index * 0.2 for index in range(20)] + [110, 109.7, 109.5, 109.6])
        quiet_volumes = pd.Series([1000] * 20 + [1800, 800, 750, 700])
        self.assertTrue(compute_quiet_pullback(quiet_closes, quiet_volumes))

        range_closes = pd.Series([100, 104, 99, 105, 100, 106, 101, 105, 99, 104,
                                  102, 103, 102.5, 103.2, 102.8, 103.1, 102.9, 103.0, 102.7, 103.2])
        range_volumes = pd.Series([1000] * 15 + [1300, 1350, 1320, 1400, 1380])
        self.assertTrue(compute_volume_range_signal(range_closes, range_volumes))

    def test_build_stock_rows_adds_accumulation_and_range_fields(self):
        stock = {"symbol": "AAA.NS", "name": "AAA", "sector": "Tech", "industry": "Tech"}
        frame = pd.DataFrame(
            {
                "Open": [100 + index for index in range(24)],
                "High": [101 + index for index in range(24)],
                "Low": [99 + index for index in range(24)],
                "Close": [100 + index for index in range(24)],
                "Volume": [1000] * 24,
            }
        )
        rows = build_stock_rows({"AAA.NS": {"price": 123, "volume": 1000}}, frame, [stock])
        self.assertIn("accumulation_score", rows[0])
        self.assertIn("obv_divergence", rows[0])
        self.assertEqual(rows[0]["day_open"], 123)
        self.assertIsNotNone(rows[0]["high52_distance"])

    @patch("app._fx_average_to_inr", return_value=88.33562561510138)
    def test_usd_financials_are_converted_to_inr_before_display(self, fx):
        infy_usd_revenue = 20_158_000_000
        converted = _financial_to_inr(infy_usd_revenue, "USD", pd.Timestamp("2026-03-31"))
        self.assertGreater(converted, 1_700_000_000_000)
        self.assertLess(converted, 1_850_000_000_000)

    def test_hover_data_embeds_prebuilt_popup_details(self):
        rows = [{
            "display_symbol": "AAA", "name": "AAA Ltd", "sector": "Tech", "price": 10,
            "change": 1, "percent": 10, "five_day_change": 2, "volume": 1000,
            "market_cap": 10_000_000, "signal": "Uptrend", "chart_series": [9, 10],
            "day_open": 9, "day_high": 11, "day_low": 8, "high52_distance": -2,
            "low52_distance": 25, "accumulation_score": 2, "obv_divergence": True,
            "quiet_pullback": False, "volume_range_signal": True, "delivery_percent": 45,
        }]
        details = {"AAA": {"roe": 20, "revenue": 100_000_000, "growth": {"1y": 12}}}
        hover = build_stock_hover_data_with_details(rows, details)
        self.assertEqual(hover["AAA"]["details"]["roe"], 20)
        self.assertEqual(hover["AAA"]["delivery_percent"], 45)

    def test_popup_snapshot_reads_latest_memory_cache(self):
        _CACHE.clear()
        _CACHE["stock_popup_details:latest"] = {
            "data": {"details": {"AAA": {"pe_ratio": 22, "description": "AAA details"}}},
            "expires": time.time() + 60,
        }
        details = get_cached_stock_popup_details_snapshot([{"display_symbol": "AAA"}])
        self.assertEqual(details["AAA"]["pe_ratio"], 22)

    def test_dashboard_insights_summarize_market_rows(self):
        rows = [
            {"display_symbol": "AAA", "sector": "Tech", "price": 100, "percent": 3.0,
             "signal": "Uptrend", "accumulation_score": 2, "volume_change": 30,
             "high52": 102, "low52": 80, "market_cap": 10, "volume": 100},
            {"display_symbol": "BBB", "sector": "Bank", "price": 70, "percent": -2.0,
             "signal": "Downtrend", "accumulation_score": 0, "volume_change": -5,
             "high52": 110, "low52": 68, "market_cap": 10, "volume": 100},
        ]
        insights = build_dashboard_insights(rows, rows[:1])
        self.assertEqual(insights["momentum"][0]["value"], 1)
        self.assertEqual(insights["risk"][0]["value"], 1)
        self.assertEqual(insights["leadership"][0]["value"], "AAA")
        self.assertEqual(insights["participation"][0]["detail"], "50.0%")
        notes = build_dashboard_notes(rows, rows[:1])
        self.assertTrue(any("Participation is 50.0%" in note for note in notes))
        self.assertTrue(any("AAA is strongest" in note for note in notes))

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

    def test_build_insights_summarizes_accumulation_and_sector_counts(self):
        deal_data = {
            "bulk": normalize_deal_frame(pd.DataFrame([
                {"Date": "15-JUN-2026", "Symbol": "AAA", "Security Name": "AAA Ltd", "Client Name": "Fund A",
                 "Buy / Sell": "BUY", "Quantity Traded": "1,00,000", "Trade Price / Wght. Avg. Price": "100"},
                {"Date": "15-JUN-2026", "Symbol": "BBB", "Security Name": "BBB Ltd", "Client Name": "Fund B",
                 "Buy / Sell": "SELL", "Quantity Traded": "50,000", "Trade Price / Wght. Avg. Price": "80"},
            ]), "bulk"),
            "block": normalize_deal_frame(pd.DataFrame([
                {"Date": "10-JUN-2026", "Symbol": "AAA", "Security Name": "AAA Ltd", "Client Name": "Fund C",
                 "Buy / Sell": "BUY", "Quantity Traded": "2,00,000", "Trade Price / Wght. Avg. Price": "105"},
            ]), "block"),
            "short": normalize_deal_frame(pd.DataFrame([
                {"Date": "15-JUN-2026", "Symbol": "CCC", "Security Name": "CCC Ltd", "Quantity": "1,00,000"},
                {"Date": "10-MAY-2026", "Symbol": "CCC", "Security Name": "CCC Ltd", "Quantity": "10,000"},
            ]), "short"),
            "source": "test",
            "latest_date": "2026-06-15",
            "refreshed_at": "2026-06-15 00:00 IST",
        }
        rows = [
            {"display_symbol": "AAA", "sector": "Tech", "price": 100, "high52": 102, "signal": "Uptrend",
             "accumulation_score": 3, "five_day_change": 4.0, "obv_divergence": True,
             "quiet_pullback": True, "volume_range_signal": True},
            {"display_symbol": "BBB", "sector": "Tech", "price": 80, "high52": 100, "signal": "Neutral",
             "accumulation_score": 2, "five_day_change": 1.0, "obv_divergence": False,
             "quiet_pullback": True, "volume_range_signal": True},
            {"display_symbol": "CCC", "sector": "Bank", "price": 50, "high52": 80, "signal": "Downtrend",
             "accumulation_score": 1, "five_day_change": 5.0, "obv_divergence": True,
             "quiet_pullback": False, "volume_range_signal": False},
        ]
        details = {
            "AAA": {"pe_ratio": 20.5, "price_to_book": 3.2, "roe": 18.5, "roce": 21.0, "debt_equity": 0.2, "dividend_yield": 1.1, "profit_cagr_3y": 14.0},
            "BBB": {"pe_ratio": 12.0, "price_to_book": 1.4, "roe": 11.0, "roce": 13.0, "debt_equity": 0.5, "dividend_yield": 0.8, "profit_cagr_3y": 8.0},
        }
        insights = build_insights(rows, deal_data, details)
        self.assertEqual(insights["accumulation_count"], 2)
        self.assertEqual(insights["uptrend_count"], 1)
        self.assertEqual(insights["near_high_count"], 1)
        self.assertEqual(insights["ranked"][0]["display_symbol"], "AAA")
        self.assertEqual(insights["high_conviction"][0]["display_symbol"], "AAA")
        self.assertEqual(insights["sector_stock_tables"][0]["sector"], "Tech")
        self.assertEqual(insights["sector_stock_tables"][0]["members"][0]["detail"]["pe_ratio"], 20.5)
        self.assertAlmostEqual(insights["sector_stock_tables"][0]["avg_roe"], 14.75)
        self.assertGreater(insights["institutional_accumulation_count"], 0)
        self.assertGreater(insights["rising_short_count"], 0)
        self.assertIn("Tech", insights["top_lines"][0])

    def test_normalize_deal_frame_accepts_seed_and_refreshed_formats(self):
        seed = normalize_deal_frame(pd.DataFrame([
            {"Date": "15-JUN-2026", "Symbol": "AAA", "Security Name": "AAA Ltd", "Client Name": "Fund A",
             "Buy / Sell": "BUY", "Quantity Traded": "1,00,000", "Trade Price / Wght. Avg. Price": "100"}
        ]), "bulk")
        refreshed = normalize_deal_frame(seed, "bulk")
        self.assertEqual(refreshed.iloc[0]["symbol"], "AAA")
        self.assertEqual(refreshed.iloc[0]["value"], 10_000_000)

    def test_seconds_until_next_ist_midnight(self):
        seconds = seconds_until_next_ist_midnight(datetime(2026, 6, 21, 23, 59, 0, tzinfo=IST))
        self.assertEqual(seconds, 60)

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
            "/blog/": "/articles",
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
        cached.side_effect = [
            (SAMPLE_MARKET, False),
            ([], False),
            ([], False),
            ([], False),
            ({"details": {}, "fx_warnings": {}, "refreshed_at": None}, False),
        ]
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("NIFTY 50 Stocks - 1 Day Performance", html)
        self.assertIn("Nearby Events", html)
        self.assertIn("Upcoming Earnings Release", html)
        self.assertIn("Simply Trading", html)
        self.assertIn("/static/css/style.css?v=20260627-1", html)
        self.assertIn("/static/js/dashboard.js?v=20260627-1", html)
        self.assertIn("AI Option Chain Analysis", html)
        self.assertIn("Analyse Options", html)
        self.assertIn("FII / DII Cash Activity", html)
        self.assertIn("Dashboard Insights", html)
        self.assertIn("Dashboard notes will appear", html)
        self.assertIn("Operating Margin", html)
        self.assertIn("Retail", html)
        self.assertIn("Shareholding / change", html)
        self.assertIn("Latest News", html)
        self.assertIn("NIFTY 500", html)
        self.assertIn("sector-toggle", html)
        self.assertIn('class="option-chain-promo" href="https://trading-simplified.com/option-chain-analysis/"', html)
        self.assertIn("Educational insights only", html)
        self.assertIn("Impact data unavailable", html)
        self.assertIn('action="/screener"', html)
        self.assertIn('class="active" href="/">Home</a>', html)
        self.assertIn('href="/insights">Insights</a>', html)
        self.assertIn('href="/articles">Articles</a>', html)
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

    @patch("app.build_insights")
    @patch("app.load_cached_market_context")
    @patch("app.get_cached_insights_snapshot")
    def test_insights_route_uses_precomputed_snapshot_only(self, snapshot, market_loader, insight_builder):
        insight_data = empty_insights_data()
        row = {
            "display_symbol": "AAA", "name": "AAA", "sector": "Tech", "price": 100,
            "high52": 101, "signal": "Uptrend", "accumulation_score": 2,
            "five_day_change": 3.2, "obv_divergence": True, "quiet_pullback": False,
            "volume_range_signal": True, "percent": 1.0, "volume": 1000, "chart_series": [90, 100],
            "change": 1.0, "market_cap": 10_000_000, "deal": {
                "bulk_net30": 0, "bulk_trades30": 0, "short_qty30": 0, "short_change": 0,
            },
            "drivers": ["2/3 accumulation setup"], "conflicts": [],
            "composite_score": 35.0, "analyst_view": "Aligned", "detail": {},
        }
        insight_data["high_conviction"] = [row]
        insight_data["ranked"] = [row]
        insight_data["deal_meta"] = {
            "source": "snapshot",
            "latest_date": "2026-06-26",
            "refreshed_at": "2026-06-27 00:05 IST",
            "row_count": 12,
        }
        snapshot.return_value = {
            "status": "ready",
            "insights": insight_data,
            "hover_data": {"AAA": {"symbol": "AAA", "series": [90, 100], "details": {}}},
            "created_at": "2026-06-27 00:06 IST",
            "refreshed_at": "2026-06-27 00:06 IST",
            "stale": False,
            "error": None,
        }
        html = self.client.get("/insights").get_data(as_text=True)
        self.assertIn("Market Insights", html)
        self.assertIn("High-Conviction Watchlist", html)
        self.assertIn("Bulk / block / short data source", html)
        self.assertIn("Accumulation Watch", html)
        self.assertIn("Sector-Wise Stocks & Financial Metrics", html)
        self.assertIn("AAA", html)
        self.assertIn("Latest News", html)
        self.assertIn("/api/insights-data", html)
        self.assertIn('class="active" href="/insights">Insights</a>', html)
        market_loader.assert_not_called()
        insight_builder.assert_not_called()

    @patch("app.build_insights")
    @patch("app.load_cached_market_context")
    @patch("app.get_cached_insights_snapshot", return_value=None)
    def test_insights_route_warming_shell_is_lightweight(self, snapshot, market_loader, insight_builder):
        html = self.client.get("/insights").get_data(as_text=True)
        self.assertIn("snapshot warming", html)
        self.assertIn("Preparing the latest Insights snapshot", html)
        market_loader.assert_not_called()
        insight_builder.assert_not_called()

    @patch("app.get_cached_insights_snapshot")
    def test_insights_data_api_ready_and_warming(self, snapshot):
        snapshot.return_value = None
        warming = self.client.get("/api/insights-data").get_json()
        self.assertEqual(warming["status"], "warming")
        snapshot.return_value = {"status": "ready", "created_at": "now", "stale": True, "error": "old"}
        ready = self.client.get("/api/insights-data").get_json()
        self.assertEqual(ready["status"], "ready")
        self.assertTrue(ready["stale"])

    @patch("app.refresh_insights_snapshot")
    @patch("app.refresh_bulk_block_short_cache_from_nse")
    def test_daily_insights_refresh_runs_after_nse_refresh(self, bulk_refresh, insights_refresh):
        bulk_refresh.return_value = {"source": "fresh"}
        refresh_daily_insights_snapshot()
        bulk_refresh.assert_called_once()
        insights_refresh.assert_called_once_with(deal_data={"source": "fresh"})

    def test_stock_news_rss_parser_sanitizes_items(self):
        rss = b"""<?xml version="1.0"?><rss><channel><item><title><![CDATA[<b>INFY</b> wins deal]]></title><link>https://example.com/infy</link><source>Yahoo</source><pubDate>Fri, 26 Jun 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
        parsed = _parse_stock_news_rss(rss)
        self.assertEqual(parsed[0]["title"], "INFY wins deal")
        self.assertEqual(parsed[0]["source"], "Yahoo")
        self.assertIn("https://example.com/infy", parsed[0]["url"])

    @patch("app._fallback_stock_news_from_market_headlines", return_value=[{"title": "MSUMI update", "url": "https://example.com", "source": "Market", "published": ""}])
    @patch("app.fetch_stock_detail", return_value={})
    def test_stock_detail_fallback_never_returns_blank(self, fetch_detail, fallback_news):
        _CACHE.clear()
        detail = self.client.get("/api/stocks/MSUMI").get_json()
        self.assertEqual(detail["symbol"], "MSUMI")
        self.assertIn("temporarily unavailable", detail["description"])
        self.assertEqual(detail["news"][0]["title"], "MSUMI update")

    def test_articles_page_uses_internal_layout_with_filters_and_search(self):
        html = self.client.get("/articles").get_data(as_text=True)
        self.assertIn("Trading Simplified Articles", html)
        self.assertIn("Practical trading research, dashboard guides, backtests and market notes.", html)
        self.assertIn('class="active" href="/articles">Articles</a>', html)
        self.assertIn('class="featured-article-card"', html)
        self.assertIn('class="recent-articles-panel"', html)
        self.assertIn('class="article-filter-pills"', html)
        self.assertIn('placeholder="Search articles..."', html)
        self.assertIn("Trading Simplified Dashboard &amp; Market Insights", html)
        self.assertIn("https://trading-simplified.com/2026/06/21/trading-simplified-dashboard-market-insights-indian-markets/", html)

    def test_articles_page_filters_by_category_and_search(self):
        stocks_html = self.client.get("/articles?category=stocks").get_data(as_text=True)
        self.assertIn("Trading Simplified Dashboard &amp; Market Insights", stocks_html)
        self.assertNotIn("Nasdaq Stock Analysis May 2026", stocks_html)

        search_html = self.client.get("/articles?q=zerodha").get_data(as_text=True)
        self.assertIn("Zerodha PnL summary", search_html)
        self.assertNotIn("Trading Simplified Dashboard &amp; Market Insights", search_html)

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
