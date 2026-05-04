"""
notifier.py
───────────
Creates in-app notification records for users.

Triggers:
1. Report submitted → notify all admins (supervisor alert)
2. Report status → needs_more_info → notify the reporter
3. Witness nominated → notify the nominated witness
"""

from sqlalchemy.orm import Session
from models.notification import Notification
from models.user import User


def notify_admins_on_submit(report_id: int, incident_type: str, location: str, db: Session) -> None:
    """
    Notify all active admins when a new report is submitted.
    Called from routers/chat.py after db.commit().
    """
    try:
        admins = db.query(User).filter(
            User.role == "admin",
            User.is_active == True
        ).all()

        message = f"New {incident_type} report #{report_id} submitted"
        if location:
            message += f" — {location}"

        for admin in admins:
            notif = Notification(
                user_id=admin.id,
                message=message,
                report_id=report_id,
            )
            db.add(notif)

        db.commit()
        print(f"[notifier] notified {len(admins)} admin(s) about report #{report_id}")

    except Exception as e:
        print(f"[notifier] failed to notify admins: {e}")


def notify_reporter_needs_info(report_id: int, reporter_user_id: int, review_note: str, db: Session) -> None:
    """
    Notify the reporter when an admin marks their report as needs_more_info.
    Called from routers/reports.py after status update.
    """
    try:
        message = f"Report #{report_id} needs more information"
        if review_note:
            preview = review_note[:80] + "..." if len(review_note) > 80 else review_note
            message += f": {preview}"

        notif = Notification(
            user_id=reporter_user_id,
            message=message,
            report_id=report_id,
        )
        db.add(notif)
        db.commit()
        print(f"[notifier] notified user {reporter_user_id} about report #{report_id} needing info")

    except Exception as e:
        print(f"[notifier] failed to notify reporter: {e}")


def notify_witness_nominated(
    report_id: int,
    witness_user_id: int,
    person_involved: str,
    location: str,
    datetime_str: str,
    db: Session
) -> None:
    """
    Notify a user that they have been nominated as a witness to an incident.
    Called from routers/reports.py POST /{report_id}/nominate-witness.

    The notification message contains only: person involved, location, date.
    No narrative, no summary — to avoid anchoring the witness's account.
    """
    try:
        parts = []
        if person_involved:
            parts.append(f"involving {person_involved}")
        if location:
            parts.append(f"at {location}")
        if datetime_str:
            parts.append(f"on {datetime_str}")

        context = " ".join(parts) if parts else f"on report #{report_id}"
        message = f"You were nominated as a witness to an incident {context}. Please share your account."

        notif = Notification(
            user_id=witness_user_id,
            message=message,
            report_id=report_id,
            notification_type="witness",
        )
        db.add(notif)
        db.commit()
        print(f"[notifier] notified witness user {witness_user_id} for report #{report_id}")

    except Exception as e:
        print(f"[notifier] failed to notify witness: {e}")