"""Deterministic mock tool responses used when MOCK_MODE is on or a given
integration isn't configured. Keeps the full LangGraph flow demonstrable
end-to-end without live external accounts, while real adapters (notion_adapter,
gdrive_adapter, teams_client) take over the moment credentials are supplied.
"""

from app.core.models import new_id


def mock_notion_page(title: str) -> dict:
    page_id = new_id("mock-notion-page")
    return {
        "mock": True,
        "page_id": page_id,
        "url": f"https://notion.so/mock-workspace/{page_id}",
        "title": title,
    }


def mock_drive_file(name: str) -> dict:
    file_id = new_id("mock-drive-file")
    return {
        "mock": True,
        "file_id": file_id,
        "url": f"https://drive.google.com/file/d/{file_id}/view",
        "name": name,
    }


def mock_teams_message(title: str) -> dict:
    return {
        "mock": True,
        "message_id": new_id("mock-teams-msg"),
        "title": title,
        "delivered_to": "mock-teams-channel",
    }
