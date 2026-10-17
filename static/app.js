/* ZK Attendance dashboard app */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
let SETTINGS = {};

async function api(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 401) { showAuth("login"); return null; }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "Request failed");
  return data;
}
const GET = (p) => api("GET", p);
const POST = (p, b) => api("POST", p, b || {});

/* ---------------- auth ---------------- */
async function showAuth(mode) {
  const need = await GET("/api/setup-needed").catch(() => ({ needed: false }));
  const isSetup = mode === "setup" || need.needed;
  $("#auth-screen").classList.remove("hidden");
  $("#app").classList.add("hidden");
  $("#setup-fields").classList.toggle("hidden", !isSetup);
  $("#login-fields").classList.toggle("hidden", isSetup);
  $("#auth-title").textContent = isSetup ? "First-time setup" : "Attendance Dashboard";
  $("#auth-sub").textContent = isSetup ? "Create the admin password for this dashboard" : "Sign in to continue";
  $("#auth-go").textContent = isSetup ? "Create password & enter" : "Sign in";
  $("#auth-go").dataset.mode = isSetup ? "setup" : "login";
  $("#auth-error").classList.add("hidden");
}
async function doAuth() {
  const mode = $("#auth-go").dataset.mode;
  const err = $("#auth-error");
  try {
    if (mode === "setup") {
      const p1 = $("#setup-pass").value, p2 = $("#setup-pass2").value;
      if (p1 !== p2) throw new Error("Passwords do not match.");
      await POST("/api/setup", { password: p1 });
    } else {
      await POST("/api/login", { password: $("#login-pass").value });
    }
    $("#auth-screen").classList.add("hidden");
    $("#app").classList.remove("hidden");
    await boot();
  } catch (e) { err.textContent = e.message; err.classList.remove("hidden"); }
}

/* ---------------- tabs ---------------- */
$$(".tab").forEach((t) => t.addEventListener("click", () => {
  $$(".tab").forEach((x) => x.classList.remove("active"));
  t.classList.add("active");
  $$(".tabpage").forEach((p) => p.classList.add("hidden"));
  $("#tab-" + t.dataset.tab).classList.remove("hidden");
  loadTab(t.dataset.tab);
}));

/* ---------------- today ---------------- */
function statusPill(s) {
  const cls = { "Present": "present", "Late": "late", "Early leave": "late", "Late + Early": "late",
    "Absent": "absent", "Leave": "leave", "Holiday": "off", "Weekly off": "off" }[s] || "off";
  return `<span class="pill ${cls}">${s}</span>`;
}
async function loadToday() {
  const d = await GET("/api/today");
  if (!d) return;
  const s = d.report.summary;
  $("#today-cards").innerHTML = `
    <div class="card"><div class="num">${s.present}</div><div class="lbl">Present</div></div>
    <div class="card warn"><div class="num">${s.late}</div><div class="lbl">Late arrivals</div></div>
    <div class="card"><div class="num">${s.early}</div><div class="lbl">Early leaves</div></div>
    <div class="card bad"><div class="num">${s.absent}</div><div class="lbl">Absent</div></div>
    <div class="card"><div class="num">${s.leave}</div><div class="lbl">On leave</div></div>`;
  $("#feed").innerHTML = d.feed.length ? d.feed.map((f) =>
    `<div class="feed-item"><span class="t">${f.punched_at.slice(11, 16)}</span><span class="n">${esc(f.name)}</span><span class="p">PIN ${esc(f.device_pin)}</span></div>`
  ).join("") : `<div class="empty">No punches recorded yet today.</div>`;
  $("#device-box").innerHTML = d.devices.length ? d.devices.map((x) =>
    `<div class="feed-item"><span class="n">● ${esc(x.sn)}</span><span class="p">${esc(x.last_seen || "")}</span></div>`
  ).join("") : `<div class="empty">No device has connected yet.<br><span class="small">Point the K40 at this server (see Settings).</span></div>`;
  const up = $("#unmapped-panel");
  if (d.unmapped_today > 0) {
    up.classList.remove("hidden");
    $("#unmapped-list").innerHTML = `<b>${d.unmapped_today}</b> punch(es) from unknown PINs today — assign them in the Staff tab.`;
  } else up.classList.add("hidden");
}

