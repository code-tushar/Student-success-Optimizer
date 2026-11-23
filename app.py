"""Student Academic Success Optimizer - Streamlit dashboard.   Run:  streamlit run app.py"""
import os
from datetime import date, datetime, timedelta
import pandas as pd
import plotly.express as px
import streamlit as st
import database
import service

st.set_page_config(page_title="Student Academic Success Optimizer", page_icon="🎓", layout="wide")
os.makedirs("data", exist_ok=True)

@st.cache_resource
def get_con():
    return database.connect("data/study_optimizer.db", check_same_thread=False)

con = get_con()
today = date.today()

# ------------------------------------------------------------------ sidebar
st.sidebar.title("🎓 Study Optimizer")
page = st.sidebar.radio("Go to", ["Dashboard", "Subjects and Topics", "Smart Timetable", "Progress and Revision", "Assignments"])
st.sidebar.markdown("---")
st.sidebar.subheader("Study settings")
daily_h = st.sidebar.slider("Available study hours per day", 1.0, 8.0, 3.0, 0.5)
block = st.sidebar.selectbox("Study block length (minutes)", [30, 45, 60], index=1)
start_t = st.sidebar.time_input("Daily start time", datetime.strptime("16:00", "%H:%M").time())
daily_min = int(daily_h * 60)
st.sidebar.markdown("---")
if st.sidebar.button("Load sample data"):
    if service.load_sample(con, today, daily_min, block):
        st.sidebar.success("Sample semester loaded (4 subjects, 21 topics) and a timetable was generated.")
    else:
        st.sidebar.warning("The database already has data. Use 'Reset all data' first.")
sure = st.sidebar.checkbox("I am sure I want to delete everything")
if st.sidebar.button("Reset all data", disabled=not sure):
    service.reset_all(con); st.sidebar.success("All data deleted."); st.rerun()

def topic_options():
    return {f"{t[2]} - {t[1]}": t[0] for t in service.topics(con)}

def fmt_time(day_sessions):
    """Attach clock times to the sessions of one day."""
    cur = datetime.combine(today, start_t); out = []
    for s in day_sessions:
        end = cur + timedelta(minutes=s["minutes"])
        out.append(f"{cur:%H:%M}-{end:%H:%M}"); cur = end
    return out

# ------------------------------------------------------------------ Dashboard
if page == "Dashboard":
    st.title("Dashboard")
    stt = service.stats(con)
    c = st.columns(4)
    c[0].metric("Total topics", stt["total"]); c[1].metric("Completed", stt["done"])
    c[2].metric("Pending", stt["pending"]); c[3].metric("Study hours done / planned", f"{stt['actual_h']:.1f} / {stt['planned_h']:.1f}")
    if stt["total"]:
        st.progress(stt["done"] / stt["total"], text=f"{100 * stt['done'] / stt['total']:.0f}% of topics completed")
    else:
        st.info("No data yet. Add subjects and topics, or press **Load sample data** in the sidebar.")
    subs = service.subjects(con)
    if subs:
        nxt = next(((n, service.s2d(e)) for _, n, e in subs if service.s2d(e) >= today), None)
        if nxt: st.metric("Next exam", nxt[0], f"in {(nxt[1] - today).days} day(s)", delta_color="off")
    st.subheader("Today's schedule")
    info = {t[0]: t for t in service.topics(con)}
    todays = [s for s in service.load_sessions(con) if s["day"] == today]
    if todays:
        times = fmt_time(todays)
        st.dataframe(pd.DataFrame([{"Time": tm, "Topic": service.full_name(con, s["topic"]), "Minutes": s["minutes"], "Status": s["status"]}
                                   for tm, s in zip(times, todays)]), hide_index=True)
    else:
        st.write("Nothing scheduled for today. Generate a timetable on the **Smart Timetable** page.")
    st.subheader("Pending assignments")
    tasks = con.execute("SELECT title, deadline, duration FROM tasks WHERE status='pending' ORDER BY deadline").fetchall()
    if tasks: st.dataframe(pd.DataFrame(tasks, columns=["Title", "Deadline", "Minutes"]), hide_index=True)
    else: st.write("No pending assignments.")

