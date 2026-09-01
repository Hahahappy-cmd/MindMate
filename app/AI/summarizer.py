from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import json

def generate_weekly_summary(entries: List[Dict]) -> Dict[str, Any]:
    """
    Generate a weekly summary from journal entries
    """
    if not entries:
        return {
            "summary": "No entries this week.",
            "statistics": {
                "total_entries": 0,
                "average_sentiment": 0.0,
                "dominant_emotions": [],
                "date_range": {"start": None, "end": None},
            },
            "insights": [],
            "recommendations": ["Write your first entry to begin tracking patterns."]
        }
    
    # Sort entries by date
    entries_sorted = sorted(entries, key=lambda x: x.get('created_at', ''))
    
    # Calculate statistics
    sentiment_scores = [e.get('sentiment_score', 0) for e in entries_sorted]
    avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
    
    # Emotion analysis
    all_emotions = {}
    for entry in entries_sorted:
        emotion_data = entry.get('emotion_data')
        if emotion_data:
            try:
                emotions = emotion_data if isinstance(emotion_data, dict) else json.loads(emotion_data)
                for emotion, score in emotions.items():
                    all_emotions[emotion] = all_emotions.get(emotion, 0) + score
            except (TypeError, json.JSONDecodeError):
                pass
    
    # Find dominant emotions
    dominant_emotions = sorted(all_emotions.items(), key=lambda x: x[1], reverse=True)[:3]
    
    # Generate insights
    insights = generate_insights(entries_sorted, avg_sentiment, dominant_emotions)
    
    # Generate recommendations
    recommendations = generate_recommendations(avg_sentiment, dominant_emotions)
    
    # Create summary text
    summary = create_summary_text(len(entries_sorted), avg_sentiment, dominant_emotions)
    
    return {
        "summary": summary,
        "statistics": {
            "total_entries": len(entries_sorted),
            "average_sentiment": round(avg_sentiment, 3),
            "dominant_emotions": dominant_emotions,
            "date_range": {
                "start": entries_sorted[0].get('created_at'),
                "end": entries_sorted[-1].get('created_at')
            }
        },
        "insights": insights,
        "recommendations": recommendations
    }

def generate_insights(entries: List[Dict], avg_sentiment: float, dominant_emotions: List) -> List[str]:
    """Generate insights from entries"""
    insights = []
    
    # Sentiment insight
    if avg_sentiment > 0.3:
        insights.append("The language in your entries was strongly positive this week.")
    elif avg_sentiment > 0.1:
        insights.append("The language in your entries leaned positive this week.")
    elif avg_sentiment > -0.1:
        insights.append("The language in your entries was generally neutral this week.")
    elif avg_sentiment > -0.3:
        insights.append("The language in your entries leaned negative this week.")
    else:
        insights.append("The language in your entries was strongly negative this week.")
    
    # Entry frequency insight
    if len(entries) >= 7:
        insights.append("Great consistency! You journaled every day this week.")
    elif len(entries) >= 5:
        insights.append("Good journaling habit! You wrote most days this week.")
    elif len(entries) >= 3:
        insights.append("You're building a good journaling routine.")
    else:
        insights.append("Consider journaling more regularly to track your progress.")
    
    # Emotion insight
    if dominant_emotions:
        top_emotion, score = dominant_emotions[0]
        if score > 0.5:
            insights.append(f"{top_emotion.capitalize()} was a prominent emotion for you this week.")
    
    return insights

def generate_recommendations(avg_sentiment: float, dominant_emotions: List) -> List[str]:
    """Generate personalized recommendations"""
    recommendations = []
    
    # Based on sentiment
    if avg_sentiment < -0.2:
        recommendations.append("Consider practicing gratitude by listing 3 things you're thankful for each day.")
        recommendations.append("Try mindfulness meditation to help manage challenging emotions.")
    
    # Based on dominant emotions
    if dominant_emotions:
        top_emotion, _ = dominant_emotions[0]
        if top_emotion in ["sadness", "anger", "fear"]:
            recommendations.append(f"To address {top_emotion}, try talking to a friend or engaging in a favorite activity.")
        elif top_emotion == "joy":
            recommendations.append("Your positive energy is great! Consider sharing it with others.")
    
    # General recommendations
    recommendations.append("Continue your journaling practice - it's a valuable tool for self-reflection.")
    recommendations.append("Try adding more detail to your entries to gain deeper insights.")
    
    return recommendations[:3]  # Limit to 3 recommendations

def create_summary_text(entry_count: int, avg_sentiment: float, dominant_emotions: List) -> str:
    """Create a natural language summary"""
    if entry_count == 0:
        return "No entries this week to summarize."
    
    sentiment_desc = "positive" if avg_sentiment > 0.1 else "neutral" if avg_sentiment > -0.1 else "challenging"
    
    if dominant_emotions:
        emotion_desc = ", ".join([e[0] for e in dominant_emotions[:2]])
    else:
        emotion_desc = "various emotions"
    
    return f"This week, you wrote {entry_count} journal entries. Their overall sentiment was {sentiment_desc}, with signals of {emotion_desc} appearing in the writing."

def get_last_week_dates() -> tuple:
    """Get date range for the last week"""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)
    return start_date, end_date
