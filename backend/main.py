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

import os
import httpx
import jwt
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

from database import engine, Base
from routers import workspaces, policies, rules, scenarios, evaluations, releases

CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")
_jwks_cache: dict = {}


async def get_clerk_jwks() -> dict:
    if _jwks_cache:
        return _jwks_cache
    if not CLERK_JWKS_URL:
        raise RuntimeError("CLERK_JWKS_URL env var not set")
    async with httpx.AsyncClient() as client:
        resp = await client.get(CLERK_JWKS_URL)
        resp.raise_for_status()
        _jwks_cache.update(resp.json())
    return _jwks_cache


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing authentication token")

        token = auth_header[7:]
        try:
            jwks = await get_clerk_jwks()
            jwt.decode(token, jwks, algorithms=["RS256"], options={"verify_aud": False})
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        return await call_next(request)


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

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://policylens-ai-sand.vercel.app",
    "https://policylens-fywkwxkvt-rajjrajender2112-9081s-projects.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ClerkAuthMiddleware)

app.include_router(workspaces.router)
app.include_router(policies.router)
app.include_router(rules.router)
app.include_router(scenarios.router)
app.include_router(evaluations.router)
app.include_router(releases.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "policylens-api", "version": "0.2.0"}
