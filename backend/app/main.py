from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.listings import router as listings_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Apartment Hunting AI Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(listings_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
