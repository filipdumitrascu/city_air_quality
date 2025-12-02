import requests
from fastapi import HTTPException
from fastapi import Header

GOOGLE_TOKEN_INFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"

def verify_token(token: str):
    """Validează un Google OAuth 2.0 Access Token și returnează datele utilizatorului."""
    response = requests.get(GOOGLE_TOKEN_INFO_URL, params={"access_token": token})
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_info = response.json()

    if "email" not in user_info:
        raise HTTPException(status_code=401, detail="Invalid token: email not found")

    return user_info

async def authorize(token: str = Header(None)):
    print(f"Received header: {token}")  # Vezi ce ajunge în FastAPI
    if not token or not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = token.replace("Bearer ", "").strip()
    user_info = verify_token(token)
    print(f"Authenticated user: {user_info['email']}")

