# Coal GPS Report — web app (Phase 1)

Shared, multi-user web version of the offline "Actual GPS Report" tool.
Flask + SQLite, per-user login, server-side xlsx parsing, the ETA/cycle engine
rewritten in Python. One shared dataset for the whole team.

## What Phase 1 does
- Per-user accounts (register / login / logout)
- Upload GPS / Dispatch Plan / Weighbridge / Subcontractor xlsx — parsed on the server
- Computes visits → cycles → fleet status (haul, ETA raw, ETA criteria, reload status)
- Dashboard table + Leaflet map of zones and routes

## Phase 2 (not built yet)
Daily / Plan-vs-Actual / Subfleet report pages, on-map route drawing UI,
automated GPS feed ingestion, WhatsApp dispatch.

---

## A. DigitalOcean setup (do this once, on the droplet)

You already run a Flask droplet, so you can reuse it or spin up a fresh one.

1. **Droplet**: Ubuntu 24.04, smallest size is fine. SSH in as a sudo user.
2. **System packages**:
   ```
   sudo apt update
   sudo apt install -y python3-venv nginx git
   ```
3. **Get the code** (after you push it to GitHub — see section B):
   ```
   sudo git clone https://github.com/YOURNAME/coalapp.git /opt/coalapp
   sudo chown -R $USER:$USER /opt/coalapp
   ```
4. **Install + create DB**:
   ```
   cd /opt/coalapp
   bash deploy/setup.sh
   ```
5. **Run it as a service**:
   ```
   # edit the SECRET_KEY line first:
   nano deploy/coalapp.service
   sudo cp deploy/coalapp.service /etc/systemd/system/
   sudo chown -R www-data:www-data /opt/coalapp
   sudo systemctl daemon-reload
   sudo systemctl enable --now coalapp
   sudo systemctl status coalapp     # should be "active (running)"
   ```
6. **Put Nginx in front**:
   ```
   sudo cp deploy/nginx.conf.sample /etc/nginx/sites-available/coalapp
   sudo nano /etc/nginx/sites-available/coalapp     # set your domain/subdomain
   sudo ln -s /etc/nginx/sites-available/coalapp /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
7. **HTTPS** (point a DNS A-record at the droplet first):
   ```
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d gps.YOURDOMAIN.com
   ```
8. **Firewall** (if using ufw):
   ```
   sudo ufw allow 'Nginx Full'
   sudo ufw allow OpenSSH
   sudo ufw enable
   ```

Open the site, click **Register**, create the first account, and upload your xlsx files.

### Updating later
```
cd /opt/coalapp && git pull
./venv/bin/pip install -r requirements.txt
sudo systemctl restart coalapp
```

---

## B. Push to GitHub (do this from your own machine)

1. Create an empty repo on GitHub named `coalapp`.
2. In the folder that holds these files:
   ```
   git init
   git add .
   git commit -m "Phase 1: Flask web app"
   git branch -M main
   git remote add origin https://github.com/YOURNAME/coalapp.git
   git push -u origin main
   ```

---

## Run locally (optional, to test before deploying)
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python wsgi.py        # http://127.0.0.1:5000
```

## Notes
- Database is a file at `instance/coalapp.db`. Back it up by copying that file.
- Zones (anchors) and the 6 route legs are seeded on first run. Route polylines
  start empty — ETA needs them drawn; the drawing UI is Phase 2, but you can
  PUT points to `/api/routes/<leg_key>` in the meantime.
