"""Glue between SQLite and the planning engine (no Streamlit code, so it is testable)."""
from datetime import date, datetime, timedelta
import dependencies
import scheduler
import rescheduler
import priority

def d2s(d): return d.isoformat()
def s2d(s): return date.fromisoformat(s)

# ---------- basic CRUD
def add_subject(con, name, exam):
    con.execute("INSERT INTO subjects(name, exam_date) VALUES(?,?)", (name.strip(), d2s(exam))); con.commit()

def add_topic(con, subject_id, name, minutes, difficulty):
    con.execute("INSERT INTO topics(subject_id,name,duration,difficulty) VALUES(?,?,?,?)",
                (subject_id, name.strip(), int(minutes), difficulty)); con.commit()

def subjects(con): return con.execute("SELECT id,name,exam_date FROM subjects ORDER BY exam_date").fetchall()
def topics(con):
    return con.execute("""SELECT t.id,t.name,s.name,s.exam_date,t.duration,t.difficulty,t.status
                          FROM topics t JOIN subjects s ON s.id=t.subject_id ORDER BY s.exam_date,t.id""").fetchall()

def full_name(con, tid):
    return con.execute("SELECT s.name||' - '||t.name FROM topics t JOIN subjects s ON s.id=t.subject_id WHERE t.id=?", (tid,)).fetchone()[0]

def build_graph(con, only_pending=False):
    g = dependencies.PrereqGraph()
    ok = {r[0] for r in con.execute("SELECT id FROM topics" + (" WHERE status='pending'" if only_pending else ""))}
    for t in ok: g.add_topic(t)
    for t, p in con.execute("SELECT topic_id, prerequisite_id FROM dependencies"):
        if t in ok and p in ok: g.add_dependency(p, t)
    return g

def add_dependency(con, topic_id, prereq_id):
    """Returns (True, msg) or (False, reason). Cycles are rejected by the graph."""
    if topic_id == prereq_id:
        return False, "A topic cannot be its own prerequisite."
    g = build_graph(con)
    try:
        g.add_dependency(prereq_id, topic_id)
    except dependencies.CycleError:
        names = " -> ".join(full_name(con, n) for n in _cycle_path(g, prereq_id, topic_id))
        return False, "Rejected: this creates a circular dependency (%s)." % names
    con.execute("INSERT OR IGNORE INTO dependencies VALUES(?,?)", (topic_id, prereq_id)); con.commit()
    return True, "Prerequisite added."

def _cycle_path(g, prereq_id, topic_id):
    """Path topic -> ... -> prereq (already in the graph) closed by the rejected edge."""
    path = dependencies.nx.shortest_path(g.g, topic_id, prereq_id)
    return path + [topic_id]

def set_topic_done(con, tid, done=True):
    con.execute("UPDATE topics SET status=? WHERE id=?", ("done" if done else "pending", tid)); con.commit()

def add_quiz(con, tid, score, qdate):
    con.execute("INSERT INTO quiz_results(topic_id,score,quiz_date) VALUES(?,?,?)", (tid, float(score), d2s(qdate))); con.commit()

def quiz_scores(con):
    out = {}
    for tid, sc in con.execute("SELECT topic_id, score FROM quiz_results ORDER BY quiz_date"):
        out.setdefault(tid, []).append(sc)
    return out

def add_task(con, title, deadline, minutes):
    con.execute("INSERT INTO tasks(title,deadline,duration) VALUES(?,?,?)", (title.strip(), d2s(deadline), int(minutes))); con.commit()

# ---------- planning
def generate_plan(con, start, daily_min, block, days=30):
    g = build_graph(con, only_pending=True)
    tp = {}
    exams = {}
    for tid, name, sname, exam, dur, diff, status in topics(con):
        if status == "pending":
            done = con.execute("SELECT COALESCE(SUM(actual_minutes),0) FROM study_sessions WHERE topic_id=? AND status='done'", (tid,)).fetchone()[0]
            left = dur - done
            if left > 0:
                tp[tid] = {"subject": sname, "minutes": left, "difficulty": diff}
                exams[sname] = s2d(exam)
    g2 = dependencies.PrereqGraph()
    for t in tp: g2.add_topic(t)
    for t in tp:
        for p in g.prerequisites(t):
            if p in tp: g2.add_dependency(p, t)
    sessions = scheduler.generate(tp, g2, exams, quiz_scores(con), start, days, daily_min, block)
    con.execute("DELETE FROM study_sessions WHERE status IN ('planned','missed')")
    for s in sessions:
        con.execute("INSERT INTO study_sessions(topic_id,date,slot,planned_minutes) VALUES(?,?,?,?)",
                    (s["topic"], d2s(s["day"]), s["slot"], s["minutes"]))
    con.commit()
    covered = {s["topic"] for s in sessions}
    total = {t: sum(s["minutes"] for s in sessions if s["topic"] == t) for t in covered}
    short = [t for t in tp if total.get(t, 0) < tp[t]["minutes"]]
    return len(sessions), short