# ------------------------------------------------------------------ Subjects and Topics
elif page == "Subjects and Topics":
    st.title("Subjects and Topics")
    c1, c2 = st.columns(2)
    with c1:
        with st.form("subject_form", clear_on_submit=True):
            st.subheader("Add subject")
            name = st.text_input("Subject name")
            exam = st.date_input("Exam date", today + timedelta(days=14))
            if st.form_submit_button("Add subject"):
                if not name.strip(): st.error("Please enter a subject name.")
                elif exam < today: st.error("The exam date cannot be in the past.")
                else:
                    try: service.add_subject(con, name, exam); st.success("Subject added."); st.rerun()
                    except Exception as e: st.error(f"Could not add subject: {e}")
    with c2:
        subs = service.subjects(con)
        with st.form("topic_form", clear_on_submit=True):
            st.subheader("Add topic")
            sub = st.selectbox("Subject", [(s[0], s[1]) for s in subs], format_func=lambda x: x[1]) if subs else None
            tname = st.text_input("Topic name")
            mins = st.number_input("Estimated study time (minutes)", 15, 600, 90, 15)
            diff = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=1)
            if st.form_submit_button("Add topic"):
                if not sub: st.error("Add a subject first.")
                elif not tname.strip(): st.error("Please enter a topic name.")
                else:
                    try: service.add_topic(con, sub[0], tname, mins, diff); st.success("Topic added."); st.rerun()
                    except Exception as e: st.error(f"Could not add topic (duplicate name?): {e}")
    st.subheader("Prerequisites (graph)")
    opts = topic_options()
    if len(opts) >= 2:
        a, b, c = st.columns([3, 3, 1])
        t = a.selectbox("Topic", list(opts), key="dep_t"); p = b.selectbox("requires prerequisite", list(opts), key="dep_p")
        c.write(""); c.write("")
        if c.button("Add"):
            ok, msg = service.add_dependency(con, opts[t], opts[p])
            (st.success if ok else st.error)(msg)
    deps = con.execute("SELECT topic_id, prerequisite_id FROM dependencies").fetchall()
    if deps:
        st.dataframe(pd.DataFrame([{"Prerequisite": service.full_name(con, p), "must come before": service.full_name(con, t)} for t, p in deps]),
                     hide_index=True)
        try:
            order = service.build_graph(con).order()
            st.caption("Valid study order (topological sort): " + " → ".join(service.full_name(con, n).split(" - ")[1] for n in order))
        except Exception as e:
            st.error(str(e))
    st.subheader("All topics")
    rows = service.topics(con)
    if rows:
        st.dataframe(pd.DataFrame(rows, columns=["id", "Topic", "Subject", "Exam", "Minutes", "Difficulty", "Status"]).drop(columns="id"),
                     hide_index=True)
        pick = st.selectbox("Mark a topic as completed / pending", list(opts), key="done_pick")
        c1, c2 = st.columns(2)
        if c1.button("Mark completed"): service.set_topic_done(con, opts[pick], True); st.rerun()
        if c2.button("Mark pending"): service.set_topic_done(con, opts[pick], False); st.rerun()

# ------------------------------------------------------------------ Smart Timetable
elif page == "Smart Timetable":
    st.title("Smart Timetable")
    horizon = st.slider("Plan ahead (days)", 7, 60, 30)
    if st.button("Generate timetable", type="primary"):
        n, short = service.generate_plan(con, today, daily_min, block, horizon)
        if n == 0: st.warning("Nothing to schedule. Add topics with exam dates in the future.")
        else: st.success(f"Timetable generated with {n} study sessions.")
        for t in short:
            st.warning(f"Not enough time before the exam to fully cover: {service.full_name(con, t)}. Increase daily hours or reduce the workload.")
    sessions = service.load_sessions(con)
    if not sessions:
        st.info("No timetable yet. Press **Generate timetable**.")
    else:
        why = service.explain(con, sessions, daily_min)
        days = sorted({s["day"] for s in sessions})
        for d in days:
            ds = [s for s in sessions if s["day"] == d]
            times = fmt_time(ds)
            with st.expander(f"{d:%A, %d %b %Y}  -  {sum(s['minutes'] for s in ds)} min", expanded=(d == today)):
                for tm, s in zip(times, ds):
                    c = st.columns([2, 4, 1, 1, 1])
                    icon = {"planned": "🕒", "done": "✅", "missed": "❌"}[s["status"]]
                    c[0].write(f"{icon} {tm}"); c[1].write(f"**{service.full_name(con, s['topic'])}** ({s['minutes']} min)")
                    c[1].caption(why.get(s["id"], ""))
                    if s["status"] != "done":
                        if c[2].button("Done", key=f"d{s['id']}"): service.mark_done(con, s["id"]); st.rerun()
                        if c[3].button("Missed", key=f"m{s['id']}"):
                            _, msg = service.mark_missed_and_reschedule(con, s["id"], today, daily_min, block)
                            st.session_state["flash"] = msg; st.rerun()
        if "flash" in st.session_state: st.info(st.session_state.pop("flash"))

