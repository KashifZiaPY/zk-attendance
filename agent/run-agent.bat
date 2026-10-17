@echo off
REM ============================================================
REM  ZK Attendance - pull agent launcher (Windows)
REM  Edit the 5 values below ONCE, save, then double-click.
REM  SERVER    = your Render URL (dashboard address)
REM  KEY       = dashboard -> Settings -> Device connection -> ingest key
REM  PASSWORD  = the Password shown on the K40 Comm screen
REM ============================================================
set ZKATT_SERVER=https://YOUR-APP.onrender.com
set ZKATT_KEY=PASTE-INGEST-KEY-HERE
set ZKATT_DEVICE_IP=192.168.100.111
set ZKATT_DEVICE_PASSWORD=PASTE-COMM-PASSWORD-HERE
set ZKATT_DEVICE_LABEL=LAN-GVTIW

cd /d %~dp0
python pull_agent.py
pause
