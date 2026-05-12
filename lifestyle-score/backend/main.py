import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import score

app = FastAPI(title="생활권 스코어 API", version="0.1.0")

_origins_env = os.getenv("ALLOWED_ORIGINS", "")
_extra = [o.strip() for o in _origins_env.split(",") if o.strip()]
ALLOWED_ORIGINS = ["http://localhost:3000", "http://localhost:3001"] + _extra

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(score.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "lifestyle-score"}
