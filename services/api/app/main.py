from fastapi import FastAPI

from services.api.app.settings import settings

app = FastAPI(title="CareerAct API")
app.state.settings = settings


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
