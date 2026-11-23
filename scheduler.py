"""Greedy, priority-driven timetable generator that respects prerequisites and exam dates."""
from datetime import timedelta
from priority import topic_priority

def generate(topics, graph, exams, scores, start, days, daily_min, block=45, brk=0):
    """topics: {name: {subject, minutes, difficulty}}; exams: {subject: date};
    scores: {topic: [quiz %]}.  Returns list of sessions (dicts)."""
    remaining = {t: v["minutes"] for t, v in topics.items()}
    finished = set()
    sessions = []
    for d in range(days):
        day = start + timedelta(days=d)
        budget, slot = daily_min, 0
        while budget >= block:
            eligible = [t for t in remaining
                        if remaining[t] > 0 and day <= exams[topics[t]["subject"]]
                        and graph.prerequisites(t) <= finished]
            if not eligible:
                break
            best = max(eligible, key=lambda t: topic_priority(
                {"difficulty": topics[t]["difficulty"], "remaining": remaining[t]},
                day, exams[topics[t]["subject"]], daily_min, scores.get(t, [])))
            m = min(block, remaining[best])
            sessions.append({"topic": best, "day": day, "slot": slot, "minutes": m, "status": "planned"})
            remaining[best] -= m
            if remaining[best] == 0:
                finished.add(best)
            budget -= m + brk
            slot += 1
    return sessions

def baseline(topics, exams, start, days, daily_min, block=45, brk=0):
    """Naive scheduler: topics in the order they were entered; ignores exam dates and prerequisites."""
    remaining = {t: v["minutes"] for t, v in topics.items()}
    queue, sessions = list(topics), []
    for d in range(days):
        day = start + timedelta(days=d)
        budget, slot = daily_min, 0
        while budget >= block and queue:
            t = queue[0]
            m = min(block, remaining[t])
            sessions.append({"topic": t, "day": day, "slot": slot, "minutes": m, "status": "planned"})
            remaining[t] -= m
            if remaining[t] == 0:
                queue.pop(0)
            budget -= m + brk
            slot += 1
    return sessions

def metrics(sessions, topics, graph, exams, daily_min, days, start):
    done_minutes, last_day, first_day = {}, {}, {}
    for s in sessions:
        done_minutes[s["topic"]] = done_minutes.get(s["topic"], 0) + s["minutes"]
        last_day[s["topic"]] = max(last_day.get(s["topic"], s["day"]), s["day"])
        first_day[s["topic"]] = min(first_day.get(s["topic"], s["day"]), s["day"])
    covered = [t for t in topics if done_minutes.get(t, 0) >= topics[t]["minutes"]
               and last_day[t] <= exams[topics[t]["subject"]]]
    viol = sum(1 for t in topics for p in graph.prerequisites(t)
               if t in first_day and (p not in last_day or first_day[t] < last_day[p]))
    per_day = [sum(s["minutes"] for s in sessions if s["day"] == start + timedelta(days=i)) for i in range(days)]
    over = sum(1 for x in per_day if x > daily_min)
    return {"coverage": len(covered) / len(topics), "violations": viol, "over_budget_days": over,
            "per_day": per_day}
