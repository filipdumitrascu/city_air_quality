import requests
from fastapi import HTTPException, Header, Depends
from typing import Optional

GOOGLE_TOKEN_INFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"


def verify_token(token: str) -> dict:
    """
    Validate a Google OAuth 2.0 Access Token.
    
    Args:
        token: The access token string (without 'Bearer ' prefix)
    
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
    FastAPI dependency for protecting endpoints with Google OAuth.
    
    Expects header: Authorization: Bearer <access_token>
    
    Args:
        authorization: The Authorization header value
    
    Returns:
        dict: Authenticated user info (email, sub, etc.)
    
    Raises:
        HTTPException: 401 if missing/invalid authorization
    
    Usage:
        @app.get("/protected")
        async def protected_route(user: dict = Depends(authorize)):
            return {"email": user["email"]}
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
    
    user_info = verify_token(token)
    
    return user_info


async def optional_authorize(authorization: Optional[str] = Header(None, alias="Authorization")) -> Optional[dict]:
    """
    Optional authentication - returns None if no token provided, user info if valid.
    
    Useful for endpoints that work for both authenticated and anonymous users.
    
    Usage:
        @app.get("/public-or-private")
        async def route(user: Optional[dict] = Depends(optional_authorize)):
            if user:
                return {"message": f"Hello {user['email']}"}
            return {"message": "Hello anonymous"}
    """
    if not authorization:
        return None
    
    try:
        return await authorize(authorization)
    except HTTPException:
        return None
