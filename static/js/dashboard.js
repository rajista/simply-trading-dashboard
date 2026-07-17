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

    const pointerQuery = window.matchMedia("(hover: none), (pointer: coarse), (max-width: 760px)");
    const isTapLayout = () => pointerQuery.matches;
    const chart = card.querySelector("[data-hover-chart]");
    const popupBody = card.querySelector(".ticker-hover-body");
    const closeButton = card.querySelector("[data-hover-close]");
    const analysisLink = card.querySelector("[data-hover-analysis-link]");
    const fields = Object.fromEntries(
        [
            "symbol", "sector", "change", "name", "price", "volume", "signal",
            "five-day", "turnover", "relative-volume", "sector-rank",
            "sector-relative", "month-change", "year-change",
            "accumulation-score", "obv", "pullback", "volume-range",
            "day-open", "day-high", "day-low", "distance-high", "distance-low",
            "market-cap", "growth-1m", "growth-3m", "growth-1y", "growth-5y",
            "pe", "revenue", "pat", "opm", "roe", "roce", "pb",
            "profit-cagr", "avg-pe", "debt-equity", "total-debt", "promoter",
            "fii", "dii", "retail", "fii-dii", "dividend-yield", "delivery",
            "description", "news", "market-news", "event", "event-title",
            "event-date", "headline-context", "selected-headline",
            "context-metrics",
        ].map((key) => [key, card.querySelector(`[data-hover-${key}]`)])
    );

    let hideTimer;
    let pinned = false;
    let lastTrigger = null;
    let dragStartY = null;
    let dragStartHeight = null;
    let suppressOpenUntil = 0;
    const detailRequests = new Map();

    const signed = (value, digits = 2) => {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
        const number = Number(value);
        return `${number >= 0 ? "+" : ""}${number.toFixed(digits)}`;
    };
    const formatPrice = (value) => (
        value === null || value === undefined
            ? "-"
            : Number(value).toLocaleString("en-IN", {maximumFractionDigits: 2})
    );
    const compactIndian = (value) => {
        if (value === null || value === undefined) return "-";
        const number = Number(value);
        if (number >= 10000000) return `${(number / 10000000).toFixed(2)} Cr`;
        if (number >= 100000) return `${(number / 100000).toFixed(2)} L`;
        return number.toLocaleString("en-IN", {maximumFractionDigits: 0});
    };
    const formatPercent = (value) => value === null || value === undefined ? "-" : `${signed(value)}%`;
    const formatRatio = (value, digits = 2) => value === null || value === undefined ? "-" : Number(value).toFixed(digits);
    const formatTrendValue = (value, trend) => {
        const formatted = formatPercent(value);
        return formatted === "-" ? "-" : `${formatted} | ${trend || "chg n/a"}`;
    };
    const setText = (field, value) => {
        if (fields[field]) fields[field].textContent = value;
    };
    const setFlag = (field, enabled) => {
        if (fields[field]) fields[field].classList.toggle("is-on", Boolean(enabled));
    };
    const hasUsefulDetails = (detail) => detail && [
        "pe_ratio", "revenue", "operating_profit_margin", "roe",
        "price_to_book", "promoter_holding", "description", "news",
    ].some((key) => detail[key] !== null && detail[key] !== undefined && detail[key] !== "");

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

    const renderNewsList = (container, news, emptyMessage) => {
        if (!container) return;
        container.textContent = "";
        const items = Array.isArray(news) ? news.slice(0, 6) : [];
        if (!items.length) {
            const empty = document.createElement("li");
            empty.className = "muted-news";
            empty.textContent = emptyMessage;
            container.appendChild(empty);
            return;
        }
        items.forEach((item) => {
            const li = document.createElement("li");
            const link = document.createElement("a");
            link.href = item.url || "#";
            link.textContent = item.title || "Market update";
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            const meta = document.createElement("small");
            meta.textContent = [item.source, item.published || item.time].filter(Boolean).join(" | ");
            li.appendChild(link);
            if (meta.textContent) li.appendChild(meta);
            container.appendChild(li);
        });
    };

    const activateTab = (name) => {
        card.querySelectorAll("[data-popup-tab]").forEach((button) => {
            const active = button.dataset.popupTab === name;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-selected", String(active));
        });
        card.querySelectorAll("[data-popup-panel]").forEach((panel) => {
            panel.classList.toggle("is-active", panel.dataset.popupPanel === name);
        });
        if (popupBody) popupBody.scrollTop = 0;
    };

    const renderHeadlineContext = (item, headlineIndex) => {
        if (!fields["headline-context"]) return;
        const related = Array.isArray(item.market_headlines) ? item.market_headlines : [];
        const selected = related.find((headline) => String(headline.headline_index) === String(headlineIndex))
            || related[0];
        fields["headline-context"].hidden = !selected;
        if (!selected) return;
        setText("selected-headline", selected.title);
        fields["context-metrics"].textContent = "";
        [
            `Today ${formatPercent(item.percent)}`,
            `5D ${formatPercent(item.five_day_change)}`,
            `1M ${formatPercent(item.month_change)}`,
            `Rel vol ${item.relative_volume == null ? "-" : `${Number(item.relative_volume).toFixed(2)}x`}`,
            `Vs sector ${formatPercent(item.sector_relative_change)}`,
        ].forEach((text) => {
            const span = document.createElement("span");
            span.textContent = text;
            fields["context-metrics"].appendChild(span);
        });
    };

    const render = (target, item) => {
        const detail = item.details || {};
        const growth = detail.growth || {};
        const positive = Number(item.percent || 0) >= 0;
        setText("symbol", item.symbol);
        setText("sector", item.sector || "");
        setText("change", `${signed(item.change)} (${signed(item.percent)}%)`);
        fields.change.className = positive ? "positive" : "negative";
        setText("name", item.name || item.symbol);
        setText("price", `Last: ${formatPrice(item.price)}`);
        setText("volume", `Volume: ${compactIndian(item.volume)}`);
        setText("signal", `Signal: ${item.signal || "Unavailable"}`);
        setText("five-day", `5 day: ${formatPercent(item.five_day_change)}`);
        setText("turnover", compactIndian(item.traded_value));
        setText("relative-volume", item.relative_volume == null ? "-" : `${Number(item.relative_volume).toFixed(2)}x`);
        setText("sector-rank", item.sector_rank ? `${item.sector_rank}/${item.sector_stock_count || "-"}` : "-");
        setText("sector-relative", formatPercent(item.sector_relative_change));
        setText("month-change", formatPercent(item.month_change));
        setText("year-change", formatPercent(item.year_change));
        setText("accumulation-score", `${item.accumulation_score || 0}/3`);
        setFlag("obv", item.obv_divergence);
        setFlag("pullback", item.quiet_pullback);
        setFlag("volume-range", item.volume_range_signal);
        setText("day-open", formatPrice(item.day_open));
        setText("day-high", formatPrice(item.day_high));
        setText("day-low", formatPrice(item.day_low));
        setText("distance-high", formatPercent(item.high52_distance));
        setText("distance-low", formatPercent(item.low52_distance));
        setText("market-cap", compactIndian(detail.market_cap ?? item.market_cap ?? item.free_float_market_cap));
        setText("growth-1m", formatPercent(growth["1m"]));
        setText("growth-3m", formatPercent(growth["3m"]));
        setText("growth-1y", formatPercent(growth["1y"] ?? item.year_change));
        setText("growth-5y", formatPercent(growth["5y"]));
        setText("pe", formatRatio(detail.pe_ratio));
        setText("revenue", compactIndian(detail.revenue));
        setText("pat", formatPercent(detail.pat_margin));
        setText("opm", formatPercent(detail.operating_profit_margin));
        setText("roe", formatPercent(detail.roe));
        setText("roce", formatPercent(detail.roce));
        setText("pb", formatRatio(detail.price_to_book));
        setText("profit-cagr", formatPercent(detail.profit_cagr_3y));
        setText("avg-pe", formatRatio(detail.avg_pe_3y));
        setText("debt-equity", formatRatio(detail.debt_equity));
        setText("total-debt", compactIndian(detail.total_debt));
        setText("promoter", formatTrendValue(detail.promoter_holding, detail.promoter_trend));
        setText("fii", formatTrendValue(detail.fii_holding, detail.fii_trend));
        setText("dii", formatTrendValue(detail.dii_holding, detail.dii_trend));
        setText("retail", formatTrendValue(detail.retail_holding, detail.retail_trend));
        setText("fii-dii", formatTrendValue(detail.fii_dii_holding, detail.fii_dii_trend));
        setText("dividend-yield", formatPercent(detail.dividend_yield));
        setText("delivery", formatPercent(detail.delivery_percent ?? item.delivery_percent));
        setText("description", detail.description || "Company details unavailable in the current popup cache.");
        if (analysisLink) analysisLink.href = `/stock/${encodeURIComponent(item.symbol)}`;
        renderNewsList(fields.news, detail.news, "No stock-specific news found in the current cache.");
        const relatedMarketNews = Array.isArray(item.market_headlines) ? item.market_headlines : [];
        const relatedMarketBox = fields["market-news"]?.closest(".stock-news-box");
        if (relatedMarketBox) relatedMarketBox.hidden = !relatedMarketNews.length;
        renderNewsList(fields["market-news"], relatedMarketNews, "");
        const event = item.next_event;
        if (fields.event) {
            fields.event.hidden = !event;
            setText("event-title", event?.title || "");
            setText("event-date", [event?.type, event?.date].filter(Boolean).join(" | "));
        }
        renderHeadlineContext(item, target?.dataset?.headlineIndex);
        if (chart) chart.setAttribute("points", chartPoints(item.series));
        card.classList.toggle("is-negative", !positive);
        card.classList.toggle("is-mobile-popup", isTapLayout());
    };

    const hydrateDetail = (item, target) => {
        const hasNews = Array.isArray(item.details?.news) && item.details.news.length >= 3;
        if ((hasUsefulDetails(item.details) && hasNews) || detailRequests.has(item.symbol)) return;
        setText("description", "Loading precomputed company details...");
        const request = fetch(`/api/stocks/${encodeURIComponent(item.symbol)}`)
            .then((response) => response.ok ? response.json() : null)
            .then((detail) => {
                if (!detail || !Object.keys(detail).length) return;
                item.details = {...(item.details || {}), ...detail};
                if (card.classList.contains("is-visible") && fields.symbol.textContent === item.symbol) {
                    render(target, item);
                }
            })
            .catch(() => null)
            .finally(() => detailRequests.delete(item.symbol));
        detailRequests.set(item.symbol, request);
    };

    const prefetchDetailSnapshot = () => {
        fetch("/api/stock-details", {headers: {"Accept": "application/json"}})
            .then((response) => response.ok ? response.json() : null)
            .then((payload) => {
                const details = payload?.details || {};
                Object.entries(details).forEach(([symbol, detail]) => {
                    if (tickerData[symbol]) {
                        tickerData[symbol].details = {...(tickerData[symbol].details || {}), ...detail};
                    }
                });
            })
            .catch(() => null);
    };
    if ("requestIdleCallback" in window) {
        window.requestIdleCallback(prefetchDetailSnapshot, {timeout: 2500});
    } else {
        window.setTimeout(prefetchDetailSnapshot, 700);
    }

    const placeCard = (target) => {
        if (isTapLayout()) {
            card.style.left = "";
            card.style.top = "";
            return;
        }
        const targetBox = target.getBoundingClientRect();
        const cardBox = card.getBoundingClientRect();
        let left = targetBox.left + Math.min(targetBox.width, 36);
        let top = targetBox.bottom + 8;
        if (left + cardBox.width > window.innerWidth - 10) left = window.innerWidth - cardBox.width - 10;
        if (top + cardBox.height > window.innerHeight - 10) top = targetBox.top - cardBox.height - 8;
        card.style.left = `${Math.max(10, left)}px`;
        card.style.top = `${Math.max(10, top)}px`;
    };

    const show = (target, keepOpen = false) => {
        if (Date.now() < suppressOpenUntil) return;
        const item = tickerData[target.dataset.symbol];
        if (!item) return;
        window.clearTimeout(hideTimer);
        pinned = keepOpen || isTapLayout();
        lastTrigger = target;
        activateTab("overview");
        render(target, item);
        card.classList.add("is-visible");
        card.classList.remove("is-sheet-expanded");
        card.style.height = "";
        card.style.transform = "";
        card.setAttribute("aria-hidden", "false");
        if (popupBody) popupBody.scrollTop = 0;
        document.body.classList.toggle("stock-popup-open", isTapLayout());
        window.requestAnimationFrame(() => {
            placeCard(target);
            if (isTapLayout()) closeButton?.focus({preventScroll: true});
        });
        hydrateDetail(item, target);
    };

    const closePopup = () => {
        window.clearTimeout(hideTimer);
        suppressOpenUntil = Date.now() + 350;
        pinned = false;
        dragStartY = null;
        dragStartHeight = null;
        card.classList.remove("is-visible", "is-sheet-expanded");
        card.setAttribute("aria-hidden", "true");
        card.style.height = "";
        card.style.transform = "";
        document.body.classList.remove("stock-popup-open");
        if (card.contains(document.activeElement)) document.activeElement.blur();
        lastTrigger = null;
    };

    const hide = (force = false) => {
        if (force) {
            closePopup();
            return;
        }
        if (pinned && !force) return;
        hideTimer = window.setTimeout(() => {
            pinned = false;
            card.classList.remove("is-visible");
            card.setAttribute("aria-hidden", "true");
            document.body.classList.remove("stock-popup-open");
        }, 140);
    };

    closeButton?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        closePopup();
    });

    if (!isTapLayout()) {
        document.addEventListener("pointerover", (event) => {
            const target = event.target.closest(".stock-ticker[data-symbol]");
            if (target) show(target, false);
        });
        document.addEventListener("pointerout", (event) => {
            if (event.target.closest(".stock-ticker[data-symbol]")) hide();
        });
        card.addEventListener("pointerenter", () => window.clearTimeout(hideTimer));
        card.addEventListener("pointerleave", () => hide());
    }

    document.addEventListener("focusin", (event) => {
        const target = event.target.closest(".stock-ticker[data-symbol]");
        if (target) show(target, false);
    });
    document.addEventListener("focusout", (event) => {
        if (event.target.closest(".stock-ticker[data-symbol]")) hide();
    });

    document.addEventListener("click", (event) => {
        const tab = event.target.closest("[data-popup-tab]");
        if (tab) {
            activateTab(tab.dataset.popupTab);
            return;
        }
        if (event.target.closest("[data-hover-close]")) {
            hide(true);
            return;
        }
        const ticker = event.target.closest(".stock-ticker[data-symbol]");
        if (ticker) {
            show(ticker, true);
            return;
        }
        const moverTab = event.target.closest("[data-mover-tab]");
        if (moverTab) {
            const group = moverTab.closest(".market-tables");
            group?.querySelectorAll("[data-mover-tab]").forEach((button) => button.classList.toggle("is-active", button === moverTab));
            group?.querySelectorAll("[data-mover-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.moverPanel === moverTab.dataset.moverTab));
            return;
        }
        const collapse = event.target.closest("[data-collapse-target]");
        if (collapse) {
            const content = document.getElementById(collapse.dataset.collapseTarget);
            if (!content) return;
            const collapsed = content.classList.toggle("is-collapsed");
            collapse.textContent = collapsed ? "Expand" : "Collapse";
            collapse.setAttribute("aria-expanded", String(!collapsed));
            return;
        }
        const heatmapExpand = event.target.closest("[data-heatmap-expand]");
        if (heatmapExpand) {
            const heatmap = heatmapExpand.closest(".heatmap");
            if (!heatmap) return;
            const expanded = heatmap.classList.toggle("is-expanded");
            document.body.classList.toggle("heatmap-expanded", expanded);
            heatmapExpand.textContent = expanded ? "Close map" : "Expand map";
            return;
        }
        const toggle = event.target.closest(".sector-toggle[data-sector-target]");
        if (toggle) {
            const row = document.getElementById(toggle.dataset.sectorTarget);
            if (!row) return;
            row.hidden = !row.hidden;
            toggle.classList.toggle("is-open", !row.hidden);
            return;
        }
        if (pinned && !card.contains(event.target)) hide(true);
    });

    document.addEventListener("keydown", (event) => {
        const expandedHeatmap = document.querySelector(".heatmap.is-expanded");
        if (event.key === "Escape" && expandedHeatmap) {
            expandedHeatmap.classList.remove("is-expanded");
            document.body.classList.remove("heatmap-expanded");
            const expandButton = expandedHeatmap.querySelector("[data-heatmap-expand]");
            if (expandButton) expandButton.textContent = "Expand map";
            return;
        }
        if (!card.classList.contains("is-visible")) return;
        if (event.key === "Escape") {
            event.preventDefault();
            hide(true);
            return;
        }
        if (event.key !== "Tab" || !isTapLayout()) return;
        const focusable = [...card.querySelectorAll("button, a[href]")].filter((element) => !element.hidden);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });

    const dragHandle = card.querySelector("[data-popup-drag-handle]");
    dragHandle?.addEventListener("touchstart", (event) => {
        if (!isTapLayout() || event.target.closest("button, a")) return;
        dragStartY = event.touches[0]?.clientY ?? null;
        dragStartHeight = card.offsetHeight;
    }, {passive: true});
    dragHandle?.addEventListener("touchmove", (event) => {
        if (dragStartY === null) return;
        const delta = (event.touches[0]?.clientY ?? dragStartY) - dragStartY;
        if (delta < 0) {
            const maximum = window.innerHeight - 8;
            card.style.height = `${Math.min(maximum, (dragStartHeight || card.offsetHeight) + Math.abs(delta))}px`;
        } else {
            card.style.transform = `translateY(${Math.min(delta, 140)}px)`;
        }
        event.preventDefault();
    }, {passive: false});
    dragHandle?.addEventListener("touchend", (event) => {
        const endY = event.changedTouches[0]?.clientY ?? dragStartY;
        const delta = dragStartY === null ? 0 : endY - dragStartY;
        card.style.transform = "";
        card.style.height = "";
        dragStartY = null;
        dragStartHeight = null;
        if (delta > 85) closePopup();
        else if (delta < -40) card.classList.add("is-sheet-expanded");
    }, {passive: true});
})();

