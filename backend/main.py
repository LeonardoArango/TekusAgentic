from fastapi import FastAPI

from api.platform.router import router as platform_router

app = FastAPI(title="Agente WhatsApp Tekus")
app.include_router(platform_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
