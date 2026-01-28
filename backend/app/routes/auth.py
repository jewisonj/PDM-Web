"""Auth API routes."""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional

from ..services.supabase import get_supabase_client, get_supabase_admin
from ..models.schemas import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=User)
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current authenticated user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ")[1]
    supabase = get_supabase_client()
    admin = get_supabase_admin()

    try:
        # Verify token and get user
        auth_user = supabase.auth.get_user(token)

        if not auth_user or not auth_user.user:
            raise HTTPException(status_code=401, detail="Invalid token")

        auth_id = auth_user.user.id
        auth_email = auth_user.user.email

        # Get user from our users table by auth_id (use admin to bypass RLS)
        user_result = admin.table("users").select("*").eq("auth_id", auth_id).execute()

        if user_result.data and len(user_result.data) > 0:
            return user_result.data[0]

        # Not found by auth_id - try to find by email and link
        email_result = admin.table("users").select("*").eq("email", auth_email).execute()

        if email_result.data and len(email_result.data) > 0:
            # Link existing user to auth by updating auth_id
            user_data = email_result.data[0]
            admin.table("users").update({"auth_id": auth_id}).eq("id", user_data["id"]).execute()
            user_data["auth_id"] = auth_id
            return user_data

        # User not in system - create new entry
        new_user = {
            "auth_id": auth_id,
            "email": auth_email,
            "username": auth_email.split("@")[0],
            "role": "viewer"
        }
        create_result = admin.table("users").insert(new_user).execute()
        if create_result.data:
            return create_result.data[0]

        raise HTTPException(status_code=404, detail="Could not create user")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication error: {str(e)}")


@router.get("/users", response_model=list[User])
async def list_users():
    """List all users (admin only in production)."""
    supabase = get_supabase_client()

    result = supabase.table("users").select("*").order("username").execute()
    return result.data


@router.post("/login")
async def login(email: str, password: str):
    """Login with email/password."""
    supabase = get_supabase_client()

    try:
        result = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        return {
            "access_token": result.session.access_token,
            "refresh_token": result.session.refresh_token,
            "user": {
                "id": result.user.id,
                "email": result.user.email
            }
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Logout current user."""
    if not authorization or not authorization.startswith("Bearer "):
        return {"message": "Already logged out"}

    supabase = get_supabase_client()

    try:
        supabase.auth.sign_out()
        return {"message": "Logged out"}
    except Exception:
        return {"message": "Logged out"}
