from datetime import datetime, timezone
from typing import Any

from ..AI.sentiment import analyze_sentiment_advanced
from ..AI.summarizer import generate_weekly_summary
from ..nlp.emotion_model import EmotionModelError, analyze_emotions

FALLBACK_MODEL = "mindmate-keyword-fallback"
FALLBACK_VERSION = "1.0"


def analyze_entry(content: str) -> dict[str, Any]:
    result = analyze_sentiment_advanced(content)
    try:
        emotion_result = analyze_emotions(content)
        scored_emotions = emotion_result["emotions"]
        dominant_emotion = emotion_result["dominant_emotion"]
        emotional_intensity = scored_emotions.get(dominant_emotion)
        analysis_confidence = emotional_intensity
    except EmotionModelError:
        # Keep journal creation available when model files/runtime are unavailable,
        # but label the legacy result explicitly so it cannot be mistaken for ML.
        scored_emotions = result.get("emotions", {})
        ranked = sorted(scored_emotions.items(), key=lambda item: (-item[1], item[0]))
        dominant_emotion = ranked[0][0] if ranked and ranked[0][1] > 0 else None
        emotional_intensity = ranked[0][1] if dominant_emotion else None
        analysis_confidence = None
        emotion_result = {
            "model_name": FALLBACK_MODEL,
            "model_version": FALLBACK_VERSION,
            "analysis_method": "keyword_fallback",
            "score_semantics": "keyword_match_density",
            "threshold": None,
            "chunks_analyzed": None,
        }
    result.update(
        {
            "emotions": scored_emotions,
            "analysis_confidence": analysis_confidence,
            "analysis_method": emotion_result["analysis_method"],
            "analysis_version": emotion_result["model_version"],
            "analyzed_at": datetime.now(timezone.utc),
            "dominant_emotion": dominant_emotion,
            "emotional_intensity": round(emotional_intensity, 6) if emotional_intensity is not None else None,
            "emotion_model_name": emotion_result["model_name"],
            "emotion_model_version": emotion_result["model_version"],
            "emotion_score_semantics": emotion_result["score_semantics"],
            "emotion_threshold": emotion_result["threshold"],
            "emotion_chunks": emotion_result["chunks_analyzed"],
        }
    )
    return result


def summarize_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return generate_weekly_summary(entries)
