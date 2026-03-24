import httpx
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Auth URLs
SIGNUP_URL = f"{SUPABASE_URL}/auth/v1/signup"
LOGIN_URL = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
USER_URL = f"{SUPABASE_URL}/auth/v1/user"

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json"
    }

class SBUser:
    def __init__(self, data):
        self.id = data.get("id")
        self.email = data.get("email")

def sign_up(email: str, password: str):
    """Sign up using Supabase Auth REST API"""
    with httpx.Client() as client:
        response = client.post(
            SIGNUP_URL,
            headers=get_headers(),
            json={"email": email, "password": password}
        )
        if response.status_code != 200:
            raise Exception(response.json().get("msg", "Registration failed"))
        return response.json()

def sign_in(email: str, password: str):
    """Sign in using Supabase Auth REST API"""
    with httpx.Client() as client:
        response = client.post(
            LOGIN_URL,
            headers=get_headers(),
            json={"email": email, "password": password}
        )
        if response.status_code != 200:
            error_data = response.json()
            raise Exception(error_data.get("error_description") or error_data.get("msg") or "Login failed")
        
        data = response.json()
        
        # Mocking the object structure perfectly
        class Session:
            def __init__(self, token):
                self.access_token = token
                
        class AuthResult:
            def __init__(self, session_token, user_data):
                self.session = Session(session_token)
                self.user = SBUser(user_data)
                
        return AuthResult(data.get("access_token"), data.get("user"))

def get_supabase_user(token: str):
    """Get user info from Supabase Auth REST API"""
    headers = get_headers()
    headers["Authorization"] = f"Bearer {token}"
    
    with httpx.Client() as client:
        response = client.get(USER_URL, headers=headers)
        if response.status_code == 200:
            return SBUser(response.json())
    return None

def reset_password_for_email(email: str):
    """Trigger password reset email via REST API"""
    with httpx.Client() as client:
        response = client.post(
            f"{SUPABASE_URL}/auth/v1/recover",
            headers=get_headers(),
            json={"email": email}
        )
        if response.status_code != 200:
            raise Exception("Failed to send reset email")
        return response.json()
