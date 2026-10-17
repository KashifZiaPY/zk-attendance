#!/usr/bin/env python3
"""LAN pull agent for ZKTeco terminals WITHOUT the ADMS/Cloud Server menu
(classic K40, plain IN01, ...).

Runs on any always-on PC on the SAME network as the device(s). Every few
minutes it reads new punches from each device over the LAN (port 4370, ZK
protocol via the `pyzk` library) and forwards them to the cloud dashboard's
ingest API. The device stores ~80-100k punches itself, so nothing is lost
while this PC is off — the backlog is forwarded when it returns.

Install:  pip install pyzk requests
Run:      python pull_agent.py

Config (edit below or use env vars):
  Single device: ZKATT_DEVICE_IP / ZKATT_DEVICE_PASSWORD / ZKATT_DEVICE_LABEL
  Several devices (even at several sites — run one agent per site):
      ZKATT_DEVICES_JSON='[{"ip":"192.168.100.111","password":"1234","label":"LAN-GVTIW"},
                           {"ip":"192.168.1.50","password":"0","label":"LAN-GTTI"}]'
  Give every site/device a DISTINCT label — it is how the dashboard tells
  "user 5" on one device from "user 5" on another.
"""
import json
import os
import time
from datetime import datetime

try:
    from zk import ZK
except ImportError:
    raise SystemExit("Install pyzk first:  pip install pyzk")

import requests

SERVER = os.environ.get("ZKATT_SERVER", "http://YOUR-SERVER:8000")
INGEST_KEY = os.environ.get("ZKATT_KEY", "PASTE-INGEST-KEY-FROM-SETTINGS")
POLL_SECONDS = int(os.environ.get("ZKATT_POLL", "180"))
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pull_agent_state.json")


def load_devices():
    raw = os.environ.get("ZKATT_DEVICES_JSON", "").strip()
    if raw:
        return json.loads(raw)
    return [{
        "ip": os.environ.get("ZKATT_DEVICE_IP", "192.168.100.111"),
        "port": int(os.environ.get("ZKATT_DEVICE_PORT", "4370")),
        "password": os.environ.get("ZKATT_DEVICE_PASSWORD", "0"),
        "label": os.environ.get("ZKATT_DEVICE_LABEL", ""),
    }]


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def poll_device(dev: dict, state: dict) -> None:
    label = dev.get("label") or f"LAN-{dev['ip']}"
    zk = ZK(dev["ip"], port=int(dev.get("port", 4370)), timeout=10,
            password=int(dev.get("password", "0")))
    conn = zk.connect()
    try:
        conn.disable_device()
        logs = conn.get_attendance()
        since = state.get(label, "2000-01-01 00:00:00")
        new = [a for a in logs if a.timestamp.strftime("%Y-%m-%d %H:%M:%S") > since]
        if new:
            payload = {
                "device_sn": label,
                "punches": [
                    {"pin": str(a.user_id),
                     "time": a.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                     "status": str(a.status), "verify": str(a.punch)}
                    for a in sorted(new, key=lambda x: x.timestamp)
                ],
            }
            r = requests.post(
                SERVER.rstrip("/") + "/api/ingest/punches",
                params={"key": INGEST_KEY}, json=payload, timeout=30)
            r.raise_for_status()
            print(f"{datetime.now():%H:%M:%S} [{label}] forwarded {r.json().get('stored', 0)} punches")
            state[label] = max(a.timestamp for a in new).strftime("%Y-%m-%d %H:%M:%S")
            save_state(state)
        else:
            print(f"{datetime.now():%H:%M:%S} [{label}] no new punches")
        conn.enable_device()
    finally:
        conn.disconnect()


if __name__ == "__main__":
    devices = load_devices()
    print(f"Pull agent -> {len(devices)} device(s) -> {SERVER}")
    state = load_state()
    while True:
        for dev in devices:
            try:
                poll_device(dev, state)
            except Exception as e:  # keep going; a device may be offline
                print(f"{datetime.now():%H:%M:%S} [{dev.get('label') or dev['ip']}] error: {e}")
        time.sleep(POLL_SECONDS)
