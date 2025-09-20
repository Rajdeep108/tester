from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from contextlib import asynccontextmanager
import threading

from utils import login
from agents import monitoring_agent
from agents.monitoring_agent import init_db, background_monitor, mcp
from DocumentUpload import document_uploader
from agents import ai_assistant
from agents.ai_assistant import router as ai_assistant_router
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(background_monitor())
    threading.Thread(target=lambda: mcp.run("stdio"), daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(ai_assistant_router, prefix="/api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8081", "http://localhost:8080", "http://localhost:8080/workflows", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(login.router)
app.include_router(monitoring_agent.router)
app.include_router(document_uploader.router)
app.include_router(ai_assistant.router)
