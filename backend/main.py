from fastapi import FastAPI

from api.webhooks.whatsapp import router as whatsapp_webhook_router

app = FastAPI(title="Agente WhatsApp Tekus")
app.include_router(whatsapp_webhook_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
