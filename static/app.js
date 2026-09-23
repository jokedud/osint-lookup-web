const $ = (id) => document.getElementById(id);
const results = [];
let es = null;
let currentType = null;
let currentQuery = null;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function safeHref(url) {
  try {
    const u = new URL(url);
    if (u.protocol === "http:" || u.protocol === "https:") return u.href;
  } catch { }
  return null;
}

function linkHtml(url) {
  const safe = safeHref(url);
  if (!safe) return url ? `<span>${esc(url)}</span>` : "";
  return `<a href="${esc(safe)}" target="_blank" rel="noopener noreferrer">Verify ↗</a>`;
}

function detectType(q) {
  if (q.includes("@")) return "email";
  if (/^\+?\d[\d\s().-]*$/.test(q)) return "phone";
  return "username";
}

function getToken() {
  return localStorage.getItem("osint_access_token") || "";
}

function setToken(t) {
  if (t) localStorage.setItem("osint_access_token", t);
  else localStorage.removeItem("osint_access_token");
  renderTokenBox();
}

function renderTokenBox() {
  const box = $("tokenBox");
  if (!box) return;
  box.classList.toggle("hidden", !box.dataset.forced && !getToken());
}

function showTokenBox() {
  const box = $("tokenBox");
  box.dataset.forced = "1";
  box.classList.remove("hidden");
  $("tokenInput").focus();
}

function showError(msg) {
  const el = $("scanError");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function clearError() {
  $("scanError").classList.add("hidden");
  $("scanError").textContent = "";
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
    li.innerHTML = `<span class="t">${esc(e.t)}</span>${esc(e.q)}`;
    li.onclick = () => { $("query").value = e.q; $("type").value = e.t; startScan(); };
    $("history").appendChild(li);
  }
}

function badge(status) {
  return `<span class="badge ${esc(status)}">${esc(status).replace("_", " ")}</span>`;
}

function detailsHtml(details) {
  if (!details || typeof details !== "object" || !Object.keys(details).length) return "";
  let inner = "";
  for (const [k, v] of Object.entries(details)) {
    inner += `${esc(k)}: ${esc(typeof v === "object" ? JSON.stringify(v) : v)}\n`;
  }
  return `<details><summary>details</summary><pre>${inner}</pre></details>`;
}

function pivotFor(res) {
  let out = "";
  if (res.details && typeof res.details.phoneNumber === "string" && res.details.phoneNumber) {
    out += ` <a class="pivot" href="#" data-phone="${esc(res.details.phoneNumber)}">Scan phone</a>`;
  }
  return out;
}

function filteredResults() {
  const foundOnly = $("foundOnly").checked;
  const filter = $("filter").value.toLowerCase();
  const disabledTools = new Set(
    [...document.querySelectorAll(".tool-toggle")]
      .filter((c) => !c.checked).map((c) => c.dataset.tool)
  );
  return results.filter((r) => {
    if (foundOnly && r.status !== "found" && r.status !== "info") return false;
    if (disabledTools.has(r.source)) return false;
    if (filter && !String(r.site).toLowerCase().includes(filter)) return false;
    return true;
  });
}

function render() {
  const tbody = $("tbody");
  tbody.innerHTML = "";
  for (const r of filteredResults()) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>${esc(r.site)}${pivotFor(r)}</td>` +
      `<td>${esc(r.source)}</td>` +
      `<td>${badge(r.status)}</td>` +
      `<td>${linkHtml(r.url)}</td>` +
      `<td>${detailsHtml(r.details)}</td>`;
    const pivot = tr.querySelector(".pivot");
    if (pivot) pivot.onclick = () => { pivotPhone(pivot.dataset.phone); return false; };
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
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "tool-toggle";
    cb.dataset.tool = t;
    cb.checked = true;
    cb.onchange = render;
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" " + t));
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
  if (t === "email" && !q.includes("@")) {
    showError("Email addresses must contain '@'.");
    return;
  }
  clearError();
  currentType = t; currentQuery = q;

  if (es) es.close();
  results.length = 0;
  $("toolToggles").innerHTML = "";
  $("progress").classList.remove("hidden");
  $("pivotUsername").classList.add("hidden");
  render();

  let url = t === "email" ? `/api/scan/email?email=${encodeURIComponent(q)}`
    : t === "username" ? `/api/scan/username?username=${encodeURIComponent(q)}`
    : `/api/scan/phone?number=${encodeURIComponent(q)}`;
  const token = getToken();
  if (token) url += `&token=${encodeURIComponent(token)}`;

  let finished = false;
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
    finished = true;
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
  es.onerror = async () => {
    if (finished) return;
    $("progress").classList.add("hidden");
    es.close();
    // EventSource gives no status code; probe the same URL to learn why.
    try {
      const headers = {};
      const token = getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
      // Probe without the token query param to distinguish 401 from 400.
      const probeUrl = url.replace(/([?&])token=[^&]+&?/, "$1").replace(/[?&]$/, "");
      const resp = await fetch(probeUrl, { headers });
      if (resp.status === 401) {
        showTokenBox();
        showError("Access token required.");
      } else if (resp.status === 400) {
        let detail = "Invalid input.";
        try {
          const body = await resp.json();
          if (body && body.detail) detail = String(body.detail);
        } catch { }
        showError(detail);
      } else {
        showError("Connection lost.");
      }
    } catch {
      showError("Connection lost.");
    }
  };
}

function download(name, content, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

$("exportJson").onclick = () => {
  const rows = filteredResults();
  download(`osint_${currentType}_${currentQuery}_${rows.length}of${results.length}.json`,
    JSON.stringify(rows, null, 2), "application/json");
};

$("exportCsv").onclick = () => {
  const data = filteredResults();
  const csvEsc = (s) => `"${String(s ?? "").replace(/"/g, '""')}"`;
  const rows = [["source", "category", "site", "status", "url", "details"]];
  for (const r of data)
    rows.push([r.source, r.category, r.site, r.status, r.url || "", JSON.stringify(r.details)]);
  download(`osint_${currentType}_${currentQuery}.csv`,
    rows.map((r) => r.map(csvEsc).join(",")).join("\n"), "text/csv");
};

$("tokenSave").onclick = () => setToken($("tokenInput").value.trim());
$("tokenClear").onclick = () => { $("tokenInput").value = ""; setToken(""); };
$("tokenInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") setToken($("tokenInput").value.trim());
});
$("tokenInput").value = getToken();

$("scanBtn").onclick = startScan;
$("query").addEventListener("keydown", (e) => { if (e.key === "Enter") startScan(); });
$("query").addEventListener("input", () => {
  if ($("type").value === "auto") $("type").dataset.detected = detectType($("query").value.trim());
});
$("foundOnly").onchange = render;
$("filter").addEventListener("input", render);
renderHistory();
renderTokenBox();
