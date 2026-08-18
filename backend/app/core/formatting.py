"""Shared rich-text helpers for turning LLM-planned step content into
properly formatted Notion blocks and Google Docs HTML.

A single lightweight inline-markdown parser (**bold**, *italic*/_italic_,
`code`) backs both renderers so a plan step's text reads the same way in
either destination.
"""

import re
from datetime import UTC, datetime

_INLINE_PATTERN = re.compile(r"(\*\*[^*]+?\*\*|`[^`]+?`|\*[^*]+?\*|_[^_]+?_)")

_BLOCK_STYLE_TO_NOTION_TYPE = {
    "paragraph": "paragraph",
    "bullet": "bulleted_list_item",
    "numbered": "numbered_list_item",
    "todo": "to_do",
}


def parse_inline(text: str) -> list[tuple[str, dict]]:
    """Split text into (content, annotations) runs based on inline markdown."""
    if not text:
        return [("", {})]
    runs: list[tuple[str, dict]] = []
    for part in _INLINE_PATTERN.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            runs.append((part[2:-2], {"bold": True}))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            runs.append((part[1:-1], {"code": True}))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            runs.append((part[1:-1], {"italic": True}))
        elif part.startswith("_") and part.endswith("_") and len(part) > 2:
            runs.append((part[1:-1], {"italic": True}))
        else:
            runs.append((part, {}))
    return runs or [(text, {})]


def notion_rich_text(text: str) -> list[dict]:
    """Render text as a Notion rich_text array, honoring inline markdown."""
    runs = [r for r in parse_inline(text) if r[0]]
    if not runs:
        return [{"type": "text", "text": {"content": ""}}]
    return [
        {
            "type": "text",
            "text": {"content": content},
            "annotations": {
                "bold": annotations.get("bold", False),
                "italic": annotations.get("italic", False),
                "strikethrough": False,
                "underline": False,
                "code": annotations.get("code", False),
                "color": "default",
            },
        }
        for content, annotations in runs
    ]


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_mrkdwn(text: str) -> str:
    """Render text as Slack's mrkdwn dialect, honoring inline markdown."""
    parts = []
    for content, annotations in parse_inline(text):
        escaped = html_escape(content)
        if annotations.get("code"):
            escaped = f"`{escaped}`"
        if annotations.get("bold"):
            escaped = f"*{escaped}*"
        if annotations.get("italic"):
            escaped = f"_{escaped}_"
        parts.append(escaped)
    return "".join(parts)


def inline_html(text: str) -> str:
    """Render text as an HTML fragment, honoring inline markdown."""
    parts = []
    for content, annotations in parse_inline(text):
        escaped = html_escape(content)
        if annotations.get("code"):
            escaped = f"<code>{escaped}</code>"
        if annotations.get("bold"):
            escaped = f"<strong>{escaped}</strong>"
        if annotations.get("italic"):
            escaped = f"<em>{escaped}</em>"
        parts.append(escaped)
    return "".join(parts)


def notion_blocks_from_sections(sections: list[dict]) -> list[dict]:
    """Turn planned `sections` into Notion blocks: a heading, then a styled
    list/paragraph per line, with a divider between sections for readability.
    """
    blocks: list[dict] = []
    for i, section in enumerate(sections):
        if i > 0:
            blocks.append({"object": "block", "type": "divider", "divider": {}})

        heading = section.get("heading")
        if heading:
            blocks.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": notion_rich_text(heading)},
                }
            )

        style = section.get("style") or ("todo" if section.get("as_todo") else "paragraph")
        block_type = _BLOCK_STYLE_TO_NOTION_TYPE.get(style, "paragraph")
        for line in section.get("lines", []):
            payload = {"rich_text": notion_rich_text(line)}
            if block_type == "to_do":
                payload["checked"] = False
            blocks.append({"object": "block", "type": block_type, block_type: payload})
    return blocks


def sections_to_html(title: str, sections: list[dict]) -> str:
    """Render `sections` as an HTML document body, for Drive's HTML->Google
    Doc import conversion (headings/bold/lists survive the conversion;
    a flat .txt upload would lose all of that).
    """
    parts = [f"<h1>{html_escape(title)}</h1>"]
    for section in sections:
        heading = section.get("heading")
        if heading:
            parts.append(f"<h2>{html_escape(heading)}</h2>")

        lines = section.get("lines", [])
        style = section.get("style") or ("todo" if section.get("as_todo") else "paragraph")
        if style == "bullet":
            items = "".join(f"<li>{inline_html(line)}</li>" for line in lines)
            parts.append(f"<ul>{items}</ul>")
        elif style == "numbered":
            items = "".join(f"<li>{inline_html(line)}</li>" for line in lines)
            parts.append(f"<ol>{items}</ol>")
        elif style == "todo":
            items = "".join(f"<li>☐ {inline_html(line)}</li>" for line in lines)
            parts.append(f"<ul>{items}</ul>")
        else:
            parts.extend(f"<p>{inline_html(line)}</p>" for line in lines)
    return "\n".join(parts)


def plain_content_to_html(title: str, content: str) -> str:
    """Fallback HTML rendering for a plain content string (no structured sections)."""
    paragraphs = "".join(f"<p>{inline_html(line)}</p>" for line in content.splitlines() if line.strip())
    return f"<h1>{html_escape(title)}</h1>\n{paragraphs}"


def timestamp_suffix() -> str:
    """A compact title-suffix for the current UTC moment, e.g.
    "Aug 18, 2026 · 2:34 PM UTC" — appended to report titles/filenames so the
    most recently created one is identifiable at a glance among a history of
    similarly-named reports. UTC keeps this unambiguous regardless of where
    the backend happens to be running. Deliberately title-only: the report
    body stays focused on the actual content, not metadata about itself.
    """
    now = datetime.now(UTC)
    hour12 = now.strftime("%I").lstrip("0") or "12"
    time_label = f"{hour12}:{now.strftime('%M %p')} UTC"
    return f"{now.strftime('%b %d, %Y')} · {time_label}"
