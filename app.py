"""
Support Desk - a small ticketing web app
Run:  pip install flask   then   python app.py
Open: http://localhost:5000

Three layers (tiers):
  1. Front end - templates/*.html + static/style.css (what the user sees)
  2. Logic     - app.py (routes, validation, SQL)
  3. Data      - support.db (SQLite database, created automatically)
"""

import os
import re
import sqlite3
import sys
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, abort

app = Flask(__name__)
app.secret_key = "dev-only-key"  # needed for flash messages

DB_FILE = "support.db"
CHANNELS = ["Phone", "Email", "In person"]
CATEGORIES = ["Login / Access", "Report", "Settlement", "Installation / Configuration", "Other"]
PRIORITIES = ["High", "Medium", "Low"]
STATUSES = ["Open", "In progress", "Escalated", "Resolved"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PREFIX = "+64"  # New Zealand numbers only
NOTE_MIN, NOTE_MAX, NOTE_MIN_WORDS = 20, 1000, 4  # history entries must say something useful
app.jinja_env.globals.update(NOTE_MIN=NOTE_MIN, NOTE_MAX=NOTE_MAX)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------- Data layer ----------------

def get_db():
    # Wait up to 10s if another program (e.g. DB Browser) holds a lock
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the tables the first time the app runs."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                client     TEXT NOT NULL,
                email      TEXT,
                phone      TEXT,
                channel    TEXT NOT NULL,
                category   TEXT NOT NULL,
                priority   TEXT NOT NULL,
                issue      TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'Open',
                resolution TEXT,
                created    TEXT NOT NULL,
                updated    TEXT NOT NULL,
                resolved   TEXT
            );
            CREATE TABLE IF NOT EXISTS notes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id),
                note      TEXT NOT NULL,
                created   TEXT NOT NULL
            );
        """)
        # Older databases: add the 'resolved' column if it is missing
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(tickets)")}
        if "resolved" not in cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN resolved TEXT")
        # Older databases: add the contact columns if they are missing
        for col in ("email", "phone"):
            if col not in cols:
                conn.execute(f"ALTER TABLE tickets ADD COLUMN {col} TEXT")


def add_note(conn, ticket_id, text):
    conn.execute("INSERT INTO notes (ticket_id, note, created) VALUES (?, ?, ?)",
                 (ticket_id, text, now()))


def set_status(conn, ticket_id, status, resolution=None):
    resolved_at = now() if status == "Resolved" else None
    conn.execute("UPDATE tickets SET status = ?, resolution = COALESCE(?, resolution), "
                 "updated = ?, resolved = ? WHERE id = ?",
                 (status, resolution, now(), resolved_at, ticket_id))


def normalise_phone(raw):
    """Turn what the user typed after +64 into '+64 <digits>', or None if invalid.

    Accepts spaces, dashes and brackets, a leading 0 (e.g. 021 123 4567) or a
    repeated +64. NZ numbers are 8-10 digits once the leading 0 is dropped.
    """
    s = raw.strip()
    if s.startswith(PHONE_PREFIX):
        s = s[len(PHONE_PREFIX):]
    if re.search(r"[^\d\s\-()]", s):
        return None
    digits = re.sub(r"\D", "", s).lstrip("0")
    if not 8 <= len(digits) <= 10:
        return None
    return f"{PHONE_PREFIX} {digits}"


def note_problem(text, what):
    """Return an error message if a history entry is too thin or too long, else None."""
    if len(text) > NOTE_MAX:
        return f"{what} is too long: keep it under {NOTE_MAX} characters (it has {len(text)})."
    if len(text) < NOTE_MIN or len(re.findall(r"[A-Za-z]{2,}", text)) < NOTE_MIN_WORDS:
        return (f"{what} needs more detail: write at least {NOTE_MIN} characters and "
                f"{NOTE_MIN_WORDS} words, not just a number. Say what you checked and what you found.")
    return None


# ---------------- Logic layer ----------------

@app.route("/")
def index():
    """Dashboard: counts by status, new-ticket form, active queue (most urgent first)."""
    with get_db() as conn:
        counts = dict(conn.execute(
            "SELECT status, COUNT(*) FROM tickets GROUP BY status").fetchall())
        queue = conn.execute("""
            SELECT * FROM tickets
            WHERE status != 'Resolved'
            ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,
                     created
        """).fetchall()
    return render_template("index.html", counts=counts, queue=queue, channels=CHANNELS,
                           categories=CATEGORIES, priorities=PRIORITIES, page="home")


@app.route("/tickets", methods=["POST"])
def create_ticket():
    """First-line support: log a request from phone, email or in person."""
    f = request.form
    client, issue = f.get("client", "").strip(), f.get("issue", "").strip()
    channel, category, priority = f.get("channel"), f.get("category"), f.get("priority")
    email, phone_raw = f.get("email", "").strip().lower(), f.get("phone", "").strip()

    if not client or not issue:
        flash("Client and issue are both required.", "error")
        return redirect(url_for("index"))
    if email and not EMAIL_RE.match(email):
        flash(f"'{email}' is not a valid email address, e.g. name@company.co.nz.", "error")
        return redirect(url_for("index"))
    phone = normalise_phone(phone_raw) if phone_raw else None
    if phone_raw and phone is None:
        flash("Phone must be a New Zealand number: +64 followed by 8-10 digits, "
              "e.g. +64 21 123 4567.", "error")
        return redirect(url_for("index"))
    if channel not in CHANNELS or category not in CATEGORIES or priority not in PRIORITIES:
        flash("Please choose a valid channel, category and priority.", "error")
        return redirect(url_for("index"))

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO tickets (client, email, phone, channel, category, priority, issue, "
            "created, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (client, email or None, phone, channel, category, priority, issue, now(), now()))
        add_note(conn, cur.lastrowid, f"Ticket logged via {channel}.")
    flash(f"Ticket #{cur.lastrowid} logged for {client}.", "ok")
    return redirect(url_for("ticket", ticket_id=cur.lastrowid))


@app.route("/tickets/<int:ticket_id>")
def ticket(ticket_id):
    """One ticket with its full history of notes."""
    with get_db() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            abort(404)
        notes = conn.execute("SELECT * FROM notes WHERE ticket_id = ? ORDER BY id",
                             (ticket_id,)).fetchall()
    return render_template("ticket.html", t=t, notes=notes, page="home")


@app.route("/tickets/<int:ticket_id>/note", methods=["POST"])
def ticket_note(ticket_id):
    """Diagnose: record what was checked. The first note moves the ticket to In progress."""
    text = request.form.get("note", "").strip()
    problem = note_problem(text, "Note")
    if problem:
        flash(problem, "error")
        return redirect(url_for("ticket", ticket_id=ticket_id))
    with get_db() as conn:
        status = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if status is None:
            abort(404)
        add_note(conn, ticket_id, text)
        if status["status"] == "Open":
            set_status(conn, ticket_id, "In progress")
        else:
            conn.execute("UPDATE tickets SET updated = ? WHERE id = ?", (now(), ticket_id))
    flash("Note added.", "ok")
    return redirect(url_for("ticket", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/escalate", methods=["POST"])
def escalate(ticket_id):
    """Collaborate with engineering: hand over with a clear summary."""
    reason = request.form.get("reason", "").strip()
    problem = note_problem(reason, "Escalation reason")
    if problem:
        flash(problem, "error")
        return redirect(url_for("ticket", ticket_id=ticket_id))
    with get_db() as conn:
        set_status(conn, ticket_id, "Escalated")
        add_note(conn, ticket_id, f"Escalated to engineering: {reason}")
    flash("Escalated to engineering.", "ok")
    return redirect(url_for("ticket", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/resolve", methods=["POST"])
def resolve(ticket_id):
    """Resolve: a resolution note is required so the fix is documented."""
    resolution = request.form.get("resolution", "").strip()
    problem = note_problem(resolution, "Resolution")
    if problem:
        flash(problem, "error")
        return redirect(url_for("ticket", ticket_id=ticket_id))
    with get_db() as conn:
        set_status(conn, ticket_id, "Resolved", resolution)
        add_note(conn, ticket_id, f"Resolved: {resolution}")
    flash(f"Ticket #{ticket_id} resolved.", "ok")
    return redirect(url_for("index"))


@app.route("/knowledge")
def knowledge():
    """Knowledge base: search past resolved tickets before solving a new one."""
    q = request.args.get("q", "").strip()
    with get_db() as conn:
        if q:
            like = f"%{q}%"
            rows = conn.execute("""
                SELECT * FROM tickets
                WHERE status = 'Resolved'
                  AND (issue LIKE ? OR resolution LIKE ? OR client LIKE ? OR category LIKE ?
                       OR email LIKE ? OR phone LIKE ?)
                ORDER BY updated DESC
            """, (like,) * 6).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tickets WHERE status = 'Resolved' "
                                "ORDER BY updated DESC").fetchall()
    return render_template("knowledge.html", rows=rows, q=q, page="knowledge")


@app.route("/health")
def health():
    """Installation check: confirm the app is set up and configured correctly."""
    checks = []
    checks.append(("Python version 3.8 or later", sys.version_info >= (3, 8),
                   sys.version.split()[0]))
    db_exists = os.path.exists(DB_FILE)
    checks.append(("Database file found", db_exists, os.path.abspath(DB_FILE)))
    try:
        with get_db() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        checks.append(("Database connection", True, "Connected"))
        checks.append(("Required tables exist", {"tickets", "notes"} <= tables,
                       ", ".join(sorted(tables - {"sqlite_sequence"}))))
        checks.append(("Tickets stored", True, str(total)))
    except sqlite3.Error as e:
        checks.append(("Database connection", False, str(e)))
    integrity = []
    try:
        with get_db() as conn:
            for name, sql in INTEGRITY_CHECKS:
                rows = conn.execute(sql).fetchall()
                integrity.append({"name": name, "sql": sql.strip(), "rows": rows,
                                  "ok": len(rows) == 0})
    except sqlite3.Error as e:
        integrity.append({"name": "Integrity checks", "sql": "", "rows": [], "ok": False,
                          "error": str(e)})
    all_ok = all(ok for _, ok, _ in checks) and all(i["ok"] for i in integrity)
    return render_template("health.html", checks=checks, integrity=integrity,
                           all_ok=all_ok, page="health")


# ---------------- Reports (data analysis with SQL) ----------------

REPORTS = [
    ("Tickets by client",
     "How many tickets each client has raised, and how many are still active.",
     """
