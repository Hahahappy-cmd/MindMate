from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from app.models import JournalEntry
from app.services.long_term_analytics import build_long_term_analytics, group_themes, rolling_sentiment


NOW = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)


def entry(identifier, days_ago, sentiment, emotion="joy", vector=None, title="School notes"):
    return SimpleNamespace(
        id=identifier,
        title=title,
        created_at=(NOW - timedelta(days=days_ago)).replace(tzinfo=None),
        sentiment_score=sentiment,
        dominant_emotion=emotion,
        emotion_data=json.dumps({emotion: 0.8}),
        theme_embedding=json.dumps(vector) if vector else None,
    )


def test_period_filtering_and_previous_period_comparison():
    entries = [entry(1, 2, 0.6), entry(2, 5, 0.4), entry(3, 6, 0.2), entry(4, 9, -0.4)]
    result = build_long_term_analytics(entries, "7", NOW)
    assert result["total_entries"] == 3
    assert result["comparison"]["previous_entries"] == 1
    assert result["comparison"]["sentiment_change"] == 0.8


@pytest.mark.parametrize(("period", "expected"), [("7", 1), ("30", 2), ("90", 3), ("all", 4)])
def test_supported_period_windows(period, expected):
    entries = [entry(1, 2, 0.1), entry(2, 20, 0.2), entry(3, 60, 0.3), entry(4, 120, 0.4)]
    assert build_long_term_analytics(entries, period, NOW)["total_entries"] == expected


def test_rolling_average_uses_calendar_window():
    points = rolling_sentiment([entry(1, 10, -0.5), entry(2, 5, 0.5), entry(3, 0, 1.0)])
    assert points[-1]["rolling_average"] == 0.75


def test_emotion_aggregation_weekdays_and_frequency():
    entries = [entry(1, 2, 0.5, "joy"), entry(2, 1, -0.5, "sadness"), entry(3, 0, 0.25, "joy")]
    result = build_long_term_analytics(entries, "30", NOW)
    assert result["emotion_distribution"] == {"joy": 1.6, "sadness": 0.8}
    assert result["dominant_emotions"][0] == {"emotion": "joy", "count": 2}
    assert sum(item["count"] for item in result["entry_frequency"]) == 3
    assert sum(item["entries"] for item in result["sentiment_by_weekday"]) == 3


def test_semantic_theme_grouping_and_sentiment_aggregation():
    entries = [
        entry(1, 3, -0.5, vector=[1, 0], title="Exam preparation"),
        entry(2, 2, -0.3, vector=[0.99, 0.01], title="School deadline"),
        entry(3, 1, 0.8, vector=[0, 1], title="Weekend walk"),
    ]
    themes = group_themes(entries)
    assert len(themes) == 1
    assert themes[0]["frequency"] == 2
    assert themes[0]["average_sentiment"] == -0.4
    assert themes[0]["label"] in {"Exam preparation", "School deadline"}


def test_insufficient_data_does_not_invent_insights_or_themes():
    result = build_long_term_analytics([entry(1, 0, 0.2)], "30", NOW)
    assert result["status"] == "insufficient_data"
    assert result["sentiment_trend"] == "insufficient_data"
    assert result["insights"] == []
    assert result["themes"] == []


def test_long_term_api_and_embedding_cache(client, auth_headers, db_session, run_pending_analysis):
    for title, content in [("School exam", "Preparing for my school exam."), ("Study plan", "More school study."), ("Class notes", "My school class went well.")]:
        created = client.post("/api/entries/", headers=auth_headers, json={"title": title, "content": content})
        assert created.status_code == 201
        run_pending_analysis(created.json()["id"])
    response = client.get("/api/entries/long-term-analytics?period=30", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["themes"][0]["frequency"] == 3
    assert all(row[0] for row in db_session.query(JournalEntry.theme_embedding).all())
    assert client.get("/api/entries/long-term-analytics?period=invalid", headers=auth_headers).status_code == 422
