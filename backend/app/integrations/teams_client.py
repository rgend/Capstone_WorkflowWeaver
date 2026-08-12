"""Microsoft Teams notifications via Incoming Webhook / Workflow webhook.

Per the capstone spec, Teams integration does not go through MCP or Graph API —
it's a direct HTTP POST of a MessageCard-style payload to the configured
webhook URL.
"""

import httpx

from app.core.config import Settings
from app.core.errors import ToolExecutionError
from app.mcp.mock import mock_teams_message


class TeamsClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def use_mock(self) -> bool:
        return self.settings.mock_mode or not self.settings.teams_configured

    async def post_message(self, title: str, text: str, facts: dict[str, str] | None = None) -> dict:
        if self.use_mock:
            return mock_teams_message(title)

        fact_set = [{"name": k, "value": v} for k, v in (facts or {}).items()]
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": title,
            "themeColor": "6C4CFF",
            "title": title,
            "sections": [{"activityTitle": title, "text": text, "facts": fact_set, "markdown": True}],
        }

        try:
            async with httpx.AsyncClient(timeout=15) as http_client:
                response = await http_client.post(self.settings.teams_webhook_url, json=payload)
            if response.status_code >= 300:
                raise ToolExecutionError(
                    "teams", "post_message", f"webhook returned HTTP {response.status_code}: {response.text[:300]}"
                )
            return {"mock": False, "title": title, "status_code": response.status_code}
        except httpx.HTTPError as exc:
            raise ToolExecutionError("teams", "post_message", str(exc)) from exc