SELECT client                                            AS "Client",
       COUNT(*)                                          AS "Total",
       SUM(CASE WHEN status != 'Resolved' THEN 1 ELSE 0 END) AS "Active",
       SUM(CASE WHEN status  = 'Resolved' THEN 1 ELSE 0 END) AS "Resolved"
FROM tickets
GROUP BY client
ORDER BY "Total" DESC, client
"""),
    ("Tickets by category and priority",
     "Which kinds of problems come up most, and how urgent they are.",
     """
SELECT category AS "Category",
       SUM(CASE WHEN priority = 'High'   THEN 1 ELSE 0 END) AS "High",
       SUM(CASE WHEN priority = 'Medium' THEN 1 ELSE 0 END) AS "Medium",
       SUM(CASE WHEN priority = 'Low'    THEN 1 ELSE 0 END) AS "Low",
       COUNT(*) AS "Total"
FROM tickets
GROUP BY category
ORDER BY "Total" DESC
"""),
    ("Average time to resolve",
     "Average hours from logging a ticket to resolving it, by priority.",
     """
SELECT priority AS "Priority",
       COUNT(*) AS "Resolved tickets",
       ROUND(AVG((julianday(resolved) - julianday(created)) * 24), 1) AS "Avg hours to resolve"
FROM tickets
WHERE status = 'Resolved' AND resolved IS NOT NULL
GROUP BY priority
ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END
"""),
    ("Oldest active tickets",
     "Active tickets that have been waiting the longest.",
     """
