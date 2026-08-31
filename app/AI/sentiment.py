from textblob import TextBlob
import numpy as np
from typing import Dict, List
import re

def analyze_sentiment_advanced(text: str) -> dict:
    """
    Advanced sentiment analysis with emotion detection
    Returns: sentiment score, label, and emotion breakdown
    """
    # Basic sentiment analysis
    analysis = TextBlob(text)
    sentiment_score = analysis.sentiment.polarity
    
    # Enhanced emotion detection
    emotions = detect_emotions(text)
    
    # Determine primary label with better thresholds
    if sentiment_score > 0.3:
        label = "very positive"
    elif sentiment_score > 0.1:
        label = "positive"
    elif sentiment_score > -0.1:
        label = "neutral"
    elif sentiment_score > -0.3:
        label = "negative"
    else:
        label = "very negative"
    
    # Calculate subjectivity
    subjectivity = analysis.sentiment.subjectivity

    # TextBlob does not expose a calibrated probability. Absolute polarity is
    # therefore labelled as strength, not confidence.
    sentiment_strength = min(1.0, abs(sentiment_score))
    
    # Detect key phrases
    key_phrases = extract_key_phrases(text)
    
    return {
        "sentiment_score": round(sentiment_score, 3),
        "sentiment_label": label,
        "subjectivity": round(subjectivity, 3),
        "sentiment_strength": round(sentiment_strength, 3),
        "analysis_confidence": None,
        "emotions": emotions,
        "key_phrases": key_phrases[:3],  # Top 3 phrases
        "word_count": len(text.split())
    }

def detect_emotions(text: str) -> Dict[str, float]:
    """
    Detect emotional content in text
    Returns dictionary of emotion scores (0-1)
    """
    text_lower = text.lower()
    emotions = {
        "joy": 0,
        "sadness": 0,
        "anger": 0,
        "fear": 0,
        "surprise": 0,
        "trust": 0,
        "anticipation": 0,
        "disgust": 0
    }
    
    # Emotion keyword dictionaries
    emotion_keywords = {
        "joy": ["happy", "joy", "excited", "great", "wonderful", "amazing", "love", "enjoy", "delighted"],
        "sadness": ["sad", "unhappy", "depressed", "lonely", "miserable", "grief", "sorrow", "tearful"],
        "anger": ["angry", "mad", "furious", "annoyed", "frustrated", "irritated", "rage", "outraged"],
        "fear": ["afraid", "scared", "fear", "worried", "anxious", "terrified", "nervous", "panic"],
        "surprise": ["surprised", "shocked", "amazed", "astonished", "unexpected", "wow"],
        "trust": ["trust", "confident", "secure", "reliable", "faith", "believe", "dependable"],
        "anticipation": ["excited", "expect", "anticipate", "look forward", "hope", "await", "eager"],
        "disgust": ["disgust", "dislike", "hate", "repulsed", "gross", "nasty", "awful"]
    }
    
    negations = {"no", "not", "never", "without", "hardly"}

    # Match whole words/phrases and ignore a nearby explicit negation.
    for emotion, keywords in emotion_keywords.items():
        count = 0
        for keyword in keywords:
            pattern = rf"\b{re.escape(keyword)}\b"
            for match in re.finditer(pattern, text_lower):
                prefix_words = re.findall(r"\b[\w']+\b", text_lower[max(0, match.start() - 35):match.start()])[-3:]
                if not negations.intersection(prefix_words):
                    count += 1
        emotions[emotion] = min(count / 5, 1.0)  # Normalize to 0-1
    
    return emotions

def extract_key_phrases(text: str) -> List[str]:
    """
    Extract key phrases from text
    """
    # Simple implementation - can be enhanced with NLP libraries
    sentences = re.split(r'[.!?]+', text)
    phrases = []
    
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence.split()) >= 3 and len(sentence.split()) <= 8:
            phrases.append(sentence.strip())
    
    return phrases[:5]

def analyze_emotion_trends(entries: List[Dict]) -> Dict:
    """
    Analyze emotion trends over time
    """
    if not entries:
        return {"trend": "insufficient_data"}
    
    # Calculate weekly averages
    sentiment_scores = [e.get("sentiment_score", 0) for e in entries]
    avg_sentiment = np.mean(sentiment_scores) if sentiment_scores else 0
    
    # Determine trend
    if len(sentiment_scores) >= 2:
        recent_avg = np.mean(sentiment_scores[-3:]) if len(sentiment_scores) >= 3 else sentiment_scores[-1]
        if recent_avg > avg_sentiment + 0.1:
            trend = "improving"
        elif recent_avg < avg_sentiment - 0.1:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"
    
    # Most common emotion
    all_emotions = {}
    for entry in entries:
        for emotion, score in entry.get("emotions", {}).items():
            all_emotions[emotion] = all_emotions.get(emotion, 0) + score
    
    dominant_emotion = max(all_emotions, key=all_emotions.get) if all_emotions else "neutral"
    
    return {
        "average_sentiment": round(avg_sentiment, 3),
        "trend": trend,
        "dominant_emotion": dominant_emotion,
        "entry_count": len(entries),
        "date_range": {
            "start": entries[0].get("created_at") if entries else None,
            "end": entries[-1].get("created_at") if entries else None
        }
    }

# Keep backward compatibility
def analyze_sentiment(text: str) -> dict:
    """Original function for backward compatibility"""
    result = analyze_sentiment_advanced(text)
    return {
        "sentiment_score": result["sentiment_score"],
        "sentiment_label": result["sentiment_label"]
    }
