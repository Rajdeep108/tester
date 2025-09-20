import asyncio
import os
import httpx
import sqlite3
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from bs4 import BeautifulSoup
import json
from pathlib import Path
import tempfile
import shutil
import zipfile
from typing import List, Optional
from docx import Document
import aiofiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Import MCP client
from fastmcp import Client
from fastmcp.client.transports import SSETransport

# MCP Server URL
MCP_SERVER_URL = "http://127.0.0.1:8002/sse"

# Global MCP client instance
mcp_client = None

async def get_mcp_client():
    """Get or create MCP client"""
    global mcp_client
    if mcp_client is None:
        transport = SSETransport(MCP_SERVER_URL)
        mcp_client = Client(transport)
        await mcp_client.__aenter__()
    return mcp_client

# ... [KEEP ALL YOUR EXISTING CODE: ConnectionManager, router, config, database functions, etc.] ...

# ---------------------------
# MCP Tool Wrapper Functions
# ---------------------------

async def fetch_url_via_mcp(url: str) -> str:
    """Call MCP server to fetch URL"""
    client = await get_mcp_client()
    result = await client.call_tool("fetch_url", {"url": url})
    return result.data

async def parse_version_via_mcp(html: str) -> str:
    """Call MCP server to parse version"""
    client = await get_mcp_client()
    result = await client.call_tool("parse_version", {"html": html})
    return result.data

async def compare_versions_via_mcp(old: str, new: str) -> str:
    """Call MCP server to compare versions"""
    client = await get_mcp_client()
    result = await client.call_tool("compare_versions", {"old": old, "new": new})
    return result.data

async def should_crawl_reasoning_via_mcp(last_checked: str, last_file: str, frequency: int, current_time: str) -> bool:
    """Call MCP server for crawl decision"""
    client = await get_mcp_client()
    result = await client.call_tool("should_crawl_reasoning_llm", {
        "last_checked": last_checked,
        "last_file": last_file,
        "frequency": frequency,
        "current_time": current_time
    })
    return result.data

async def send_notification_via_mcp(to_email: str, subject: str, content: str, attachment_path: str = None) -> int:
    """Call MCP server to send notification"""
    client = await get_mcp_client()
    
    if attachment_path:
        result = await client.call_tool("send_notification", {
            "to_email": to_email,
            "subject": subject,
            "content": content,
            "attachment_path": attachment_path
        })
    else:
        result = await client.call_tool("send_notification", {
            "to_email": to_email,
            "subject": subject,
            "content": content
        })
    
    return result.data

# ---------------------------
# Updated Agent Logic (using MCP tools)
# ---------------------------

async def monitor_site():
    url = read_crawler_config()["crawler_url"]
    
    # Use MCP tool instead of local function
    html = await fetch_url_via_mcp(url)
    await asyncio.sleep(2)
    
    # Use MCP tool for parsing
    latest_file = os.path.basename(await parse_version_via_mcp(html))
    
    if not latest_file:
        print(f"❌ No .zip files found at {url}")
        print_and_store(f"❌ No .zip files found at {url}")
        return

    last_seen = get_latest_file()
    last_filename = os.path.basename(last_seen["filename"]) if last_seen else None
    
    # Use MCP tool for comparison
    decision = await compare_versions_via_mcp(last_filename or "", latest_file)

    if not url.endswith('/'):
        url += '/'
    file_url = url + latest_file
    add_file(latest_file, url, decision)
    await broadcast_status()

    if decision == "new version":
        print(f"🚀 New file detected: {latest_file}")
        print_and_store(f"🚀 New file detected: {latest_file}")
        await asyncio.sleep(15)

        # ... [YOUR EXISTING CODE FOR DOWNLOADING AND PROCESSING] ...

        # Use MCP tool for sending notification
        subject = f"New 3GPP File Available: {latest_file}"
        content = (
            f"<p>Dear Team,</p>"
            f"<p>We are pleased to inform you that a new version of the 3GPP standard <b>{latest_file}</b> has been uploaded to the official 3GPP website.</p>"
            f"<p>Please find a brief summary of the document attached in this email, to help you quickly identify what is new.</p>"
            f"<p>Best regards,<br>Standards Monitoring Automation</p>"
        )

        print_and_store("Sending Email Notification with summary attached...")
        for email in RECIPIENT_EMAILS:
            status = await send_notification_via_mcp(
                email, subject, content, attachment_path=summary_docx_path
            )
            if status == 200:
                print_and_store(f"Email sent successfully to {email}")
            else:
                print_and_store(f"Failed to send email to {email}, status: {status}")
        
        print_and_store("Email Notification sent with summary attached!")

# ---------------------------
# Updated Background Task
# ---------------------------

async def background_monitor():
    global last_active
    
    while True:
        cfg = read_crawler_config()
        freq = cfg["crawler_frequency"]
        
        if cfg["crawler_active"]:
            last = get_latest_file()
            last_checked = last['last_checked'] if last and last['last_checked'] else "never"
            last_file = last['filename'] if last else "none"
            
            # Use MCP tool for decision making
            now = datetime.now().isoformat()
            should_crawl = await should_crawl_reasoning_via_mcp(
                last_checked=last_checked,
                last_file=last_file,
                frequency=freq,
                current_time=now
            )
            
            if should_crawl:
                try:
                    await monitor_site()
                except Exception as e:
                    print(f"❌ Error during monitoring: {e}")
                    print_and_store(f"Monitoring error: {e}")
            else:
                print("Agentic Reasoning: Decided not to crawl this cycle.")
                print_and_store("Agentic Reasoning: Decided not to crawl this cycle.")
        
        # ... [REST OF YOUR EXISTING CODE] ...

# ---------------------------
# Cleanup function
# ---------------------------

async def cleanup_mcp_client():
    """Clean up MCP client when router is being shut down"""
    global mcp_client
    if mcp_client:
        await mcp_client.__aexit__(None, None, None)
        mcp_client = None

# Your existing router and endpoints remain unchanged
router = APIRouter()
# ... [YOUR EXISTING ROUTER ENDPOINTS] ...