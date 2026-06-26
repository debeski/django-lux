"use strict";

const TOKEN = document.querySelector('meta[name="dlb-token"]').content;

// ── tiny helpers ──────────────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const el = (tag, props = {}, children = []) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k === "html") n.innerHTML = v;
    else n.setAttribute(k, v);
  }
  for (const c of [].concat(children)) n.append(c);
  return n;
};

async function api(path, opts = {}) {
  const headers = Object.assign({ "X-DLB-Token": TOKEN }, opts.headers || {});
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || res.statusText);
  return data;
}

function fileURL(zipPath, download) {
  const q = new URLSearchParams({ path: zipPath, token: TOKEN });
  if (download) q.set("download", "1");
  return "/api/file?" + q.toString();
}

function baseName(p) {
  const s = String(p == null ? "" : p);
  const i = s.lastIndexOf("/");
  return i >= 0 ? s.slice(i + 1) : s;
}

// scopeLabel turns the tri-state media_included flag into a display label.
// true → full backup, false → data-only/quick, null/undefined → legacy (unknown).
function scopeLabel(mediaIncluded) {
  if (mediaIncluded === true) return { text: "Full (database + media)", cls: "" };
  if (mediaIncluded === false) return { text: "Data only — media excluded", cls: "warn" };
  return null;
}

function show(id) {
  for (const s of ["screen-open", "screen-unlock", "screen-browse"]) {
    $("#" + s).hidden = s !== id;
  }
}

function fmtBytes(n) {
  if (n == null) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}

// ── application state ─────────────────────────────────────────────────────────
let META = null;
let SUMMARY = null;

// Lazy index of archived files keyed by `model|pk|field`, built from
// SUMMARY.files. Lets the data tables turn a record's file-field cell into a
// direct open/download link without the user hunting the Stored-files table by
// its random storage name. Rebuilt per backup (cleared in enterBrowse).
let FILE_INDEX = null;
function fileKey(model, pk, field) {
  const pkStr = typeof pk === "object" ? JSON.stringify(pk) : String(pk);
  return `${String(model).toLowerCase()}|${pkStr}|${field}`;
}
function fileIndex() {
  if (FILE_INDEX) return FILE_INDEX;
  FILE_INDEX = new Map();
  for (const f of (SUMMARY && SUMMARY.files) || []) {
    FILE_INDEX.set(fileKey(f.model, f.pk, f.field), f);
  }
  return FILE_INDEX;
}

// Relation schema (manifest.schema) and the user's "resolve relations" choice.
let SCHEMA = null;
let RESOLVE_RELATIONS = localStorage.getItem("dlb-resolve-relations") === "1";
// Cache of label maps per target model: key -> Promise<{by_pk, by_nk}>.
const LABEL_CACHE = {};

function schemaFor(key) {
  return (SCHEMA && SCHEMA[String(key).toLowerCase()]) || null;
}

function hasRelations() {
  if (!SCHEMA) return false;
  return Object.values(SCHEMA).some(
    (m) => m.relations && Object.keys(m.relations).length,
  );
}

async function getLabels(key) {
  const k = String(key).toLowerCase();
  if (!LABEL_CACHE[k]) {
    LABEL_CACHE[k] = api("/api/labels?key=" + encodeURIComponent(k)).catch(
      () => ({ by_pk: {}, by_nk: {} }),
    );
  }
  return LABEL_CACHE[k];
}

// Resolve one relation reference to a display label, falling back to the raw
// reference. `value` is a PK scalar or a natural-key array (e.g. ["alice"]).
function resolveRef(to, value, maps) {
  const m = maps[String(to).toLowerCase()] || { by_pk: {}, by_nk: {} };
  if (Array.isArray(value)) {
    const nk = (m.by_nk || {})[JSON.stringify(value)];
    return nk != null ? nk : value.join(" / ");
  }
  const pk = (m.by_pk || {})[String(value)];
  return pk != null ? pk : String(value);
}

