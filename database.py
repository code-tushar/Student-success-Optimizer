"""SQLite persistence layer (primary keys, foreign keys, CHECK constraints)."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    exam_date TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS topics(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    duration INTEGER NOT NULL CHECK(duration > 0),
    difficulty TEXT NOT NULL CHECK(difficulty IN ('Easy','Medium','Hard')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done')),
    UNIQUE(subject_id, name));
CREATE TABLE IF NOT EXISTS dependencies(
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    prerequisite_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY(topic_id, prerequisite_id),
    CHECK(topic_id <> prerequisite_id));
CREATE TABLE IF NOT EXISTS tasks(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, deadline TEXT NOT NULL,
    duration INTEGER NOT NULL CHECK(duration > 0),
    status TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS study_sessions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    date TEXT NOT NULL, slot INTEGER NOT NULL DEFAULT 0, planned_minutes INTEGER NOT NULL,
    actual_minutes INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','done','missed')));
CREATE TABLE IF NOT EXISTS quiz_results(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    score REAL NOT NULL CHECK(score BETWEEN 0 AND 100),
    quiz_date TEXT NOT NULL);
"""

def connect(path=":memory:", check_same_thread=True):
    con = sqlite3.connect(path, check_same_thread=check_same_thread)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con
