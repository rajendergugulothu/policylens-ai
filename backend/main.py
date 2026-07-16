"""
PolicyLens AI — Backend API
Pre-production AI agent policy compliance testing.

Full endpoint list:
  Workspaces:    POST / GET / GET /{id}
  Policies:      POST upload/{pdf|text|notion} / GET workspace/{id} / GET /{id}
  Rules:         POST extract/{id} / GET policy/{id} / POST /{id}/{approve|edit|reject}
                 GET ambiguity/policy/{id} / POST ambiguity/{id}/resolve
  Scenarios:     POST generate/{id} / GET policy/{id} / POST policy/{id}/custom / DELETE policy/{id}
  Evaluations:   POST / POST /{id}/upload-batch / GET workspace/{id} / GET /{id}
                 GET /{id}/results / GET /{id}/findings
  Releases:      POST / POST /{id}/sign / GET /{id} / GET /{id}/findings / POST /compare
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import engine, Base
from routers import workspaces, policies, rules, scenarios, evaluations, releases


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="PolicyLens AI",
    description="Pre-production AI agent policy compliance testing.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspaces.router)
app.include_router(policies.router)
app.include_router(rules.router)
app.include_router(scenarios.router)
app.include_router(evaluations.router)
app.include_router(releases.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "policylens-api", "version": "0.2.0"}
