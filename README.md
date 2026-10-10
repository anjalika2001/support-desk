# Support Desk

A small ticketing web app that follows a first-line support workflow:
log -> diagnose -> escalate -> resolve -> reuse the fix -> report on it.
Built with Python (Flask) and SQLite.

## Run it
```
pip install flask
python seed.py      (optional: loads sample tickets)
python app.py
```
Open http://localhost:5000. Press Ctrl + C to stop.

## Features
| Feature | What it does |
|---|---|
| Log a ticket | Client, contact email and NZ phone (+64, both optional but format-checked), channel (phone / email / in person), category, priority, issue |
| Active queue | Unresolved tickets, most urgent first |
| Ticket history | Every diagnosis note, status change and escalation is timestamped |
| Escalate | Hand over to engineering with steps to reproduce and impact |
| Resolve | Requires a resolution note so every fix is documented |
| Knowledge base | Search past fixes before solving a new problem |
| Reports | SQL reports: by client, category/priority, time to resolve, oldest tickets, channels |
| SQL practice | Run your own read-only SELECT queries against the data |
| System check | Installation check plus SQL data integrity checks |
| User guide | Short training guide for new users |

## How it is built (three tiers)
| Layer | Files | Job |
|---|---|---|
| Front end | `templates/`, `static/style.css` | Pages the user sees |
| Logic | `app.py` | Routes, validation, SQL |
| Data | `support.db` (created on first run) | Tables `tickets` and `notes` |

## SQL used
INSERT, SELECT, UPDATE, WHERE, ORDER BY, GROUP BY, COUNT, SUM, AVG, CASE,
LEFT JOIN / JOIN, subqueries, LIKE search, and date maths with julianday().
All user input goes through `?` placeholders to prevent SQL injection.