def load_sessions(con):
    rows = con.execute("""SELECT id,topic_id,date,slot,planned_minutes,actual_minutes,status FROM study_sessions
                          ORDER BY date,slot,id""").fetchall()
    return [{"id": r[0], "topic": r[1], "day": s2d(r[2]), "slot": r[3], "minutes": r[4], "actual": r[5], "status": r[6]} for r in rows]

def explain(con, sessions, daily_min):
    """Reason text for each planned session, using the same priority factors as the scheduler."""
    info = {t[0]: t for t in topics(con)}
    scores = quiz_scores(con)
    left = {t: info[t][4] for t in info}
    why = {}
    for s in sorted(sessions, key=lambda x: (x["day"], x["slot"])):
        t = info[s["topic"]]
        exam = s2d(t[3])
        u = priority.urgency(s["day"], exam); d = priority.DIFFICULTY[t[5]]; w = priority.weakness(scores.get(s["topic"], []))
        tt = priority.time_pressure(left[s["topic"]], s["day"], exam, daily_min)
        p = priority.calculate_priority(u, d, w, tt)
        left[s["topic"]] -= s["minutes"]
        why[s["id"]] = "Priority %.1f  (urgency %.2f, difficulty %.2f, weakness %.2f, time %.2f); exam in %d day(s)" % (
            p, u, d, w, tt, max((exam - s["day"]).days, 0))
    return why

def mark_done(con, session_id):
    con.execute("UPDATE study_sessions SET status='done', actual_minutes=planned_minutes WHERE id=?", (session_id,))
    tid = con.execute("SELECT topic_id FROM study_sessions WHERE id=?", (session_id,)).fetchone()[0]
    dur = con.execute("SELECT duration FROM topics WHERE id=?", (tid,)).fetchone()[0]
    got = con.execute("SELECT COALESCE(SUM(actual_minutes),0) FROM study_sessions WHERE topic_id=? AND status='done'", (tid,)).fetchone()[0]
    if got >= dur: set_topic_done(con, tid)
    con.commit()

def mark_missed_and_reschedule(con, session_id, today, daily_min, block):
    """Returns (moved_to or None, message)."""
    sess = load_sessions(con)
    idx = next(i for i, s in enumerate(sess) if s["id"] == session_id)
    tp, exams = {}, {}
    for tid, name, sname, exam, dur, diff, status in topics(con):
        tp[tid] = {"subject": sname, "minutes": dur, "difficulty": diff}; exams[sname] = s2d(exam)
    g = build_graph(con)
    new, unplaced = rescheduler.reschedule(sess, [idx], tp, g, exams, today, daily_min, block)
    for s in new:
        if s.get("moved"):
            con.execute("UPDATE study_sessions SET date=?, slot=?, status='planned' WHERE id=?", (d2s(s["day"]), s["slot"], s["id"]))
    for s in unplaced:
        con.execute("UPDATE study_sessions SET status='missed' WHERE id=?", (s["id"],))
    con.commit()
    if unplaced:
        # No slot satisfies prerequisites + capacity: fall back to a full re-plan of the remaining work.
        generate_plan(con, today, daily_min, block)
        return None, "No single free slot respects the prerequisites, so the remaining plan was regenerated from today."
    moved = next(s for s in new if s["id"] == session_id)
    return moved["day"], "Moved to %s." % moved["day"].strftime("%a %d %b")

def stats(con):
    tt = con.execute("SELECT COUNT(*), SUM(status='done') FROM topics").fetchone()
    planned = con.execute("SELECT COALESCE(SUM(planned_minutes),0) FROM study_sessions WHERE status!='missed'").fetchone()[0]
    actual = con.execute("SELECT COALESCE(SUM(actual_minutes),0) FROM study_sessions WHERE status='done'").fetchone()[0]
    return {"total": tt[0], "done": tt[1] or 0, "pending": tt[0] - (tt[1] or 0), "planned_h": planned / 60, "actual_h": actual / 60}

def weak_topics(con):
    rows = []
    for tid, sc in quiz_scores(con).items():
        avg = sum(sc) / len(sc)
        rows.append((full_name(con, tid), len(sc), round(avg, 1), round(priority.weakness(sc), 2)))
    return sorted(rows, key=lambda r: r[2])