SELECT id AS "#", client AS "Client", priority AS "Priority", status AS "Status",
       issue AS "Issue",
       ROUND((julianday('now', 'localtime') - julianday(created)) * 24, 1) AS "Hours open"
FROM tickets
WHERE status != 'Resolved'
ORDER BY created
LIMIT 5
"""),
    ("Contact channels",
     "How clients get in touch: phone, email or in person.",
     """
SELECT channel AS "Channel",
       COUNT(*) AS "Tickets",
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM tickets), 0) AS "% of all tickets"
FROM tickets
GROUP BY channel
ORDER BY "Tickets" DESC
"""),
    ("Most active tickets",
     "Tickets with the most notes, using a JOIN between tickets and notes.",
     """
SELECT t.id AS "#", t.client AS "Client", t.issue AS "Issue",
       COUNT(n.id) AS "Notes"
FROM tickets t
JOIN notes n ON n.ticket_id = t.id
GROUP BY t.id
ORDER BY "Notes" DESC
LIMIT 5
"""),
]

# Each check should return NO rows. Any row returned is a data problem to fix.
INTEGRITY_CHECKS = [
    ("Resolved tickets without a resolution note", """
SELECT id, client, issue FROM tickets
WHERE status = 'Resolved' AND (resolution IS NULL OR TRIM(resolution) = '')
"""),
    ("Tickets with no history notes", """
