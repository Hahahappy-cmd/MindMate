from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from typing import Any

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity

from ..config import settings

MIN_ENTRIES = 3
VALID_PERIODS = {"7": 7, "30": 30, "90": 90, "all": None}


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _emotions(entry: Any) -> dict[str, float]:
    if isinstance(entry.emotion_data, dict):
        return entry.emotion_data
    try:
        return json.loads(entry.emotion_data or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _bucket(value: datetime, weekly: bool) -> str:
    day = _naive_utc(value).date()
    if weekly:
        day -= timedelta(days=day.weekday())
    return day.isoformat()


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def filter_periods(entries: list[Any], period: str, now: datetime) -> tuple[list[Any], list[Any]]:
    if period not in VALID_PERIODS:
        raise ValueError("period must be one of: 7, 30, 90, all")
    days = VALID_PERIODS[period]
    ordered = sorted(entries, key=lambda entry: entry.created_at)
    if days is None:
        return ordered, []
    end = _naive_utc(now)
    start = end - timedelta(days=days)
    previous_start = start - timedelta(days=days)
    current = [entry for entry in ordered if entry.created_at and start <= _naive_utc(entry.created_at) <= end]
    previous = [entry for entry in ordered if entry.created_at and previous_start <= _naive_utc(entry.created_at) < start]
    return current, previous


def rolling_sentiment(entries: list[Any], window_days: int = 7) -> list[dict[str, Any]]:
    points = []
    scored = [entry for entry in entries if entry.sentiment_score is not None and entry.created_at]
    for entry in scored:
        cutoff = _naive_utc(entry.created_at) - timedelta(days=window_days)
        values = [other.sentiment_score for other in scored if cutoff < _naive_utc(other.created_at) <= _naive_utc(entry.created_at)]
        points.append({"date": entry.created_at.isoformat(), "score": entry.sentiment_score, "rolling_average": _average(values)})
    return points


def _comparison(current: list[Any], previous: list[Any]) -> dict[str, Any]:
    current_scores = [entry.sentiment_score for entry in current if entry.sentiment_score is not None]
    previous_scores = [entry.sentiment_score for entry in previous if entry.sentiment_score is not None]
    current_avg, previous_avg = _average(current_scores), _average(previous_scores)
    sentiment_change = round(current_avg - previous_avg, 4) if current_avg is not None and previous_avg is not None else None
    current_emotions = Counter(entry.dominant_emotion for entry in current if entry.dominant_emotion)
    previous_emotions = Counter(entry.dominant_emotion for entry in previous if entry.dominant_emotion)
    emotion_changes = {
        label: current_emotions[label] - previous_emotions[label]
        for label in sorted(current_emotions.keys() | previous_emotions.keys())
    }
    return {
        "available": bool(previous),
        "current_entries": len(current),
        "previous_entries": len(previous),
        "sentiment_change": sentiment_change,
        "entry_count_change": len(current) - len(previous) if previous else None,
        "dominant_emotion_count_changes": emotion_changes if previous else {},
    }


def group_themes(entries: list[Any]) -> list[dict[str, Any]]:
    embedded = []
    for entry in entries:
        try:
            vector = entry.theme_embedding if isinstance(entry.theme_embedding, list) else json.loads(entry.theme_embedding) if entry.theme_embedding else None
        except (TypeError, json.JSONDecodeError):
            vector = None
        if vector:
            embedded.append((entry, vector))
    if len(embedded) < 2:
        return []
    vectors = np.asarray([item[1] for item in embedded], dtype=float)
    labels = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=1 - settings.theme_similarity_threshold,
    ).fit_predict(vectors)
    groups: dict[int, list[int]] = defaultdict(list)
    for index, label in enumerate(labels):
        groups[int(label)].append(index)

    themes = []
    for indices in groups.values():
        if len(indices) < 2:
            continue
        cluster_vectors = vectors[indices]
        medoid_local = int(np.argmax(cosine_similarity(cluster_vectors).mean(axis=1)))
        representative = embedded[indices[medoid_local]][0]
        members = [embedded[index][0] for index in indices]
        scores = [entry.sentiment_score for entry in members if entry.sentiment_score is not None]
        emotions: Counter[str] = Counter()
        timeline: Counter[str] = Counter()
        for entry in members:
            emotions.update(_emotions(entry))
            timeline[_bucket(entry.created_at, weekly=True)] += 1
        themes.append({
            "label": representative.title,
            "representative_entry_id": representative.id,
            "frequency": len(members),
            "average_sentiment": _average(scores),
            "top_emotions": dict(emotions.most_common(3)),
            "entry_ids": [entry.id for entry in members],
            "frequency_over_time": [{"date": date, "count": count} for date, count in sorted(timeline.items())],
        })
    return sorted(themes, key=lambda theme: (-theme["frequency"], theme["label"].lower()))


