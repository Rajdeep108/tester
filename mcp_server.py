import asyncio
import os
from fastmcp import FastMCP, Context
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from langsmith.run_helpers import traceable

os.environ["LANGCHAIN_TRACING_V2"] = "true"

# Initialize MCP server
mcp = FastMCP("Monitoring Tools MCP Server", api_route="/mcp/", debug=True)

# ---------------------------
# MCP Tools
# ---------------------------

@traceable
@mcp.tool()
async def fetch_url(url: str, ctx: Context) -> str:
    """Fetch the content of a URL asynchronously"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text

@traceable
@mcp.tool()
def parse_version(html: str, ctx: Context):
    """Parse the latest .zip file in the HTML page"""
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
        except Exception:
            continue
        files.append((filename, date_obj))
    if not files:
        return None
    files.sort(key=lambda x: x[1], reverse=True)
    return files[0][0]

@traceable
@mcp.tool()
def compare_versions(old: str, new: str, ctx: Context):
    return "new version" if old != new else "same version"

# ---------------------------
# Run MCP Server standalone
# ---------------------------
if __name__ == "__main__":
    # You can run this with Uvicorn
    # uv run mcp_server.py --port 8001
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8001)
