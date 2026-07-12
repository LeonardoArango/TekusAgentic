from fastapi import FastAPI

app = FastAPI(title="Agente WhatsApp Tekus")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
