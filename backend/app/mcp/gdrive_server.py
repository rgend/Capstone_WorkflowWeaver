"""First-party Google Drive MCP server, launched as a local stdio subprocess
by GoogleDriveAdapter (same transport as the Notion MCP server).

Community `gdrive` MCP packages (e.g. @isaacphi/mcp-gdrive) only expose
search/read/sheets tools, not file creation, so this implements the minimal
create/delete surface WorkflowWeaver's rollback-capable workflow needs,
directly against the Drive v3 API.

Credentials: an OAuth "Desktop app" client secrets file (GOOGLE_CREDENTIALS_PATH).
On first use this opens a browser for one-time user consent and caches the
resulting token at GDRIVE_TOKEN_PATH for silent reuse/refresh afterwards.
"""

import json
import os

import anyio
import mcp.types as types
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload
from mcp.server import Server
from mcp.server.stdio import stdio_server

# drive.file: access limited to files this app creates — least privilege
# for a "create a doc, maybe delete it on rollback" workflow.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _load_credentials() -> Credentials:
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
    token_path = os.environ.get("GDRIVE_TOKEN_PATH", "./data/gdrive_token.json")

    creds: Credentials | None = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token_path) or ".", exist_ok=True)
        with open(token_path, "w") as fh:
            fh.write(creds.to_json())

    return creds


def _drive_service():
    return build("drive", "v3", credentials=_load_credentials(), cache_discovery=False)


server = Server("workflowweaver-gdrive")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="create_file",
            description=(
                "Create a new file in Google Drive with the given name and content. "
                "When mimeType is 'text/html', Drive converts it into a native Google "
                "Doc on upload (headings/bold/lists are preserved)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                    "mimeType": {"type": "string"},
                    "parents": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="delete_file",
            description="Delete a file from Google Drive by file ID",
            inputSchema={
                "type": "object",
                "properties": {"fileId": {"type": "string"}},
                "required": ["fileId"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    service = await anyio.to_thread.run_sync(_drive_service)

    if name == "create_file":
        media_mime_type = arguments.get("mimeType", "text/plain")
        metadata = {"name": arguments["name"]}
        if media_mime_type == "text/html":
            # Import-convert the uploaded HTML into a native Google Doc
            # instead of storing it as a raw .html/.txt blob.
            metadata["mimeType"] = "application/vnd.google-apps.document"
        parents = arguments.get("parents") or []
        if parents:
            metadata["parents"] = parents
        media = MediaInMemoryUpload(
            arguments.get("content", "").encode("utf-8"),
            mimetype=media_mime_type,
        )

        def _create():
            return service.files().create(body=metadata, media_body=media, fields="id, webViewLink").execute()

        try:
            file = await anyio.to_thread.run_sync(_create)
        except HttpError as exc:
            raise RuntimeError(f"Drive create_file failed: {exc}") from exc
        return [types.TextContent(type="text", text=json.dumps(file))]

    if name == "delete_file":
        file_id = arguments["fileId"]

        def _delete():
            service.files().delete(fileId=file_id).execute()

        try:
            await anyio.to_thread.run_sync(_delete)
        except HttpError as exc:
            raise RuntimeError(f"Drive delete_file failed: {exc}") from exc
        return [types.TextContent(type="text", text=json.dumps({"deleted": True, "fileId": file_id}))]

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