// Resolve a whole relation cell value (m2m is an array of references).
function resolveRelation(rel, value, maps) {
  if (rel.kind === "m2m") {
    if (!Array.isArray(value)) return String(value);
    return value.map((e) => resolveRef(rel.to, e, maps)).join(", ");
  }
  return resolveRef(rel.to, value, maps);
}

// ── step 1: open ──────────────────────────────────────────────────────────────
function wireOpen() {
  const dz = $("#dropzone");
  const fileInput = $("#file-input");

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) uploadFile(fileInput.files[0]);
  });

  ["dragenter", "dragover"].forEach((e) =>
    dz.addEventListener(e, (ev) => { ev.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((e) =>
    dz.addEventListener(e, (ev) => { ev.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (ev) => {
    const f = ev.dataTransfer.files[0];
    if (f) uploadFile(f);
  });

  $("#path-btn").addEventListener("click", openByPath);
  $("#path-input").addEventListener("keydown", (e) => { if (e.key === "Enter") openByPath(); });

  $("#back-to-open").addEventListener("click", () => { show("screen-open"); });
}

function openError(msg) {
  const e = $("#open-error");
  e.textContent = msg;
  e.hidden = !msg;
}

async function uploadFile(file) {
  openError("");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const st = await api("/api/open-upload", { method: "POST", body: fd });
    onLoaded(st);
  } catch (err) { openError(err.message); }
}

async function openByPath() {
  openError("");
  const p = $("#path-input").value.trim();
  if (!p) return;
  try {
    const st = await api("/api/open-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: p }),
    });
    onLoaded(st);
  } catch (err) { openError(err.message); }
}

// ── step 2: unlock ────────────────────────────────────────────────────────────
function onLoaded(state) {
  META = state.meta;
  $("#source-label").textContent = state.source || "";
  renderUnlockMeta();
  if (state.unlocked) { SUMMARY = state.manifest; enterBrowse(); }
  else show("screen-unlock");
}

function renderUnlockMeta() {
  const enc = META.encryption || {};
  const passphrase = enc.key_source === "passphrase";
  const dl = $("#unlock-meta");
  dl.innerHTML = "";
  const add = (k, v) => { dl.append(el("dt", { text: k }), el("dd", {}, v)); };
  add("Created", META.created_at || "—");
  add("Dlux version", META.dlux_version || "—");
  add("Models / rows", `${META.models ?? "—"} / ${META.rows ?? "—"}`);
  add("Stored files", String(META.files ?? "—"));
  const metaScope = scopeLabel(META.media_included);
  if (metaScope) add("Backup scope", el("span", { class: "badge " + metaScope.cls, text: metaScope.text }));
  add("Protection", el("span", {
    class: "badge " + (passphrase ? "warn" : ""),
    text: passphrase ? "passphrase" : "project SECRET_KEY",
  }));

  $("#password-label").textContent = passphrase ? "Backup passphrase" : "Project SECRET_KEY";
  $("#password-hint").textContent = passphrase
    ? "This backup was protected with a one-off passphrase chosen when it was exported."
    : "This backup is tied to the originating project's Django SECRET_KEY. Paste that key here.";
  $("#unlock-error").hidden = true;
  $("#password-input").value = "";
  setTimeout(() => $("#password-input").focus(), 0);
}

function wireUnlock() {
  $("#unlock-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = $("#unlock-error");
    errEl.hidden = true;
    const btn = $("#unlock-btn");
    btn.disabled = true;
    btn.textContent = "Decrypting…";
    try {
      const st = await api("/api/unlock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: $("#password-input").value }),
      });
      SUMMARY = st.manifest;
      enterBrowse();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = "Unlock";
    }
  });

  $("#toggle-pw").addEventListener("click", () => {
    const i = $("#password-input");
    i.type = i.type === "password" ? "text" : "password";
  });
}

