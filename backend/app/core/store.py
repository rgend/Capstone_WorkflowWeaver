import asyncio
import json
import os

from pydantic import ValidationError

from app.core.models import ExecutionReport, WorkflowSummary


class WorkflowStore:
    """Simple JSON-file-backed store for run history/reports.

    A capstone-scoped project doesn't need a database; this keeps history
    durable across backend restarts without adding infra dependencies.
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()
        self._reports: dict[str, ExecutionReport] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._reports = {}
            return
        for run_id, data in raw.items():
            try:
                self._reports[run_id] = ExecutionReport.model_validate(data)
            except ValidationError:
                # Skip records that predate a schema change (e.g. a renamed
                # tool) instead of letting one legacy record crash startup.
                continue

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({k: v.model_dump(mode="json") for k, v in self._reports.items()}, f, indent=2)

    async def save_report(self, report: ExecutionReport) -> None:
        async with self._lock:
            self._reports[report.run_id] = report
            self._persist()

    async def get_report(self, run_id: str) -> ExecutionReport | None:
        async with self._lock:
            return self._reports.get(run_id)

    async def list_summaries(self) -> list[WorkflowSummary]:
        async with self._lock:
            items = [
                WorkflowSummary(
                    run_id=r.run_id,
                    description=r.description,
                    status=r.status,
                    started_at=r.started_at,
                    finished_at=r.finished_at,
                )
                for r in self._reports.values()
            ]
            return sorted(items, key=lambda s: s.started_at, reverse=True)
