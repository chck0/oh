from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import score

app = FastAPI(title="생활권 스코어 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(score.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "lifestyle-score"}