// ── step 3: browse ────────────────────────────────────────────────────────────
function enterBrowse() {
  SCHEMA = (SUMMARY && SUMMARY.schema) || null;
  FILE_INDEX = null;
  for (const k of Object.keys(LABEL_CACHE)) delete LABEL_CACHE[k];
  setupRelToggle();
  buildSidebar();
  show("screen-browse");
  selectView("overview");
}

// Reveal the relation toggle only for backups that carry a relation schema
// (older .dlb files fall back to raw references with no toggle shown).
function setupRelToggle() {
  const wrap = $("#rel-toggle");
  const input = $("#rel-toggle-input");
  const available = hasRelations();
  wrap.hidden = !available;
  if (!available) return;
  input.checked = RESOLVE_RELATIONS;
  input.onchange = () => {
    RESOLVE_RELATIONS = input.checked;
    localStorage.setItem("dlb-resolve-relations", RESOLVE_RELATIONS ? "1" : "0");
    if (MODEL_STATE.key) loadModelPage();
  };
}

function buildSidebar() {
  const list = $("#model-list");
  list.innerHTML = "";
  const models = (SUMMARY && SUMMARY.models) || [];
  models
    .slice()
    .sort((a, b) => a.model.localeCompare(b.model))
    .forEach((m) => {
      const item = el("button", { class: "modelitem", "data-model": m.model }, [
        el("span", { text: m.model }),
        el("span", { class: "count", text: String(m.count) }),
      ]);
      item.addEventListener("click", () => selectModel(m.model));
      list.append(item);
    });

  document.querySelectorAll(".navitem").forEach((b) => {
    b.addEventListener("click", () => selectView(b.dataset.view));
  });
}

function setActive(predicate) {
  document.querySelectorAll(".navitem, .modelitem").forEach((b) => {
    b.classList.toggle("active", predicate(b));
  });
}

function selectView(view) {
  setActive((b) => b.classList.contains("navitem") && b.dataset.view === view);
  const c = $("#content");
  if (view === "overview") return renderOverview(c);
  if (view === "files") return renderFiles(c);
  if (view === "migrations") return renderMigrations(c);
  if (view === "manifest") return renderManifest(c);
}

function renderOverview(c) {
  c.innerHTML = "";
  c.append(el("h2", { text: "Backup overview" }));

  const stat = (n, l) => el("div", { class: "stat" }, [
    el("div", { class: "n", text: String(n) }),
    el("div", { class: "l", text: l }),
  ]);
  const models = (SUMMARY && SUMMARY.models) || [];
  const totalRows = models.reduce((s, m) => s + (m.count || 0), 0);
  c.append(el("div", { class: "cards" }, [
    stat(models.length, "models"),
    stat(totalRows, "rows"),
    stat((SUMMARY.files || []).length, "stored files"),
    stat((SUMMARY.missing_files || []).length, "missing files"),
  ]));

  const dl = el("dl", { class: "meta-grid" });
  const add = (k, v) => dl.append(el("dt", { text: k }), el("dd", { text: v }));
  add("Generated at", SUMMARY.generated_at || META.created_at || "—");
  add("Dlux version", SUMMARY.dlux_version || META.dlux_version || "—");
  const ovScope = scopeLabel(SUMMARY.media_included);
  add("Backup scope", ovScope ? ovScope.text : "Unknown (pre-1.2.10 backup)");
  const enc = META.encryption || {};
  add("Encryption", `${enc.scheme || "fernet-chunked"} · ${enc.kdf || ""} · ${enc.iterations || ""} iters`);
  add("Key source", enc.key_source || "—");
  c.append(dl);

  if (SUMMARY.superuser_policy) {
    c.append(el("h3", { text: "Superuser policy" }));
    c.append(el("pre", { class: "raw", text: JSON.stringify(SUMMARY.superuser_policy, null, 2) }));
  }
}

