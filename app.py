"""
Support Desk - a small ticketing web app built with Flask and SQLite.

Run:  pip install flask   then   python app.py
Open: http://localhost:5000

Three layers:
  1. Front end - templates/*.html and static/  (what the user sees)
  2. Logic     - app.py                         (routes and validation)
  3. Data      - support.db                     (SQLite database)

Ticket workflow:  Open -> In progress -> Escalated -> Resolved
"""

import os
import re
import sqlite3
import sys
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, abort

from queries import REPORTS, INTEGRITY_CHECKS, EXAMPLE_QUERIES

app = Flask(__name__)
app.secret_key = "dev-only-key"  # Flask needs this to show flash messages

# ---------------- Settings ----------------

DB_FILE = "support.db"

# Allowed values for the drop-downs (the server checks these too)
CHANNELS = ["Phone", "Email", "In person"]
CATEGORIES = ["Login / Access", "Report", "Settlement", "Installation / Configuration", "Other"]
PRIORITIES = ["High", "Medium", "Low"]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PREFIX = "+64"  # New Zealand numbers only

# Notes must be useful: between 20 and 1000 characters, with at least 4 words
NOTE_MIN = 20
NOTE_MAX = 1000
NOTE_MIN_WORDS = 4
app.jinja_env.globals.update(NOTE_MIN=NOTE_MIN, NOTE_MAX=NOTE_MAX)  # used by ticket.html


# ---------------- Database ----------------

def get_db():
    """Open the database. Rows can be read by column name, e.g. row["client"]."""
    conn = sqlite3.connect(DB_FILE, timeout=10)  # wait if another program has it locked
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the two tables if they don't exist yet. One ticket has many notes."""
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


def now():
    """Current time as text, e.g. '2026-10-12 14:30'."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def get_ticket_or_404(conn, ticket_id):
    """Load one ticket, or show a 404 page if it doesn't exist."""
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if ticket is None:
        abort(404)
    return ticket


def add_note(conn, ticket_id, text):
    """Add one entry to a ticket's history."""
    conn.execute("INSERT INTO notes (ticket_id, note, created) VALUES (?, ?, ?)",
                 (ticket_id, text, now()))


def set_status(conn, ticket_id, status, resolution=None):
    """Change a ticket's status. The resolved time is only set when it is resolved."""
    resolved_time = now() if status == "Resolved" else None
    conn.execute("""
        UPDATE tickets
        SET status = ?, resolution = COALESCE(?, resolution), updated = ?, resolved = ?
        WHERE id = ?
    """, (status, resolution, now(), resolved_time, ticket_id))


# ---------------- Validation ----------------

def clean_phone(raw):
    """Turn a typed NZ number into '+64 <digits>', or return None if it isn't valid.

    Example: '021 123-4567' -> '+64 211234567'
    """
    number = raw.strip()
    if number.startswith(PHONE_PREFIX):
        number = number[len(PHONE_PREFIX):]          # user typed +64 again
    if re.search(r"[^\d\s\-()]", number):
        return None                                  # letters or other symbols
    digits = re.sub(r"\D", "", number).lstrip("0")   # keep digits, drop leading 0
    if not 8 <= len(digits) <= 10:
        return None
    return f"{PHONE_PREFIX} {digits}"


def check_note(text, label):
    """Return an error message if a note is too short or too long, otherwise None."""
    words = re.findall(r"[A-Za-z]{2,}", text)
    if len(text) > NOTE_MAX:
        return f"{label} is too long: keep it under {NOTE_MAX} characters (it has {len(text)})."
    if len(text) < NOTE_MIN or len(words) < NOTE_MIN_WORDS:
        return (f"{label} needs more detail: write at least {NOTE_MIN} characters and "
                f"{NOTE_MIN_WORDS} words. Say what you checked and what you found.")
    return None


