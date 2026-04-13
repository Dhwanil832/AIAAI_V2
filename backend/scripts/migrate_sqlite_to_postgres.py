import sqlite3
import psycopg2
import json

SQLITE_PATH = r"C:\Users\chauha56\Desktop\New folder\safety-chatbot\backend\safety_chatbot.db"

PG_CONN = {
    "host": "localhost",
    "port": 5432,
    "database": "safety_chatbot_db",
    "user": "postgres",
    "password": "admin123"  # change to your password
}

def migrate():
    print("Connecting to SQLite...")
    sqlite = sqlite3.connect(SQLITE_PATH)
    sqlite.row_factory = sqlite3.Row

    print("Connecting to PostgreSQL...")
    pg = psycopg2.connect(**PG_CONN)
    pg_cursor = pg.cursor()

    # ── Users ─────────────────────────────────────────────────────────────────
    print("\nMigrating users...")
    rows = sqlite.execute("SELECT * FROM users").fetchall()
    success = 0
    for row in rows:
        try:
            pg_cursor.execute("""
                INSERT INTO users (id, username, email, hashed_password, role, job_title, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (
                row["id"], row["username"], row["email"],
                row["hashed_password"], row["role"], row["job_title"],
                bool(row["is_active"]), row["created_at"]
            ))
            pg.commit()
            success += 1
        except Exception as e:
            pg.rollback()
            print(f"  User {row['username']} error: {e}")
    print(f"  {success}/{len(rows)} users migrated")

    # ── Incident Reports ───────────────────────────────────────────────────────
    print("\nMigrating incident reports...")
    rows = sqlite.execute("SELECT * FROM incident_reports").fetchall()
    success = 0
    for row in rows:
        try:
            report_json = row["report_json"]
            if isinstance(report_json, str):
                report_json = json.loads(report_json)

            context_doc = row["context_document"]
            if isinstance(context_doc, str) and context_doc:
                context_doc = json.loads(context_doc)

            similar = row["similar_incidents"] if "similar_incidents" in row.keys() else None
            if isinstance(similar, str) and similar:
                similar = json.loads(similar)

            pg_cursor.execute("""
                INSERT INTO incident_reports (
                    id, user_id, report_json, context_document,
                    creator_name, creator_job_title,
                    last_modified_name, last_modified_job,
                    flagged, flag_reason, similar_incidents, supervisor_notified,
                    status, review_note, reviewed_by, reviewed_at,
                    created_at, last_modified_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (
                row["id"], row["user_id"],
                json.dumps(report_json),
                json.dumps(context_doc) if context_doc else None,
                row["creator_name"], row["creator_job_title"],
                row["last_modified_name"], row["last_modified_job"],
                bool(row["flagged"]), row["flag_reason"],
                json.dumps(similar) if similar else None,
                bool(row["supervisor_notified"]) if "supervisor_notified" in row.keys() else False,
                row["status"] if "status" in row.keys() else "submitted",
                row["review_note"] if "review_note" in row.keys() else None,
                row["reviewed_by"] if "reviewed_by" in row.keys() else None,
                row["reviewed_at"] if "reviewed_at" in row.keys() else None,
                row["created_at"], row["last_modified_at"]
            ))
            pg.commit()
            success += 1
        except Exception as e:
            pg.rollback()
            print(f"  Report {row['id']} error: {e}")
    print(f"  {success}/{len(rows)} reports migrated")

    # ── Unfinished Reports ─────────────────────────────────────────────────────
    print("\nMigrating unfinished reports...")
    rows = sqlite.execute("SELECT * FROM unfinished_reports").fetchall()
    success = 0
    for row in rows:
        try:
            report_json = row["report_json"] if "report_json" in row.keys() else None
            chat_history = row["chat_history"] if "chat_history" in row.keys() else None

            pg_cursor.execute("""
                INSERT INTO unfinished_reports (
                    id, user_id, session_id, report_json, chat_history,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (
                row["id"], row["user_id"], row["session_id"],
                report_json, chat_history,
                row["created_at"] if "created_at" in row.keys() else None,
                row["updated_at"] if "updated_at" in row.keys() else None,
            ))
            pg.commit()
            success += 1
        except Exception as e:
            pg.rollback()
            print(f"  Unfinished {row['id']} error: {e}")
    print(f"  {success}/{len(rows)} unfinished reports migrated")

    pg_cursor.close()
    pg.close()
    sqlite.close()
    print("\nMigration complete.")

if __name__ == "__main__":
    migrate()