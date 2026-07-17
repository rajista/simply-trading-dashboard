(() => {
    const dataElement = document.getElementById("stock-page-data");
    if (!dataElement) return;
    let stock = {};
    try {
        stock = JSON.parse(dataElement.textContent || "{}");
    } catch {
        return;
    }

    const chart = document.querySelector("[data-stock-page-chart]");
    const series = stock.row?.chart_series || [];
    if (chart && series.length > 1) {
        const low = Math.min(...series);
        const high = Math.max(...series);
        const range = high - low || 1;
        const points = series.map((value, index) => {
            const x = index / (series.length - 1) * 760;
            const y = 235 - (value - low) / range * 220;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        }).join(" ");
        chart.setAttribute("points", points);
        chart.classList.toggle("negative", series[series.length - 1] < series[0]);
    }

    const newsList = document.querySelector("[data-stock-page-news]");
    const renderNews = (items) => {
        if (!newsList || !Array.isArray(items) || !items.length) return;
        newsList.textContent = "";
        items.slice(0, 6).forEach((item) => {
            const row = document.createElement("li");
            const link = document.createElement("a");
            link.href = item.url;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
            link.textContent = item.title;
            const meta = document.createElement("small");
            meta.textContent = [item.source, item.published].filter(Boolean).join(" | ");
            row.append(link, meta);
            newsList.appendChild(row);
        });
    };
    if ((stock.detail?.news || []).length < 3 && stock.symbol) {
        fetch(`/api/stocks/${encodeURIComponent(stock.symbol)}`, {headers: {"Accept": "application/json"}})
            .then((response) => response.ok ? response.json() : null)
            .then((detail) => renderNews(detail?.news))
            .catch(() => null);
    }

    const button = document.querySelector("[data-stock-ai]");
    const result = document.querySelector("[data-stock-ai-result]");
    if (!button || !result) return;

    const addList = (parent, title, items) => {
        const section = document.createElement("section");
        const heading = document.createElement("h4");
        heading.textContent = title;
        const list = document.createElement("ul");
        (Array.isArray(items) ? items : []).forEach((value) => {
            const item = document.createElement("li");
            item.textContent = value;
            list.appendChild(item);
        });
        section.append(heading, list);
        parent.appendChild(section);
    };

    const render = (analysis) => {
        result.textContent = "";
        result.hidden = false;
        const head = document.createElement("div");
        const verdict = document.createElement("strong");
        verdict.className = `ai-verdict verdict-${String(analysis.verdict || "neutral").toLowerCase()}`;
        verdict.textContent = analysis.verdict || "Neutral";
        const source = document.createElement("span");
        source.textContent = analysis.generated_by === "gemini" ? "Gemini grounded analysis" : "Rules-based fallback";
        head.append(verdict, source);
        const summary = document.createElement("p");
        summary.textContent = analysis.executive_summary || "Analysis unavailable.";
        result.append(head, summary);
        [["Technical view", analysis.technical_view], ["Valuation view", analysis.valuation_view], ["Peer context", analysis.peer_context]].forEach(([title, value]) => {
            const section = document.createElement("section");
            const heading = document.createElement("h4");
            heading.textContent = title;
            const text = document.createElement("p");
            text.textContent = value || "Unavailable";
            section.append(heading, text);
            result.appendChild(section);
        });
        const columns = document.createElement("div");
        columns.className = "ai-analysis-columns";
        addList(columns, "Supporting evidence", analysis.strengths);
        addList(columns, "Risks and conflicts", analysis.risks);
        addList(columns, "What to monitor", analysis.watch_items);
        result.appendChild(columns);
        if (analysis.fallback_reason) {
            const fallback = document.createElement("small");
            fallback.textContent = analysis.fallback_reason;
            result.appendChild(fallback);
        }
        const disclaimer = document.createElement("small");
        disclaimer.textContent = [analysis.generated_at, analysis.disclaimer].filter(Boolean).join(" | ");
        result.appendChild(disclaimer);
    };

    button.addEventListener("click", () => {
        const original = button.textContent;
        button.disabled = true;
        button.textContent = "Analysing cached evidence...";
        fetch(`/api/stocks/${encodeURIComponent(button.dataset.symbol)}/analysis`, {
            method: "POST",
            headers: {"Accept": "application/json"},
        })
            .then((response) => response.ok ? response.json() : Promise.reject(new Error("Analysis request failed")))
            .then(render)
            .catch(() => {
                result.hidden = false;
                result.textContent = "Analysis is temporarily unavailable. Please retry after the market cache refreshes.";
            })
            .finally(() => {
                button.disabled = false;
                button.textContent = original;
            });
    });
})();
