# Simply Trading

A dense market dashboard for Indian equities, built with Flask.

## What this includes

- `/`: Indian market homepage with index candlestick charts, breadth, movers,
  technical signals, sector heatmap, and market headlines
- `/screener`: NSE stock screener with search and sector filtering
- Yahoo Finance market data with a shared 20-minute in-memory cache
- Stale-while-refresh behavior so visitors do not wait when cached data expires
- Economic Times and Moneycontrol RSS headlines
- Official NIFTY Indices constituent feed, refreshed daily with a local fallback
- `requirements.txt`: Python dependencies

## Setup

1. Create a virtual environment:

    python -m venv venv

2. Activate it:

    venv\Scripts\activate

3. Install dependencies:

    pip install -r requirements.txt

4. Run the app:

    python app.py

5. Open the site in your browser:

    http://127.0.0.1:5000

## Notes

- Market data is fetched using `yfinance`; headlines use public RSS feeds.
- The NIFTY 50 universe comes from the official NIFTY Indices CSV and is
  validated to contain exactly 50 constituents before use.
- Dashboard prices and history are cached for twenty minutes. Expired data is
  served immediately while a single background refresh updates the cache.
- Headlines are cached for fifteen minutes; company calendar data is cached for
  six hours because earnings dates do not need intraday refreshes.
- You can extend `stocks.py` with more NSE symbols.

## Production

The included `render.yaml` configures a paid, always-on Render web service in
Singapore with one Gunicorn worker, eight threads, `/health` monitoring, and a
20-minute market-data cache.

The single worker is intentional: the cache is in process memory, so this avoids
duplicate Yahoo Finance refreshes. For horizontal scaling, replace the in-memory
cache with Render Key Value or another shared Redis-compatible service.
