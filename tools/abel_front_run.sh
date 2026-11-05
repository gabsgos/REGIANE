#!/data/data/com.termux/files/usr/bin/sh
exec proot-distro login debian -- bash -lc 'cd /opt/regianefront; export DATA_BACKEND=abel_api ABEL_API_URL=http://127.0.0.1:8001/api PORT=8050 DASH_PREFIX=/abel-front/; exec /opt/regianefront/.venv/bin/python app.py'
