"""
OpenBMC AI-BDD Portal — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pathlib import Path

from backend.api.routes import qemu, robot
from backend.core.config import settings

app = FastAPI(
    title="OpenBMC AI-BDD Portal",
    description="Web portal for scheduling QEMU & OpenBMC Robot Framework tests",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(qemu.router)
app.include_router(robot.router)

# ── Static files & templates ──────────────────────────────────────────────────
# Path(__file__).parent  →  backend/
# .parent                →  project root (openbmc-ai-bdd-portal/)
BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "frontend" / "templates"))
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "frontend" / "static")),
    name="static",
)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse(url="/static/assets/favicon.png")


@app.get("/health")
def health():
    return {"status": "ok", "service": "OpenBMC AI-BDD Portal"}
