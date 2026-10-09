import json

from .conftest import POLICY, build_demo_specialist, upload, wait_job


def test_health_tools_and_jobs_404(client):
    h = client.get("/api/health").json()
    assert "demo_mode" in h and h["lancedb"] is True
    assert {t["tool_id"] for t in client.get("/api/tools").json()} >= {"lookup_order", "escalate_to_human"}
    assert client.get("/api/jobs/nope").status_code == 404


def test_full_flow_and_job_stages(client):
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    job = upload(client, sid)
    assert job["status"] == "done" and all(s["status"] == "done" for s in job["stages"])
    r = job["result"]
    assert r["chunk_count"] == 5 and r["sample_facts"] and r["draft_spec"]["knowledge"]["collection_id"].startswith("col_")
    assert r["assistant_message"]["role"] == "assistant"
    session = client.get(f"/api/architect/sessions/{sid}").json()
    assert session["documents"][0]["filename"] == POLICY.name


def test_document_injection_warning(client):
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    from .fakes import ROOT
    job = upload(client, sid, ROOT / "data" / "demo" / "injected_doc.md")
    assert job["status"] == "done" and len(job["result"]["warnings"]) == 2


def test_failed_ingest_leaves_session_usable(client):
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    r = client.post(f"/api/architect/sessions/{sid}/documents", files={"file": ("e.txt", b"  ", "text/plain")})
    j = wait_job(client, r.json()["job_id"])
    assert j["status"] == "failed" and any(s["status"] == "failed" for s in j["stages"])
    assert client.get(f"/api/architect/sessions/{sid}").status_code == 200


def test_specialist_listing_and_manifest_immutable(client, specialist, settings):
    lst = client.get("/api/specialists").json()
    assert lst[0]["id"] == specialist and lst[0]["status"] == "verified"
    f = settings.manifests_dir / f"{specialist}.json"
    before = f.read_text()
    client.post(f"/api/specialists/{specialist}/smoke-test")      # re-run tests mutates status only
    assert f.read_text() == before and (settings.manifests_dir / f"{specialist}.status.json").exists()
    assert "deployment_status" not in json.loads(before)["manifest"]


def test_failed_status_blocks_chat(client, specialist, settings):
    from datetime import datetime, timezone
    from app.models.manifest import DeploymentRecord
    client.app.state.c.store.save_status(specialist, DeploymentRecord(status="failed", updated_at=datetime.now(timezone.utc)))
    assert client.post(f"/api/specialists/{specialist}/chat", json={"message": "hello there"}).status_code == 409
    assert client.post("/api/specialists/nope/chat", json={"message": "hello"}).status_code == 404


def test_sessions_persist_across_app_restart(client, settings, llm):
    from fastapi.testclient import TestClient
    from app.main import create_app
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    spec = build_demo_specialist(client)
    with TestClient(create_app(settings, llm)) as c2:
        assert c2.get(f"/api/architect/sessions/{sid}").status_code == 200
        assert c2.get(f"/api/specialists/{spec}").json()["status"] == "verified"
