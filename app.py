import json
import os
import random
import socket
import sqlite3
import string
import threading
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import qrcode
from flask import Flask, Response, jsonify, send_from_directory
from flask_sock import Sock

BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "local_data"
DB_PATH = DB_DIR / "sync_cast.db"

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
sock = Sock(app)
state_lock = threading.Lock()
rooms = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    DB_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                presenter_id TEXT,
                mute_all INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                closed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                peer_id TEXT NOT NULL,
                role TEXT NOT NULL,
                joined_at TEXT NOT NULL,
                left_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT,
                event_type TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT,
                source_peer TEXT,
                target_peer TEXT,
                signal_type TEXT,
                payload TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def db_exec(query: str, params=()) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(query, params)


def db_insert_room(room_id: str, presenter_id: str) -> None:
    db_exec(
        "INSERT OR REPLACE INTO rooms (room_id, presenter_id, mute_all, created_at, closed_at) VALUES (?, ?, 1, ?, NULL)",
        (room_id, presenter_id, utc_now()),
    )


def db_close_room(room_id: str) -> None:
    db_exec("UPDATE rooms SET closed_at = ? WHERE room_id = ?", (utc_now(), room_id))


def db_set_mute_state(room_id: str, state: bool) -> None:
    db_exec("UPDATE rooms SET mute_all = ? WHERE room_id = ?", (1 if state else 0, room_id))


def db_participant_join(room_id: str, peer_id: str, role: str) -> None:
    db_exec(
        "INSERT INTO participants (room_id, peer_id, role, joined_at, left_at) VALUES (?, ?, ?, ?, NULL)",
        (room_id, peer_id, role, utc_now()),
    )


def db_participant_leave(room_id: str, peer_id: str) -> None:
    db_exec(
        "UPDATE participants SET left_at = ? WHERE room_id = ? AND peer_id = ? AND left_at IS NULL",
        (utc_now(), room_id, peer_id),
    )


def db_event(room_id: str | None, event_type: str, payload: dict | None = None) -> None:
    db_exec(
        "INSERT INTO events (room_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
        (room_id, event_type, json.dumps(payload or {}, ensure_ascii=False), utc_now()),
    )


def db_signal(room_id: str | None, source: str | None, target: str | None, signal_type: str, payload: dict) -> None:
    db_exec(
        "INSERT INTO signals (room_id, source_peer, target_peer, signal_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (room_id, source, target, signal_type, json.dumps(payload, ensure_ascii=False), utc_now()),
    )


def generate_room_id() -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    with state_lock:
        while True:
            candidate = "".join(random.choice(chars) for _ in range(4))
            if candidate not in rooms:
                return candidate


def send_json(ws, payload: dict) -> bool:
    try:
        ws.send(json.dumps(payload, ensure_ascii=False))
        return True
    except Exception:
        return False


def make_meta(ws):
    return {
        "socket": ws,
        "role": None,
        "room_id": None,
        "peer_id": None,
    }


def get_room_snapshot(room_id: str):
    room = rooms.get(room_id)
    if not room:
        return None
    return {
        "room_id": room_id,
        "viewer_count": len(room["viewers"]),
        "mute_all": room["mute_all"],
    }


def cleanup_connection(meta: dict):
    room_id = meta.get("room_id")
    role = meta.get("role")
    peer_id = meta.get("peer_id")
    if not room_id or room_id not in rooms:
        return

    room = rooms[room_id]

    if role == "viewer" and peer_id in room["viewers"]:
        room["viewers"].pop(peer_id, None)
        db_participant_leave(room_id, peer_id)
        db_event(room_id, "viewer_left", {"viewer_id": peer_id, "viewer_count": len(room["viewers"])})
        send_json(room["presenter_ws"], {"type": "viewer_left", "viewerId": peer_id, "viewerCount": len(room["viewers"])})

    if role == "presenter":
        db_participant_leave(room_id, room.get("presenter_id", "presenter"))
        db_event(room_id, "host_left", {})
        for viewer_ws in list(room["viewers"].values()):
            send_json(viewer_ws, {"type": "host_left"})
        db_close_room(room_id)
        rooms.pop(room_id, None)
        return

    if role == "viewer" and not room["viewers"] and room.get("presenter_ws") is None:
        db_close_room(room_id)
        rooms.pop(room_id, None)


@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/health")
def health():
    with state_lock:
        snapshot = [get_room_snapshot(room_id) for room_id in rooms]
    return jsonify({"status": "ok", "rooms": [s for s in snapshot if s is not None], "timestamp": utc_now()})


@app.route("/qr/<room_id>.png")
def qr_png(room_id: str):
    room_id = room_id.upper()
    join_url = f"http://{get_lan_ip()}:{DEFAULT_PORT}/?room={room_id}"
    img = qrcode.make(join_url)
    buff = BytesIO()
    img.save(buff, format="PNG")
    return Response(buff.getvalue(), mimetype="image/png")


