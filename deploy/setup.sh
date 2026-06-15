#!/usr/bin/env bash
# Run ON THE DROPLET after cloning the repo to /opt/coalapp
set -e
cd /opt/coalapp
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
# create the DB + seed defaults
./venv/bin/python -c "from app import create_app; create_app()"
echo "Setup done. Now install the systemd service and nginx config (see README)."
