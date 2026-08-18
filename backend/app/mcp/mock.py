"""Deterministic mock tool responses used when MOCK_MODE is on or a given
integration isn't configured. Keeps the full LangGraph flow demonstrable
end-to-end without live external accounts, while real adapters (notion_adapter,
gdrive_adapter, slack_client) take over the moment credentials are supplied.
"""

from app.core.models import new_id


def mock_notion_page(title: str) -> dict:
    block_id = new_id("mock-notion-page")
    return {
        "mock": True,
        "block_id": block_id,
        "url": f"https://notion.so/mock-workspace/{block_id}",
        "title": title,
    }


def mock_drive_file(name: str) -> dict:
    file_id = new_id("mock-drive-file")
    return {
        "mock": True,
        "file_id": file_id,
        "url": f"https://docs.google.com/document/d/{file_id}/edit",
        "name": name,
    }


def mock_slack_message(title: str) -> dict:
    message_id = new_id("mock-slack-msg")
    return {
        "mock": True,
        "message_id": message_id,
        "title": title,
        "url": f"https://app.slack.com/client/mock-workspace/mock-channel/{message_id}",
        "delivered_to": "mock-slack-channel",
    }