/* ---------------- daily ---------------- */
async function loadDaily() {
  const day = $("#daily-date").value || localISODate(new Date());
  const d = await GET("/api/daily?day=" + day);
  if (!d) return;
  $("#daily-meta").textContent = `${d.weekday}, ${d.date} · Shift ${d.shift}${d.holiday_name ? " · " + d.holiday_name : ""}${d.kind !== "working" ? " · " + d.kind.replace("_", " ") : ""}`;
  const s = d.summary;
  $("#daily-cards").innerHTML = `
    <div class="card"><div class="num">${s.present}</div><div class="lbl">Present</div></div>
    <div class="card warn"><div class="num">${s.late}</div><div class="lbl">Late</div></div>
    <div class="card"><div class="num">${s.early}</div><div class="lbl">Early leave</div></div>
    <div class="card bad"><div class="num">${s.absent}</div><div class="lbl">Absent</div></div>
    <div class="card"><div class="num">${s.leave}</div><div class="lbl">Leave</div></div>`;
  $("#daily-table tbody").innerHTML = d.rows.map((r) => `
    <tr><td><b>${esc(r.name)}</b></td><td>${esc(r.pin)}</td><td>${esc(r.department)}</td>
    <td>${statusPill(r.status)}</td><td>${r.in || "—"}</td><td>${r.out || "—"}</td>
    <td>${r.late_min ? r.late_min + " min" : "—"}</td><td>${r.early_min ? r.early_min + " min" : "—"}</td>
    <td><button class="btn xs" data-leave="${r.id}|${r.date}">${r.status === "Leave" ? "Unmark leave" : "Mark leave"}</button></td></tr>`
  ).join("") || `<tr><td colspan="9" class="empty">No active staff yet.</td></tr>`;
  $$("#daily-table [data-leave]").forEach((b) => b.onclick = async () => {
    const [sid, dt] = b.dataset.leave.split("|");
    await POST("/api/leave", { staff_id: +sid, date: dt });
    loadDaily();
  });
}

/* ---------------- monthly ---------------- */
async function loadMonthly() {
  const month = $("#monthly-month").value || localISODate(new Date()).slice(0, 7);
  const r = await GET("/api/monthly?month=" + month);
  if (!r) return;
  const thead = `<tr><th>Staff</th>` + r.days.map((d) =>
    `<th class="${d.kind !== "working" ? "offday" : ""}" title="${d.kind}">${d.d}<br><span style="font-weight:400">${d.wd}</span></th>`
  ).join("") + `<th>P</th><th>L</th><th>E</th><th>A</th><th>LV</th></tr>`;
  const tbody = r.grid.map((g) => {
    const cells = g.cells.map((c, i) =>
      `<td class="${r.days[i].kind !== "working" ? "offday" : ""} cell-${c.code}" title="${esc(c.status)}${c.in ? " · " + c.in + "–" + (c.out || "?") : ""}">${c.code}</td>`
    ).join("");
    return `<tr><th>${esc(g.name)}<br><span class="muted small">PIN ${esc(g.pin)}</span></th>${cells}` +
      `<td class="tot">${g.totals.P}</td><td class="tot">${g.totals.L}</td><td class="tot">${g.totals.E}</td><td class="tot">${g.totals.A}</td><td class="tot">${g.totals.LV}</td></tr>`;
  }).join("");
  $("#register-table thead").innerHTML = thead;
  $("#register-table tbody").innerHTML = tbody || `<tr><td class="empty">No active staff yet.</td></tr>`;
}

