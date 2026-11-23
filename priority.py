"""Transparent priority score  P = 0.35U + 0.25D + 0.30W + 0.10T  (scaled to 0-100)."""
from datetime import date

DIFFICULTY = {"Easy": 0.33, "Medium": 0.67, "Hard": 1.0}
NEUTRAL_QUIZ = 50.0            # used when no quiz exists: "unknown", not "weak"

def urgency(today: date, exam: date) -> float:
    return 1.0 / (1 + max((exam - today).days, 0))

def weakness(scores):
    avg = sum(scores) / len(scores) if scores else NEUTRAL_QUIZ
    return 1 - avg / 100.0

def time_pressure(remaining_min, today, exam, daily_min):
    capacity = max((exam - today).days + 1, 1) * daily_min
    return min(1.0, remaining_min / capacity)

def calculate_priority(u, d, w, t):
    return round((0.35 * u + 0.25 * d + 0.30 * w + 0.10 * t) * 100, 2)

def topic_priority(topic, today, exam, daily_min, scores=()):
    return calculate_priority(
        urgency(today, exam), DIFFICULTY[topic["difficulty"]],
        weakness(list(scores)), time_pressure(topic["remaining"], today, exam, daily_min))
