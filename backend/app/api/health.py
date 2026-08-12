from fastapi import APIRouter, Depends

from app.api.deps import get_settings
from app.core.config import Settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "mock_mode": settings.mock_mode,
        "integrations": {
            "llm": {"provider": settings.llm_provider, "configured": settings.llm_configured},
            "notion": {"configured": settings.notion_configured},
            "google_drive": {"configured": settings.gdrive_configured},
            "teams": {"configured": settings.teams_configured},
            "langfuse": {"configured": settings.langfuse_configured},
        },
    }
