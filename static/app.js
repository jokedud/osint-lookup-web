const $ = (id) => document.getElementById(id);
const results = [];
let es = null;
let currentType = null;
let currentQuery = null;

function detectType(q) {
  if (q.includes("@")) return "email";
  if (/^\+?\d[\d\s().-]*$/.test(q)) return "phone";
  return "username";
}

function saveHistory(q, t) {
  let h = JSON.parse(localStorage.getItem("osint_history") || "[]");
  h = h.filter((e) => !(e.q === q && e.t === t));
  h.unshift({ q, t });
  localStorage.setItem("osint_history", JSON.stringify(h.slice(0, 20)));
  renderHistory();
}

function renderHistory() {
  const h = JSON.parse(localStorage.getItem("osint_history") || "[]");
  $("history").innerHTML = "";
  for (const e of h) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="t">${e.t}</span>${e.q}`;
    li.onclick = () => { $("query").value = e.q; $("type").value = e.t; startScan(); };
    $("history").appendChild(li);
  }
}

function badge(status) {
  return `<span class="badge ${status}">${status.replace("_", " ")}</span>`;
}

function detailsHtml(details) {
  if (!details || !Object.keys(details).length) return "";
  let inner = "";
  for (const [k, v] of Object.entries(details)) {
    inner += `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}\n`;
  }
  return `<details><summary>details</summary><pre>${escapeHtml(inner)}</pre></details>`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function pivotFor(res) {
  let out = "";
  if (res.details && res.details.phoneNumber) {
    out += ` <a class="pivot" href="#" onclick="pivotPhone('${res.details.phoneNumber}');return false">Scan phone</a>`;
  }
  return out;
}

function render() {
  const foundOnly = $("foundOnly").checked;
  const filter = $("filter").value.toLowerCase();
  const disabledTools = new Set(
    [...document.querySelectorAll(".tool-toggle")]
      .filter((c) => !c.checked).map((c) => c.dataset.tool)
  );
  const tbody = $("tbody");
  tbody.innerHTML = "";
  for (const r of results) {
    if (foundOnly && r.status !== "found" && r.status !== "info") continue;
    if (disabledTools.has(r.source)) continue;
    if (filter && !r.site.toLowerCase().includes(filter)) continue;
    const tr = document.createElement("tr");
    const link = r.url ? `<a href="${r.url}" target="_blank" rel="noopener">Verify ↗</a>` : "";
    tr.innerHTML =
      `<td>${escapeHtml(r.site)}${pivotFor(r)}</td>` +
      `<td>${r.source}</td>` +
      `<td>${badge(r.status)}</td>` +
      `<td>${link}</td>` +
      `<td>${detailsHtml(r.details)}</td>`;
    tbody.appendChild(tr);
  }
  renderChips();
}

function renderChips(summary) {
  const counts = { found: 0, checked: 0, rate_limited: 0, error: 0 };
  for (const r of results) {
    counts.checked++;
    if (counts[r.status] !== undefined) counts[r.status]++;
  }
  if (summary) Object.assign(counts, summary);
  $("summary").innerHTML =
    `<span class="chip">found ${counts.found}</span>` +
    `<span class="chip">checked ${counts.checked}</span>` +
    `<span class="chip">rate-limited ${counts.rate_limited}</span>` +
    `<span class="chip">errors ${counts.error}</span>`;
}

function renderToolToggles() {
  const tools = [...new Set(results.map((r) => r.source))];
  const el = $("toolToggles");
  const existing = new Set([...el.querySelectorAll(".tool-toggle")].map((c) => c.dataset.tool));
  for (const t of tools) {
    if (existing.has(t)) continue;
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" class="tool-toggle" data-tool="${t}" checked> ${t}`;
    label.querySelector("input").onchange = render;
    el.appendChild(label);
  }
}

function pivotPhone(num) {
  $("query").value = num;
  $("type").value = "phone";
  startScan();
}

function startScan() {
  const q = $("query").value.trim();
  if (!q) return;
  let t = $("type").value;
  if (t === "auto") t = detectType(q);
  currentType = t; currentQuery = q;

  if (es) es.close();
  results.length = 0;
  $("toolToggles").innerHTML = "";
  $("progress").classList.remove("hidden");
  $("pivotUsername").classList.add("hidden");
  render();

  const url = t === "email" ? `/api/scan/email?email=${encodeURIComponent(q)}`
    : t === "username" ? `/api/scan/username?username=${encodeURIComponent(q)}`
    : `/api/scan/phone?number=${encodeURIComponent(q)}`;

  es = new EventSource(url);
  es.onmessage = (ev) => {
    let res;
    try { res = JSON.parse(ev.data); } catch { return; }
    if (res.detail && !res.site) { console.error(res.detail); return; }
    results.push(res);
    renderToolToggles();
    render();
  };
  es.addEventListener("done", (ev) => {
    $("progress").classList.add("hidden");
    try { renderChips(JSON.parse(ev.data)); } catch { renderChips(); }
    saveHistory(q, t);
    if (t === "email") {
      const btn = $("pivotUsername");
      const local = q.split("@")[0];
      btn.textContent = `Scan username '${local}'`;
      btn.classList.remove("hidden");
      btn.onclick = () => {
        $("query").value = local; $("type").value = "username"; startScan();
      };
    }
    es.close();
  });
  es.onerror = () => {
    $("progress").classList.add("hidden");
    es.close();
  };
}

function download(name, content, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

$("exportJson").onclick = () =>
  download(`osint_${currentType}_${currentQuery}.json`,
    JSON.stringify(results, null, 2), "application/json");

$("exportCsv").onclick = () => {
  const esc = (s) => `"${String(s ?? "").replace(/"/g, '""')}"`;
  const rows = [["source", "category", "site", "status", "url", "details"]];
  for (const r of results)
    rows.push([r.source, r.category, r.site, r.status, r.url || "", JSON.stringify(r.details)]);
  download(`osint_${currentType}_${currentQuery}.csv`,
    rows.map((r) => r.map(esc).join(",")).join("\n"), "text/csv");
};

$("scanBtn").onclick = startScan;
$("query").addEventListener("keydown", (e) => { if (e.key === "Enter") startScan(); });
$("query").addEventListener("input", () => {
  if ($("type").value === "auto") $("type").dataset.detected = detectType($("query").value.trim());
});
$("foundOnly").onchange = render;
$("filter").addEventListener("input", render);
renderHistory();
