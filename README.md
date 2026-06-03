# Local ScreenShare (USB-Portable)

A fully local Python screen-sharing web app.

- No external API calls
- Same-WiFi access supported
- Portable folder usage (USB friendly)
- Auto install + launch with `start_localhost.bat`

## Project files

- `app.py` - Flask server and local signaling endpoints
- `templates/index.html` - screen-share UI (presenter/viewer)
- `requirements.txt` - dependencies
- `start_localhost.bat` - Windows auto setup and launch

## Setup (Windows)

1. Put the folder anywhere, e.g. `D:\sharescreen`.
2. Ensure Python 3 is installed (either `py` launcher or `python` in PATH).
3. Double-click `start_localhost.bat`.
4. Keep terminal open while hosting.

## Usage

1. Host clicks **Start Presenting**.
2. Click **Create Room**.
3. Click **Start Screen Share** and allow browser screen capture.
4. Viewer on same Wi-Fi opens host URL, chooses **Join Session**, enters room code.

## URLs

- Local: `http://127.0.0.1:<PORT>`
- Same Wi-Fi: `http://<host-lan-ip>:<PORT>`

Default port is `8000`. If `8000` is busy, run with another port:

```bat
set PORT=8001
python app.py
```

## Notes

- Signaling data is stored in local server memory only.
- No third-party cloud signaling is used.
- For LAN access, allow Python through Windows Firewall if prompted.
