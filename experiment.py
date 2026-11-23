import random, statistics as st, json
from datetime import date, timedelta
from modules import dependencies, scheduler
TODAY = date(2026, 11, 16)
def instance(rng):
    nsub = 5; topics = {}; exams = {}; g = dependencies.PrereqGraph(); order = []
    subs = [f"S{i}" for i in range(nsub)]
    exam_days = rng.sample(range(6, 20), nsub)
    for s, ed in zip(subs, exam_days):
        exams[s] = TODAY + timedelta(days=ed)
        n = rng.randint(3, 5); names = [f"{s}-T{j}" for j in range(n)]
        for nm in names:
            topics[nm] = {"subject": s, "minutes": rng.choice([60, 90, 120]), "difficulty": rng.choice(["Easy", "Medium", "Hard"])}
            g.add_topic(nm)
        for j in range(1, n):                       # chain with some branching
            g.add_dependency(names[rng.randint(0, j - 1)], names[j])
    items = list(topics.items()); rng.shuffle(items)   # entry order is arbitrary
    topics = dict(items)
    scores = {t: [rng.randint(20, 95)] for t in topics if rng.random() < 0.6}
    return topics, exams, g, scores
res = {"smart": [], "base": []}
for seed in range(200):
    rng = random.Random(seed)
    topics, exams, g, scores = instance(rng)
    for daily in (180,):
        a = scheduler.generate(topics, g, exams, scores, TODAY, 21, daily)
        b = scheduler.baseline(topics, exams, TODAY, 21, daily)
        for k, s in (("smart", a), ("base", b)):
            m = scheduler.metrics(s, topics, g, exams, daily, 21, TODAY)
            res[k].append((m["coverage"], m["violations"], m["over_budget_days"], st.pstdev([x for x in m["per_day"] if x > 0] or [0])))
out = {}
for k, v in res.items():
    out[k] = {"coverage": round(100 * st.mean(x[0] for x in v), 1), "violations": round(st.mean(x[1] for x in v), 2),
              "over": sum(x[2] for x in v), "total_viol": sum(x[1] for x in v)}
print(json.dumps(out, indent=1))
# worked example with sample data
import tests.test_scheduler as T
topics, exams, g = T.sample()
s = scheduler.generate(topics, g, exams, {"Normalization": [35]}, TODAY, 14, 180)
for x in s[:8]: print(x["day"], x["slot"], x["topic"], x["minutes"])
print("order", g.order())
new, un = __import__("modules.rescheduler", fromlist=["x"]).reschedule(s, [0], topics, g, exams, TODAY, 180)
print("moved:", [(x["day"].isoformat(), x["slot"], x["topic"]) for x in new if x.get("moved")], "unplaced", len(un))
try: g.add_dependency("Normalization", "DBMS Fundamentals")
except Exception as e: print(e)