def check_new_ticket(form):
    """Read the new-ticket form. Returns (ticket, None) if valid, or (None, error)."""
    ticket = {
        "client":   form.get("client", "").strip(),
        "issue":    form.get("issue", "").strip(),
        "email":    form.get("email", "").strip().lower() or None,
        "phone":    None,
        "channel":  form.get("channel"),
        "category": form.get("category"),
        "priority": form.get("priority"),
    }
    phone_typed = form.get("phone", "").strip()

    if not ticket["client"] or not ticket["issue"]:
        return None, "Client and issue are both required."
    if ticket["email"] and not EMAIL_PATTERN.match(ticket["email"]):
        return None, f"'{ticket['email']}' is not a valid email address, e.g. name@company.co.nz."
    if phone_typed:
        ticket["phone"] = clean_phone(phone_typed)
        if ticket["phone"] is None:
            return None, ("Phone must be a New Zealand number: +64 followed by 8-10 digits, "
                          "e.g. +64 21 123 4567.")
    if (ticket["channel"] not in CHANNELS or ticket["category"] not in CATEGORIES
            or ticket["priority"] not in PRIORITIES):
        return None, "Please choose a valid channel, category and priority."
    return ticket, None


# ---------------- Pages: tickets ----------------

@app.route("/")
def index():
    """Home page: ticket counts, the new-ticket form and the active queue."""
    with get_db() as conn:
        counts = dict(conn.execute(
            "SELECT status, COUNT(*) FROM tickets GROUP BY status").fetchall())
        # Most urgent first: High, then Medium, then Low. Oldest first within each.
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
    """Log a new ticket from the form on the home page."""
    ticket, error = check_new_ticket(request.form)
    if error:
        flash(error, "error")
        return redirect(url_for("index"))

    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO tickets (client, email, phone, channel, category, priority, issue,
                                 created, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ticket["client"], ticket["email"], ticket["phone"], ticket["channel"],
              ticket["category"], ticket["priority"], ticket["issue"], now(), now()))
        new_id = cur.lastrowid
        add_note(conn, new_id, f"Ticket logged via {ticket['channel']}.")

    flash(f"Ticket #{new_id} logged for {ticket['client']}.", "ok")
    return redirect(url_for("ticket", ticket_id=new_id))


@app.route("/tickets/<int:ticket_id>")
def ticket(ticket_id):
    """Show one ticket and its full history."""
    with get_db() as conn:
        t = get_ticket_or_404(conn, ticket_id)
        notes = conn.execute("SELECT * FROM notes WHERE ticket_id = ? ORDER BY id",
                             (ticket_id,)).fetchall()
    return render_template("ticket.html", t=t, notes=notes, page="home")


