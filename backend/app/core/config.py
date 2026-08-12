from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM ---
    llm_provider: str = "anthropic"
    llm_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    openai_model: str = "gpt-4o"

    @property
    def anthropic_api_key(self) -> str | None:
        return self.llm_api_key if self.llm_provider == "anthropic" else None

    @property
    def openai_api_key(self) -> str | None:
        return self.llm_api_key if self.llm_provider == "openai" else None

    # --- Notion MCP ---
    notion_token: str | None = None
    notion_page_id: str | None = None
    notion_mcp_command: str = "npx"
    notion_mcp_args: str = "-y,@notionhq/notion-mcp-server"

    # --- Google Drive MCP ---
    google_credentials_path: str = "./credentials.json"
    google_drive_folder_id: str | None = None
    gdrive_mcp_command: str = "npx"
    gdrive_mcp_args: str = "-y,@isaacphi/mcp-gdrive"

    # --- Microsoft Teams ---
    teams_webhook_url: str | None = None

    # --- Langfuse ---
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- App behavior ---
    mock_mode: bool = True
    max_step_retries: int = 3
    retry_backoff_base_seconds: float = 1.5
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    workflow_store_path: str = "./data/workflows.json"

    @property
    def notion_configured(self) -> bool:
        return bool(self.notion_token and self.notion_page_id)

    @property
    def gdrive_configured(self) -> bool:
        import os

        return bool(self.google_drive_folder_id and os.path.exists(self.google_credentials_path))

    @property
    def teams_configured(self) -> bool:
        return bool(self.teams_webhook_url)

    @property
    def langfuse_configured(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
