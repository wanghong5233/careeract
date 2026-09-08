from fastapi import FastAPI

from services.browser.app.settings import settings

app = FastAPI(title="CareerAct Browser Service")
app.state.settings = settings


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
