from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import PROJECT_NAME
from app.routers import adjust, dashboard, dayseal, guns, piles, rates, sessions, settings, sites
from app.seed import seed_if_empty

seed_if_empty()

app = FastAPI(title=PROJECT_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(dashboard.router, prefix="/api")
app.include_router(sites.router, prefix="/api")
app.include_router(piles.router, prefix="/api")
app.include_router(guns.router, prefix="/api")
app.include_router(rates.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(dayseal.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(adjust.router, prefix="/api")


@app.get("/api/健康")
def health():
    return {"产品": PROJECT_NAME, "状态": "正常"}