/* ---------------- staff ---------------- */
async function loadStaff() {
  const d = await GET("/api/staff");
  if (!d) return;
  $("#staff-table tbody").innerHTML = d.staff.map((s) => `
    <tr><td><b>${esc(s.name)}</b></td><td>${esc(s.device_pin)}${s.device_sn ? `<br><span class="muted small">${esc(s.device_sn)}</span>` : ""}</td><td>${esc(s.department)}</td>
    <td>${s.active ? '<span class="pill present">Active</span>' : '<span class="pill off">Inactive</span>'}</td>
    <td><button class="btn xs" data-edit="${s.id}">Edit</button>
    ${s.active ? `<button class="btn xs danger" data-deact="${s.id}">Deactivate</button>` : ""}</td></tr>`
  ).join("") || `<tr><td colspan="5" class="empty">No staff yet — add your first member.</td></tr>`;
  window._staff = Object.fromEntries(d.staff.map((s) => [s.id, s]));
  $$("#staff-table [data-edit]").forEach((b) => b.onclick = () => {
    const s = window._staff[b.dataset.edit];
    $("#staff-id").value = s.id; $("#staff-name").value = s.name;
    $("#staff-pin").value = s.device_pin; $("#staff-pin").disabled = true;
    $("#staff-device").value = s.device_sn || "";
    $("#staff-dept").value = s.department;
    $("#staff-form-title").textContent = "Edit staff";
    $("#staff-cancel").classList.remove("hidden");
  });
  $$("#staff-table [data-deact]").forEach((b) => b.onclick = async () => {
    if (!confirm("Deactivate this staff member? Their history is kept.")) return;
    await api("DELETE", "/api/staff/" + b.dataset.deact);
    loadStaff();
  });
  const u = await GET("/api/unmapped");
  $("#unmapped-table tbody").innerHTML = (u.pins || []).map((p) => `
    <tr><td><b>${esc(p.device_pin)}</b></td><td>${p.c}</td><td>${p.first_seen}</td><td>${p.last_seen}</td>
    <td><button class="btn xs primary" data-assign="${esc(p.device_pin)}">Assign to staff</button></td></tr>`
  ).join("") || `<tr><td colspan="5" class="empty">All punches are mapped to staff. Good.</td></tr>`;
  $$("#unmapped-table [data-assign]").forEach((b) => b.onclick = () => {
    $("#staff-pin").value = b.dataset.assign;
    $("#staff-name").focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}
async function saveStaff() {
  const id = $("#staff-id").value;
  const body = { name: $("#staff-name").value, pin: $("#staff-pin").value, department: $("#staff-dept").value, device_sn: $("#staff-device").value };
  try {
    if (id) await api("PUT", "/api/staff/" + id, { name: body.name, department: body.department, device_sn: body.device_sn, active: 1 });
    else await POST("/api/staff", body);
    resetStaffForm(); loadStaff();
  } catch (e) { alert(e.message); }
}
function resetStaffForm() {
  $("#staff-id").value = ""; $("#staff-name").value = ""; $("#staff-pin").value = "";
  $("#staff-pin").disabled = false; $("#staff-dept").value = ""; $("#staff-device").value = "";
  $("#staff-form-title").textContent = "Add staff";
  $("#staff-cancel").classList.add("hidden");
}

/* ---------------- settings ---------------- */
async function loadSettings() {
  const d = await GET("/api/settings");
  if (!d) return;
  SETTINGS = d.settings;
  $("#hdr-institute").textContent = SETTINGS.institute_name || "Attendance";
  document.title = (SETTINGS.institute_name || "Attendance") + " — ZK Attendance";
  $("#set-institute").value = SETTINGS.institute_name;
  $("#set-start").value = SETTINGS.shift_start;
  $("#set-end").value = SETTINGS.shift_end;
  $("#set-grace").value = SETTINGS.grace_minutes;
  $("#set-weeklyoff").value = SETTINGS.weekly_off;
  $("#ingest-key").textContent = SETTINGS.ingest_key;
  $("#srv-addr").textContent = location.host;
  const h = await GET("/api/holidays");
  $("#hol-table tbody").innerHTML = (h.holidays || []).map((x) =>
    `<tr><td>${x.date}</td><td>${esc(x.name)}</td><td><button class="btn xs danger" data-hol="${x.date}">Remove</button></td></tr>`
  ).join("") || `<tr><td colspan="3" class="empty">No holidays added.</td></tr>`;
  $$("#hol-table [data-hol]").forEach((b) => b.onclick = async () => {
    await api("DELETE", "/api/holidays/" + b.dataset.hol);
    loadSettings();
  });
}

/* ---------------- boot ---------------- */
function loadTab(t) {
  ({ today: loadToday, daily: loadDaily, monthly: loadMonthly, staff: loadStaff, settings: loadSettings })[t]();
}
function localISODate(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
async function boot() {
  const now = new Date();
  $("#hdr-date").textContent = now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  $("#daily-date").value = localISODate(now);
  $("#monthly-month").value = localISODate(now).slice(0, 7);
  await loadSettings();
  await loadToday();
}
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

$("#auth-go").addEventListener("click", doAuth);
$("#login-pass")?.addEventListener("keydown", (e) => e.key === "Enter" && doAuth());
$("#setup-pass2")?.addEventListener("keydown", (e) => e.key === "Enter" && doAuth());
$("#logout").addEventListener("click", async () => { await POST("/api/logout"); location.reload(); });
$("#daily-date").addEventListener("change", loadDaily);
$("#monthly-month").addEventListener("change", loadMonthly);
$("#daily-csv").addEventListener("click", () => { location.href = "/api/export/daily.csv?day=" + $("#daily-date").value; });
$("#monthly-csv").addEventListener("click", () => { location.href = "/api/export/monthly.csv?month=" + $("#monthly-month").value; });
$("#staff-save").addEventListener("click", saveStaff);
$("#staff-cancel").addEventListener("click", resetStaffForm);
$("#settings-save").addEventListener("click", async () => {
  try {
    await POST("/api/settings", {
      institute_name: $("#set-institute").value, shift_start: $("#set-start").value,
      shift_end: $("#set-end").value, grace_minutes: $("#set-grace").value,
      weekly_off: $("#set-weeklyoff").value, new_password: $("#set-pass").value,
    });
    $("#set-pass").value = "";
    alert("Settings saved.");
    loadSettings();
  } catch (e) { alert(e.message); }
});
$("#hol-add").addEventListener("click", async () => {
  if (!$("#hol-date").value) return alert("Pick a date first.");
  try { await POST("/api/holidays", { date: $("#hol-date").value, name: $("#hol-name").value }); loadSettings(); }
  catch (e) { alert(e.message); }
});

showAuth("login");