@app.route("/tickets/<int:ticket_id>/note", methods=["POST"])
def ticket_note(ticket_id):
    """Add a diagnosis note. The first note moves an Open ticket to In progress."""
    text = request.form.get("note", "").strip()
    error = check_note(text, "Note")
    if error:
        flash(error, "error")
        return redirect(url_for("ticket", ticket_id=ticket_id))

    with get_db() as conn:
        t = get_ticket_or_404(conn, ticket_id)
        add_note(conn, ticket_id, text)
        if t["status"] == "Open":
            set_status(conn, ticket_id, "In progress")
        else:
            conn.execute("UPDATE tickets SET updated = ? WHERE id = ?", (now(), ticket_id))

    flash("Note added.", "ok")
    return redirect(url_for("ticket", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/escalate", methods=["POST"])
def escalate(ticket_id):
    """Hand the ticket to engineering with a clear reason."""
    reason = request.form.get("reason", "").strip()
    error = check_note(reason, "Escalation reason")
    if error:
        flash(error, "error")
        return redirect(url_for("ticket", ticket_id=ticket_id))

    with get_db() as conn:
        get_ticket_or_404(conn, ticket_id)
        set_status(conn, ticket_id, "Escalated")
        add_note(conn, ticket_id, f"Escalated to engineering: {reason}")

    flash("Escalated to engineering.", "ok")
    return redirect(url_for("ticket", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/resolve", methods=["POST"])
def resolve(ticket_id):
    """Close the ticket. A resolution note is required so the fix is documented."""
    resolution = request.form.get("resolution", "").strip()
    error = check_note(resolution, "Resolution")
    if error:
        flash(error, "error")
        return redirect(url_for("ticket", ticket_id=ticket_id))

    with get_db() as conn:
        get_ticket_or_404(conn, ticket_id)
        set_status(conn, ticket_id, "Resolved", resolution)
        add_note(conn, ticket_id, f"Resolved: {resolution}")

    flash(f"Ticket #{ticket_id} resolved.", "ok")
    return redirect(url_for("index"))


# ---------------- Pages: knowledge, reports, SQL, health, guide ----------------

@app.route("/knowledge")
def knowledge():
    """Search past resolved tickets to reuse earlier fixes."""
    q = request.args.get("q", "").strip()
    with get_db() as conn:
        if q:
            term = f"%{q}%"
            rows = conn.execute("""
                SELECT * FROM tickets
                WHERE status = 'Resolved'
                  AND (issue LIKE ? OR resolution LIKE ? OR client LIKE ?
                       OR category LIKE ? OR email LIKE ? OR phone LIKE ?)
                ORDER BY updated DESC
            """, (term, term, term, term, term, term)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM tickets WHERE status = 'Resolved' ORDER BY updated DESC
            """).fetchall()
    return render_template("knowledge.html", rows=rows, q=q, page="knowledge")


def run_query(sql, read_only=False):
    """Run a SELECT and return (column names, rows)."""
    if read_only:
        # mode=ro: the database itself refuses any change
        conn = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=10)
    else:
        conn = sqlite3.connect(DB_FILE, timeout=10)
    try:
        cur = conn.execute(sql)
        cols = [c[0] for c in cur.description] if cur.description else []
        return cols, cur.fetchall()
    finally:
        conn.close()


@app.route("/reports")
def reports():
    """Run every report in queries.py and show the results as tables."""
    results = []
    for title, desc, sql in REPORTS:
        cols, rows = run_query(sql)
        results.append({"title": title, "desc": desc, "sql": sql.strip(),
                        "cols": cols, "rows": rows})
    return render_template("reports.html", results=results, page="reports")


@app.route("/sql", methods=["GET", "POST"])
def sql_console():
    """Let the user practise SQL. Only SELECT queries, on a read-only connection."""
    sql = request.form.get("sql", "").strip() or request.args.get("q", "").strip()
    cols, rows, error = [], [], None

    if sql:
        first_word = sql.split()[0].upper()
        if first_word not in ("SELECT", "WITH"):
            error = "Only SELECT queries are allowed here (this page is read-only)."
        else:
            try:
                cols, rows = run_query(sql, read_only=True)
            except sqlite3.Error as e:
                error = f"SQL error: {e}"

    return render_template("sql.html", sql=sql, cols=cols, rows=rows, error=error,
                           examples=EXAMPLE_QUERIES, page="sql")


@app.route("/health")
def health():
    """System check: is the app installed correctly, and is the data consistent?"""
    # 1. Installation checks: (name, passed?, detail)
    checks = [
        ("Python version 3.8 or later", sys.version_info >= (3, 8), sys.version.split()[0]),
        ("Database file found", os.path.exists(DB_FILE), os.path.abspath(DB_FILE)),
    ]
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

    # 2. Data integrity checks: each query should return no rows
    integrity = []
    for name, sql in INTEGRITY_CHECKS:
        try:
            _, rows = run_query(sql)
            integrity.append({"name": name, "sql": sql.strip(), "rows": rows,
                              "ok": len(rows) == 0})
        except sqlite3.Error as e:
            integrity.append({"name": name, "sql": sql.strip(), "rows": [],
                              "ok": False, "error": str(e)})

    all_ok = all(ok for _, ok, _ in checks) and all(i["ok"] for i in integrity)
    return render_template("health.html", checks=checks, integrity=integrity,
                           all_ok=all_ok, page="health")


@app.route("/guide")
def guide():
    """A short how-to guide for new users."""
    return render_template("guide.html", page="guide")


# ---------------- Start the app ----------------

if __name__ == "__main__":
    try:
        init_db()
    except sqlite3.OperationalError as e:
        if "locked" not in str(e):
            raise
        sys.exit(f"{DB_FILE} is locked. If DB Browser for SQLite is open, "
                 "click 'Write Changes' or close it, then run the app again.")
    app.run(debug=True)
