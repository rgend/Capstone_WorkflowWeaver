def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mock_mode"] is True
    assert "notion" in body["integrations"]


def test_list_templates_has_required_minimum(client):
    response = client.get("/api/templates")
    assert response.status_code == 200
    templates = response.json()
    assert len(templates) >= 3
    ids = {t["id"] for t in templates}
    assert "meeting-to-tasks" in ids


def test_get_unknown_template_404(client):
    response = client.get("/api/templates/does-not-exist")
    assert response.status_code == 404


def test_start_workflow_and_fetch_report(client):
    start = client.post(
        "/api/workflows",
        json={
            "description": "Create a Notion page and post a Teams summary about the launch.",
            "meeting_notes": None,
        },
    )
    assert start.status_code == 200
    run_id = start.json()["run_id"]

    # Drain the SSE stream synchronously so the background run completes.
    with client.stream("GET", f"/api/workflows/{run_id}/stream") as stream:
        for _ in stream.iter_lines():
            pass

    report = client.get(f"/api/workflows/{run_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["run_id"] == run_id
    assert body["status"] in {"success", "failed", "rolled_back"}
    assert body["mock_mode"] is True


def test_unknown_run_report_404(client):
    response = client.get("/api/workflows/run_doesnotexist/report")
    assert response.status_code == 404