SAMPLE = {
    # subject: (days until exam, [(topic, minutes, difficulty, prerequisite topic names)])
    "Discrete Mathematics": (7, [
        ("Sets and Logic", 90, "Easy", []),
        ("Relations and Functions", 120, "Medium", ["Sets and Logic"]),
        ("Partial Orders", 90, "Medium", ["Relations and Functions"]),
        ("Graph Theory Basics", 120, "Hard", ["Sets and Logic"]),
        ("Trees and Spanning Trees", 120, "Hard", ["Graph Theory Basics"]),
        ("Counting and Pigeonhole", 90, "Medium", ["Sets and Logic"])]),
    "DBMS": (10, [
        ("DBMS Fundamentals", 90, "Easy", []),
        ("ER Model", 120, "Medium", ["DBMS Fundamentals"]),
        ("Relational Model and Keys", 120, "Medium", ["DBMS Fundamentals"]),
        ("SQL Queries", 150, "Medium", ["Relational Model and Keys"]),
        ("Normalization", 180, "Hard", ["Relational Model and Keys"]),
        ("Transactions", 120, "Hard", ["SQL Queries"])]),
    "Data Structures": (13, [
        ("Arrays and Linked Lists", 120, "Easy", []),
        ("Stacks and Queues", 90, "Easy", ["Arrays and Linked Lists"]),
        ("Trees and BST", 150, "Medium", ["Arrays and Linked Lists"]),
        ("Graphs and Traversal", 150, "Hard", ["Trees and BST"]),
        ("Sorting Algorithms", 120, "Medium", [])]),
    "Java OOP": (15, [
        ("Classes and Objects", 90, "Easy", []),
        ("Inheritance", 120, "Medium", ["Classes and Objects"]),
        ("Polymorphism and Interfaces", 120, "Medium", ["Inheritance"]),
        ("Exception Handling", 90, "Easy", ["Classes and Objects"])]),
}
SAMPLE_QUIZZES = [("Normalization", 25), ("Normalization", 31), ("Trees and BST", 38), ("Graph Theory Basics", 42),
                  ("Relations and Functions", 55), ("SQL Queries", 80), ("Inheritance", 72), ("Sets and Logic", 88)]
SAMPLE_TASKS = [("Discrete Maths assignment sheet", 3, 60), ("DBMS practical file", 4, 90),
                ("Java lab record", 6, 120), ("Data Structures mini-project", 9, 180)]
SAMPLE_DONE = [  # topic, days ago, [session minutes]
    ("Sets and Logic", 2, [45, 45]), ("Classes and Objects", 2, [45]), ("Classes and Objects", 1, [45]),
    ("DBMS Fundamentals", 1, [45, 45]), ("Arrays and Linked Lists", 1, [60, 60])]

def reset_all(con):
    for t in ("study_sessions", "quiz_results", "dependencies", "tasks", "topics", "subjects"):
        con.execute("DELETE FROM " + t)
    con.commit()

def load_sample(con, today, daily_min=180, block=45):
    """Fill an empty database with a realistic semester; returns False if data already exists."""
    if con.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]: return False
    for sname, (days, tps) in SAMPLE.items():
        add_subject(con, sname, today + timedelta(days=days))
        sid = con.execute("SELECT id FROM subjects WHERE name=?", (sname,)).fetchone()[0]
        for name, m, d, _ in tps: add_topic(con, sid, name, m, d)
    tid = {t[1]: t[0] for t in topics(con)}
    for sname, (days, tps) in SAMPLE.items():
        for name, _, _, pres in tps:
            for p in pres:
                ok, msg = add_dependency(con, tid[name], tid[p]); assert ok, msg
    for name, score in SAMPLE_QUIZZES: add_quiz(con, tid[name], score, today)
    for title, days, m in SAMPLE_TASKS: add_task(con, title, today + timedelta(days=days), m)
    for name, ago, mins in SAMPLE_DONE:                       # completed history for the progress charts
        for k, m in enumerate(mins):
            con.execute("INSERT INTO study_sessions(topic_id,date,slot,planned_minutes,actual_minutes,status) VALUES(?,?,?,?,?,'done')",
                        (tid[name], d2s(today - timedelta(days=ago)), k, m, m))
    for name in ("Sets and Logic", "Classes and Objects", "DBMS Fundamentals", "Arrays and Linked Lists"):
        set_topic_done(con, tid[name], True)
    con.commit()
    generate_plan(con, today, daily_min, block)
    return True
