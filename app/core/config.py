from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App 
    app_env: Literal["development", "staging", "production"] = "development"
    secret_key: str = Field(default="demo-secret-key-16chars-minimum", min_length=16)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    demo_mode: bool = Field(default=False)

    # GCP / Vertex AI 
    gcp_project_id: str = Field(default="demo-project")
    gcp_location: str = Field(default="us-central1")
    vertex_model: str = Field(default="gemini-2.5-flash")
    vertex_sa_path: Path | None = None 

    # Google Drive   
    drive_folder_id: str = Field(default="demo-folder")
    oauth_credentials_path: Path = Field(default=Path("credentials/oauth_credentials.json"))
    oauth_token_path: Path = Field(default=Path("credentials/token.json"))

    # Summarization tuning 
    max_chunk_size: int = Field(default=8000, ge=1000, le=30000)
    chunk_overlap: int = Field(default=200, ge=0)
    summary_max_tokens: int = Field(default=4096, ge=256, le=8192)
    summary_temperature: float = Field(default=0.2, ge=0.0, le=1.0)

    def model_post_init(self, __context) -> None:
        placeholders = {
            "your-gcp-project-id",
            "your-google-drive-folder-id",
            "demo-project",
            "demo-folder",
            "",
        }
        # Force demo mode if placeholders or missing OAuth file are detected
        if (
            self.gcp_project_id.lower() in placeholders
            or self.drive_folder_id.lower() in placeholders
            or not self.oauth_credentials_path.exists()
            or self.demo_mode
        ):
            self.demo_mode = True

    @field_validator("vertex_sa_path", "oauth_credentials_path", mode="before")
    @classmethod
    def path_must_exist_if_set(cls, v: str | Path | None) -> Path | None:
        if v is None:
            return None
        p = Path(v)
        return p

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.
    Use this everywhere instead of instantiating Settings directly.
    """
    return Settings()