function renderMigrations(c) {
  c.innerHTML = "";
  c.append(el("h2", { text: "Migration state at backup time" }));
  const states = (SUMMARY && SUMMARY.migration_state) || [];
  c.append(el("p", { class: "muted", text: `${states.length} applied migrations recorded.` }));
  c.append(el("pre", { class: "raw", text: states.join("\n") || "—" }));
}

async function renderManifest(c) {
  c.innerHTML = "";
  c.append(el("h2", { text: "Raw manifest.json" }));
  c.append(el("div", { class: "spinner", text: "Loading…" }));
  try {
    const raw = await api("/api/manifest");
    c.innerHTML = "";
    c.append(el("h2", { text: "Raw manifest.json" }));
    c.append(el("pre", { class: "raw", text: JSON.stringify(raw, null, 2) }));
  } catch (err) {
    c.innerHTML = "";
    c.append(el("p", { class: "error", text: err.message }));
  }
}

function renderFiles(c) {
  c.innerHTML = "";
  c.append(el("h2", { text: "Stored files" }));
  const files = (SUMMARY && SUMMARY.files) || [];
  if (!files.length) {
    const mi = SUMMARY ? SUMMARY.media_included : undefined;
    const msg = mi === false
      ? "This is a data-only (Quick) backup — media files were intentionally excluded. The database records are fully present and restorable; only the stored blobs were skipped."
      : mi === true
        ? "This is a full backup, but no records had stored files to archive."
        : "This backup contains no stored files.";
    c.append(el("p", { class: "muted", text: msg }));
    return;
  }
  const head = el("tr", {}, ["Model", "PK", "Field", "Name", ""].map((h) => el("th", { text: h })));
  const rows = files.map((f) => el("tr", {}, [
    el("td", { text: f.model }),
    el("td", { text: typeof f.pk === "object" ? JSON.stringify(f.pk) : String(f.pk) }),
    el("td", { text: f.field }),
    el("td", { text: f.name }),
    el("td", {}, [
      el("a", { class: "filelink", href: fileURL(f.path, false), target: "_blank", text: "open" }),
      document.createTextNode("  "),
      el("a", { class: "filelink", href: fileURL(f.path, true), text: "download" }),
    ]),
  ]));
  c.append(el("div", { class: "table-wrap" }, [el("table", {}, [el("thead", {}, head), el("tbody", {}, rows)])]));
}

// ── model record browsing (paged) ─────────────────────────────────────────────
let MODEL_STATE = { key: null, offset: 0, limit: 50, total: 0 };

function selectModel(key) {
  setActive((b) => b.classList.contains("modelitem") && b.dataset.model === key);
  MODEL_STATE = { key, offset: 0, limit: 50, total: 0 };
  loadModelPage();
}

async function loadModelPage() {
  const c = $("#content");
  c.innerHTML = "";
  c.append(el("h2", { text: MODEL_STATE.key }));
  c.append(el("div", { class: "spinner", text: "Loading records…" }));
  try {
    const q = new URLSearchParams({
      key: MODEL_STATE.key,
      offset: String(MODEL_STATE.offset),
      limit: String(MODEL_STATE.limit),
    });
    const data = await api("/api/model?" + q.toString());
    MODEL_STATE.total = data.total;
    await renderModelTable(c, data);
  } catch (err) {
    c.innerHTML = "";
    c.append(el("h2", { text: MODEL_STATE.key }));
    c.append(el("p", { class: "error", text: err.message }));
  }
}

