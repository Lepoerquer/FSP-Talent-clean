from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from backend.app.api.v1.api import api_router
    from backend.app.core.config import settings
    from backend.app.core.database import SessionLocal, create_all_tables
    from backend.app.modules.dictionaries.service import seed_dictionaries
except ImportError:
    from app.api.v1.api import api_router
    from app.core.config import settings
    from app.core.database import SessionLocal, create_all_tables
    from app.modules.dictionaries.service import seed_dictionaries


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist
    create_all_tables()
    
    # Auto-seed dictionaries if empty
    db = SessionLocal()
    try:
        seed_dictionaries(db)
    finally:
        db.close()
    
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="FSP-Talent Platform Backend Core API with 152-FZ compliance, CAT IRT testing, and reverse recruitment mechanics",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
    }


@app.get("/", tags=["Health"])
def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "docs": "/docs",
        "health": "/health",
    }
