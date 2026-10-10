"""
Load sample tickets so the reports have data to show.
Run once:  python seed.py
(It clears the existing tickets and notes first.)
"""

from datetime import datetime, timedelta
import app

now = datetime.now()


def ts(hours_ago):
    return (now - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M")


# Contact details for each sample client (email, NZ phone)
CONTACTS = {
    "Harbour Securities": ("support@harboursecurities.co.nz", "+64 93021455"),
    "Southern Brokers": ("ops@southernbrokers.co.nz", "+64 34778120"),
    "Kiwi Wealth": ("helpdesk@kiwiwealth.co.nz", "+64 211234567"),
    "Tasman Capital": ("it@tasmancapital.co.nz", "+64 45550198"),
    "Pacific Wealth Partners": ("admin@pacificwealth.co.nz", "+64 2758812345"),
}

# client, channel, category, priority, issue, hours ago logged,
# status, resolution, hours ago resolved, extra notes
SAMPLES = [
    ("Harbour Securities", "Phone", "Login / Access", "High",
     "User locked out after getting a new phone (MFA)", 200, "Resolved",
     "Verified identity, reset MFA. User re-enrolled and confirmed login works.", 198,
     ["Verified caller identity with security questions."]),
    ("Southern Brokers", "Email", "Settlement", "High",
     "Today's trades are not settling", 6, "Escalated", None, None,
     ["Affects all of this client's trades today. Other clients fine.",
      "Escalated to engineering: settlement batch failing since 9am. Deadline 4pm."]),
    ("Kiwi Wealth", "Email", "Report", "Low",
     "Contract note shows wrong brokerage fee", 30, "Open", None, None, []),
    ("Tasman Capital", "In person", "Installation / Configuration", "Medium",
     "Upgrade failed on client's own server", 20, "In progress", None, None,
     ["Server meets requirements. Upgrade log shows database connection timeout."]),
    ("Harbour Securities", "Email", "Report", "Medium",
     "Month-end holdings report missing two accounts", 150, "Resolved",
     "Accounts were filtered out by report settings. Updated filter and re-ran.", 140,
     ["Reproduced with client's report settings."]),
    ("Pacific Wealth Partners", "Phone", "Login / Access", "Medium",
     "Password expired, can't reset", 120, "Resolved",
     "Reset password after identity check. Sent guide on self-service reset.", 119, []),
    ("Southern Brokers", "Phone", "Settlement", "High",
     "Dividend applied to wrong share quantity", 300, "Resolved",
     "Holding was wrong before record date. Engineering corrected holding and re-ran dividend.", 280,
     ["Checked holding on record date - incorrect.",
      "Escalated to engineering with trade history."]),
    ("Kiwi Wealth", "Phone", "Other", "Low",
     "How do I export client list to Excel?", 90, "Resolved",
     "Walked client through export option and sent the user guide page.", 89, []),
    ("Tasman Capital", "Email", "Login / Access", "High",
     "No users can log in this morning", 60, "Resolved",
     "Client firewall change blocked the system. Client IT reversed the change.", 57,
     ["All users at one site affected. Other clients fine.",
      "Asked client IT about recent network changes."]),
    ("Pacific Wealth Partners", "Email", "Report", "Low",
     "Report layout cut off when printing", 10, "Open", None, None, []),
    ("Harbour Securities", "In person", "Installation / Configuration", "Medium",
     "New staff member needs access set up", 48, "Resolved",
     "Created user with correct role and permissions. Confirmed access.", 46, []),
    ("Kiwi Wealth", "Email", "Settlement", "Medium",
     "Settlement report shows a trade twice", 4, "In progress", None, None,
     ["Checked database - trade recorded once. Looking at report query."]),
]


def seed():
    app.init_db()
    with app.get_db() as conn:
        conn.execute("DELETE FROM notes")
        conn.execute("DELETE FROM tickets")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('tickets', 'notes')")
        for (client, channel, category, priority, issue, logged, status,
             resolution, resolved_ago, notes) in SAMPLES:
            created = ts(logged)
            resolved = ts(resolved_ago) if resolved_ago is not None else None
            updated = resolved or ts(max(logged - 1, 0))
            email, phone = CONTACTS.get(client, (None, None))
            cur = conn.execute(
                "INSERT INTO tickets (client, email, phone, channel, category, priority, issue, "
                "status, resolution, created, updated, resolved) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client, email, phone, channel, category, priority, issue, status,
                 resolution, created, updated, resolved))
            tid = cur.lastrowid
            conn.execute("INSERT INTO notes (ticket_id, note, created) VALUES (?, ?, ?)",
                         (tid, f"Ticket logged via {channel}.", created))
            for i, n in enumerate(notes):
                conn.execute("INSERT INTO notes (ticket_id, note, created) VALUES (?, ?, ?)",
                             (tid, n, ts(logged - 0.5 * (i + 1))))
            if resolution:
                conn.execute("INSERT INTO notes (ticket_id, note, created) VALUES (?, ?, ?)",
                             (tid, f"Resolved: {resolution}", resolved))
    print(f"Loaded {len(SAMPLES)} sample tickets.")


if __name__ == "__main__":
    seed()
