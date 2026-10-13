"""
SQL used by the Reports, System check and SQL practice pages.
Kept here so app.py only contains the app logic.
"""

# Reports page: (title, description, SQL)
REPORTS = [
    ("Tickets by client",
     "How many tickets each client has raised, and how many are still active.",
     """
SELECT client                                                AS "Client",
       COUNT(*)                                              AS "Total",
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

# System check page: each query should return NO rows.
# Any row returned is a data problem to fix.
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

# SQL practice page: clickable examples
EXAMPLE_QUERIES = [
    "SELECT * FROM tickets",
    "SELECT * FROM notes WHERE ticket_id = 1",
    "SELECT status, COUNT(*) FROM tickets GROUP BY status",
    "SELECT client, issue FROM tickets WHERE priority = 'High' AND status != 'Resolved'",
    "SELECT t.id, t.client, n.created, n.note FROM tickets t JOIN notes n ON n.ticket_id = t.id ORDER BY t.id, n.id",
]
