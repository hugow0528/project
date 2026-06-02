# LocalHub (USB-Portable Localhost Web App)

A fully local Python web app that stores all data on the local server using SQLite.

- No external API calls
- Local database only (`/data/localhub.db`)
- Usable on same Wi-Fi (`http://<your-lan-ip>:8000`)
- Includes `start_localhost.bat` for one-click Windows setup and run

## Files

- `/tmp/workspace/hugow0528/project/app.py` - Python server (Flask + SQLite)
- `/tmp/workspace/hugow0528/project/templates/index.html` - Web UI
- `/tmp/workspace/hugow0528/project/requirements.txt` - Python dependencies
- `/tmp/workspace/hugow0528/project/start_localhost.bat` - Auto install + host launcher

## Setup (Windows, USB portable)

1. Copy the project folder to a USB drive (or any folder).
2. On target PC, install Python 3.10+ (with `py` launcher enabled).
3. Double-click `start_localhost.bat`.
4. Script will:
   - create `.venv`
   - install libraries from `requirements.txt`
   - start the website
   - show Local URL and same-Wi-Fi URL
5. Keep terminal open while hosting.

## Access from same Wi-Fi

- Host computer: `http://127.0.0.1:8000`
- Other devices on same Wi-Fi: `http://<host-ip>:8000`

If other devices cannot connect, allow Python through Windows Firewall and verify both devices are in the same subnet.

## App usage

1. Click **Create New Room** to generate a room code.
2. Share room code with users in same Wi-Fi.
3. Users enter room code + name and click **Join**.
4. Send messages; all are saved to local SQLite.

## Notes

- Data is stored in `data/localhub.db` on the host machine.
- To clear data, stop server and delete `data/localhub.db`.
