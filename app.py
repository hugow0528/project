from __future__ import annotations

import os
import random
import socket
import sqlite3
import string
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "localhub.db"
DEFAULT_PORT = int(os.environ.get("PORT", "8000"))
MAX_ROOM_CODE_ATTEMPTS = 20
MAX_USERNAME_LENGTH = 40
MAX_MESSAGE_LENGTH = 800

app = Flask(__name__)


def get_local_ip() -> str:
    """Best-effort LAN IP detection without external network calls."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with db_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                code TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code TEXT NOT NULL,
                username TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (room_code) REFERENCES rooms(code) ON DELETE CASCADE
            );
            """
        )


def generate_room_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


@app.get("/")
def home():
    return render_template(
        "index.html",
        max_username_length=MAX_USERNAME_LENGTH,
        max_message_length=MAX_MESSAGE_LENGTH,
    )


@app.get("/api/server-info")
def server_info():
    host = request.host.split(":")[0] if request.host else "localhost"
    port = request.host.split(":")[1] if ":" in request.host else str(DEFAULT_PORT)
    local_ip = get_local_ip()
    return jsonify(
        {
            "host": host,
            "port": port,
            "local_url": f"http://127.0.0.1:{port}",
            "lan_url": f"http://{local_ip}:{port}",
            "storage": str(DB_PATH),
        }
    )


@app.post("/api/rooms")
def create_room():
    code = None
    with db_conn() as conn:
        for _ in range(MAX_ROOM_CODE_ATTEMPTS):
            candidate = generate_room_code()
            exists = conn.execute("SELECT 1 FROM rooms WHERE code = ?", (candidate,)).fetchone()
            if not exists:
                code = candidate
                break

        if not code:
            return jsonify({"error": "Could not generate a unique room code."}), 500

        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO rooms (code, created_at) VALUES (?, ?)", (code, created_at))
        conn.commit()

    return jsonify({"room_code": code}), 201


@app.get("/api/rooms/<room_code>/messages")
def get_messages(room_code: str):
    room_code = room_code.upper().strip()
    with db_conn() as conn:
        room = conn.execute("SELECT code FROM rooms WHERE code = ?", (room_code,)).fetchone()
        if not room:
            return jsonify({"error": "Room not found."}), 404

        rows = conn.execute(
            """
            SELECT username, content, created_at
            FROM messages
            WHERE room_code = ?
            ORDER BY id ASC
            """,
            (room_code,),
        ).fetchall()

    return jsonify(
        {
            "room_code": room_code,
            "messages": [
                {
                    "username": row["username"],
                    "content": row["content"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
        }
    )


@app.post("/api/rooms/<room_code>/messages")
def post_message(room_code: str):
    room_code = room_code.upper().strip()
    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip()[:MAX_USERNAME_LENGTH]
    content = str(data.get("content", "")).strip()[:MAX_MESSAGE_LENGTH]

    if not username or not content:
        return jsonify({"error": "username and content are required."}), 400

    with db_conn() as conn:
        room = conn.execute("SELECT code FROM rooms WHERE code = ?", (room_code,)).fetchone()
        if not room:
            return jsonify({"error": "Room not found."}), 404

        conn.execute(
            """
            INSERT INTO messages (room_code, username, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (room_code, username, content, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    return jsonify({"ok": True}), 201


if __name__ == "__main__":
    init_db()
    lan_ip = get_local_ip()
    print()
    print("LocalHub server is starting...")
    print(f"Local URL: http://127.0.0.1:{DEFAULT_PORT}")
    print(f"LAN URL:   http://{lan_ip}:{DEFAULT_PORT}")
    print(f"SQLite DB: {DB_PATH}")
    print()
    app.run(host="0.0.0.0", port=DEFAULT_PORT)