@sock.route("/ws")
def ws_handler(ws):
    meta = make_meta(ws)
    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                send_json(ws, {"type": "error", "message": "Invalid JSON payload"})
                continue

            msg_type = data.get("type")

            if msg_type == "presenter_create":
                presenter_id = data.get("presenterId") or "presenter"
                room_id = generate_room_id()
                with state_lock:
                    rooms[room_id] = {
                        "presenter_ws": ws,
                        "presenter_id": presenter_id,
                        "viewers": {},
                        "mute_all": True,
                    }
                meta.update({"role": "presenter", "room_id": room_id, "peer_id": presenter_id})
                db_insert_room(room_id, presenter_id)
                db_participant_join(room_id, presenter_id, "presenter")
                db_event(room_id, "room_created", {"presenter_id": presenter_id})
                send_json(ws, {"type": "room_created", "roomId": room_id, "muteAll": True})
                continue

            if msg_type == "viewer_join":
                room_id = (data.get("roomId") or "").upper()
                viewer_id = data.get("viewerId")
                if not room_id or not viewer_id:
                    send_json(ws, {"type": "error", "message": "roomId and viewerId are required"})
                    continue

                with state_lock:
                    room = rooms.get(room_id)
                    if not room:
                        send_json(ws, {"type": "join_failed", "message": "Room not found"})
                        continue
                    room["viewers"][viewer_id] = ws
                    viewer_count = len(room["viewers"])
                    mute_all = room["mute_all"]
                    presenter_ws = room["presenter_ws"]

                meta.update({"role": "viewer", "room_id": room_id, "peer_id": viewer_id})
                db_participant_join(room_id, viewer_id, "viewer")
                db_event(room_id, "viewer_joined", {"viewer_id": viewer_id, "viewer_count": viewer_count})
                send_json(ws, {"type": "join_ok", "roomId": room_id, "muteAll": mute_all, "viewerId": viewer_id})
                send_json(
                    presenter_ws,
                    {"type": "viewer_joined", "viewerId": viewer_id, "viewerCount": viewer_count},
                )
                continue

            room_id = (data.get("roomId") or meta.get("room_id") or "").upper()
            if not room_id:
                send_json(ws, {"type": "error", "message": "roomId is required"})
                continue

            room = rooms.get(room_id)
            if not room:
                send_json(ws, {"type": "error", "message": "Room is not active"})
                continue

            if msg_type == "signal":
                target = data.get("to")
                source = data.get("from") or meta.get("peer_id")
                payload = data.get("payload") or {}
                signal_kind = payload.get("kind", "signal")
                db_signal(room_id, source, target, signal_kind, payload)

                if target == "presenter":
                    send_json(room["presenter_ws"], {"type": "signal", "roomId": room_id, "from": source, "payload": payload})
                else:
                    target_ws = room["viewers"].get(target)
                    if not target_ws:
                        send_json(ws, {"type": "error", "message": "Target viewer is offline"})
                        continue
                    send_json(target_ws, {"type": "signal", "roomId": room_id, "from": source, "payload": payload})
                continue

            if msg_type == "mute_all":
                if meta.get("role") != "presenter":
                    send_json(ws, {"type": "error", "message": "Only presenter can set mute state"})
                    continue
                new_state = bool(data.get("state", True))
                room["mute_all"] = new_state
                db_set_mute_state(room_id, new_state)
                db_event(room_id, "mute_all", {"state": new_state})
                for viewer_ws in list(room["viewers"].values()):
                    send_json(viewer_ws, {"type": "mute_all_state", "state": new_state})
                continue

            if msg_type == "share_state":
                if meta.get("role") != "presenter":
                    continue
                active = bool(data.get("active", False))
                db_event(room_id, "share_state", {"active": active})
                for viewer_ws in list(room["viewers"].values()):
                    send_json(viewer_ws, {"type": "share_state", "active": active})
                continue

            if msg_type == "heartbeat":
                send_json(ws, {"type": "heartbeat_ack", "timestamp": utc_now()})
                continue

            send_json(ws, {"type": "error", "message": f"Unknown message type: {msg_type}"})

    finally:
        with state_lock:
            cleanup_connection(meta)


def get_lan_ip() -> str:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as s:
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


DEFAULT_PORT = int(os.environ.get("SYNC_CAST_PORT", "5000"))

if __name__ == "__main__":
    init_db()
    lan_ip = get_lan_ip()
    print("=" * 60)
    print("SyncCast Local Server")
    print(f"Local URL : http://127.0.0.1:{DEFAULT_PORT}")
    print(f"LAN URL   : http://{lan_ip}:{DEFAULT_PORT}")
    print(f"Database  : {DB_PATH}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=DEFAULT_PORT, debug=False)
