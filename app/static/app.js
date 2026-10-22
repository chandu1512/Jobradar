const $ = (s) => document.querySelector(s);
const form = $("#f"),
  list = $("#list"),
  more = $("#more");
let lastId = null;
let loadRequest = 0;
let categoryLabels = {};

const ago = (t) => {
  const m = Math.max(0, (Date.now() - new Date(t)) / 60000);
  if (m < 60) return `${Math.round(m)}m ago`;
  if (m < 1440) return `${Math.round(m / 60)}h ago`;
  return `${Math.round(m / 1440)}d ago`;
};
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c],
  );

function params() {
  const fd = new FormData(form),
    p = new URLSearchParams();
  for (const k of ["q", "company", "category", "level", "state", "hours", "sponsorship", "requirement"])
    if (fd.get(k)) p.set(k, fd.get(k));
  for (const key of ["remote", "salary_disclosed", "opt_mentioned"])
    if (fd.get(key)) p.set(key, "true");
  return p;
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : "#";
  } catch {
    return "#";
  }
}

function row(j, fresh) {
  const li = document.createElement("li");
  li.className = `job-card${fresh ? " fresh" : ""}`;
  li.dataset.id = j.id;
  const company = j.company || "Company";
  const initials = company
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  const tone = [...company].reduce((n, c) => n + c.charCodeAt(0), 0) % 4;
  const category = (j.categories || [])
    .map((c) => categoryLabels[c])
    .find(Boolean);
  const href = esc(safeUrl(j.url));
  const ranges = j.salary?.ranges || [];
  const pay = ranges.map(r => `${r.currency || "$ (currency unspecified)"} ${Number(r.min).toLocaleString()}–${Number(r.max).toLocaleString()}${r.interval ? ` / ${r.interval}` : " (period unspecified)"}`).join("; ");
  const visa = {offered: "Sponsorship offered", not_offered: "Sponsorship not offered", conflicting: "Conflicting sponsorship statements", unknown: "Sponsorship unknown"}[j.sponsorship?.status || "unknown"];
  const findings = j.requirements?.findings || [];
  const requirementLabels = {experience: "Experience requirement", doctoral_degree: "PhD mentioned", work_authorization: "Authorization restriction mentioned", enrollment: "Enrollment mentioned", graduation_window: "Graduation window"};
  const evidence = [...(j.sponsorship?.evidence || []), ...(j.salary?.evidence || []),
    ...findings.map(f => `${requirementLabels[f.type]} (${f.qualification}): ${f.evidence}`)];
  li.innerHTML = `
    <div class="company-avatar tone-${tone}" aria-hidden="true">${esc(initials)}</div>
    <div class="job-info">
      <div class="company-name">${esc(company)}</div>
      <h3 class="job-title"><a href="${href}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a></h3>
      <p class="job-location" title="${esc(j.location || "Location not specified")}"><span aria-hidden="true">⌖</span>${esc(j.location || "Location not specified")}</p>
      <div class="job-tags">${category ? `<span class="tag">${esc(category)}</span>` : ""}
        ${j.remote ? '<span class="tag remote">Remote</span>' : ""}
        ${[...new Set(findings.map(f => f.type))].map(t => `<span class="tag">${esc(requirementLabels[t])}</span>`).join("")}
        ${j.discovered_live ? '<span class="tag new">New discovery</span>' : '<span class="tag">Company careers</span>'}</div>
      <p class="job-location">${esc(pay || "Salary not disclosed")} · ${esc(visa)}${j.opt?.mentioned ? " · OPT / CPT mentioned" : ""}</p>
      ${evidence.length ? `<details><summary>Posting evidence</summary>${evidence.map(s => `<p>${esc(s)}</p>`).join("")}<small>Mentions do not establish work authorization eligibility. Verify the linked posting.</small></details>` : ""}
    </div>
    <div class="job-side"><span class="age" data-t="${esc(j.first_seen)}">Found ${ago(j.first_seen)}</span>
      <a class="apply-link" href="${href}" target="_blank" rel="noopener noreferrer" aria-label="${esc(`View ${j.title} at ${company}, opens a new tab`)}">View role <span aria-hidden="true">↗</span></a></div>`;
  return li;
}

