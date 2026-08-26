import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.documents.db import init_db
from src.documents.router import router as documents_router
from src.intake.router import router as intake_router
from src.intake.service import process_inbox

logger = logging.getLogger(__name__)


async def poll_inbox_forever(client, interval: float) -> None:
    while True:
        try:
            await asyncio.to_thread(process_inbox, client)
        except Exception:
            logger.exception("gmail poll failed; retrying next interval")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    poller = None
    if settings.enable_gmail_poller:
        from scripts.google_auth import get_credentials
        from src.intake.gmail_client import GmailClient

        client = GmailClient(get_credentials())
        poller = asyncio.create_task(
            poll_inbox_forever(client, settings.gmail_poll_seconds)
        )
    yield
    if poller:
        poller.cancel()


app = FastAPI(title="Contract Review Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(intake_router)
app.include_router(documents_router)
