"""ZK Attendance — ADMS receiver + web dashboard API.

Device side (ZKTeco K40 in ADMS / Cloud Server mode, plain HTTP):
    GET  /iclock/cdata          (also /iclock/cdata.aspx)  -> registration, reply options
    POST /iclock/cdata?table=ATTLOG                          -> punch upload, reply OK
    GET  /iclock/getrequest     (also .aspx)                 -> device polls for commands
    POST /iclock/devicecmd     (also .aspx)                 -> command result from device
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import attendance, db

BASE = Path(__file__).resolve().parent.parent
STATIC = BASE / "static"
SERVER_VER = "1.0.0"

app = FastAPI(title="ZK Attendance", docs_url=None, redoc_url=None)
db.init_db()

# ---------------------------------------------------------------- iclock ---

def _device_options(sn: str) -> str:
    return (
        f"GET OPTION FROM: {sn}\n"
        "ATTLOGStamp=None\n"
        "OPERLOGStamp=None\n"
        "ATTPHOTOStamp=None\n"
        "ErrorDelay=30\n"
        "Delay=10\n"
        "TransTimes=00:00;14:05\n"
        "TransInterval=1\n"
        "TransFlag=TransData AttLog OpLog\n"
        "TimeZone=5\n"
        "Realtime=1\n"
        "Encrypt=None\n"
        f"ServerVer={SERVER_VER}\n"
    )


def _touch_device(conn, sn: str, ip: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO devices(sn, last_seen, last_ip) VALUES(?,?,?) "
        "ON CONFLICT(sn) DO UPDATE SET last_seen=excluded.last_seen, last_ip=excluded.last_ip",
        (sn, now, ip),
    )
    conn.commit()


def _register_cdata(app_: FastAPI, path: str) -> None:
    @app_.get(path, response_class=PlainTextResponse, include_in_schema=False)
    async def cdata_get(request: Request):
        sn = request.query_params.get("SN", "UNKNOWN")
        conn = db.connect()
        try:
            _touch_device(conn, sn, request.client.host if request.client else "")
        finally:
            conn.close()
        return _device_options(sn)

    @app_.post(path, response_class=PlainTextResponse, include_in_schema=False)
    async def cdata_post(request: Request):
        params = request.query_params
        sn = params.get("SN", "UNKNOWN")
        table = params.get("table", "").upper()
        body = (await request.body()).decode("utf-8", errors="replace")
        lines = [ln for ln in body.splitlines() if ln.strip()]
        conn = db.connect()
        try:
            _touch_device(conn, sn, request.client.host if request.client else "")
            if table == "ATTLOG":
                n = _store_attlog(conn, sn, lines)
                conn.commit()
                return f"OK: {n}"
            return "OK"
        finally:
            conn.close()


def _store_attlog(conn, sn: str, lines: list[str]) -> int:
    """Parse tab-separated ATTLOG lines: PIN, datetime, status, verify, ..."""
    n = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for ln in lines:
        if "\t" not in ln or ln.startswith("SN="):
            continue
        parts = ln.split("\t")
        pin = parts[0].strip()
        ts = parts[1].strip() if len(parts) > 1 else ""
        if not pin or not ts:
            continue
        # normalize "2026-10-13 08:04:12" (device sends local time already)
        try:
            punched = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        staff = conn.execute(
            "SELECT id FROM staff WHERE device_pin=? AND active=1 "
            "AND (device_sn='' OR device_sn IS NULL OR device_sn=?) "
            "ORDER BY CASE WHEN device_sn=? THEN 0 ELSE 1 END LIMIT 1",
            (pin, sn, sn)).fetchone()
        conn.execute(
            "INSERT OR IGNORE INTO punches(device_sn, device_pin, punched_at, raw_status, verify,"
            " raw_line, staff_id, received_at) VALUES(?,?,?,?,?,?,?,?)",
            (sn, pin, punched, parts[2] if len(parts) > 2 else "",
             parts[3] if len(parts) > 3 else "", ln, staff["id"] if staff else None, now),
        )
        n += 1
    return n


for _p in ("/iclock/cdata", "/iclock/cdata.aspx"):
    _register_cdata(app, _p)


def _register_getrequest(app_: FastAPI, path: str) -> None:
    @app_.get(path, response_class=PlainTextResponse, include_in_schema=False)
    async def getrequest(request: Request):
        # v1: no server->device commands queued; device just keeps polling.
        return "OK"


for _p in ("/iclock/getrequest", "/iclock/getrequest.aspx"):
    _register_getrequest(app, _p)


def _register_devicecmd(app_: FastAPI, path: str) -> None:
    @app_.get(path, response_class=PlainTextResponse, include_in_schema=False)
    @app_.post(path, response_class=PlainTextResponse, include_in_schema=False)
    async def devicecmd(request: Request):
        return "OK"


for _p in ("/iclock/devicecmd", "/iclock/devicecmd.aspx"):
    _register_devicecmd(app, _p)

# ------------------------------------------------------------------ API ---

def _authed(request: Request) -> bool:
    conn = db.connect()
    try:
        return db.valid_session(conn, request.cookies.get("zkatt"))
    finally:
        conn.close()


def _need_auth(request: Request):
    if not _authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return None


@app.get("/api/setup-needed")
async def setup_needed():
    conn = db.connect()
    try:
        return {"needed": not db.get_setting(conn, "admin_pass")}
    finally:
        conn.close()


@app.post("/api/setup")
async def setup(request: Request):
    body = await request.json()
    password = (body.get("password") or "").strip()
    if len(password) < 4:
        return JSONResponse({"error": "Password must be at least 4 characters."}, status_code=400)
    conn = db.connect()
    try:
        if db.get_setting(conn, "admin_pass"):
            return JSONResponse({"error": "Already set up."}, status_code=400)
        db.set_setting(conn, "admin_pass", db.hash_password(password))
        token = db.create_session(conn)
    finally:
        conn.close()
    resp = JSONResponse({"ok": True})
    resp.set_cookie("zkatt", token, httponly=True, samesite="lax", max_age=72 * 3600)
    return resp


@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    conn = db.connect()
    try:
        stored = db.get_setting(conn, "admin_pass")
        if stored and db.verify_password(body.get("password") or "", stored):
            token = db.create_session(conn)
            resp = JSONResponse({"ok": True})
            resp.set_cookie("zkatt", token, httponly=True, samesite="lax", max_age=72 * 3600)
            return resp
    finally:
        conn.close()
    return JSONResponse({"error": "Wrong password."}, status_code=401)


@app.post("/api/logout")
async def logout(request: Request):
    conn = db.connect()
    try:
        db.destroy_session(conn, request.cookies.get("zkatt") or "")
    finally:
        conn.close()
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("zkatt")
    return resp


@app.get("/api/today")
async def api_today(request: Request):
    if (r := _need_auth(request)):
        return r
    conn = db.connect()
    try:
        today = attendance.pk_today()
        rep = attendance.daily_report(conn, today)
        feed = conn.execute(
            "SELECT p.punched_at, p.device_pin, COALESCE(s.name, '(unmapped)') AS name "
            "FROM punches p LEFT JOIN staff s ON s.id=p.staff_id "
            "WHERE substr(p.punched_at,1,10)=? "
            "ORDER BY p.punched_at DESC LIMIT 12",
            (today.isoformat(),),
        ).fetchall()
        devs = conn.execute("SELECT sn, label, last_seen, last_ip FROM devices ORDER BY last_seen DESC").fetchall()
        unmapped = conn.execute(
            "SELECT COUNT(*) c FROM punches WHERE staff_id IS NULL AND substr(punched_at,1,10)=?",
            (today.isoformat(),),
        ).fetchone()["c"]
        return {"report": rep,
                "feed": [dict(f) for f in feed],
                "devices": [dict(d) for d in devs],
                "unmapped_today": unmapped}
    finally:
        conn.close()


@app.get("/api/daily")
async def api_daily(request: Request, day: str = ""):
    if (r := _need_auth(request)):
        return r
    try:
        d = date.fromisoformat(day) if day else attendance.pk_today()
    except ValueError:
        return JSONResponse({"error": "bad date"}, status_code=400)
    conn = db.connect()
    try:
        return attendance.daily_report(conn, d)
    finally:
        conn.close()


@app.get("/api/monthly")
async def api_monthly(request: Request, month: str = ""):
    if (r := _need_auth(request)):
        return r
    try:
        y, m = (int(x) for x in (month or attendance.pk_today().strftime("%Y-%m")).split("-"))
        assert 1 <= m <= 12
    except (ValueError, AssertionError):
        return JSONResponse({"error": "bad month"}, status_code=400)
    conn = db.connect()
    try:
        return attendance.monthly_register(conn, y, m)
    finally:
        conn.close()


@app.get("/api/staff")
async def api_staff(request: Request):
    if (r := _need_auth(request)):
        return r
    conn = db.connect()
    try:
        rows = conn.execute("SELECT id, name, device_pin, device_sn, department, active FROM staff ORDER BY name").fetchall()
        return {"staff": [dict(x) for x in rows]}
    finally:
        conn.close()


@app.post("/api/staff")
async def api_staff_add(request: Request):
    if (r := _need_auth(request)):
        return r
    body = await request.json()
    name, pin = (body.get("name") or "").strip(), (body.get("pin") or "").strip()
    device_sn = (body.get("device_sn") or "").strip()
    if not name or not pin:
        return JSONResponse({"error": "Name and device PIN are required."}, status_code=400)
    conn = db.connect()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            conn.execute(
                "INSERT INTO staff(name, device_pin, device_sn, department, active, created_at) VALUES(?,?,?,?,?,?)",
                (name, pin, device_sn, (body.get("department") or "").strip(), 1, now))
        except Exception:
            return JSONResponse({"error": f"Device PIN {pin} is already assigned on that device."}, status_code=400)
        sid = conn.execute("SELECT id FROM staff WHERE device_pin=? AND device_sn=?", (pin, device_sn)).fetchone()["id"]
        if device_sn:
            conn.execute("UPDATE punches SET staff_id=? WHERE device_pin=? AND device_sn=? AND staff_id IS NULL",
                         (sid, pin, device_sn))
        else:
            conn.execute("UPDATE punches SET staff_id=? WHERE device_pin=? AND staff_id IS NULL", (sid, pin))
        conn.commit()
        return {"ok": True, "id": sid}
    finally:
        conn.close()


@app.put("/api/staff/{sid}")
async def api_staff_edit(sid: int, request: Request):
    if (r := _need_auth(request)):
        return r
    body = await request.json()
    conn = db.connect()
    try:
        conn.execute("UPDATE staff SET name=?, department=?, device_sn=?, active=? WHERE id=?",
                     ((body.get("name") or "").strip(), (body.get("department") or "").strip(),
                      (body.get("device_sn") or "").strip(),
                      1 if body.get("active") else 0, sid))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/staff/{sid}")
async def api_staff_del(sid: int, request: Request):
    if (r := _need_auth(request)):
        return r
    conn = db.connect()
    try:
        conn.execute("UPDATE staff SET active=0 WHERE id=?", (sid,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/unmapped")
async def api_unmapped(request: Request):
    if (r := _need_auth(request)):
        return r
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT device_pin, COUNT(*) c, MIN(punched_at) first_seen, MAX(punched_at) last_seen "
            "FROM punches WHERE staff_id IS NULL GROUP BY device_pin ORDER BY last_seen DESC LIMIT 50"
        ).fetchall()
        return {"pins": [dict(x) for x in rows]}
    finally:
        conn.close()


@app.get("/api/holidays")
async def api_holidays_get(request: Request):
    if (r := _need_auth(request)):
        return r
    conn = db.connect()
    try:
        rows = conn.execute("SELECT date, name FROM holidays ORDER BY date DESC LIMIT 100").fetchall()
        return {"holidays": [dict(x) for x in rows]}
    finally:
        conn.close()


@app.post("/api/holidays")
async def api_holidays_add(request: Request):
    if (r := _need_auth(request)):
        return r
    body = await request.json()
    try:
        d = date.fromisoformat(body.get("date") or "")
    except ValueError:
        return JSONResponse({"error": "bad date"}, status_code=400)
    conn = db.connect()
    try:
        conn.execute("INSERT OR REPLACE INTO holidays(date, name) VALUES(?, ?)",
                     (d.isoformat(), (body.get("name") or "").strip()))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/holidays/{day}")
async def api_holidays_del(day: str, request: Request):
    if (r := _need_auth(request)):
        return r
    conn = db.connect()
    try:
        conn.execute("DELETE FROM holidays WHERE date=?", (day,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/leave")
async def api_leave_toggle(request: Request):
    if (r := _need_auth(request)):
        return r
    body = await request.json()
    conn = db.connect()
    try:
        exists = conn.execute("SELECT 1 FROM leaves WHERE staff_id=? AND date=?",
                              (body.get("staff_id"), body.get("date"))).fetchone()
        if exists:
            conn.execute("DELETE FROM leaves WHERE staff_id=? AND date=?", (body.get("staff_id"), body.get("date")))
            action = "removed"
        else:
            conn.execute("INSERT INTO leaves(staff_id, date, note) VALUES(?,?,?)",
                         (body.get("staff_id"), body.get("date"), (body.get("note") or "").strip()))
            action = "added"
        conn.commit()
        return {"ok": True, "action": action}
    finally:
        conn.close()


@app.get("/api/settings")
async def api_settings_get(request: Request):
    if (r := _need_auth(request)):
        return r
    conn = db.connect()
    try:
        keys = ("institute_name", "shift_start", "shift_end", "grace_minutes", "weekly_off", "ingest_key")
        return {"settings": {k: db.get_setting(conn, k) for k in keys}}
    finally:
        conn.close()


@app.post("/api/settings")
async def api_settings_post(request: Request):
    if (r := _need_auth(request)):
        return r
    body = await request.json()
    conn = db.connect()
    try:
        for k in ("institute_name", "shift_start", "shift_end", "grace_minutes", "weekly_off"):
            if k in body:
                db.set_setting(conn, k, str(body[k]).strip())
        if body.get("new_password"):
            if len(body["new_password"]) < 4:
                return JSONResponse({"error": "Password must be at least 4 characters."}, status_code=400)
            db.set_setting(conn, "admin_pass", db.hash_password(body["new_password"]))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def _csv(rows: list[list[str]]) -> PlainTextResponse:
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerows(rows)
    return PlainTextResponse("\ufeff" + buf.getvalue(), media_type="text/csv")


@app.get("/api/export/daily.csv")
async def export_daily(request: Request, day: str = ""):
    if (r := _need_auth(request)):
        return r
    conn = db.connect()
    try:
        d = date.fromisoformat(day) if day else attendance.pk_today()
        rep = attendance.daily_report(conn, d)
    finally:
        conn.close()
    rows = [["Date", "Name", "Device PIN", "Department", "Status", "In", "Out", "Late (min)", "Early leave (min)", "Punches"]]
    for x in rep["rows"]:
        rows.append([rep["date"], x["name"], x["pin"], x["department"], x["status"],
                     x["in"] or "", x["out"] or "", x["late_min"], x["early_min"], x["punches"]])
    resp = _csv(rows)
    resp.headers["Content-Disposition"] = f"attachment; filename=attendance-{rep['date']}.csv"
    return resp


@app.get("/api/export/monthly.csv")
async def export_monthly(request: Request, month: str = ""):
    if (r := _need_auth(request)):
        return r
    conn = db.connect()
    try:
        y, m = (int(x) for x in (month or attendance.pk_today().strftime("%Y-%m")).split("-"))
        reg = attendance.monthly_register(conn, y, m)
    finally:
        conn.close()
    head = ["Name", "PIN", "Department"] + [str(d["d"]) for d in reg["days"]] + ["P", "L", "E", "A", "LV"]
    rows = [head]
    for g in reg["grid"]:
        rows.append([g["name"], g["pin"], g["department"]] +
                    [c["code"] for c in g["cells"]] +
                    [g["totals"]["P"], g["totals"]["L"], g["totals"]["E"], g["totals"]["A"], g["totals"]["LV"]])
    resp = _csv(rows)
    resp.headers["Content-Disposition"] = f"attachment; filename=register-{y}-{m:02d}.csv"
    return resp


@app.post("/api/ingest/punches")
async def ingest_punches(request: Request):
    """For the LAN pull agent: JSON {punches:[{pin, time, status, verify}]}."""
    key = request.query_params.get("key", "")
    conn = db.connect()
    try:
        if not key or key != db.get_setting(conn, "ingest_key"):
            return JSONResponse({"error": "bad key"}, status_code=403)
        body = await request.json()
        sn = (body.get("device_sn") or "LAN-AGENT").strip()
        lines = [f"{p['pin']}\t{p['time']}\t{p.get('status','')}\t{p.get('verify','')}"
                 for p in body.get("punches", [])]
        n = _store_attlog(conn, sn, lines)
        _touch_device(conn, sn, request.client.host if request.client else "")
        conn.commit()
        return {"ok": True, "stored": n}
    finally:
        conn.close()


@app.get("/api/health")
async def health():
    return {"ok": True}


# ------------------------------------------------------------- static ---
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(str(STATIC / "index.html"))
