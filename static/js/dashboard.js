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
    };
    let hideTimer;

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

    const show = (target) => {
        const item = tickerData[target.dataset.symbol];
        if (!item) return;
        clearTimeout(hideTimer);
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
        chart.setAttribute("points", chartPoints(item.series));
        card.classList.toggle("is-negative", !positive);
        card.classList.add("is-visible");
        card.setAttribute("aria-hidden", "false");
        requestAnimationFrame(() => placeCard(target));
    };

    const hide = () => {
        hideTimer = window.setTimeout(() => {
            card.classList.remove("is-visible");
            card.setAttribute("aria-hidden", "true");
        }, 90);
    };

    const handleEnter = (event) => {
        const target = event.target.closest(".stock-ticker[data-symbol]");
        if (target) show(target);
    };
    const handleLeave = (event) => {
        if (event.target.closest(".stock-ticker[data-symbol]")) hide();
    };
    document.addEventListener("pointerover", handleEnter);
    document.addEventListener("mouseover", handleEnter);
    document.addEventListener("click", handleEnter);
    document.addEventListener("pointerout", handleLeave);
    document.addEventListener("mouseout", handleLeave);
    document.addEventListener("focusin", (event) => {
        const target = event.target.closest(".stock-ticker[data-symbol]");
        if (target) show(target);
    });
    document.addEventListener("focusout", (event) => {
        if (event.target.closest(".stock-ticker[data-symbol]")) hide();
    });
})();
