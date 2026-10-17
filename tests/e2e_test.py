import json, urllib.request, http.cookiejar, sys

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8125"
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def call(method, path, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": ctype} if data else {})
    with op.open(req) as r:
        return (r.status, r.read().decode())

fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

check("setup", '"ok":true' in call("POST", "/api/setup", {"password": "test1234"})[1])
for name, pin, dept in [("Ayesha Khan", "5", "Teaching"), ("Bilal Ahmed", "7", "Teaching"),
                        ("Sana Tariq", "9", "Accounts"), ("Imran Ali", "11", "Support")]:
    check("staff " + name, '"ok":true' in call("POST", "/api/staff", {"name": name, "pin": pin, "department": dept})[1])
try:
    call("POST", "/api/staff", {"name": "Clone", "pin": "5", "department": "X"}); check("dup pin blocked", False)
except Exception: check("dup pin blocked", True)

def push(day, rows):
    body = "".join(f"{pin}\t{day} {t}\t0\t1\t0\t0\t0\n" for pin, t in rows)
    r1 = call("POST", "/iclock/cdata.aspx?SN=K40TEST001&table=ATTLOG", raw=body.encode(), ctype="text/plain")[1]
    call("POST", "/iclock/cdata.aspx?SN=K40TEST001&table=ATTLOG", raw=body.encode(), ctype="text/plain")  # dup resend
    return r1

check("push 12th", push("2026-10-12", [("5","08:01:00"),("5","14:33:00"),("7","08:05:00"),("7","14:30:00"),
                    ("9","08:20:00"),("9","14:29:00"),("99","09:00:00")]).startswith("OK"))
check("push 14th", push("2026-10-14", [("5","08:03:00"),("7","08:31:00"),("9","07:59:00"),("9","14:32:00"),
                    ("99","09:10:00")]).startswith("OK"))
check("holiday add", '"ok":true' in call("POST", "/api/holidays", {"date": "2026-10-13", "name": "Test Holiday"})[1])
d = json.loads(call("GET", "/api/daily?day=2026-10-12")[1])
rows = {r["name"]: r for r in d["rows"]}
check("Ayesha present", rows["Ayesha Khan"]["status"] == "Present")
check("Sana late10 early1", rows["Sana Tariq"]["status"] == "Late + Early" and rows["Sana Tariq"]["late_min"] == 10 and rows["Sana Tariq"]["early_min"] == 1)
check("Imran absent", rows["Imran Ali"]["status"] == "Absent")
t = json.loads(call("GET", "/api/today")[1])
check("today summary", t["report"]["summary"] == {"present": 3, "late": 1, "early": 0, "absent": 1, "leave": 0, "off": 0})
check("today unmapped=1", t["unmapped_today"] == 1)
m = json.loads(call("GET", "/api/monthly?month=2026-10")[1])
g = {x["name"]: x for x in m["grid"]}
check("register holiday cell", g["Ayesha Khan"]["cells"][12]["code"] == "H")
check("register totals", g["Ayesha Khan"]["totals"]["P"] == 2 and g["Imran Ali"]["totals"]["A"] == 26)
u = json.loads(call("GET", "/api/unmapped")[1])
check("unmapped pin99 x2 (no dupes)", u["pins"] == [{"device_pin": "99", "c": 2, "first_seen": "2026-10-12 09:00:00", "last_seen": "2026-10-14 09:10:00"}] if u["pins"] else False)
check("daily csv", call("GET", "/api/export/daily.csv?day=2026-10-12")[1].count("\n") >= 5)
s = json.loads(call("GET", "/api/settings")[1])["settings"]
check("ingest key exists", bool(s["ingest_key"]))
check("ingest good key", '"ok":true' in call("POST", f"/api/ingest/punches?key={s['ingest_key']}",
      {"device_sn": "LAN-TEST", "punches": [{"pin": "5", "time": "2026-10-14 15:00:00", "status": "1", "verify": "1"}]})[1])
try:
    call("POST", "/api/ingest/punches?key=wrong", {"punches": []}); check("ingest bad key blocked", False)
except Exception: check("ingest bad key blocked", True)
check("leave toggle", '"action":"added"' in call("POST", "/api/leave", {"staff_id": rows["Imran Ali"]["id"], "date": "2026-10-12"})[1])
d2 = json.loads(call("GET", "/api/daily?day=2026-10-12")[1])
check("Imran now Leave", {r["name"]: r for r in d2["rows"]}["Imran Ali"]["status"] == "Leave")

# --- multi-device: same PIN 5 on device SITE2 is a DIFFERENT person ---
check("staff Murree pin5@SITE2", '"ok":true' in call("POST", "/api/staff",
      {"name": "Murree Tester", "pin": "5", "department": "GTTI", "device_sn": "SITE2"})[1])
check("ingest SITE2 pin5", '"ok":true' in call("POST", f"/api/ingest/punches?key={s['ingest_key']}",
      {"device_sn": "SITE2", "punches": [{"pin": "5", "time": "2026-10-14 09:05:00", "status": "0", "verify": "1"}]})[1])
d3 = json.loads(call("GET", "/api/daily?day=2026-10-14")[1])
rows3 = {r["name"]: r for r in d3["rows"]}
check("SITE2 punch -> Murree Tester 09:05", rows3["Murree Tester"]["in"] == "09:05")
check("Ayesha keeps her own 08:03 (no cross-device mixup)", rows3["Ayesha Khan"]["in"] == "08:03")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
