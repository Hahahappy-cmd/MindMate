def create_entry(client, headers, title="A day", content="I feel happy and hopeful today."):
    return client.post("/api/entries/", headers=headers, json={"title": title, "content": content})


def test_entry_crud(client, auth_headers, run_pending_analysis):
    created = create_entry(client, auth_headers)
    assert created.status_code == 201
    entry = created.json()
    assert entry["analysis_state"] == "pending"
    assert entry["sentiment_label"] is None
    run_pending_analysis(entry["id"])
    entry = client.get(f"/api/entries/{entry['id']}", headers=auth_headers).json()
    assert entry["sentiment_label"] in {"positive", "very positive"}
    assert entry["detected_emotions"]["joy"] > 0
    assert entry["dominant_emotion"] == "joy"
    assert entry["analysis_confidence"] == 0.82
    assert entry["emotion_score_semantics"] == "sigmoid_probability"
    assert entry["emotion_model_name"] == "test/go-emotions"
    entry_id = entry["id"]
    assert client.get(f"/api/entries/{entry_id}", headers=auth_headers).status_code == 200
    updated = client.put(f"/api/entries/{entry_id}", headers=auth_headers, json={"title": "Updated"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated"
    assert updated.json()["analysis_state"] == "pending"
    assert client.delete(f"/api/entries/{entry_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/entries/{entry_id}", headers=auth_headers).status_code == 404


def test_entry_validation(client, auth_headers):
    assert client.post("/api/entries/", headers=auth_headers, json={"title": "", "content": ""}).status_code == 422
    assert client.post("/api/entries/", headers=auth_headers, json={"title": "A", "content": "B", "user_mood": "happy"}).status_code == 422


def test_users_cannot_access_each_others_entries(client, auth_headers):
    entry_id = create_entry(client, auth_headers).json()["id"]
    client.post("/api/users/register", json={"email":"sam@example.com","username":"sam","password":"another-pass"})
    token = client.post("/api/users/login", json={"username":"sam","password":"another-pass"}).json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}
    assert client.get(f"/api/entries/{entry_id}", headers=other).status_code == 404
    assert client.put(f"/api/entries/{entry_id}", headers=other, json={"title":"stolen"}).status_code == 404
    assert client.delete(f"/api/entries/{entry_id}", headers=other).status_code == 404


def test_named_routes_are_not_shadowed(client, auth_headers):
    assert client.get("/api/entries/weekly-summary", headers=auth_headers).status_code == 200
    assert client.get("/api/entries/emotion-trends", headers=auth_headers).status_code == 200
    assert client.get("/api/entries/dashboard", headers=auth_headers).status_code == 200


def test_current_user_response_includes_enhanced_entries(client, auth_headers, run_pending_analysis):
    entry_id = create_entry(client, auth_headers).json()["id"]
    run_pending_analysis(entry_id)
    response = client.get("/api/users/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["entries"][0]["detected_emotions"]["joy"] > 0