function syncFilters() {
  const p = params();
  let count = [...p].filter(([k, v]) => k !== "hours" || v !== "24").length;
  $("#filter-count").textContent = count ? `${count} active` : "Filters";
  document.querySelectorAll("[data-category]").forEach((button) => {
    const active = button.dataset.category === (p.get("category") || "");
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function resultCount() {
  const n = list.children.length;
  $("#result-count").textContent =
    `${n.toLocaleString()} ${n === 1 ? "opportunity" : "opportunities"} loaded`;
}

async function getJson(url) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetch(url, {signal: AbortSignal.timeout(15000)});
      if (!response.ok) {
        if ([502, 503, 504].includes(response.status) && attempt < 2) {
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
          continue;
        }
        throw new Error(`Request failed: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      if (attempt === 2 || !(error instanceof TypeError || error.name === "TimeoutError")) throw error;
      await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
    }
  }
}

async function load(reset) {
  const request = ++loadRequest;
  const p = params();
  p.set("limit", 50);
  syncFilters();
  if (!reset && lastId) p.set("before_id", lastId);
  list.setAttribute("aria-busy", "true");
  more.disabled = true;
  $("#error").hidden = true;
  if (reset) $("#result-count").textContent = "Finding opportunities…";
  try {
    const jobs = await getJson(`/jobs?${p}`);
    if (request !== loadRequest) return;
    if (!Array.isArray(jobs)) throw new Error("Invalid jobs response");
    if (reset) {
      lastId = null;
      list.replaceChildren();
      updateCoverage(p.get("company"), request);
    }
    const ids = new Set([...list.children].map((li) => li.dataset.id));
    jobs
      .filter((j) => !ids.has(String(j.id)))
      .forEach((j) => list.append(row(j)));
    lastId = jobs.length ? jobs[jobs.length - 1].id : lastId;
    more.hidden = jobs.length < 50;
    $("#empty").hidden = list.children.length > 0;
    resultCount();
  } catch {
    if (request !== loadRequest) return;
    $("#error").textContent =
      "We couldn’t load opportunities. Please check your connection and try refreshing.";
    $("#error").hidden = false;
    $("#result-count").textContent = "Search unavailable";
  } finally {
    if (request === loadRequest) {
      list.setAttribute("aria-busy", "false");
      more.disabled = false;
    }
  }
}

async function updateCoverage(company, request) {
  const notice = $("#coverage");
  notice.hidden = true;
  if (!company?.trim()) return;
  try {
    const response = await fetch(
      `/coverage?${new URLSearchParams({ company })}`,
    );
    if (!response.ok) throw new Error("Coverage unavailable");
    const coverage = await response.json();
    if (request !== loadRequest) return;
    notice.hidden = false;
    if (!coverage.covered) {
      notice.textContent = `Company not covered yet: ${company}. This does not mean it has no openings.`;
      return;
    }
    const companies = coverage.companies;
    const count = companies.reduce((sum, c) => sum + Number(c.active_jobs), 0);
    const pending = companies.some((c) => !c.last_crawled_at);
    const errors = companies.some((c) => c.last_status === "error");
    const partial = companies.some((c) => c.ats === "amazon");
    notice.textContent =
      `${count.toLocaleString()} active indexed jobs across matching companies. ` +
      (pending ? "Initial collection is pending. " : "") +
      (errors ? "Some sources have crawl errors. " : "") +
      (partial
        ? "Amazon coverage is limited to a recent US window; closure status may be stale. "
        : "") +
      "Your selected filters may show fewer results.";
  } catch {
    if (request === loadRequest) {
      notice.hidden = false;
      notice.textContent = "Company coverage could not be checked. Try again.";
    }
  }
}

function matches(j) {
  const p = params(),
    q = (p.get("q") || "").toLowerCase();
  if (!j.is_us) return false;
  if (
    p.get("company") &&
    !j.company.toLowerCase().includes(p.get("company").toLowerCase())
  )
    return false;
  if (p.get("category") && !(j.categories || []).includes(p.get("category")))
    return false;
  if (
    q &&
    !j.title.toLowerCase().includes(q) &&
    !j.company.toLowerCase().includes(q)
  )
    return false;
  if (p.get("state") && !j.states.includes(p.get("state"))) return false;
  if (p.get("remote") && !j.remote) return false;
  if (p.get("sponsorship") && j.sponsorship?.status !== p.get("sponsorship")) return false;
  if (p.get("salary_disclosed") && !j.salary?.ranges?.length) return false;
  if (p.get("opt_mentioned") && !j.opt?.mentioned) return false;
  if (p.get("requirement") && !j.requirements?.findings?.some(f => f.type === p.get("requirement"))) return false;
  if (p.get("level")) return false; // level regex lives server side; the next reload picks these up
  return true;
}

async function stats() {
  const s = await getJson("/stats");
  $("#stat-jobs").textContent = Number(s.active_us_jobs).toLocaleString();
  $("#stat-companies").textContent = Number(s.companies).toLocaleString();
  $("#stat-new").textContent = Number(s.new_last_24h).toLocaleString();
}

let companyRequest = 0;
async function companies() {
  const request = ++companyRequest;
  const p = new URLSearchParams({ q: form.elements.company.value });
  const rows = await getJson(`/companies?${p}`);
  if (request !== companyRequest) return;
  $("#companies").replaceChildren(
    ...rows.map((c) => new Option(c.name, c.name)),
  );
}

async function categories() {
  const rows = await getJson("/categories");
  categoryLabels = Object.fromEntries(rows.map((c) => [c.id, c.label]));
  rows.forEach((c) => form.elements.category.add(new Option(c.label, c.id)));
}

async function states() {
  const rows = await getJson("/states"),
    sel = form.state;
  rows
    .sort((a, b) => a.state.localeCompare(b.state))
    .forEach((r) => sel.add(new Option(`${r.state} (${r.n})`, r.state)));
}

function live() {
  if (
    [".trycloudflare.com", ".ngrok-free.app", ".ngrok-free.dev"].some((s) =>
      location.hostname.endsWith(s),
    )
  ) {
    $("#livetxt").textContent = "Updates every minute";
    $("#dot").classList.add("on");
    setInterval(() => {
      if (document.visibilityState === "visible") load(true);
    }, 60000);
    return;
  }
  const es = new EventSource("/jobs/stream");
  es.onopen = () => {
    $("#dot").className = "dot on";
    $("#livetxt").textContent = "live";
  };
  es.onerror = () => {
    $("#dot").className = "dot";
    $("#livetxt").textContent = "reconnecting";
  };
  es.onmessage = (e) => {
    const j = JSON.parse(e.data);
    if (
      matches(j) &&
      ![...list.children].some((li) => li.dataset.id === String(j.id))
    ) {
      $("#empty").hidden = true;
      list.prepend(row(j, true));
      resultCount();
    }
  };
}

let companyTimer;
form.elements.company.addEventListener("input", () => {
  clearTimeout(companyTimer);
  companyTimer = setTimeout(() => companies().catch(() => {}), 200);
});
let t;
form.addEventListener("input", () => {
  clearTimeout(t);
  t = setTimeout(() => load(true), 250);
});
form.addEventListener("submit", (e) => e.preventDefault());
more.onclick = () => load(false);
setInterval(
  () =>
    document
      .querySelectorAll(".age")
      .forEach((el) => (el.textContent = `Found ${ago(el.dataset.t)}`)),
  30000,
);
setInterval(() => stats().catch(() => {}), 60000);

function resetFilters() {
  form.reset();
  load(true);
}
$("#clear").onclick = resetFilters;
$("#empty-reset").onclick = resetFilters;
document.querySelectorAll("[data-category]").forEach((button) => {
  button.onclick = () => {
    form.elements.category.value = button.dataset.category;
    load(true);
  };
});
const mobile = matchMedia("(max-width: 760px)");
function layoutFilters() {
  $("#filter-panel").open = !mobile.matches;
}
layoutFilters();
mobile.addEventListener("change", layoutFilters);

async function start() {
  await Promise.allSettled([categories(), states(), companies(), stats()]);
  load(true);
  live();
}
start();
