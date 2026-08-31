from datetime import datetime, timezone
from typing import Any

from ..AI.sentiment import analyze_sentiment_advanced
from ..AI.summarizer import generate_weekly_summary

ANALYSIS_METHOD = "textblob-keyword"
ANALYSIS_VERSION = "1.0"


def analyze_entry(content: str) -> dict[str, Any]:
    result = analyze_sentiment_advanced(content)
    scored_emotions = result.get("emotions", {})
    dominant_emotion = None
    emotional_intensity = 0.0
    if scored_emotions:
        name, score = max(scored_emotions.items(), key=lambda item: item[1])
        if score > 0:
            dominant_emotion = name
            emotional_intensity = score
    result.update(
        {
            "analysis_method": ANALYSIS_METHOD,
            "analysis_version": ANALYSIS_VERSION,
            "analyzed_at": datetime.now(timezone.utc),
            "dominant_emotion": dominant_emotion,
            # Keyword-match density, not a model probability/confidence.
            "emotional_intensity": round(emotional_intensity, 3),
        }
    )
    return result


def summarize_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return generate_weekly_summary(entries)