async function renderModelTable(c, data) {
  c.innerHTML = "";
  c.append(el("h2", { text: data.key }));

  const recs = data.records || [];
  c.append(pager(data));

  if (!recs.length) {
    c.append(el("p", { class: "muted", text: "No records in this range." }));
    return;
  }

  // Build column set from the union of field keys on this page.
  const fieldKeys = [];
  const seen = new Set();
  for (const r of recs) {
    const fields = r.fields || {};
    for (const k of Object.keys(fields)) {
      if (!seen.has(k)) { seen.add(k); fieldKeys.push(k); }
    }
  }
  const cols = ["pk", ...fieldKeys];

  // Relation columns for this model, and the label maps they need (loaded only
  // when the user has opted to resolve relations).
  const relations = (schemaFor(data.key) || {}).relations || {};
  let maps = {};
  if (RESOLVE_RELATIONS) {
    const targets = [...new Set(
      cols.filter((col) => relations[col]).map((col) => relations[col].to),
    )];
    const loaded = await Promise.all(targets.map(getLabels));
    targets.forEach((t, i) => { maps[String(t).toLowerCase()] = loaded[i]; });
  }

  const head = el("tr", {}, cols.map((col) => {
    const th = el("th", { text: col });
    if (relations[col]) {
      th.classList.add("rel-col");
      th.title = `${relations[col].kind} → ${relations[col].to}`;
    }
    return th;
  }));

  const body = recs.map((r) => {
    const cells = cols.map((col) => {
      const v = col === "pk" ? r.pk : (r.fields || {})[col];
      if (v === null || v === undefined) return el("td", { class: "muted", text: "—" });

      // File-field cell: if this record's (model, pk, field) has an archived
      // blob, surface it as a direct open-inline link (+ a download caret) using
      // the readable basename, instead of the raw random storage path. Absent for
      // data-only/quick backups, where the blob isn't in the container.
      if (col !== "pk") {
        const entry = fileIndex().get(fileKey(data.key, r.pk, col));
        if (entry) {
          const td = el("td", { class: "filecell" });
          td.append(el("a", {
            class: "filelink", href: fileURL(entry.path, false),
            target: "_blank", rel: "noopener",
            text: baseName(entry.name) || String(v), title: String(v),
          }));
          td.append(document.createTextNode(" "));
          td.append(el("a", {
            class: "filelink dl", href: fileURL(entry.path, true),
            title: "download", text: "↓",
          }));
          return td;
        }
      }

      const rel = relations[col];
      if (rel && RESOLVE_RELATIONS) {
        const name = resolveRelation(rel, v, maps);
        const raw = typeof v === "object" ? JSON.stringify(v) : String(v);
        const td = el("td", { class: "rel-name", title: `${rel.kind} → ${rel.to} · ${raw}` });
        td.append(document.createTextNode(name));
        if (name !== raw) td.append(el("span", { class: "rel-raw", text: ` (${raw})` }));
        return td;
      }

      if (typeof v === "object") return el("td", { class: "json", text: JSON.stringify(v) });
      const s = String(v);
      return el("td", { text: s, title: s });
    });
    return el("tr", {}, cells);
  });

  c.append(el("div", { class: "table-wrap" }, [el("table", {}, [el("thead", {}, head), el("tbody", {}, body)])]));
  c.append(pager(data));
}

function pager(data) {
  const start = data.total ? data.offset + 1 : 0;
  const end = Math.min(data.offset + (data.records || []).length, data.total);
  const wrap = el("div", { class: "pager" });
  const prev = el("button", { class: "btn ghost", text: "← Prev" });
  const next = el("button", { class: "btn ghost", text: "Next →" });
  prev.disabled = data.offset <= 0;
  next.disabled = end >= data.total;
  prev.addEventListener("click", () => { MODEL_STATE.offset = Math.max(0, MODEL_STATE.offset - MODEL_STATE.limit); loadModelPage(); });
  next.addEventListener("click", () => { MODEL_STATE.offset += MODEL_STATE.limit; loadModelPage(); });
  wrap.append(prev, next, el("span", { class: "muted", text: `${start}–${end} of ${data.total}` }));
  return wrap;
}

// ── boot ──────────────────────────────────────────────────────────────────────
async function boot() {
  wireOpen();
  wireUnlock();
  try {
    const st = await api("/api/state");
    if (st.loaded) onLoaded(st);
    else show("screen-open");
  } catch {
    show("screen-open");
  }
}

boot();
