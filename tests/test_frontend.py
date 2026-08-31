def login_cookie(client):
    client.post("/register", data={"username":"webuser","email":"web@example.com","password":"web-password","confirm_password":"web-password"})
    response = client.post("/login", data={"username":"webuser","password":"web-password"}, follow_redirects=False)
    assert response.status_code == 303


def test_public_pages_render(client):
    assert client.get("/").status_code == 200
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200


def test_authenticated_pages_render(client):
    login_cookie(client)
    for path in ["/dashboard", "/journal", "/weekly-summary", "/profile", "/settings"]:
        assert client.get(path).status_code == 200


def test_cookie_mutation_requires_csrf(client):
    login_cookie(client)
    client.cookies.delete("csrf_token")
    response = client.post("/api/entries/", json={"title":"Blocked","content":"No CSRF"})
    assert response.status_code == 403


def test_cookie_mutation_rejects_mismatched_csrf(client):
    login_cookie(client)
    response = client.post(
        "/api/entries/",
        headers={"X-CSRF-Token": "wrong-token"},
        json={"title": "Blocked", "content": "Mismatched CSRF"},
    )
    assert response.status_code == 403


def test_journal_content_is_escaped_by_frontend(client):
    source = client.get("/static/js/app.js").text
    assert "function escapeHtml" in source
    assert "async function csrfFetch" in source
    journal = client.get("/journal", follow_redirects=False)
    assert journal.status_code in {302, 307}


def test_journal_mutations_use_explicit_csrf_helper(client):
    login_cookie(client)
    source = client.get("/journal").text
    assert "csrfFetch('/api/entries/'" in source
    csrf = client.cookies.get("csrf_token")
    created = client.post(
        "/api/entries/",
        headers={"X-CSRF-Token": csrf},
        json={"title": "Detail", "content": "Test detail actions."},
    ).json()
    detail = client.get(f"/journal/{created['id']}").text
    assert "csrfFetch(`/api/entries/${entryId}`" in detail


def test_complete_browser_session_flow(client):
    login_cookie(client)
    csrf = client.cookies.get("csrf_token")
    headers = {"X-CSRF-Token": csrf}
    created = client.post("/api/entries/", headers=headers, json={
        "title": "Browser entry",
        "content": "I feel calm and hopeful.",
    })
    assert created.status_code == 201
    entry_id = created.json()["id"]
    assert client.get(f"/journal/{entry_id}").status_code == 200
    edited = client.put(f"/api/entries/{entry_id}", headers=headers, json={"title": "Edited browser entry"})
    assert edited.status_code == 200
    assert client.get("/api/entries/dashboard").json()["total_entries"] == 1
    assert client.get("/api/entries/weekly-summary").json()["statistics"]["total_entries"] == 1
    assert client.delete(f"/api/entries/{entry_id}", headers=headers).status_code == 204

    persistent = client.post("/api/entries/", headers=headers, json={"title": "Persistent", "content": "This should survive another login."})
    assert persistent.status_code == 201
    logout = client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
    assert logout.status_code == 303
    assert client.get("/dashboard", follow_redirects=False).status_code in {302, 307}
    relogin = client.post("/login", data={"username":"webuser","password":"web-password"}, follow_redirects=False)
    assert relogin.status_code == 303
    titles = [entry["title"] for entry in client.get("/api/entries/").json()]
    assert titles == ["Persistent"]
