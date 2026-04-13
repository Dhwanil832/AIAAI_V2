from datetime import datetime

def format_report(session: dict, user_info: dict) -> dict:
    """
    Takes the session data and converts it into the final report structure
    ready to be saved to the database.
    """
    report = session.get("report", {})
    chat_history = session.get("chat_history", [])

    # Build the context document — full narrative saved alongside structured report
    context_document = {
        "chat_history": chat_history,
        "session_id": session.get("session_id", ""),
        "created_at": datetime.utcnow().isoformat(),
        "raw_report": report,
        "generated_summary": session.get("generated_summary", None),
    }

    return {
        "report_json": report,
        "context_document": context_document,
        "creator_name": user_info.get("name", "Unknown"),
        "creator_job_title": user_info.get("job", "Unknown"),
    }