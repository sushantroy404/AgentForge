import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .fakes import ROOT, FakeLLM

POLICY = ROOT / "data" / "demo" / "acme_refund_policy.md"
TURN1 = "We are Acme Cloud. Build a Customer Support Specialist named Aria for Acme customers asking about hardware orders, returns and refunds."
TURN2 = "In scope: order status, refunds. Out of scope: competitor comparisons. Enable lookup_order and escalate_to_human."


@pytest.fixture
def settings(tmp_path):
    d = tmp_path / "data"
    return Settings(_env_file=None, DATA_DIR=str(d), UPLOAD_DIR=str(d / "uploads"), LANCEDB_URI=str(d / "lancedb"),
                    MANIFESTS_DIR=str(d / "manifests"), RAG_SCORE_THRESHOLD=0.08, SCOPE_OUT_MIN=0.35,
                    SCOPE_MARGIN=0.05, DEMO_MODE="off")


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def client(settings, llm):
    app = create_app(settings, llm)
    with TestClient(app) as c:
        c.app = app
        yield c


def wait_job(client, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job timed out")


def upload(client, sid, path=POLICY, name=None):
    r = client.post(f"/api/architect/sessions/{sid}/documents",
                    files={"file": (name or path.name, path.read_bytes(), "text/markdown")})
    assert r.status_code == 202, r.text
    return wait_job(client, r.json()["job_id"])


def build_demo_specialist(client) -> str:
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    assert client.post(f"/api/architect/sessions/{sid}/chat", json={"message": TURN1}).status_code == 200
    assert client.post(f"/api/architect/sessions/{sid}/chat", json={"message": TURN2}).status_code == 200
    assert upload(client, sid)["status"] == "done"
    assert client.post(f"/api/architect/sessions/{sid}/fill-defaults").status_code == 200
    r = client.post(f"/api/architect/sessions/{sid}/finalize", json={})
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    return job["result"]["specialist_id"]


@pytest.fixture
def specialist(client):
    return build_demo_specialist(client)
