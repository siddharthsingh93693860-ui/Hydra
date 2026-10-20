import pytest
from fastapi import HTTPException

import app


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB", tmp_path / "test.db")
    app.init_db()
    yield


def task_payload(confirmed=True):
    return {"name":"Supplier Order Status","target_url":"https://supplier.demo/orders",
            "goal":"Enter an order ID and return status and delivery date.",
            "input_schema":{"type":"object"},"output_schema":{"type":"object"},
            "example_inputs":{"order_id":"ORD-1024"},"cache_ttl":300,
            "compliance_confirmed":confirmed,"user_label":"test"}


def test_compliance_compile_run_and_semantic_failure(service):
    with pytest.raises(HTTPException) as denied:
        app.create_task(app.TaskCreate(**task_payload(False)))
    assert denied.value.status_code == 403
    created = app.create_task(app.TaskCreate(**task_payload()))
    task_id = created["id"]
    compiled = app.compile_task(task_id)
    assert compiled["status"] == "ready" and compiled["mocked"] is True
    result = app.run_task(task_id, app.RunInput(inputs={"order_id":"ORD-1024"}))
    assert result["status"] == "verified" and result["data"]["status"] == "Shipped"
    app.mutation(app.MutationInput(mutation="semantic_swap"))
    rejected = app.run_task(task_id, app.RunInput(inputs={"order_id":"ORD-1024"}))
    assert rejected["status"] == "failed"


def test_captcha_is_blocked_and_not_healed(service):
    task_id = app.create_task(app.TaskCreate(**task_payload()))["id"]
    app.compile_task(task_id)
    app.mutation(app.MutationInput(mutation="captcha"))
    result = app.run_task(task_id, app.RunInput(inputs={"order_id":"ORD-1024"}))
    assert result["status"] == "blocked_needs_human"
    healed = app.heal_task(task_id)
    assert healed["status"] == "blocked_needs_human"


def test_browser_get_rejects_workflows_with_required_inputs(service):
    payload = task_payload()
    payload["input_schema"] = {"type":"object", "required":["order_id"]}
    task_id = app.create_task(app.TaskCreate(**payload))["id"]
    with pytest.raises(HTTPException) as denied:
        app.run_task_from_browser(task_id)
    assert denied.value.status_code == 405


def test_delete_task_removes_related_data(service):
    task_id = app.create_task(app.TaskCreate(**task_payload()))["id"]
    app.compile_task(task_id)
    app.delete_task(task_id)
    with pytest.raises(HTTPException) as missing:
        app.get_task(task_id)
    assert missing.value.status_code == 404
    with app.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM runs WHERE task_id=?", (task_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM versions WHERE task_id=?", (task_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM events WHERE task_id=?", (task_id,)).fetchone()[0] == 0
