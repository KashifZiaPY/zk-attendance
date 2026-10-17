# ZK Attendance — browser dashboard for the ZKTeco K40

A free, self-hosted attendance system. Punches from the K40 end up on your own
server, and you open an elegant dashboard in any browser — office, home, phone.

**No license fees. No ZKTeco dealer. Your data stays on your server.**

## How it works

```
K40 (office LAN)
   │  Path A (K40 Pro): ADMS push — device calls OUT, no static IP needed
   │  Path B (classic K40): tiny reader on an office PC forwards punches
   ▼
Dashboard server (free cloud hosting) — receives punches, stores them safely
   ▼
Dashboard in your browser — today, daily, monthly register, staff, exports
```

## Hosting — recommended: Render + Neon (free, NO card anywhere)

Oracle/Google/Fly/Railway all demand a card even for "free". These two don't:

- **Render** (the app): [render.com](https://render.com) — free web service.
- **Neon** (the database): [neon.tech](https://neon.tech) — free Postgres,
  1 GB (years of attendance), data survives restarts — unlike Render's own
  disk, which is wiped on every restart, so the database MUST live in Neon.

Steps:

1. **Put this project on GitHub** (Render deploys from a repo): create a repo
   on [github.com](https://github.com) and upload these files (web upload is
   fine, like your other projects).
2. **Create the database:** sign up at [neon.tech](https://neon.tech) (Google/
   GitHub login, no card) → **New Project** → copy the **connection string**
   (looks like `postgresql://user:pass@host/db?sslmode=require`). Keep it secret.
3. **Create the app:** sign up at [render.com](https://render.com) (GitHub
   login, no card) → **New + → Blueprint** → pick your repo (it reads
   `render.yaml`) → when prompted for **DATABASE_URL**, paste the Neon
   connection string → **Apply**. First deploy takes a few minutes.
4. Open the Render URL (like `https://zk-attendance-xxxx.onrender.com`) and
   create your admin password. Done — live worldwide over HTTPS.

Honest tradeoffs of the free tier: the app **sleeps after 15 minutes** with no
traffic, and the first visit after that takes ~30–60 seconds to wake. In
practice the office reader sends punches every 3 minutes, which keeps it
awake all working day; the sleep mainly shows up on quiet mornings/weekends.
Nothing is ever lost — punches live in Neon, and the device + reader buffer
everything else.

## Hosting — alternative: your own server (Oracle VM / VPS / Pi)

If you later get a server of your own, the same code runs there with a local
SQLite database (no Neon needed) — Oracle Cloud Always Free steps:

1. **Create a free Oracle Cloud account:** [oracle.com/cloud/free](https://www.oracle.com/cloud/free/)
   → **Start for free** (card required for verification — skip this whole
   option if that's a dealbreaker). Pick region closest to Pakistan (Mumbai).
2. **Create the VM:** [cloud.oracle.com](https://cloud.oracle.com) → ☰ →
   **Compute → Instances → Create instance**. Image: Canonical Ubuntu 22.04.
   Shape: **VM.Standard.E2.1.Micro** (Always Free). SSH keys: **Generate a key
   pair for me → Save private key**. Copy the **Public IP** when Running.
3. **Open port 8000:** instance → **Primary VNIC → Subnet → Security Lists →
   Default Security List → Add Ingress Rules**: `0.0.0.0/0`, TCP, **8000**.
4. **Install:**
   ```bash
   ssh -i path\to\ssh-key.key ubuntu@<PUBLIC-IP>
   sudo apt update && sudo apt install -y python3-venv git ufw
   git clone <this-repo-url> zkatt && cd zkatt && bash deploy/install.sh
   ```
5. Open **http://&lt;PUBLIC-IP&gt;:8000** and create the admin password.

Optional, recommended: point a free DuckDNS name at the server IP so you don't
have to remember the IP, and put the dashboard behind a login (already built
in — change the password in Settings).

## K40 device setup — read this first

**Check your unit's label: "K40" or "K40 Pro"?** Per ZKTeco's official datasheet,
the classic **K40 has no ADMS/cloud option** (its optional functions are only
ID/IC card, SSR reports, external bell). The **K40 Pro lists ADMS as an
optional function**.

### Path A — K40 Pro with "Cloud Server Setting" in the menu (2 minutes)

1. On the device: **Menu → COMM → Cloud Server Setting**
2. Set **Server Mode: ADMS**
3. **Server Address:** your server's public IP (or DuckDNS name)
4. **Server Port:** 8000
5. **HTTPS: Off** (most K40 firmware only speaks plain HTTP)
6. Save, reboot the device.

Within a minute, the dashboard's **Today → Device** panel shows the K40 as
connected. Every fingerprint punch appears in the live feed within seconds.

### Path B — classic K40 (no cloud menu): LAN pull agent

This is the reliable path for the classic K40. Two one-time settings on the
device first:

1. **Menu → System → Comm**: set **DHCP to Off** and keep the IP
   (e.g. 192.168.100.111). DHCP lets the router change the device's address,
   which would break the reader — a fixed IP keeps it findable.
2. Note the **Password** shown on that same Comm screen — the reader needs it
   to connect.

Then, on any office PC that is on during working hours:

1. Install Python 3: [python.org/downloads](https://www.python.org/downloads/)
   (Windows installer — tick **"Add python.exe to PATH"** during setup).
2. Open Command Prompt / Terminal and run:
   ```bash
   pip install pyzk requests
   ```
3. Copy the `agent` folder to the PC and edit **`agent/run-agent.bat`**:
   server URL (your Render URL like `https://zk-attendance-xxxx.onrender.com`),
   ingest key (dashboard → Settings → Device connection), device password
   (the Comm screen), device IP (`192.168.100.111`), label `LAN-GVTIW`.
4. Double-click `run-agent.bat`. It reads new punches from the K40 over the
   LAN every 3 minutes and forwards them to the dashboard.
5. **Auto-start with Windows (2 minutes):** open **Task Scheduler** →
   *Create Basic Task* → name it `ZK Attendance Agent` → Trigger: **When I
   log on** → Action: **Start a program** → browse to `run-agent.bat` →
   Finish. Now it starts by itself every morning; just leave the PC logged in.

It reads new punches from the K40 over the LAN every 3 minutes and forwards
them to the dashboard. The device stores up to ~100,000 punches itself, so
nothing is lost while the PC is off — the agent forwards the backlog when the
PC comes back on. The dashboard is identical to Path A.

## Daily use

- **Multiple devices / institutes:** one dashboard can serve several devices,
  even at different institutes. Each device gets a distinct serial (ADMS) or
  reader **label** (pull agent, e.g. `LAN-GVTIW`, `LAN-GTTI`) — give every
  site its own label, because "user 5" on one device is a different person
  from "user 5" on another. When adding staff, fill the optional *Device
  serial / reader label* field to tie that person to their device; leave it
  blank only if you run a single device. A reader for a device must run on a
  PC on that device's own network; an ADMS device needs no reader anywhere.

- **Staff tab** — add each employee: name + the user number shown on the K40
  ("Device PIN") + department. If someone already punched before being added,
  assigning their PIN links all their past punches automatically.
- **Today** — present / late / absent cards + live punch feed.
- **Daily** — pick any date: in/out times, late minutes, early-leave minutes,
  one-click leave marking, CSV download, print.
- **Monthly Register** — the classic attendance grid (P/L/E/A/LV/H/W) with
  totals, CSV download, print-friendly.
- **Settings** — shift start/end, late grace minutes, weekly off day, holidays,
  change password.
- ⚠ **Unmapped fingerprints** — punches from PINs no staff owns are flagged,
  never silently dropped.

Rules: first punch of the day = check-in, last punch = check-out. Late =
arrival after shift start + grace. Early leave = last punch before shift end.

## Fallback: LAN pull agent (no ADMS menu on the device)

On any office PC that stays on during working hours:

```bash
pip install pyzk requests
# edit agent/pull_agent.py: device IP, server URL, ingest key (from Settings)
python agent/pull_agent.py
```

It reads new punches from the K40 over the LAN every 3 minutes and forwards
them to the dashboard. Everything else is identical.

> **PC off? Nothing is lost.** The K40 stores up to ~80,000 punches itself
> (years at institute usage). The agent forwards the whole backlog when the
> PC comes back on. The only cost of the PC being off is that the dashboard
> pauses at the last sync instead of updating live.

### Always-on without the office PC: Raspberry Pi

If you want the dashboard live 24/7 without depending on any office PC, a
Raspberry Pi (4, or Zero 2 W — roughly Rs. 8–12k, uses ~5W, survives on a
small UPS through load shedding) does the job:

```bash
# on the Pi (Raspberry Pi OS), connected to the office network by cable or WiFi
sudo apt update && sudo apt install -y python3-pip
pip3 install --break-system-packages pyzk requests
mkdir -p ~/zkatt-agent && cp pull_agent.py zkatt-agent.service ~/zkatt-agent/
# edit ~/zkatt-agent/pull_agent.py (or set the env vars in the .service file):
#   device IP, device password, server URL, ingest key
sudo cp ~/zkatt-agent/zkatt-agent.service /etc/systemd/system/
sudo systemctl enable --now zkatt-agent
```

Check it's alive: `systemctl status zkatt-agent` and `journalctl -u zkatt-agent -f`.
The Pi just sits there forever — no screen, no keyboard needed after setup.

## Files

```
app/main.py        FastAPI: /iclock/* device endpoints + /api/* dashboard API
app/db.py          SQLite schema, sessions, password hashing
app/attendance.py  pairing logic, daily/monthly reports (Pakistan time)
static/            the dashboard (no build step, TEVTA green theme)
agent/pull_agent.py  fallback LAN reader (pyzk)
deploy/            install.sh + systemd unit for the free VM
```

## Security notes

- The ADMS protocol itself has no password; the server only *receives* punches
  (a forged punch is visible and voidable, it can't read or change anything).
- The dashboard is password-protected (hashed, salted) with expiring sessions.
- Keep the VM's OS updated (`sudo apt upgrade`) like any server.
