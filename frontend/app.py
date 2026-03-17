from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import httpx
import os

app = FastAPI(
    title="CityAirQ Frontend",
    description="Air Quality Monitoring and Routing Dashboard",
    version="2.0.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Backend service URLs
CLIENT_HANDLER_URL = os.getenv("CLIENT_HANDLER_URL", "http://client-message-handler:8000")
ROUTING_SERVICE_URL = os.getenv("ROUTING_SERVICE_URL", "http://routing-service:8000")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "frontend"}

@app.post("/api/route/")
async def proxy_route(request: Request):
    """Proxy to Routing Service"""
    body = await request.json()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{ROUTING_SERVICE_URL}/route", json=body)
            if response.status_code != 200:
                return {"detail": response.json().get("detail", "Route calculation failed")}
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Routing service timeout")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/api/results/")
async def proxy_results(request: Request):
    """Proxy to Client Message Handler"""
    body = await request.json()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{CLIENT_HANDLER_URL}/results/", json=body)
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/api/ingest/")
async def proxy_ingest(request: Request):
    """Proxy to Client Message Handler"""
    body = await request.json()
    auth = request.headers.get("Authorization")
    headers = {"Authorization": auth} if auth else {}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{CLIENT_HANDLER_URL}/ingest/", json=body, headers=headers)
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Service timeout")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
