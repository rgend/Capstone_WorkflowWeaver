from fastapi import APIRouter, HTTPException

from app.core.models import WorkflowTemplate
from app.core.templates import TEMPLATES, get_template

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[WorkflowTemplate])
async def list_templates() -> list[WorkflowTemplate]:
    return TEMPLATES


@router.get("/{template_id}", response_model=WorkflowTemplate)
async def get_template_by_id(template_id: str) -> WorkflowTemplate:
    template = get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template
