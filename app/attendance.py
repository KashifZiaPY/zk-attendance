"""Attendance math: pair punches into in/out, late/early, registers."""
from __future__ import annotations

import calendar
import sqlite3
from datetime import date, datetime, timedelta, timezone

PKT = timezone(timedelta(hours=5))


def pk_today() -> date:
    """'Today' in Pakistan time — the device stamps punches in local PKT."""
    return datetime.now(PKT).date()

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _fmt_min(total: int | None) -> str:
    if total is None:
        return ""
    return f"{total // 60:02d}:{total % 60:02d}"


def day_kind(conn: sqlite3.Connection, day: date, weekly_off: str) -> str:
    """'holiday' | 'weekly_off' | 'working'."""
    if conn.execute("SELECT 1 FROM holidays WHERE date=?", (day.isoformat(),)).fetchone():
        return "holiday"
    if WEEKDAYS[day.weekday()] == weekly_off:
        return "weekly_off"
    return "working"


def on_leave(conn: sqlite3.Connection, staff_id: int, day: date):
    return conn.execute(
        "SELECT note FROM leaves WHERE staff_id=? AND date=?", (staff_id, day.isoformat())
    ).fetchone()


def staff_day(conn: sqlite3.Connection, staff_id: int, day: date, cfg: dict) -> dict:
    """One staff member's attendance summary for one date."""
    day_s = day.isoformat()
    kind = day_kind(conn, day, cfg["weekly_off"])
    leave = on_leave(conn, staff_id, day)

    rows = conn.execute(
        "SELECT punched_at FROM punches WHERE staff_id=? AND substr(punched_at,1,10)=? ORDER BY punched_at",
        (staff_id, day_s),
    ).fetchall()
    times = [r["punched_at"][11:16] for r in rows]
    in_t = times[0] if times else None
    out_t = times[-1] if len(times) > 1 else None

    rec = {
        "date": day_s, "kind": kind, "punches": len(times),
        "in": in_t, "out": out_t, "status": "", "late_min": 0, "early_min": 0,
        "leave_note": leave["note"] if leave else "",
    }
    if kind != "working":
        rec["status"] = "Holiday" if kind == "holiday" else "Weekly off"
        return rec
    if leave:
        rec["status"] = "Leave"
        return rec
    if not times:
        rec["status"] = "Absent"
        return rec

    late = max(0, _to_min(in_t) - (_to_min(cfg["shift_start"]) + int(cfg["grace_minutes"])))
    early = max(0, _to_min(cfg["shift_end"]) - _to_min(out_t)) if out_t else 0
    rec["late_min"], rec["early_min"] = late, early
    if late and early:
        rec["status"] = "Late + Early"
    elif late:
        rec["status"] = "Late"
    elif early:
        rec["status"] = "Early leave"
    else:
        rec["status"] = "Present"
    return rec


def daily_report(conn: sqlite3.Connection, day: date) -> dict:
    cfg = {k: conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()["value"]
           for k in ("shift_start", "shift_end", "grace_minutes", "weekly_off")}
    staff = conn.execute(
        "SELECT id, name, device_pin, department FROM staff WHERE active=1 ORDER BY name"
    ).fetchall()
    rows = []
    for s in staff:
        r = staff_day(conn, s["id"], day, cfg)
        rows.append({"id": s["id"], "name": s["name"], "pin": s["device_pin"],
                     "department": s["department"] or "", **r})
    summary = {"present": 0, "late": 0, "early": 0, "absent": 0, "leave": 0, "off": 0}
    for r in rows:
        st = r["status"]
        if st in ("Present",):
            summary["present"] += 1
        if "Late" in st:
            summary["late"] += 1
            summary["present"] += 1
        if "Early" in st:
            summary["early"] += 1
            if "Late" not in st:
                summary["present"] += 1
        if st == "Absent":
            summary["absent"] += 1
        if st == "Leave":
            summary["leave"] += 1
        if st in ("Holiday", "Weekly off"):
            summary["off"] += 1
    holiday = conn.execute("SELECT name FROM holidays WHERE date=?", (day.isoformat(),)).fetchone()
    return {"date": day.isoformat(), "weekday": WEEKDAYS[day.weekday()],
            "kind": day_kind(conn, day, cfg["weekly_off"]),
            "holiday_name": holiday["name"] if holiday else "",
            "shift": f"{cfg['shift_start']} – {cfg['shift_end']}",
            "summary": summary, "rows": rows}


def monthly_register(conn: sqlite3.Connection, year: int, month: int) -> dict:
    cfg = {k: conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()["value"]
           for k in ("shift_start", "shift_end", "grace_minutes", "weekly_off")}
    staff = conn.execute(
        "SELECT id, name, device_pin, department FROM staff WHERE active=1 ORDER BY name"
    ).fetchall()
    ndays = calendar.monthrange(year, month)[1]
    days = [date(year, month, d) for d in range(1, ndays + 1)]
    grid, totals = [], []
    for s in staff:
        cells, t = [], {"P": 0, "L": 0, "E": 0, "A": 0, "LV": 0}
        for d in days:
            r = staff_day(conn, s["id"], d, cfg)
            code = {"Present": "P", "Late": "L", "Early leave": "E",
                    "Late + Early": "L", "Absent": "A", "Leave": "LV"}.get(r["status"], "")
            if r["status"] in ("Holiday", "Weekly off"):
                code = "H" if r["status"] == "Holiday" else "W"
            cells.append({"d": d.day, "code": code, "status": r["status"],
                          "in": r["in"], "out": r["out"],
                          "late_min": r["late_min"], "early_min": r["early_min"]})
            if code in t:
                t[code] += 1
        grid.append({"id": s["id"], "name": s["name"], "pin": s["device_pin"],
                     "department": s["department"] or "", "cells": cells, "totals": t})
        totals.append(t)
    return {"year": year, "month": month, "month_name": calendar.month_name[month],
            "days": [{"d": d.day, "wd": WEEKDAYS[d.weekday()][0],
                      "kind": day_kind(conn, d, cfg["weekly_off"])} for d in days],
            "grid": grid}


def today_str() -> str:
    return date.today().isoformat()
