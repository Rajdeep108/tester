import asyncio
import os
import sqlite3
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pathlib import Path
import json

from pydantic import BaseModel
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from .tools.notifier_tool import send_notification
from llm.llm_endpoints import chat_completion

# ---------------------------
# WebSocket Manager
# ---------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections.copy():
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()
router = APIRouter()

# ---------------------------
# DB and Config
# ---------------------------

DB_PATH = r"C:\Users\342534\Desktop\backend\backend\telecom_ai.db"
CONFIG_PATH = Path(r"C:\Users\342534\Desktop\backend\backend\agents\config\crawler_config.json")

RECIPIENT_EMAILS = [
    "342534@nttdata.com",
    "harshitanagaraj.guled@nttdata.com",
    "neelambuz.singh@nttdata.com"
]

LATEST_STATUS = ""
def update_latest_status(msg: str):
    global LATEST_STATUS
    LATEST_STATUS = msg

def print_and_store(msg: str):
    update_latest_status(msg)
    try:
        asyncio.create_task(manager.broadcast({"type": "log", "data": msg}))
    except Exception:
        pass

def read_crawler_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
            data.setdefault("crawler_active", False)
            data.setdefault("crawler_frequency", 10)
            return data
    else:
        return {"crawler_active": False, "crawler_frequency": 10}

def write_crawler_config(active: bool = None, frequency: int = None):
    cfg = read_crawler_config()
    orig_active = cfg.get("crawler_active", False)
    if active is not None:
        cfg["crawler_active"] = active
    if frequency is not None:
        cfg["crawler_frequency"] = frequency
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f)

crawler_wakeup_event = asyncio.Event()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS files (
               id INTEGER PRIMARY KEY,
               filename TEXT UNIQUE,
               url TEXT,
               status TEXT,
               last_checked TEXT
           )"""
    )
    conn.commit()
    conn.close()

def add_file(filename: str, url: str, status: str):
    current_time = datetime.now().isoformat() 
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT INTO files (filename, url, status, last_checked)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(filename) DO UPDATE SET
               status=excluded.status,
               last_checked=excluded.last_checked""",
        (filename, url, status,current_time)
    )
    conn.commit()
    conn.close()

def get_latest_file():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT filename, url, last_checked FROM files ORDER BY last_checked DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return {"filename": row[0], "url": row[1], "last_checked": row[2]} if row else None

# ---------------------------
# MCP Client (Connect to mcp_server.py)
# ---------------------------

MCP_SERVER_URL = "http://127.0.0.1:8001/mcp/"
mcp_client = Client(StreamableHttpTransport(MCP_SERVER_URL))

async def fetch_url_mcp(url: str) -> str:
    async with mcp_client:
        return await mcp_client.call_tool("fetch_url", {"url": url})

async def parse_version_mcp(html: str):
    async with mcp_client:
        return await mcp_client.call_tool("parse_version", {"html": html})

async def compare_versions_mcp(old: str, new: str):
    async with mcp_client:
        return await mcp_client.call_tool("compare_versions", {"old": old, "new": new})

# ---------------------------
# Agent Logic
# ---------------------------

async def monitor_site(BASE_URL):
    html = await fetch_url_mcp(BASE_URL)
    latest_file = await parse_version_mcp(html)
    if not latest_file:
        print_and_store(f"❌ No .zip files found at {BASE_URL}")
        return

    last_seen = get_latest_file()
    last_filename = last_seen["filename"] if last_seen else None
    decision = await compare_versions_mcp(last_filename or "", latest_file)
    file_url = BASE_URL + latest_file
    add_file(latest_file, file_url, decision)
    if decision == "new version":
        print_and_store(f"🚀 New file detected: {latest_file}")
        # Send notifications
        subject = f"New 3GPP File Available: {latest_file}"
        content = f"<p>New file <b>{latest_file}</b> at {file_url}</p>"
        for email in RECIPIENT_EMAILS:
            send_notification(email, subject, content)

# Background monitor task
async def background_monitor(BASE_URL):
    while True:
        cfg = read_crawler_config()
        if cfg["crawler_active"]:
            await monitor_site(BASE_URL)
        await asyncio.sleep(cfg["crawler_frequency"])

# ---------------------------
# FastAPI Endpoints (Optional)
# ---------------------------

@router.get("/monitor/status")
def get_status():
    last = get_latest_file()
    cfg = read_crawler_config()
    return {
        "filename": last["filename"] if last else None,
        "url": last["url"] if last else None,
        "last_checked": last["last_checked"] if last else None,
        "frequency": cfg["crawler_frequency"]
    }

@router.websocket("/ws/monitor")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
