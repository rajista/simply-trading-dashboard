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
        description: card.querySelector("[data-hover-description]"),
    };
    let hideTimer;
    let pinned = false;
    const detailCache = {};
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

    const setFlag = (element, enabled) => {
        if (!element) return;
        element.classList.toggle("is-on", Boolean(enabled));
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

    const show = (target, keepOpen = false) => {
        const item = tickerData[target.dataset.symbol];
        if (!item) return;
        clearTimeout(hideTimer);
        pinned = keepOpen || prefersTapPopup;
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
        fields.growth1m.textContent = "-";
        fields.growth3m.textContent = "-";
        fields.growth1y.textContent = "-";
        fields.growth5y.textContent = "-";
        fields.pe.textContent = "-";
        fields.revenue.textContent = "-";
        fields.pat.textContent = "-";
        fields.description.textContent = "Loading company details...";
        chart.setAttribute("points", chartPoints(item.series));
        card.classList.toggle("is-negative", !positive);
        card.classList.toggle("is-mobile-popup", prefersTapPopup);
        card.classList.add("is-visible");
        card.scrollTop = 0;
        card.setAttribute("aria-hidden", "false");
        requestAnimationFrame(() => placeCard(target));
        loadDetails(item.symbol);
    };

    const applyDetails = (symbol, detail) => {
        if (!card.classList.contains("is-visible") || fields.symbol.textContent !== symbol) return;
        const growth = detail.growth || {};
        fields.growth1m.textContent = `${signed(growth["1m"])}%`;
        fields.growth3m.textContent = `${signed(growth["3m"])}%`;
        fields.growth1y.textContent = `${signed(growth["1y"])}%`;
        fields.growth5y.textContent = `${signed(growth["5y"])}%`;
        fields.pe.textContent = detail.pe_ratio === null || detail.pe_ratio === undefined ? "-" : Number(detail.pe_ratio).toFixed(2);
        fields.revenue.textContent = formatRevenue(detail.revenue);
        fields.pat.textContent = detail.pat_margin === null || detail.pat_margin === undefined ? "-" : `${Number(detail.pat_margin).toFixed(2)}%`;
        fields.description.textContent = detail.description || "Business description unavailable.";
    };

    const loadDetails = async (symbol) => {
        if (detailCache[symbol]) {
            applyDetails(symbol, detailCache[symbol]);
            return;
        }
        try {
            const response = await fetch(`/api/stocks/${encodeURIComponent(symbol)}`);
            if (!response.ok) throw new Error("detail request failed");
            const detail = await response.json();
            detailCache[symbol] = detail;
            applyDetails(symbol, detail);
        } catch {
            fields.description.textContent = "Company details temporarily unavailable.";
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
