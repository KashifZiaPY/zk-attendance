#!/usr/bin/env bash
# Install ZK Attendance on a fresh Ubuntu server (e.g. Oracle Cloud Always Free).
# Run as a user with sudo:  bash deploy/install.sh
set -euo pipefail

APP_DIR=/opt/zk-attendance
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"

# copy project files (run this script from the repo root)
cp -r app static agent "$APP_DIR"/

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet fastapi "uvicorn[standard]"

sudo cp deploy/zk-attendance.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zk-attendance

# open the dashboard port (Oracle Cloud also needs the ingress rule in the console)
if command -v ufw >/dev/null; then
  sudo ufw allow 8000/tcp || true
fi

echo "ZK Attendance is starting on port 8000."
echo "Open http://<this-server-ip>:8000 and create your admin password."
