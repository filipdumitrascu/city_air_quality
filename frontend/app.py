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

# Backend API URL (Client Message Handler)
API_URL = os.getenv("API_URL", "http://client-message-handler:8000")


# Endpoints
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve main dashboard"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "api_url": API_URL
        }
    )

@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "service": "frontend"}
