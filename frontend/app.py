from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import os

app = FastAPI(
    title="CityAirQ Frontend",
    description="Air Quality Monitoring and Routing Dashboard",
    version="1.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Backend API URL
# For browser access, use external URL or relative path
# Internal URL is only for server-to-server communication
API_URL_INTERNAL = os.getenv("API_URL", "http://client-message-handler:8000")
API_URL_EXTERNAL = os.getenv("API_URL_EXTERNAL", "")  # Will be set for cloud deployment


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve main dashboard"""
    # If external URL is set, use it; otherwise frontend will use relative proxy
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "api_url": API_URL_EXTERNAL if API_URL_EXTERNAL else ""
        }
    )


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "frontend"}


# Proxy endpoints - forward requests to backend API
import httpx

@app.post("/api/route/")
async def proxy_route(request: Request):
    """Proxy route requests to backend"""
    body = await request.json()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{API_URL_INTERNAL}/route/", json=body)
        return response.json()


@app.post("/api/results/")
async def proxy_results(request: Request):
    """Proxy results requests to backend"""
    body = await request.json()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{API_URL_INTERNAL}/results/", json=body)
        return response.json()


@app.post("/api/ingest/")
async def proxy_ingest(request: Request):
    """Proxy ingest requests to backend"""
    body = await request.json()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{API_URL_INTERNAL}/ingest/", json=body)
        return response.json()