(() => {
    const dialog = document.getElementById("fii-dii-dialog");
    const content = dialog?.querySelector("[data-fii-dii-content]");
    const triggers = document.querySelectorAll("[data-fii-dii-open]");
    if (!dialog || !content || !triggers.length) return;

    let dataPromise = null;
    let previouslyFocused = null;
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[character]);
    const crore = (value) => {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
        const number = Number(value);
        return `${number >= 0 ? "+" : "-"}₹${Math.abs(number).toLocaleString("en-IN", {maximumFractionDigits: 0})} Cr`;
    };
    const tone = (value) => Number(value || 0) >= 0 ? "positive" : "negative";

    const stockList = (items) => {
        if (!Array.isArray(items) || !items.length) return '<li><span class="unavailable">No classified deals</span></li>';
        return items.map((item) => `
            <li>
                <a href="/stock/${encodeURIComponent(item.symbol)}" title="${escapeHtml(item.name)}">${escapeHtml(item.symbol)}</a>
                <b>₹${Number(item.value_crore || 0).toLocaleString("en-IN", {maximumFractionDigits: 1})} Cr</b>
            </li>
        `).join("");
    };

    const categoryBlock = (name, data) => `
        <section class="institution-category">
            <h4>${escapeHtml(name)}</h4>
            <div class="institution-side-grid">
                <div class="buy"><h5>Top disclosed buys</h5><ul class="institution-stock-list">${stockList(data?.buy)}</ul></div>
                <div class="sell"><h5>Top disclosed sells</h5><ul class="institution-stock-list">${stockList(data?.sell)}</ul></div>
            </div>
        </section>
    `;

    const render = (payload) => {
        if (!payload || payload.status !== "ready") {
            content.innerHTML = '<div class="institution-flow-loading"><strong>Institutional history is warming</strong><span>Please reopen this panel shortly.</span></div>';
            return;
        }
        const periodCards = (payload.periods || []).map((period) => `
            <article class="flow-period-card">
                <strong>${escapeHtml(period.label)}</strong>
                <span>FII net</span><b class="${tone(period.fii)}">${crore(period.fii)}</b>
                <span>DII net</span><b class="${tone(period.dii)}">${crore(period.dii)}</b>
                <small class="${period.complete ? "" : "partial"}">${period.sessions} sessions · ${period.complete ? "complete window" : `partial coverage: ${escapeHtml(period.coverage)}`}</small>
            </article>
        `).join("");
        const chartRows = (payload.history || []).map((row) => `
            <div class="flow-day-row">
                <time>${escapeHtml(row.date_label)}</time>
                <div class="flow-day-bars" title="FII ${crore(row.fii)}; DII ${crore(row.dii)}">
                    <i class="fii" style="width:${Math.max(1.5, Number(row.fii_width || 0))}%"></i>
                    <i class="dii" style="width:${Math.max(1.5, Number(row.dii_width || 0))}%"></i>
                </div>
                <b class="${tone(row.fii)}">${crore(row.fii)}</b>
                <b class="${tone(row.dii)}">${crore(row.dii)}</b>
            </div>
        `).join("");
        const deals = payload.institutional_deals || {};
        const periodEntries = ["latest", "1m", "6m"]
            .filter((key) => deals.periods?.[key])
            .map((key) => [key, deals.periods[key]]);
        const dealTabs = periodEntries.map(([key, period], index) => `
            <button type="button" class="${index === 0 ? "is-active" : ""}" data-institution-period="${escapeHtml(key)}">${escapeHtml(period.label)}</button>
        `).join("");
        const dealPanels = periodEntries.map(([key, period], index) => `
            <div class="institution-deal-period" data-institution-panel="${escapeHtml(key)}" ${index === 0 ? "" : "hidden"}>
                <div class="institution-deal-grid">
                    ${categoryBlock("FII / FPI", period.categories?.["FII/FPI"])}
                    ${categoryBlock("DII", period.categories?.DII)}
                </div>
            </div>
        `).join("");
        content.innerHTML = `
            <div class="flow-period-grid">${periodCards}</div>
            <section class="flow-chart-panel">
                <h3>Past 7 trading sessions · net cash activity</h3>
                <div class="flow-chart-legend"><span><i class="fii"></i>FII / FPI</span><span><i class="dii"></i>DII</span></div>
                ${chartRows || '<div class="unavailable">No recent sessions available</div>'}
            </section>
            <section class="institution-deal-panel">
                <h3>Stocks institutions bought and sold most · disclosed bulk/block deals</h3>
                <div class="institution-deal-tabs">${dealTabs}</div>
                ${dealPanels || '<div class="unavailable">No explicitly classified institutional deals available</div>'}
                <p class="institution-flow-note">Latest disclosed deal date: ${escapeHtml(deals.latest_date || "unavailable")}. ${escapeHtml(payload.source_note || "")} Ambiguous client names are excluded, so these lists are not a complete record of all institutional trading.</p>
            </section>
        `;
    };

    const load = () => {
        if (!dataPromise) {
            dataPromise = fetch("/api/fii-dii-insights", {headers: {"Accept": "application/json"}})
                .then((response) => response.ok ? response.json() : Promise.reject(new Error("Unavailable")))
                .then((payload) => { render(payload); return payload; })
                .catch(() => {
                    dataPromise = null;
                    content.innerHTML = '<div class="institution-flow-loading"><strong>Institutional data is temporarily unavailable</strong><span>The last cached view could not be loaded. Please try again shortly.</span></div>';
                });
        }
        return dataPromise;
    };
    const open = () => {
        previouslyFocused = document.activeElement;
        dialog.hidden = false;
        document.body.classList.add("stock-popup-open");
        dialog.querySelector("button[data-fii-dii-close]")?.focus({preventScroll: true});
        load();
    };
    const close = () => {
        dialog.hidden = true;
        document.body.classList.remove("stock-popup-open");
        previouslyFocused?.focus?.({preventScroll: true});
    };

    triggers.forEach((trigger) => {
        trigger.addEventListener("click", open);
        trigger.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                open();
            }
        });
    });
    dialog.addEventListener("click", (event) => {
        const closer = event.target.closest("[data-fii-dii-close]");
        if (closer) { close(); return; }
        const periodButton = event.target.closest("[data-institution-period]");
        if (!periodButton) return;
        dialog.querySelectorAll("[data-institution-period]").forEach((button) => button.classList.toggle("is-active", button === periodButton));
        dialog.querySelectorAll("[data-institution-panel]").forEach((panel) => { panel.hidden = panel.dataset.institutionPanel !== periodButton.dataset.institutionPeriod; });
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !dialog.hidden) close();
    });
    if ("requestIdleCallback" in window) window.requestIdleCallback(load, {timeout: 3500});
    else window.setTimeout(load, 1200);
})();
