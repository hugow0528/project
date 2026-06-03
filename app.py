from __future__ import annotations

import os
import random
import socket
import string
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = int(os.environ.get("PORT", "8000"))
ROOM_TTL_SECONDS = 6 * 60 * 60  # 6 hours
ROOM_CODE_LENGTH = 6
MAX_ROOM_GENERATION_ATTEMPTS = 40

app = Flask(__name__)

rooms_lock = threading.Lock()
rooms: dict[str, dict] = {}


def get_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def now_ts() -> float:
    return time.time()


def generate_room_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(ROOM_CODE_LENGTH))


def cleanup_expired_rooms() -> None:
    cutoff = now_ts() - ROOM_TTL_SECONDS
    with rooms_lock:
        expired = [code for code, room in rooms.items() if room["updated_at"] < cutoff]
        for code in expired:
            del rooms[code]


def create_room_state() -> dict:
    ts = now_ts()
    return {
        "created_at": ts,
        "updated_at": ts,
        "offer": None,
        "answer": None,
        "presenter_candidates": [],
        "viewer_candidates": [],
    }


def get_room_or_404(room_code: str):
    room_code = room_code.upper().strip()
    with rooms_lock:
        room = rooms.get(room_code)
        if room:
            room["updated_at"] = now_ts()
    if not room:
        return None, (jsonify({"error": "Room not found."}), 404)
    return room, None


@app.get("/")
def home():
    return render_template("index.html")


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
        }
    )


@app.post("/api/share/rooms")
def create_room():
    cleanup_expired_rooms()
    with rooms_lock:
        code = None
        for _ in range(MAX_ROOM_GENERATION_ATTEMPTS):
            candidate = generate_room_code()
            if candidate not in rooms:
                code = candidate
                break
        if not code:
            return jsonify({"error": "Could not allocate room."}), 500
        rooms[code] = create_room_state()
    return jsonify({"room_code": code}), 201


@app.post("/api/share/<room_code>/reset")
def reset_room(room_code: str):
    room, err = get_room_or_404(room_code)
    if err:
        return err
    with rooms_lock:
        room["offer"] = None
        room["answer"] = None
        room["presenter_candidates"] = []
        room["viewer_candidates"] = []
        room["updated_at"] = now_ts()
    return jsonify({"ok": True})


@app.post("/api/share/<room_code>/offer")
def post_offer(room_code: str):
    room, err = get_room_or_404(room_code)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    sdp = payload.get("sdp")
    sdp_type = payload.get("type")
    if not sdp or sdp_type != "offer":
        return jsonify({"error": "Invalid offer payload."}), 400

    with rooms_lock:
        room["offer"] = {"type": "offer", "sdp": sdp}
        room["answer"] = None
        room["presenter_candidates"] = []
        room["viewer_candidates"] = []
        room["updated_at"] = now_ts()
    return jsonify({"ok": True})


@app.get("/api/share/<room_code>/offer")
def get_offer(room_code: str):
    room, err = get_room_or_404(room_code)
    if err:
        return err
    return jsonify({"offer": room["offer"]})


@app.post("/api/share/<room_code>/answer")
def post_answer(room_code: str):
    room, err = get_room_or_404(room_code)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    sdp = payload.get("sdp")
    sdp_type = payload.get("type")
    if not sdp or sdp_type != "answer":
        return jsonify({"error": "Invalid answer payload."}), 400

    with rooms_lock:
        room["answer"] = {"type": "answer", "sdp": sdp}
        room["updated_at"] = now_ts()
    return jsonify({"ok": True})


@app.get("/api/share/<room_code>/answer")
def get_answer(room_code: str):
    room, err = get_room_or_404(room_code)
    if err:
        return err
    return jsonify({"answer": room["answer"]})


@app.post("/api/share/<room_code>/candidate")
def post_candidate(room_code: str):
    room, err = get_room_or_404(room_code)
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    role = str(payload.get("role", "")).strip().lower()
    candidate = payload.get("candidate")
    if role not in {"presenter", "viewer"} or not isinstance(candidate, dict):
        return jsonify({"error": "Invalid candidate payload."}), 400

    with rooms_lock:
        if role == "presenter":
            room["presenter_candidates"].append(candidate)
        else:
            room["viewer_candidates"].append(candidate)
        room["updated_at"] = now_ts()
    return jsonify({"ok": True})


@app.get("/api/share/<room_code>/candidates")
def get_candidates(room_code: str):
    room, err = get_room_or_404(room_code)
    if err:
        return err

    receiver = str(request.args.get("for", "")).strip().lower()
    after = request.args.get("after", "0")
    if receiver not in {"presenter", "viewer"}:
        return jsonify({"error": "Query parameter 'for' must be presenter or viewer."}), 400
    try:
        idx = max(int(after), 0)
    except ValueError:
        return jsonify({"error": "Query parameter 'after' must be an integer."}), 400

    source = room["viewer_candidates"] if receiver == "presenter" else room["presenter_candidates"]
    sliced = source[idx:]
    return jsonify({"candidates": sliced, "next_index": len(source)})


if __name__ == "__main__":
    lan_ip = get_local_ip()
    print()
    print("Local ScreenShare server is starting...")
    print(f"Local URL: http://127.0.0.1:{DEFAULT_PORT}")
    print(f"LAN URL:   http://{lan_ip}:{DEFAULT_PORT}")
    print()
    app.run(host="0.0.0.0", port=DEFAULT_PORT)
