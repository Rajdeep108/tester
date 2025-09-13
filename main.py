from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from contextlib import asynccontextmanager
from agents import monitoring_agent

BASE_URL = "https://www.3gpp.org/ftp/specs/archive/23_series/23.002"

@asynccontextmanager
async def lifespan(app: FastAPI):
    monitoring_agent.init_db()
    asyncio.create_task(monitoring_agent.background_monitor(BASE_URL))
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include monitoring agent routes
app.include_router(monitoring_agent.router)
