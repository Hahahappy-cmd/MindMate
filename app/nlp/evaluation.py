from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sklearn.metrics import f1_score, precision_recall_fscore_support, precision_score, recall_score
from sklearn.preprocessing import MultiLabelBinarizer

from ..AI.sentiment import detect_emotions
from .emotion_model import EmotionAnalyzer

FIXTURE = Path(__file__).with_name("fixtures") / "emotion_eval.json"
SHARED_KEYWORD_LABELS = {"joy", "sadness", "anger", "fear", "surprise", "disgust"}


def _metrics(truth: list[list[str]], predicted: list[list[str]], labels: list[str]) -> dict[str, float]:
    encoder = MultiLabelBinarizer(classes=labels)
    encoder.fit([labels])
    y_true = encoder.transform(truth)
    y_pred = encoder.transform(predicted)
    _, _, per_label_f1, support = precision_recall_fscore_support(
        y_true, y_pred, average=None, zero_division=0
    )
    return {
        "micro_precision": round(precision_score(y_true, y_pred, average="micro", zero_division=0), 4),
        "micro_recall": round(recall_score(y_true, y_pred, average="micro", zero_division=0), 4),
        "micro_f1": round(f1_score(y_true, y_pred, average="micro", zero_division=0), 4),
        "macro_f1": round(f1_score(y_true, y_pred, average="macro", zero_division=0), 4),
        "per_label_f1": {
            label: {"f1": round(float(score), 4), "support": int(count)}
            for label, score, count in zip(labels, per_label_f1, support)
        },
    }


def evaluate(fixture: Path = FIXTURE, threshold: float = 0.5) -> dict[str, Any]:
    examples = json.loads(fixture.read_text())
    analyzer = EmotionAnalyzer(threshold=threshold)
    predicted = [list(analyzer.analyze(item["text"])["emotions"]) for item in examples]
    truth = [item["labels"] for item in examples]
    report: dict[str, Any] = {
        "dataset": str(fixture),
        "examples": len(examples),
        "threshold": threshold,
        "model": analyzer.model_name,
        "model_version": analyzer.model_version,
        "transformer": _metrics(truth, predicted, analyzer.labels),
    }

    comparable = [item for item in examples if set(item["labels"]) <= SHARED_KEYWORD_LABELS]
    keyword_predictions = []
    for item in comparable:
        scores = detect_emotions(item["text"])
        keyword_predictions.append([label for label in SHARED_KEYWORD_LABELS if scores.get(label, 0) > 0])
    report["keyword_baseline_shared_labels"] = {
        "note": "Partial comparison restricted to six labels shared by both systems.",
        "examples": len(comparable),
        **_metrics([item["labels"] for item in comparable], keyword_predictions, sorted(SHARED_KEYWORD_LABELS)),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate MindMate emotion classification")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.fixture, args.threshold), indent=2))


if __name__ == "__main__":
    main()
