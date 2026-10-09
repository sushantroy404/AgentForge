from .conftest import TURN1, TURN2


def test_session_create_and_restore(client):
    r = client.post("/api/architect/sessions", json={})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert r.json()["missing_report"]["completeness_pct"] == 0
    again = client.get(f"/api/architect/sessions/{sid}").json()
    assert again["messages"][0]["role"] == "assistant"
    assert client.get("/api/architect/sessions/nope").status_code == 404


def test_scripted_turns_patch_draft(client):
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    r1 = client.post(f"/api/architect/sessions/{sid}/chat", json={"message": TURN1}).json()
    assert "identity.name" in r1["applied_paths"] and r1["draft_spec"]["identity"]["name"] == "Aria"
    r2 = client.post(f"/api/architect/sessions/{sid}/chat", json={"message": TURN2}).json()
    assert r2["draft_spec"]["tools"] == ["lookup_order", "escalate_to_human"] and r2["request_upload"]
    assert r2["ready_to_finalize"] is False        # greeting still missing; backend decides, not the model
    assert "persona.greeting_message" in r2["missing_report"]["missing_required"]


def test_rejected_ops_are_reported_and_fed_back(client, llm):
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    llm.architect_queue.append({"reply_to_user": "ok", "ops": [
        {"op": "set", "path": "knowledge.collection_id", "value": "col_evil"},
        {"op": "set", "path": "identity.name", "value": "Zed"}]})
    r = client.post(f"/api/architect/sessions/{sid}/chat", json={"message": "hi"}).json()
    assert r["applied_paths"] == ["identity.name"] and r["rejected_ops"][0]["path"] == "knowledge.collection_id"
    llm.architect_queue.append({"reply_to_user": "next"})
    client.post(f"/api/architect/sessions/{sid}/chat", json={"message": "again"})
    architect_system = [c for c in llm.calls if c[0] == "architect"][-1][1]
    assert "REJECTED" in architect_system and "col_evil" in architect_system


def test_finalize_409_when_incomplete_and_defaults_409(client):
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    r = client.post(f"/api/architect/sessions/{sid}/finalize", json={})
    assert r.status_code == 409 and r.json()["missing_report"]["missing_required"]
    assert client.post(f"/api/architect/sessions/{sid}/fill-defaults").status_code == 409


def test_bad_inputs(client):
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    assert client.post(f"/api/architect/sessions/{sid}/chat", json={"message": ""}).status_code == 422
    r = client.post(f"/api/architect/sessions/{sid}/documents", files={"file": ("a.exe", b"x", "application/octet-stream")})
    assert r.status_code == 400
    r = client.post(f"/api/architect/sessions/{sid}/documents", files={"file": ("a.md", b"", "text/markdown")})
    assert r.status_code == 400


def test_loop_guard_text_after_many_turns(client, llm):
    sid = client.post("/api/architect/sessions", json={}).json()["session_id"]
    for _ in range(6):
        llm.architect_queue.append({"reply_to_user": "more?"})
        client.post(f"/api/architect/sessions/{sid}/chat", json={"message": "hmm"})
    llm.architect_queue.append({"reply_to_user": "more?"})
    client.post(f"/api/architect/sessions/{sid}/chat", json={"message": "hmm"})
    assert "LOOP GUARD" in [c for c in llm.calls if c[0] == "architect"][-1][1]
