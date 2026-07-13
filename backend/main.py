from fastapi import FastAPI

from api.platform.router import router as platform_router
from api.webhooks.whatsapp import router as whatsapp_webhook_router

app = FastAPI(title="Agente WhatsApp Tekus")
app.include_router(platform_router)
app.include_router(whatsapp_webhook_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
