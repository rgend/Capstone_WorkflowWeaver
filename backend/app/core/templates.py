from app.core.models import WorkflowConfig, WorkflowTemplate

TEMPLATES: list[WorkflowTemplate] = [
    WorkflowTemplate(
        id="meeting-to-tasks",
        name="Meeting Notes to Tasks",
        category="Productivity",
        icon="clipboard-list",
        description=(
            "Turn raw meeting notes into a Notion project page with action items, save a "
            "summary document to Google Drive, and notify the team on Slack."
        ),
        nl_description=(
            "Take today's meeting notes and create a Notion project page, "
            "generate action items with owners, save a summary document to Google Drive, "
            "and post a summary to Slack."
        ),
        default_config=WorkflowConfig(),
    ),
    WorkflowTemplate(
        id="sprint-planning",
        name="Sprint Planning Kickoff",
        category="Project Management",
        icon="calendar",
        description=(
            "Create a Notion sprint board page from a backlog description, save the sprint "
            "goal doc to Google Drive, and announce the sprint kickoff on Slack."
        ),
        nl_description=(
            "From this backlog list, create a Notion sprint page with a prioritized task "
            "breakdown, save a sprint goal summary document to Google Drive, and post a "
            "kickoff announcement to Slack with the sprint goal and dates."
        ),
        default_config=WorkflowConfig(),
    ),
    WorkflowTemplate(
        id="incident-response",
        name="Incident Response Report",
        category="Operations",
        icon="alert-triangle",
        description=(
            "Document an incident in Notion, archive the full postmortem to Google Drive, "
            "and alert stakeholders on Slack immediately."
        ),
        nl_description=(
            "An incident just occurred. Create a Notion incident report page with impact, "
            "timeline, and remediation steps, save the full postmortem document to Google "
            "Drive, and post an urgent summary notification to Slack."
        ),
        default_config=WorkflowConfig(),
    ),
    WorkflowTemplate(
        id="requirements-to-notion",
        name="Requirements to Notion Backlog",
        category="Product",
        icon="file-text",
        description=(
            "Convert an unstructured requirements list into a structured Notion backlog, save "
            "a copy to Google Drive, and notify the product team on Slack."
        ),
        nl_description=(
            "Take this requirements list and create a structured Notion backlog page with "
            "each requirement as a task with priority, save a copy to Google Drive, and post "
            "a notification to Slack summarizing what was added."
        ),
        default_config=WorkflowConfig(),
    ),
]


def get_template(template_id: str) -> WorkflowTemplate | None:
    return next((t for t in TEMPLATES if t.id == template_id), None)
