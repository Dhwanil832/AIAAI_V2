REQUIRED_FIELDS = {
    "basic_info": ["datetime", "shift", "location", "person_involved", "person_type", "incident_type", "actions_taken", "severity"],
    "injury_data": ["accident_type", "accident_agent", "injury_type", "injury_agent", "sif_case"],
    "near_miss_data": ["sif_case", "life_saving_rules"],
    "equipment_damage_data": ["damage_amount", "activity_type", "incident_activity", "incident_agent"]
}

def check_flags(report: dict, incident_type: str) -> tuple[bool, str]:
    """
    Returns (is_flagged, flag_reason).
    Flagged if 3 or more required fields are empty.
    """
    skip_count = 0
    skipped_fields = []

    sections = ["basic_info"]
    if incident_type == "Personal Injuries":
        sections.append("injury_data")
    elif incident_type == "Near Miss":
        sections.append("near_miss_data")
    elif incident_type == "Equipment Damage":
        sections.append("equipment_damage_data")

    for section in sections:
        fields = REQUIRED_FIELDS.get(section, [])
        for field in fields:
            value = report.get(section, {}).get(field, "")
            if value == "" or value is None:
                skip_count += 1
                skipped_fields.append(field.replace("_", " ").title())

    if skip_count >= 3:
        return True, f"Multiple skipped fields: {', '.join(skipped_fields[:5])}"

    return False, ""