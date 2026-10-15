(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { page: 1, pages: 1, selected: null, section: "basic", searchToken: 0, detailToken: 0 };
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = String(text);
    if (className) element.className = className;
    return element;
  };
  function error(message) {
    $("catalog-error").textContent = message || "";
    $("catalog-error").hidden = !message;
  }
  async function get(url) {
    const response = await fetch(url, { credentials: "same-origin" });
    if (response.status === 401) throw new Error("로그인이 만료되었습니다. 다시 로그인해 주세요.");
    if (!response.ok) throw new Error(`데이터를 불러오지 못했습니다. (${response.status})`);
    return response.json();
  }
  const formatted = (value) => value === null || value === undefined ? "—" : typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
  function sourceHeading(source) {
    const box = node("section", null, "catalog-source");
    box.append(node("h2", source.table_name + (source.field_name ? "." + source.field_name : "")));
    const info = node("div", null, "catalog-source-info");
    info.append(node("div", `${source.source_file} · ${source.row_number}행${source.ctid ? " · " + source.ctid : ""}`));
    if (source.long_file) info.append(node("div", `${source.long_file}:L${source.long_line}`));
    box.append(info);
    return box;
  }
  function rawDisclosure(value, title = "원문 JSON") {
    const details = node("details");
    details.append(node("summary", title), node("pre", value));
    return details;
  }
  function valueTable(entries) {
    const table = node("table", null, "catalog-value-table");
    const body = node("tbody");
    entries.forEach(([key, value]) => {
      const row = node("tr");
      row.append(node("th", key), node("td", formatted(value)));
      body.append(row);
    });
    table.append(body);
    return table;
  }
  function renderDetail(data) {
    const panel = $("catalog-panel");
    panel.replaceChildren();
    panel.setAttribute("aria-busy", "false");
    if (!data.sources.length) {
      panel.append(node("p", "이 영역의 적재된 데이터가 없습니다.", "catalog-empty"));
      return;
    }
    data.sources.forEach((source) => {
      const box = sourceHeading(source);
      if (data.section === "basic") {
        const entries = Object.entries(source.payload).filter(([, value]) => value !== null && value !== "");
        box.append(valueTable(entries));
      } else if (data.section === "specs") {
        const table = node("table", null, "catalog-value-table catalog-specs");
        const head = node("thead"), headerRow = node("tr"), body = node("tbody");
        ["분류", "항목", "값"].forEach((text) => headerRow.append(node("th", text)));
        head.append(headerRow);
        source.specs.forEach((spec) => {
          const row = node("tr");
          [spec.group, spec.name, spec.value].forEach((value) => row.append(node("td", value)));
          body.append(row);
        });
        table.append(head, body);
        box.append(table, rawDisclosure(source.raw));
      } else if (data.section === "features") {
        source.features.forEach((feature) => {
          const article = node("article", null, "catalog-feature");
          if (feature.title) article.append(node("h3", feature.title));
          if (feature.subtitle) article.append(node("p", feature.subtitle));
          if (feature.body) article.append(node("p", feature.body));
          if (feature.footnote) {
            const footnote = node("details");
            footnote.append(node("summary", "각주"), node("p", feature.footnote, "catalog-footnote"));
            article.append(footnote);
          }
          if (feature.media.length) {
            const media = node("details");
            media.append(node("summary", `미디어 참조 ${feature.media.length}개`));
            feature.media.forEach((item) => {
              media.append(node("pre", (item.description ? item.description + "\n" : "") + item.url));
            });
            article.append(media);
          }
          box.append(article);
        });
        if (!source.features.length) box.append(node("p", source.plain, "catalog-document-text"));
        box.append(rawDisclosure(source.raw));
      } else {
        box.append(node("div", source.plain, "catalog-document-text"), rawDisclosure(source.raw, "원문 보기"));
      }
      panel.append(box);
    });
  }
  async function loadDetail() {
    if (!state.selected) return;
    const token = ++state.detailToken;
    const panel = $("catalog-panel");
    panel.setAttribute("aria-busy", "true");
    panel.replaceChildren(node("p", "불러오는 중…", "catalog-empty"));
    try {
      const { country, sku } = state.selected;
      const data = await get(`/api/products/${encodeURIComponent(country)}/${encodeURIComponent(sku)}?section=${state.section}`);
      if (token === state.detailToken) renderDetail(data);
    } catch (exc) {
      if (token === state.detailToken) {
        panel.setAttribute("aria-busy", "false");
        panel.replaceChildren(node("p", exc.message, "catalog-empty"));
      }
    }
  }
  function selectProduct(product) {
    state.selected = product;
    $("catalog-detail-name").textContent = product.name || product.sku;
    $("catalog-detail-country").textContent = `${product.country.toUpperCase()}${product.color ? " · " + product.color : ""}`;
    $("catalog-detail-sku").textContent = product.sku;
    $("catalog-copy-sku").hidden = false;
    document.querySelectorAll("#catalog-results tr").forEach((row) => row.setAttribute("aria-selected", String(row.dataset.sku === product.sku && row.dataset.country === product.country)));
    loadDetail();
  }
  async function search() {
    const token = ++state.searchToken;
    const params = new URLSearchParams(new FormData($("catalog-form")));
    params.set("page", state.page);
    error("");
    $("catalog-result-count").textContent = "검색 중…";
    $("catalog-results").setAttribute("aria-busy", "true");
    try {
      const data = await get(`/api/products?${params}`);
      if (token !== state.searchToken) return;
      const body = $("catalog-results");
      body.replaceChildren();
      data.items.forEach((product) => {
        const row = node("tr"), cell = node("td"), button = node("button", null, "catalog-result-button");
        row.dataset.sku = product.sku;
        row.dataset.country = product.country;
        row.setAttribute("aria-selected", "false");
        button.type = "button";
        button.append(node("strong", product.sku), node("span", product.name));
        if (product.color) button.append(node("span", product.color));
        button.addEventListener("click", () => selectProduct(product));
        cell.append(button);
        row.append(node("td", product.country.toUpperCase()), cell);
        body.append(row);
      });
      state.pages = Math.max(1, Math.ceil(data.total / data.page_size));
      $("catalog-result-count").textContent = `${data.total.toLocaleString()}개 제품`;
      $("catalog-page-number").textContent = `${state.page} / ${state.pages}`;
      $("catalog-prev").disabled = state.page <= 1;
      $("catalog-next").disabled = state.page >= state.pages;
      $("catalog-no-results").hidden = data.items.length !== 0;
      if (data.items.length) {
        selectProduct(data.items.find((p) => state.selected && p.sku === state.selected.sku && p.country === state.selected.country) || data.items[0]);
      } else {
        ++state.detailToken;
        state.selected = null;
        $("catalog-detail-name").textContent = "제품 선택";
        $("catalog-detail-sku").textContent = "";
        $("catalog-detail-country").textContent = "";
        $("catalog-copy-sku").hidden = true;
        $("catalog-panel").replaceChildren(node("p", "선택된 제품이 없습니다.", "catalog-empty"));
      }
    } catch (exc) {
      if (token === state.searchToken) {
        error(exc.message);
        $("catalog-result-count").textContent = "검색 실패";
      }
    } finally {
      if (token === state.searchToken) $("catalog-results").setAttribute("aria-busy", "false");
    }
  }
  $("catalog-form").addEventListener("submit", (event) => { event.preventDefault(); state.page = 1; search(); });
  ["catalog-country", "catalog-scope"].forEach((id) => $(id).addEventListener("change", () => { state.page = 1; search(); }));
  $("catalog-reset").addEventListener("click", () => { $("catalog-form").reset(); state.page = 1; search(); });
  $("catalog-export").addEventListener("click", () => {
    const params = new URLSearchParams(new FormData($("catalog-form")));
    window.location.assign(`/api/products/export?${params}`);
  });
  $("catalog-prev").addEventListener("click", () => { if (state.page > 1) { state.page--; search(); } });
  $("catalog-next").addEventListener("click", () => { if (state.page < state.pages) { state.page++; search(); } });
  const tabs = [...document.querySelectorAll(".catalog-tabs [role=tab]")];
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => {
      state.section = tab.dataset.section;
      tabs.forEach((other) => { other.setAttribute("aria-selected", String(other === tab)); other.tabIndex = other === tab ? 0 : -1; });
      $("catalog-panel").setAttribute("aria-labelledby", tab.id);
      loadDetail();
    });
    tab.addEventListener("keydown", (event) => {
      let next = null;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== null) { event.preventDefault(); tabs[next].focus(); tabs[next].click(); }
    });
  });
  $("catalog-copy-sku").addEventListener("click", async () => {
    if (!state.selected) return;
    try { await navigator.clipboard.writeText(state.selected.sku); }
    catch (_) { error("클립보드 접근이 제한되어 있습니다. SKU 텍스트를 직접 선택해 주세요."); }
  });
  get("/api/products/stats").then((stats) => {
    $("catalog-summary").textContent = `${stats.total_products.toLocaleString()}개 · ${(stats.size_bytes / 1048576).toFixed(1)} MB`;
    const box = $("catalog-import-status");
    if (!stats.countries.length) box.append(node("p", "적재된 데이터가 없습니다.", "catalog-import-entry"));
    stats.countries.forEach((item) => {
      const div = node("div", null, "catalog-import-entry");
      div.append(node("strong", `${item.country.toUpperCase()} · ${item.product_count.toLocaleString()}개`));
      div.append(node("div", item.workbook), node("div", item.long_file || ""));
      div.append(node("div", `적재 ${new Date(item.imported_at).toLocaleString()} · 미해결 참조 ${item.unresolved_refs}건`));
      box.append(div);
    });
  }).catch((exc) => error(exc.message));
  search();
})();
