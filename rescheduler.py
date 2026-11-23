"""Greedy rescheduling of missed sessions into the earliest suitable free slot."""
from datetime import timedelta

def reschedule(sessions, missed_idx, topics, graph, exams, today, daily_min, block=45, brk=0, horizon=60):
    for i in missed_idx:
        sessions[i]["status"] = "missed"
    pending = [s for s in sessions if s["status"] == "missed"]
    kept = [s for s in sessions if s["status"] != "missed"]
    pending.sort(key=lambda s: exams[topics[s["topic"]]["subject"]])      # earliest deadline first
    unplaced, placed = [], []
    for s in pending:
        t = s["topic"]; exam = exams[topics[t]["subject"]]
        dep_first = [(x["day"], x["slot"]) for x in kept + placed if x["topic"] in graph.dependents(t)
                     and x["status"] == "planned"]
        pre_last = [(x["day"], x["slot"]) for x in kept + placed if x["topic"] in graph.prerequisites(t)
                    and x["status"] == "planned"]
        lo = max(pre_last) if pre_last else (today, -1)
        hi = min(dep_first) if dep_first else (exam, 10**6)
        spot = None
        for d in range(horizon):
            day = today + timedelta(days=d)
            if day > exam: break
            used = sum(x["minutes"] + brk for x in kept + placed if x["day"] == day and x["status"] != "missed")
            if daily_min - used < s["minutes"] + brk:
                continue
            slot = 1 + max([x["slot"] for x in kept + placed if x["day"] == day] + [-1])
            if (day, slot) > lo and (day, slot) < hi:
                spot = (day, slot); break
        if spot:
            placed.append({**s, "day": spot[0], "slot": spot[1], "status": "planned", "moved": True})
        else:
            unplaced.append(s)
    return kept + placed, unplaced
