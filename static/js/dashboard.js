(() => {
    const dataElement = document.getElementById("ticker-hover-data");
    const card = document.getElementById("ticker-hover-card");
    if (!dataElement || !card) return;

    let tickerData = {};
    try {
        tickerData = JSON.parse(dataElement.textContent || "{}");
    } catch {
        return;
    }

    const chart = card.querySelector("[data-hover-chart]");
    const fields = {
        symbol: card.querySelector("[data-hover-symbol]"),
        sector: card.querySelector("[data-hover-sector]"),
        change: card.querySelector("[data-hover-change]"),
        name: card.querySelector("[data-hover-name]"),
        price: card.querySelector("[data-hover-price]"),
        volume: card.querySelector("[data-hover-volume]"),
        signal: card.querySelector("[data-hover-signal]"),
        fiveDay: card.querySelector("[data-hover-five-day]"),
        accumulationScore: card.querySelector("[data-hover-accumulation-score]"),
        obv: card.querySelector("[data-hover-obv]"),
        pullback: card.querySelector("[data-hover-pullback]"),
        volumeRange: card.querySelector("[data-hover-volume-range]"),
        dayOpen: card.querySelector("[data-hover-day-open]"),
        dayHigh: card.querySelector("[data-hover-day-high]"),
        dayLow: card.querySelector("[data-hover-day-low]"),
        distanceHigh: card.querySelector("[data-hover-distance-high]"),
        distanceLow: card.querySelector("[data-hover-distance-low]"),
        marketCap: card.querySelector("[data-hover-market-cap]"),
        growth1m: card.querySelector("[data-hover-growth-1m]"),
        growth3m: card.querySelector("[data-hover-growth-3m]"),
        growth1y: card.querySelector("[data-hover-growth-1y]"),
        growth5y: card.querySelector("[data-hover-growth-5y]"),
        pe: card.querySelector("[data-hover-pe]"),
        revenue: card.querySelector("[data-hover-revenue]"),
        pat: card.querySelector("[data-hover-pat]"),
        opm: card.querySelector("[data-hover-opm]"),
        roe: card.querySelector("[data-hover-roe]"),
        roce: card.querySelector("[data-hover-roce]"),
        pb: card.querySelector("[data-hover-pb]"),
        profitCagr: card.querySelector("[data-hover-profit-cagr]"),
        avgPe: card.querySelector("[data-hover-avg-pe]"),
        debtEquity: card.querySelector("[data-hover-debt-equity]"),
        totalDebt: card.querySelector("[data-hover-total-debt]"),
        promoter: card.querySelector("[data-hover-promoter]"),
        fii: card.querySelector("[data-hover-fii]"),
        dii: card.querySelector("[data-hover-dii]"),
        retail: card.querySelector("[data-hover-retail]"),
        fiiDii: card.querySelector("[data-hover-fii-dii]"),
        dividendYield: card.querySelector("[data-hover-dividend-yield]"),
        delivery: card.querySelector("[data-hover-delivery]"),
        description: card.querySelector("[data-hover-description]"),
    };
    let hideTimer;
    let pinned = false;
    const detailRequests = new Map();
    const prefersTapPopup = window.matchMedia("(hover: none), (pointer: coarse)").matches;

    const signed = (value, digits = 2) => {
        if (value === null || value === undefined) return "-";
        return `${value >= 0 ? "+" : ""}${Number(value).toFixed(digits)}`;
    };

    const compactIndian = (value) => {
        if (value === null || value === undefined) return "-";
        if (value >= 10000000) return `${(value / 10000000).toFixed(2)} Cr`;
        if (value >= 100000) return `${(value / 100000).toFixed(2)} L`;
        return Number(value).toLocaleString("en-IN");
    };

    const formatRevenue = (value) => {
        if (value === null || value === undefined) return "-";
        if (value >= 10000000) return `${(value / 10000000).toFixed(2)} Cr`;
        if (value >= 100000) return `${(value / 100000).toFixed(2)} L`;
        return Number(value).toLocaleString("en-IN");
    };

    const formatPrice = (value) => {
        if (value === null || value === undefined) return "-";
        return Number(value).toLocaleString("en-IN", {maximumFractionDigits: 2});
    };

    const formatPercent = (value) => {
        if (value === null || value === undefined) return "-";
        return `${signed(value)}%`;
    };

    const formatRatio = (value, digits = 2) => {
        if (value === null || value === undefined) return "-";
        return Number(value).toFixed(digits);
    };

    const formatTrendValue = (value, trend) => {
        const formatted = formatPercent(value);
        if (formatted === "-") return "-";
        return `${formatted} · ${trend || "chg -"}`;
    };

    const setFlag = (element, enabled) => {
        if (!element) return;
        element.classList.toggle("is-on", Boolean(enabled));
    };

    const needsDetailFetch = (detail) => {
        if (!detail || !Object.keys(detail).length) return true;
        return [
            "operating_profit_margin",
            "total_debt",
            "promoter_holding",
            "fii_holding",
            "dii_holding",
            "retail_holding",
        ].every((key) => detail[key] === null || detail[key] === undefined);
    };

    const hydrateDetail = (item, target) => {
        if (!needsDetailFetch(item.details) || detailRequests.has(item.symbol)) return;
        const request = fetch(`/api/stocks/${encodeURIComponent(item.symbol)}`)
            .then((response) => response.ok ? response.json() : null)
            .then((detail) => {
                if (!detail || !Object.keys(detail).length) return;
                item.details = {...(item.details || {}), ...detail};
                if (card.classList.contains("is-visible") && fields.symbol.textContent === item.symbol) {
                    render(target, item);
                }
            })
            .catch(() => null);
        detailRequests.set(item.symbol, request);
    };

    const chartPoints = (series) => {
        if (!series || series.length < 2) return "";
        const min = Math.min(...series);
        const max = Math.max(...series);
        const range = max - min || 1;
        return series.map((value, index) => {
            const x = (index / (series.length - 1)) * 420;
            const y = 140 - ((value - min) / range) * 130;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(" ");
    };

    const placeCard = (target) => {
        if (prefersTapPopup) {
            card.style.left = "";
            card.style.top = "";
            return;
        }
        const targetBox = target.getBoundingClientRect();
        const cardBox = card.getBoundingClientRect();
        let left = targetBox.left + Math.min(targetBox.width, 36);
        let top = targetBox.bottom + 8;
        if (left + cardBox.width > window.innerWidth - 10) {
            left = window.innerWidth - cardBox.width - 10;
        }
        if (top + cardBox.height > window.innerHeight - 10) {
            top = targetBox.top - cardBox.height - 8;
        }
        card.style.left = `${Math.max(10, left)}px`;
        card.style.top = `${Math.max(10, top)}px`;
    };

    const render = (target, item) => {
        const positive = Number(item.percent || 0) >= 0;
        fields.symbol.textContent = item.symbol;
        fields.sector.textContent = item.sector || "";
        fields.change.textContent = `${signed(item.change)} (${signed(item.percent)}%)`;
        fields.change.className = positive ? "positive" : "negative";
        fields.name.textContent = item.name || item.symbol;
        fields.price.textContent = `Last: ${item.price === null ? "-" : Number(item.price).toLocaleString("en-IN", {maximumFractionDigits: 2})}`;
        fields.volume.textContent = `Volume: ${compactIndian(item.volume)}`;
        fields.signal.textContent = `Signal: ${item.signal || "Unavailable"}`;
        fields.fiveDay.textContent = `5 day: ${signed(item.five_day_change)}%`;
        fields.accumulationScore.textContent = `${item.accumulation_score || 0}/3`;
        fields.dayOpen.textContent = formatPrice(item.day_open);
        fields.dayHigh.textContent = formatPrice(item.day_high);
        fields.dayLow.textContent = formatPrice(item.day_low);
        fields.distanceHigh.textContent = formatPercent(item.high52_distance);
        fields.distanceLow.textContent = formatPercent(item.low52_distance);
        fields.marketCap.textContent = compactIndian(item.market_cap);
        setFlag(fields.obv, item.obv_divergence);
        setFlag(fields.pullback, item.quiet_pullback);
        setFlag(fields.volumeRange, item.volume_range_signal);
        const detail = item.details || {};
        const growth = detail.growth || {};
        fields.growth1m.textContent = formatPercent(growth["1m"]);
        fields.growth3m.textContent = formatPercent(growth["3m"]);
        fields.growth1y.textContent = formatPercent(growth["1y"]);
        fields.growth5y.textContent = formatPercent(growth["5y"]);
        fields.pe.textContent = formatRatio(detail.pe_ratio);
        fields.revenue.textContent = formatRevenue(detail.revenue);
        fields.pat.textContent = formatPercent(detail.pat_margin);
        fields.opm.textContent = formatPercent(detail.operating_profit_margin);
        fields.roe.textContent = formatPercent(detail.roe);
        fields.roce.textContent = formatPercent(detail.roce);
        fields.pb.textContent = formatRatio(detail.price_to_book);
        fields.profitCagr.textContent = formatPercent(detail.profit_cagr_3y);
        fields.avgPe.textContent = formatRatio(detail.avg_pe_3y);
        fields.debtEquity.textContent = formatRatio(detail.debt_equity);
        fields.totalDebt.textContent = compactIndian(detail.total_debt);
        fields.promoter.textContent = formatTrendValue(detail.promoter_holding, detail.promoter_trend);
        fields.fii.textContent = formatTrendValue(detail.fii_holding, detail.fii_trend);
        fields.dii.textContent = formatTrendValue(detail.dii_holding, detail.dii_trend);
        fields.retail.textContent = formatTrendValue(detail.retail_holding, detail.retail_trend);
        fields.fiiDii.textContent = formatTrendValue(detail.fii_dii_holding, detail.fii_dii_trend);
        fields.dividendYield.textContent = formatPercent(detail.dividend_yield);
        fields.delivery.textContent = formatPercent(detail.delivery_percent ?? item.delivery_percent);
        fields.description.textContent = detail.description || "Company details unavailable in the current popup cache.";
        chart.setAttribute("points", chartPoints(item.series));
        card.classList.toggle("is-negative", !positive);
        card.classList.toggle("is-mobile-popup", prefersTapPopup);
    };

    const show = (target, keepOpen = false) => {
        const item = tickerData[target.dataset.symbol];
        if (!item) return;
        clearTimeout(hideTimer);
        pinned = keepOpen || prefersTapPopup;
        render(target, item);
        card.classList.add("is-visible");
        card.scrollTop = 0;
        card.setAttribute("aria-hidden", "false");
        requestAnimationFrame(() => placeCard(target));
        if (keepOpen || prefersTapPopup) {
            hydrateDetail(item, target);
        }
    };

    const hide = (force = false) => {
        if (pinned && !force) return;
        hideTimer = window.setTimeout(() => {
            pinned = false;
            card.classList.remove("is-visible");
            card.setAttribute("aria-hidden", "true");
        }, 90);
    };

    const handleEnter = (event) => {
        const target = event.target.closest(".stock-ticker[data-symbol]");
        if (target) show(target, false);
    };
    const handleLeave = (event) => {
        if (event.target.closest(".stock-ticker[data-symbol]")) hide();
    };
    if (!prefersTapPopup) {
        document.addEventListener("pointerover", handleEnter);
        document.addEventListener("mouseover", handleEnter);
        document.addEventListener("pointerout", handleLeave);
        document.addEventListener("mouseout", handleLeave);
    }
    document.addEventListener("focusin", (event) => {
        const target = event.target.closest(".stock-ticker[data-symbol]");
        if (target) show(target, false);
    });
    document.addEventListener("focusout", (event) => {
        if (event.target.closest(".stock-ticker[data-symbol]")) hide();
    });

    document.addEventListener("click", (event) => {
        if (event.target.closest("[data-hover-close]")) {
            hide(true);
            return;
        }
        const ticker = event.target.closest(".stock-ticker[data-symbol]");
        if (ticker) {
            show(ticker, true);
            return;
        }
        const toggle = event.target.closest(".sector-toggle[data-sector-target]");
        if (toggle) {
            const row = document.getElementById(toggle.dataset.sectorTarget);
            if (!row) return;
            const isOpen = !row.hidden;
            row.hidden = isOpen;
            toggle.classList.toggle("is-open", !isOpen);
            return;
        }
        if (pinned && !card.contains(event.target)) {
            hide(true);
        }
    });
})();
