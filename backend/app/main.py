import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.database import check_database_connection
from app.routers import (
    admin,
    applications,
    auth,
    contracts,
    jobs,
    ledger,
    payouts,
    profiles,
    receipts,
)

app = FastAPI(title="AlgoStrat API")

# The SPA is served from a different origin, so CORS must be explicit
# (ADR-013): a comma-separated allowlist via CORS_ORIGINS, defaulting
# to the Vite dev server. Never "*" — browsers would allow any site to
# call the API with a user's bearer token from JS.
_allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(contracts.router)
app.include_router(ledger.router)
app.include_router(profiles.router)
app.include_router(admin.router)
app.include_router(payouts.router)
app.include_router(receipts.router)


@app.get("/")
def home():
    return {
        "message": "Welcome to AlgoStrat!",
        "status": "running",
    }


@app.get("/health/database")
def database_health():
    try:
        result = check_database_connection()

        return {
            "database": "connected",
            "test_query": result,
        }
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed.",
        )
