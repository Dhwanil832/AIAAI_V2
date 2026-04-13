"""
corrective_actions.py
─────────────────────
Takes the list of similar incidents returned by the similarity search
and extracts, deduplicates, and ranks corrective action suggestions.

These are surfaced to the worker after report submission as clickable
chips so they can add proven corrective actions from past incidents
without having to know what to write.
"""

import re
from collections import Counter


# Actions shorter than this are too vague to be useful
MIN_ACTION_LENGTH = 8

# Hard cap on suggestions shown to the worker
MAX_SUGGESTIONS = 5

# Common filler words to skip when deduplicating
_STOP_FRAGMENTS = {
    "n/a", "na", "none", "unknown", "n.a.", "-", "tbd", "see above",
    "see report", "see attached", "no action", "no actions taken"
}


def _split_actions(raw: str) -> list[str]:
    """
    Split a raw actions_taken string into individual action items.
    Handles comma-separated, semicolon-separated, and numbered lists.
    """
    if not raw or not isinstance(raw, str):
        return []

    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"^\s*\d+[\.\)]\s*", "", raw, flags=re.MULTILINE)

    if ";" in raw:
        parts = [p.strip() for p in raw.split(";")]
    elif "\n" in raw:
        parts = [p.strip() for p in raw.split("\n")]
    else:
        parts = [p.strip() for p in raw.split(",")]

    return [p for p in parts if p]


def _normalize(action: str) -> str:
    """
    Lowercase, strip punctuation from ends, collapse whitespace.
    Used for deduplication comparisons only — not for display.
    """
    action = action.lower().strip()
    action = re.sub(r"[.!?,;:]+$", "", action)
    action = re.sub(r"\s+", " ", action)
    return action


def _is_useful(action: str) -> bool:
    """
    Filter out actions that are too short, too vague, or placeholder text.
    """
    if len(action) < MIN_ACTION_LENGTH:
        return False
    if _normalize(action) in _STOP_FRAGMENTS:
        return False
    return True


def get_corrective_action_suggestions(similar_incidents: list) -> list[str]:
    """
    Extract and rank corrective action suggestions from similar incidents.

    Steps:
    1. Pull actions_taken from each similar incident
    2. Split compound action strings into individual items
    3. Filter out vague or empty entries
    4. Deduplicate using normalized text as key (preserve original casing for display)
    5. Rank by frequency — actions that appear in multiple incidents rank higher
    6. Return top MAX_SUGGESTIONS

    Returns a list of action strings ready to display as chips.
    """
    if not similar_incidents:
        return []

    freq: Counter = Counter()
    display_map: dict[str, str] = {}

    for incident in similar_incidents:
        raw = incident.get("actions_taken", "") or ""
        items = _split_actions(raw)

        for item in items:
            if not _is_useful(item):
                continue
            key = _normalize(item)
            freq[key] += 1
            if key not in display_map or len(item) > len(display_map[key]):
                display_map[key] = item

    if not freq:
        return []

    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    suggestions = [display_map[key] for key, _ in ranked[:MAX_SUGGESTIONS]]

    print(f"[corrective_actions] {len(suggestions)} suggestions from {len(similar_incidents)} similar incidents")
    return suggestions