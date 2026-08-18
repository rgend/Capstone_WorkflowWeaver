"""Slack notifications via the Slack Web API (chat.postMessage).

Posts a proper Block Kit card — a header, a markdown summary, a prominent
"Created Resources" section linking straight to any Notion page/Drive doc
made earlier in the same run, and an optional fields section for key/value
facts — rather than a flat text blob. Resolves a permalink so the execution
report can link straight to the message. Falls back to a mock response when
Slack isn't configured or MOCK_MODE is enabled.
"""

from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from app.core.config import Settings
from app.core.errors import ToolExecutionError
from app.core.formatting import html_escape, slack_mrkdwn
from app.mcp.mock import mock_slack_message


class SlackClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def use_mock(self) -> bool:
        return self.settings.mock_mode or not self.settings.slack_configured

    async def post_message(
        self,
        title: str,
        text: str,
        facts: dict[str, str] | None = None,
        channel: str | None = None,
        resource_links: list[dict] | None = None,
    ) -> dict:
        if self.use_mock:
            return mock_slack_message(title)

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": title[:150], "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": slack_mrkdwn(text) or " "}},
        ]

        valid_links = [link for link in (resource_links or []) if link.get("url")]
        if valid_links:
            blocks.append({"type": "divider"})
            links_text = "\n".join(
                f":link: <{link['url']}|*{html_escape(link['label'])}*>" for link in valid_links
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*:white_check_mark: Created Resources*\n{links_text}"},
                }
            )

        if facts:
            blocks.append(
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*{k}*\n{slack_mrkdwn(v)}"} for k, v in list(facts.items())[:10]
                    ],
                }
            )
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "Posted by *WorkflowWeaver* :robot_face:"}]}
        )

        target_channel = channel or self.settings.slack_channel_id
        client = AsyncWebClient(token=self.settings.slack_bot_token)
        try:
            response = await client.chat_postMessage(channel=target_channel, text=title, blocks=blocks)
        except SlackApiError as exc:
            raise ToolExecutionError("slack", "post_message", str(exc)) from exc

        permalink = None
        try:
            link_response = await client.chat_getPermalink(channel=response["channel"], message_ts=response["ts"])
            permalink = link_response.get("permalink")
        except SlackApiError:
            pass  # Permalink lookup can need an extra scope; the post itself already succeeded.

        return {
            "mock": False,
            "title": title,
            "url": permalink,
            "channel": response.get("channel"),
            "ts": response.get("ts"),
        }
