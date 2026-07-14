import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.platform.rag_qa import router as platform_rag_qa_router
from api.platform.router import router as platform_router
from api.webhooks.whatsapp import router as whatsapp_webhook_router
from knowledge_mining.odoo_ticket_sync import sync_open_tickets_incremental

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _run_odoo_ticket_sync() -> None:
    try:
        summary = sync_open_tickets_incremental()
        logger.info("Sincronización de minería de tickets Odoo completada: %s", summary)
    except Exception:
        logger.exception("Falló la sincronización de minería de tickets Odoo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        _run_odoo_ticket_sync,
        "cron",
        hour=3,
        minute=0,
        id="odoo_ticket_mining_sync",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Agente WhatsApp Tekus", lifespan=lifespan)

# La plataforma web (Angular) y el backend corren en orígenes distintos incluso
# en desarrollo local (localhost:4200 vs localhost:8000) — sin esto, el
# navegador bloquea la llamada por CORS antes de que llegue al SSO/RAG.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:4200")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(platform_router)
app.include_router(platform_rag_qa_router)
app.include_router(whatsapp_webhook_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
