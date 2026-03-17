import os
import requests
from fastapi import HTTPException, Header
from typing import Optional

GOOGLE_TOKEN_INFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"

SENSOR_API_KEYS = set(
    key.strip() for key in os.getenv("SENSOR_API_KEYS", "").split(",") if key.strip()
)

def verify_google_token(token: str) -> dict:
    """
    Validate a Google OAuth 2.0 Access Token.
    
    Returns:
        dict: User info containing email, sub (user ID), etc.
    
    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    try:
        response = requests.get(
            GOOGLE_TOKEN_INFO_URL, 
            params={"access_token": token},
            timeout=5
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=503, 
            detail=f"Authentication service unavailable: {str(e)}"
        )
    
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_info = response.json()

    if "email" not in user_info:
        raise HTTPException(status_code=401, detail="Invalid token: email not found")

    return user_info

async def authorize(authorization: Optional[str] = Header(None, alias="Authorization")) -> dict:
    """
    FastAPI dependency for protecting endpoints.
    
    Supports two authentication methods:
    1. Google OAuth 2.0 tokens (for mobile app users in production)
    2. API Keys (for development, testing, and direct sensor access)

    API Keys are checked first - if no match, falls back to Google OAuth.
    
    Returns:
        dict: Authenticated entity info
    
    Raises:
        HTTPException: 401 if missing/invalid authorization
    """
    if not authorization:
        raise HTTPException(
            status_code=401, 
            detail="Missing Authorization header"
        )
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, 
            detail="Invalid Authorization header format. Expected: Bearer <token>"
        )
    
    token = authorization.replace("Bearer ", "").strip()
    
    if not token:
        raise HTTPException(
            status_code=401, 
            detail="Empty token provided"
        )
    
    # Check API key first (faster, no network call)
    if token in SENSOR_API_KEYS:
        return {
            "type": "api_key",
            "email": f"sensor-{token[:8]}@cityairq.local"
        }
    
    # Fallback to Google OAuth
    return verify_google_token(token)

async def optional_authorize(authorization: Optional[str] = Header(None, alias="Authorization")) -> Optional[dict]:
    """
    Optional authentication - returns None if no token provided.
    """
    if not authorization:
        return None
    
    try:
        return await authorize(authorization)
    except HTTPException:
        return None