# ------------------------------------------------------------------ Progress and Revision
elif page == "Progress and Revision":
    st.title("Progress and Revision")
    stt = service.stats(con)
    c = st.columns(3)
    c[0].metric("Completed topics", f"{stt['done']} / {stt['total']}"); c[1].metric("Planned hours", f"{stt['planned_h']:.1f}")
    c[2].metric("Actual hours", f"{stt['actual_h']:.1f}")
    rows = con.execute("SELECT date, SUM(planned_minutes), SUM(CASE WHEN status='done' THEN actual_minutes ELSE 0 END) FROM study_sessions GROUP BY date ORDER BY date").fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["Date", "Planned", "Completed"]).melt("Date", var_name="Type", value_name="Minutes")
        st.plotly_chart(px.bar(df, x="Date", y="Minutes", color="Type", barmode="group", title="Planned vs completed study time"))
    st.subheader("Record a quiz score")
    opts = topic_options()
    if opts:
        with st.form("quiz_form", clear_on_submit=True):
            t = st.selectbox("Topic", list(opts)); sc = st.slider("Score (%)", 0, 100, 60); qd = st.date_input("Quiz date", today)
            if st.form_submit_button("Save score"): service.add_quiz(con, opts[t], sc, qd); st.success("Saved."); st.rerun()
    st.subheader("Weak topics")
    weak = service.weak_topics(con)
    if weak:
        df = pd.DataFrame(weak, columns=["Topic", "Quizzes", "Average score (%)", "Weakness W"])
        st.dataframe(df, hide_index=True)
        st.plotly_chart(px.bar(df, x="Average score (%)", y="Topic", orientation="h", range_x=[0, 100], title="Average quiz score per topic"))
        for r in weak:
            if r[2] < 50: st.warning(f"Revise **{r[0]}** (average {r[2]}%). Its higher weakness raises its priority in the next timetable.")
    else:
        st.write("No quiz scores yet.")

# ------------------------------------------------------------------ Assignments
elif page == "Assignments":
    st.title("Assignments")
    with st.form("task_form", clear_on_submit=True):
        title = st.text_input("Title"); dl = st.date_input("Deadline", today + timedelta(days=7)); mins = st.number_input("Estimated time (minutes)", 15, 1200, 60, 15)
        if st.form_submit_button("Add assignment"):
            if not title.strip(): st.error("Please enter a title.")
            elif dl < today: st.error("The deadline cannot be in the past.")
            else: service.add_task(con, title, dl, mins); st.success("Added."); st.rerun()
    rows = con.execute("SELECT id, title, deadline, duration, status FROM tasks ORDER BY deadline").fetchall()
    if rows:
        st.dataframe(pd.DataFrame(rows, columns=["id", "Title", "Deadline", "Minutes", "Status"]).drop(columns="id"), hide_index=True)
        pick = st.selectbox("Mark as completed", [(r[0], r[1]) for r in rows if r[4] == "pending"] or [None], format_func=lambda x: x[1] if x else "-")
        if pick and st.button("Mark completed"):
            con.execute("UPDATE tasks SET status='done' WHERE id=?", (pick[0],)); con.commit(); st.rerun()