SELECT t.id, t.client, t.issue FROM tickets t
LEFT JOIN notes n ON n.ticket_id = t.id
WHERE n.id IS NULL
"""),
    ("Notes linked to a ticket that doesn't exist", """
SELECT n.id, n.ticket_id, n.note FROM notes n
LEFT JOIN tickets t ON t.id = n.ticket_id
WHERE t.id IS NULL
"""),
    ("Invalid priority or status values", """
SELECT id, priority, status FROM tickets
WHERE priority NOT IN ('High', 'Medium', 'Low')
   OR status NOT IN ('Open', 'In progress', 'Escalated', 'Resolved')
"""),
    ("Badly formatted email or phone", """
SELECT id, client, email, phone FROM tickets
WHERE (email IS NOT NULL AND email NOT LIKE '%_@_%._%')
   OR (phone IS NOT NULL AND phone NOT GLOB '+64 [1-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]*')
"""),
    ("High priority tickets active for more than 24 hours", """
SELECT id, client, issue, created FROM tickets
WHERE priority = 'High' AND status != 'Resolved'
  AND julianday('now', 'localtime') - julianday(created) > 1
"""),
]


def run_query(sql, read_only=False):
    """Run a SELECT and return (column names, rows)."""
    if read_only:
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=10)
    else:
        conn = sqlite3.connect(DB_FILE, timeout=10)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, cur.fetchall()
    finally:
        conn.close()


@app.route("/reports")
def reports():
    """Data analysis: summary reports built with GROUP BY, CASE, AVG and JOIN."""
    results = []
    for title, desc, sql in REPORTS:
        cols, rows = run_query(sql)
        results.append({"title": title, "desc": desc, "sql": sql.strip(),
                        "cols": cols, "rows": rows})
    return render_template("reports.html", results=results, page="reports")


EXAMPLE_QUERIES = [
    "SELECT * FROM tickets",
    "SELECT * FROM notes WHERE ticket_id = 1",
    "SELECT status, COUNT(*) FROM tickets GROUP BY status",
    "SELECT client, issue FROM tickets WHERE priority = 'High' AND status != 'Resolved'",
    "SELECT t.id, t.client, n.created, n.note FROM tickets t JOIN notes n ON n.ticket_id = t.id ORDER BY t.id, n.id",
]


@app.route("/sql", methods=["GET", "POST"])
def sql_console():
    """Practise SQL: read-only, SELECT queries only."""
    sql = request.form.get("sql", "").strip() or request.args.get("q", "").strip()
    cols, rows, error = [], [], None
    if sql:
        first_word = sql.split(None, 1)[0].upper()
        if first_word not in ("SELECT", "WITH"):
            error = "Only SELECT queries are allowed here (this page is read-only)."
        else:
            try:
                cols, rows = run_query(sql, read_only=True)
            except sqlite3.Error as e:
                error = f"SQL error: {e}"
    return render_template("sql.html", sql=sql, cols=cols, rows=rows, error=error,
                           examples=EXAMPLE_QUERIES, page="sql")


@app.route("/guide")
def guide():
    """User training: a short how-to guide for new users."""
    return render_template("guide.html", page="guide")


if __name__ == "__main__":
    try:
        init_db()
    except sqlite3.OperationalError as e:
        if "locked" not in str(e):
            raise
        sys.exit(f"{DB_FILE} is locked by another program. If DB Browser for SQLite "
                 "is open, click 'Write Changes' or 'Revert Changes' (or close it), "
                 "then run the app again.")
    app.run(debug=True)
