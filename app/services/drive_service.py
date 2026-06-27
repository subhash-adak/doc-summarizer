import io
from pathlib import Path
from typing import Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    DriveAccessError,
    FolderNotFoundError,
    UnsupportedFileTypeError,
)
from app.core.logging import get_logger
from app.models.document import DriveFile, SupportedMimeType

logger = get_logger(__name__)

# Read-only access to Drive files
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Fields to request from the Drive API 
FILE_FIELDS = "id, name, mimeType, size, createdTime, modifiedTime, webViewLink"

SUPPORTED_MIME_TYPES = {m.value for m in SupportedMimeType}


class DriveService:
    """
    Encapsulates all Google Drive interactions.

    Usage:
        service = DriveService(credentials)
        files = await service.list_folder_files(folder_id)
        content = await service.download_file(file_id)
    """

    def __init__(self, credentials: Credentials) -> None:
        self._credentials = credentials
        settings = get_settings()
        if settings.demo_mode:
            self._client = None
        else:
            self._client = build("drive", "v3", credentials=credentials, cache_discovery=False)

    # Auth helpers 
    @classmethod
    def get_auth_url(cls) -> tuple[str, str, Optional[str]]:
        """
        Build the OAuth2 consent URL.
        Returns (auth_url, state, code_verifier) — store `state` and `code_verifier` in session.
        """
        settings = get_settings()
        if settings.demo_mode:
            # Bypass actual Google consent redirection in demo mode
            auth_url = "http://localhost:8000/auth/callback?code=mock_code&state=mock_state"
            return auth_url, "mock_state", None

        flow = cls._build_flow(settings)
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url, state, getattr(flow, "code_verifier", None)

    @classmethod
    def exchange_code(cls, code: str, state: str, code_verifier: Optional[str] = None) -> Credentials:
        """
        Exchange the OAuth2 auth code for credentials and persist the token.
        """
        settings = get_settings()
        if settings.demo_mode:
            credentials = Credentials(
                token="mock_access_token",
                refresh_token="mock_refresh_token",
                token_uri="https://oauth2.googleapis.com/token",
                client_id="mock_client_id",
                client_secret="mock_client_secret",
            )
            cls._save_token(credentials, settings.oauth_token_path)
            logger.info("mock_oauth_token_saved", path=str(settings.oauth_token_path))
            return credentials

        flow = cls._build_flow(settings)
        if code_verifier:
            flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        credentials = flow.credentials
        cls._save_token(credentials, settings.oauth_token_path)
        logger.info("oauth_token_saved", path=str(settings.oauth_token_path))
        return credentials

    @classmethod
    def load_credentials(cls) -> Optional[Credentials]:
        """
        Load stored OAuth2 credentials from disk and refresh if expired.
        Returns None if no token file exists (user needs to log in).
        """
        settings = get_settings()
        token_path = settings.oauth_token_path

        if not token_path.exists():
            return None

        if settings.demo_mode:
            return Credentials(
                token="mock_access_token",
                refresh_token="mock_refresh_token",
                token_uri="https://oauth2.googleapis.com/token",
                client_id="mock_client_id",
                client_secret="mock_client_secret",
            )

        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)

        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                cls._save_token(credentials, token_path)
                logger.info("oauth_token_refreshed")
            except RefreshError as exc:
                logger.warning("oauth_token_refresh_failed", error=str(exc))
                token_path.unlink(missing_ok=True)
                return None

        return credentials if credentials.valid else None

    @classmethod
    def revoke_credentials(cls) -> None:
        """Delete the stored token (logout)."""
        settings = get_settings()
        settings.oauth_token_path.unlink(missing_ok=True)
        logger.info("oauth_token_revoked")

    # Drive operations 

    def list_folder_files(
        self,
        folder_id: Optional[str] = None,
    ) -> list[DriveFile]:
        """
        List all supported documents in the given Drive folder.
        Raises FolderNotFoundError if the folder is inaccessible.
        """
        if get_settings().demo_mode:
            logger.info("demo_drive_folder_listed", folder_id=folder_id, file_count=6)
            return [
                DriveFile(
                    id="mock-file-1",
                    name="q3_financial_report.pdf",
                    mime_type=SupportedMimeType.PDF,
                    size_bytes=460800,  # 450 KB
                    created_at=None,
                    modified_at=None,
                    web_view_link="https://docs.google.com/document/d/mock-file-1/view",
                ),
                DriveFile(
                    id="mock-file-2",
                    name="marketing_strategy_v2.docx",
                    mime_type=SupportedMimeType.DOCX,
                    size_bytes=1258291,  # 1.2 MB
                    created_at=None,
                    modified_at=None,
                    web_view_link="https://docs.google.com/document/d/mock-file-2/view",
                ),
                DriveFile(
                    id="mock-file-3",
                    name="server_configuration_guide.txt",
                    mime_type=SupportedMimeType.TXT,
                    size_bytes=24576,  # 24 KB
                    created_at=None,
                    modified_at=None,
                    web_view_link="https://docs.google.com/document/d/mock-file-3/view",
                ),
                DriveFile(
                    id="mock-file-4",
                    name="empty_document.txt",
                    mime_type=SupportedMimeType.TXT,
                    size_bytes=0,
                    created_at=None,
                    modified_at=None,
                    web_view_link="https://docs.google.com/document/d/mock-file-4/view",
                ),
                DriveFile(
                    id="mock-file-5",
                    name="product_roadmap.md",
                    mime_type=SupportedMimeType.MD,
                    size_bytes=15360,  # 15 KB
                    created_at=None,
                    modified_at=None,
                    web_view_link="https://docs.google.com/document/d/mock-file-5/view",
                ),
                DriveFile(
                    id="mock-file-6",
                    name="customer_feedback_data.csv",
                    mime_type=SupportedMimeType.CSV,
                    size_bytes=81920,  # 80 KB
                    created_at=None,
                    modified_at=None,
                    web_view_link="https://docs.google.com/document/d/mock-file-6/view",
                ),
            ]

        folder_id = folder_id or get_settings().drive_folder_id
        mime_filter = " or ".join(
            f"mimeType='{m}'" for m in SUPPORTED_MIME_TYPES
        )
        query = (
            f"'{folder_id}' in parents "
            f"and ({mime_filter}) "
            f"and trashed=false"
        )

        files = []
        next_page_token = None

        while True:
            try:
                response = (
                    self._client.files()
                    .list(
                        q=query,
                        fields=f"nextPageToken, files({FILE_FIELDS})",
                        pageSize=100,
                        pageToken=next_page_token,
                        orderBy="name",
                    )
                    .execute()
                )
            except HttpError as exc:
                if exc.resp.status == 404:
                    raise FolderNotFoundError(
                        f"Drive folder '{folder_id}' not found or access denied."
                    ) from exc
                raise DriveAccessError(f"Drive API error: {exc}") from exc

            files.extend(response.get("files", []))
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        logger.info("drive_folder_listed", folder_id=folder_id, file_count=len(files))
        return [self._parse_file_metadata(f) for f in files]

    def download_file(self, file_id: str) -> bytes:
        """
        Download a file's content as bytes.
        Raises DriveAccessError on failure.
        """
        if get_settings().demo_mode:
            mock_data = {
                "mock-file-1": b"Mock PDF financial report content. Revenue grew by 14% to reach $42.5 million.",
                "mock-file-2": b"Mock DOCX marketing strategy document. Launch Product X in late Q3 using social ads.",
                "mock-file-3": b"Mock TXT server guide. Setup corporate servers, SSH configs, and configure daily backups.",
                "mock-file-4": b"",
                "mock-file-5": b"Mock Markdown content. # Product Roadmap\n- Phase 1: Authentication and Drive integration completed.\n- Phase 2: SSE streaming support implemented.",
                "mock-file-6": b"Mock CSV customer data. ID,Rating,Comment\n1,5,Great tool!\n2,4,Very fast summary\n3,5,Helped me process massive reports",
            }
            logger.debug("demo_drive_file_downloaded", file_id=file_id)
            return mock_data.get(file_id, b"Mock document content")

        try:
            request = self._client.files().get_media(fileId=file_id)
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            content = buffer.getvalue()
            logger.debug("drive_file_downloaded", file_id=file_id, size_bytes=len(content))
            return content

        except HttpError as exc:
            raise DriveAccessError(
                f"Failed to download file '{file_id}': {exc}"
            ) from exc

    # Private helpers 

    @staticmethod
    def _parse_file_metadata(raw: dict) -> DriveFile:
        """Map raw Drive API response dict to DriveFile model."""
        return DriveFile(
            id=raw["id"],
            name=raw["name"],
            mime_type=SupportedMimeType(raw["mimeType"]),
            size_bytes=int(raw["size"]) if raw.get("size") else None,
            created_at=raw.get("createdTime"),
            modified_at=raw.get("modifiedTime"),
            web_view_link=raw.get("webViewLink"),
        )

    @staticmethod
    def _build_flow(settings) -> Flow:
        return Flow.from_client_secrets_file(
            str(settings.oauth_credentials_path),
            scopes=SCOPES,
            redirect_uri="http://localhost:8000/auth/callback",
        )

    @staticmethod
    def _save_token(credentials: Credentials, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(credentials.to_json())
