import asyncio
import os
import httpx
import sqlite3
from datetime import datetime
from fastmcp import FastMCP, Context
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from llm.llm_endpoints import chat_completion
from langsmith.run_helpers import traceable
import json
from pathlib import Path
import base64
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition

# Load environment variables
load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "Standards-Monitoring-Agent"
os.environ["LANGCHAIN_API_KEY"] = "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"

# Initialize MCP server
mcp = FastMCP("WebsiteMonitor")

# Configuration
DB_PATH = r"C:\Users\342534\Desktop\Telecom Standards Management\backend\telecom_ai.db"

# ---------------------------
# MCP Tools (all tools including notifier)
# ---------------------------

@traceable
@mcp.tool()
async def fetch_url(url: str, ctx: Context) -> str:
    """Fetch HTML content from a URL"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }
    async with httpx.AsyncClient(headers=headers) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text

@traceable
@mcp.tool()
def parse_version(html: str, ctx: Context) -> str:
    """Parse the latest .zip file in the folder page by uploaded date"""
    soup = BeautifulSoup(html, "html.parser")
    files = []
    
    for row in soup.select("tbody tr"):
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
            
        a_tag = cols[2].find("a", href=True)
        if not a_tag or not a_tag["href"].endswith(".zip"):
            continue
            
        filename = os.path.basename(a_tag["href"])
        date_str = cols[3].get_text(strip=True)
        
        try:
            date_obj = datetime.strptime(date_str, "%Y/%m/%d %H:%M")
            files.append((filename, date_obj))
        except Exception:
            continue
    
    if not files:
        return None
        
    files.sort(key=lambda x: x[1], reverse=True)
    return files[0][0]

@traceable
@mcp.tool()
def compare_versions(old: str, new: str, ctx: Context) -> str:
    """Compare two version strings"""
    if old != new:
        return "new version"
    return "same version"

@traceable
@mcp.tool()
def should_crawl_reasoning_llm(last_checked: str, last_file: str, frequency: int, current_time: str, ctx: Context) -> bool:
    """LLM-powered decision making for crawling"""
    prompt = (
        f"You are an autonomous standards monitoring agent for 3GPP. "
        f"Your goal is to efficiently detect updates to the website: "
        f"- Last checked: {last_checked}\n"
        f"Current time: {current_time}\n"
        f"- Last file seen: {last_file}\n"
        f"- Check frequency (seconds): {frequency}\n"
        "You must decide whether to crawl the website NOW. "
        "Crawling too often may waste resources, but missing updates is worse. "
        "Consider the following:\n"
        "- If it has been a long time since last check, crawling is more urgent.\n"
        "- If the last file has not changed for several checks, occasional crawling is still needed to catch updates.\n"
        "- If frequency is low but there is an important pattern (e.g., frequent updates), crawling may be justified.\n"
        "Your decision should balance efficiency and vigilance. "
        "Reply ONLY with 'yes' or 'no' and a short reason. Never be stuck rejecting every crawl."
    )
    
    resp = chat_completion(
        user_prompt=prompt,
        system_instruction=(
            "Decide if the agent should crawl now. "
            "Always reply with 'yes' or 'no' and a brief reason. "
            "STRICTLY check If time since last check(in seconds) >= frequency (in seconds), you must definitely reply 'yes'."
            "Do NOT reject crawling indefinitely; at least crawl occasionally. "
        )
    )
    
    return resp.strip().lower().startswith('yes')

@traceable
@mcp.tool()
def send_notification(to_email: str, subject: str, content: str, attachment_path: str = None, ctx: Context = None) -> int:
    """Send email notification with optional attachment"""
    from_email = 'telecomproject4@gmail.com' 
    sendgrid_api_key = os.environ.get('SENDGRID_API_KEY') 

    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        html_content=content
    )

    if attachment_path:
        # Read and encode the file
        with open(attachment_path, 'rb') as f:
            data = f.read()
        encoded_file = base64.b64encode(data).decode()

        # Prepare the attachment
        filename = os.path.basename(attachment_path)
        attachment = Attachment(
            FileContent(encoded_file),
            FileName(filename),
            FileType('application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
            Disposition('attachment')
        )
        message.attachment = attachment

    try:
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        return response.status_code
    except Exception as e:
        print(f"Error sending email: {e}")
        return None

if __name__ == "__main__":
    print("🚀 Starting MCP Server at http://127.0.0.1:8002/")
    mcp.run(transport="sse", host="127.0.0.1", port=8002)