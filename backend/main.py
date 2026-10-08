from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.repositories import router as repositories_router
from app.api.analysis import router as analysis_router
from app.api.execution import router as execution_router
from app.api.failures import router as failures_router
from app.api.patches import router as patches_router
from app.api.workflow import router as workflow_router
from app.api.rollback import router as rollback_router
from app.api.auth import router as auth_router
from app.auth.store import init_auth_store


app = FastAPI(title="DevPilot API", version="0.1.0")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


init_auth_store()


app.include_router(
    health_router,
    prefix="/api",
)

app.include_router(
    repositories_router,
    prefix="/api",
)

app.include_router(
    analysis_router,
    prefix="/api",
)

app.include_router(
    execution_router,
    prefix="/api",
)

app.include_router(
    failures_router,
    prefix="/api",
)

app.include_router(
    patches_router,
    prefix="/api",
)

app.include_router(
    workflow_router,
    prefix="/api",
)

app.include_router(
    rollback_router,
    prefix="/api",
)

app.include_router(
    auth_router,
    prefix="/api",
)
