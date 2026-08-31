from app.AI.sentiment import analyze_sentiment_advanced
from app.AI.summarizer import generate_weekly_summary


def test_empty_weekly_summary(client, auth_headers):
    data = client.get("/api/entries/weekly-summary", headers=auth_headers).json()
    assert data["statistics"]["total_entries"] == 0
    assert data["summary"] == "No entries this week."


def test_dashboard_uses_ai_sentiment_and_emotions(client, auth_headers, run_pending_analysis):
    entry_id = client.post("/api/entries/", headers=auth_headers, json={"title":"Good day","content":"I feel happy and wonderful."}).json()["id"]
    run_pending_analysis(entry_id)
    data = client.get("/api/entries/dashboard", headers=auth_headers).json()
    assert data["total_entries"] == 1
    assert data["average_sentiment"] > 0
    assert data["dominant_emotion_over_time"][0]["emotion"] == "joy"


def test_sentiment_and_emotion_analysis():
    data = analyze_sentiment_advanced("I am happy, excited, and hopeful about tomorrow.")
    assert data["sentiment_score"] > 0
    assert data["emotions"]["joy"] > 0
    assert data["analysis_confidence"] is None
    assert 0 <= data["sentiment_strength"] <= 1


def test_negated_emotion_keyword_is_not_counted():
    data = analyze_sentiment_advanced("I am not happy about what happened.")
    assert data["emotions"]["joy"] == 0


def test_summary_statistics_are_structured():
    result = generate_weekly_summary([{"created_at":"2026-01-01","sentiment_score":0.5,"emotion_data":"{\"joy\": 0.6}"}])
    assert result["statistics"]["total_entries"] == 1
