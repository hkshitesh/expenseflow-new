"""FastAPI application entrypoint for ExpenseFlow."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create database tables on startup."""
    init_db()
    yield


app = FastAPI(title="ExpenseFlow", lifespan=lifespan)
app.include_router(router)
