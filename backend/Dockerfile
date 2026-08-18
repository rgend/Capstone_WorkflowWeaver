FROM python:3.12-slim

# Node.js 20 is required alongside Python: NotionAdapter launches the
# community `@notionhq/notion-mcp-server` via `npx` as a stdio subprocess
# (see app/mcp/notion_adapter.py). Installed via NodeSource's apt repo rather
# than cherry-picking binaries from the official node image — npm/npx's
# internal `require` paths aren't stable enough across Node versions for a
# partial file-level copy to reliably keep working (hit MODULE_NOT_FOUND).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Safe to use --reload here (unlike bare Windows): uvicorn's Windows-only
# SelectorEventLoop workaround for --reload never triggers on Linux, so the
# MCP adapters' subprocess spawning (anyio.open_process) keeps working.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
