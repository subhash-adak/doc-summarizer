from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.core.exceptions import AuthenticationError, http_401
from app.core.logging import get_logger
from app.services.drive_service import DriveService

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


@router.get("/login", summary="Start Google OAuth2 flow")
async def login(request: Request) -> RedirectResponse:
    """Redirect the user to Google's consent screen."""
    auth_url, state, code_verifier = DriveService.get_auth_url()
    request.session["oauth_state"] = state
    if code_verifier:
        request.session["code_verifier"] = code_verifier
    logger.info("oauth_flow_started")
    return RedirectResponse(url=auth_url)


@router.get("/callback", summary="OAuth2 redirect callback")
async def callback(request: Request, code: str, state: str) -> RedirectResponse:
    """
    Handle the OAuth2 redirect from Google.
    Exchanges the auth code for credentials and stores the token.
    """
    stored_state = request.session.get("oauth_state")
    if stored_state != state:
        logger.warning("oauth_state_mismatch", expected=stored_state, received=state)
        raise http_401("OAuth2 state mismatch. Possible CSRF attack.")

    try:
        code_verifier = request.session.pop("code_verifier", None)
        DriveService.exchange_code(code=code, state=state, code_verifier=code_verifier)
        request.session.pop("oauth_state", None)
        logger.info("oauth_login_success")
    except Exception as exc:
        logger.error("oauth_callback_error", error=str(exc))
        raise http_401(f"Authentication failed: {exc}") from exc

    return RedirectResponse(url="/")


@router.get("/logout", summary="Revoke credentials and log out")
async def logout(request: Request) -> RedirectResponse:
    """Delete the stored OAuth token and redirect to home."""
    DriveService.revoke_credentials()
    request.session.clear()
    logger.info("user_logged_out")
    return RedirectResponse(url="/")


@router.get("/status", summary="Check auth status")
async def auth_status() -> dict:
    """Returns whether a valid OAuth token exists."""
    from app.core.config import get_settings
    settings = get_settings()
    credentials = DriveService.load_credentials()
    return {
        "authenticated": credentials is not None,
        "demo_mode": settings.demo_mode,
    }