def build_long_term_analytics(entries: list[Any], period: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    current, previous = filter_periods(entries, period, now)
    enough = len(current) >= MIN_ENTRIES
    weekly = period in {"90", "all"}
    scores = [entry.sentiment_score for entry in current if entry.sentiment_score is not None]
    dominant = Counter(entry.dominant_emotion for entry in current if entry.dominant_emotion)
    emotion_totals: Counter[str] = Counter()
    emotion_timeline: dict[str, Counter[str]] = defaultdict(Counter)
    frequency: Counter[str] = Counter()
    weekdays: dict[int, list[float]] = defaultdict(list)
    for entry in current:
        bucket = _bucket(entry.created_at, weekly)
        frequency[bucket] += 1
        if entry.sentiment_score is not None:
            weekdays[_naive_utc(entry.created_at).weekday()].append(entry.sentiment_score)
        for label, score in _emotions(entry).items():
            emotion_totals[label] += score
            emotion_timeline[bucket][label] += score

    rolling = rolling_sentiment(current)
    trend = "insufficient_data"
    if enough and len(rolling) >= 3:
        slope = float(np.polyfit(range(len(rolling)), [point["rolling_average"] for point in rolling], 1)[0])
        trend = "improving" if slope > 0.02 else "declining" if slope < -0.02 else "stable"
    comparison = _comparison(current, previous)
    themes = group_themes(current) if enough else []
    insights: list[str] = []
    if enough:
        if comparison["sentiment_change"] is not None:
            direction = "increased" if comparison["sentiment_change"] > 0 else "decreased" if comparison["sentiment_change"] < 0 else "was unchanged"
            insights.append(f"Average sentiment {direction} by {abs(comparison['sentiment_change']):.2f} compared with the previous {period}-day period.")
        if dominant:
            label, count = dominant.most_common(1)[0]
            insights.append(f"{label.capitalize()} was the most frequent dominant emotion, appearing in {count} of {len(current)} entries.")
        changed_emotions = comparison["dominant_emotion_count_changes"]
        if changed_emotions:
            label, change = max(changed_emotions.items(), key=lambda item: (abs(item[1]), item[0]))
            if change:
                direction = "increased" if change > 0 else "decreased"
                insights.append(f"Entries with {label} as the dominant emotion {direction} by {abs(change)} compared with the previous period.")
        for theme in themes[:3]:
            sentiment = theme["average_sentiment"]
            sentiment_text = "no sentiment score" if sentiment is None else f"an average sentiment of {sentiment:+.2f}"
            insights.append(f"The recurring theme “{theme['label']}” appeared {theme['frequency']} times and had {sentiment_text}.")

    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return {
        "period": period,
        "period_days": VALID_PERIODS[period],
        "status": "ready" if enough else "insufficient_data",
        "minimum_entries": MIN_ENTRIES,
        "total_entries": len(current),
        "average_sentiment": _average(scores),
        "sentiment_trend": trend,
        "rolling_sentiment": rolling,
        "comparison": comparison,
        "dominant_emotions": [{"emotion": label, "count": count} for label, count in dominant.most_common()],
        "emotion_distribution": {label: round(score, 4) for label, score in emotion_totals.most_common()},
        "emotion_over_time": [{"date": date, "emotions": {k: round(v, 4) for k, v in values.items()}} for date, values in sorted(emotion_timeline.items())],
        "sentiment_by_weekday": [{"weekday": name, "average": _average(weekdays[index]), "entries": len(weekdays[index])} for index, name in enumerate(weekday_names)],
        "entry_frequency": [{"date": date, "count": count} for date, count in sorted(frequency.items())],
        "themes": themes,
        "insights": insights,
    }
