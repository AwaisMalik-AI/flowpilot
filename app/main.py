"""FlowPilot — FastAPI entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, executions, simulate, webhooks, workflows
from app.api.routes.templates import router as templates_router
from app.core.config import settings
from app.core.database import Base, engine

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.DEBUG:
        Base.metadata.create_all(bind=engine)
        logger.warning("DEBUG=True: created database tables (use Alembic in production)")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Event-driven workflow automation engine (API-first).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = settings.API_PREFIX
app.include_router(auth.router, prefix=api)
app.include_router(workflows.router, prefix=api)
app.include_router(executions.router, prefix=api)
app.include_router(templates_router, prefix=api)
app.include_router(webhooks.router, prefix=api)
app.include_router(simulate.router, prefix=api)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.APP_NAME}
