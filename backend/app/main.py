import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.api.auth import router as auth_router
from app.api.wallets import router as wallets_router
from app.api.transactions import router as transactions_router
from app.api.budgets import router as budgets_router
from app.api.bot_pairing import router as bot_router
from app.api.webhooks import router as webhooks_router
from app.api.planner import router as planner_router
from app.api.cfp import router as cfp_legacy_router
from app.api.fire import router as fire_router
from app.api.admin import router as admin_router
from app.api.investment_research import router as investment_research_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ai_finance")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Initializing AI-Finance Backend & Database Auto-Schema...")
    init_db()
    logger.info("Database and seeds ready.")
    yield
    logger.info("Shutting down AI-Finance Backend.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API & Multimodal AI Engine for AI-Finance Platform",
    lifespan=lifespan,
)

# CORS Middleware
origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_origin_regex=r"^https?://.*$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers under /api/v1 prefix
app.include_router(auth_router, prefix="/api/v1")
app.include_router(wallets_router, prefix="/api/v1")
app.include_router(transactions_router, prefix="/api/v1")
app.include_router(budgets_router, prefix="/api/v1")
app.include_router(bot_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(planner_router, prefix="/api/v1")
app.include_router(cfp_legacy_router, prefix="/api/v1")
app.include_router(fire_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(investment_research_router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}

