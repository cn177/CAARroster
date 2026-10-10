"""表单解析：把 request.form 变成模型层需要的字典，含技能 0-5 的收集。"""
from skills import SKILL_KEYS, parse_age

MEMBER_TEXT_FIELDS = [
    "name", "real_name", "contact_qq", "contact_discord", "contact_email", "phone",
    "best_result", "notes", "status",
]


def _int(form, key, default=None):
    raw = form.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def parse_member_form(form) -> dict:
    data = {field: (form.get(field) or "").strip() for field in MEMBER_TEXT_FIELDS}
    data["experience"] = form.get("experience") or "newbie"
    data["intent"] = form.get("intent") or "any"
    data["sleep_schedule"] = form.get("sleep_schedule") or "flexible"
    data["hunts_played"] = _int(form, "hunts_played", 0)
    data["mentor_capacity"] = _int(form, "mentor_capacity", 0)
    data["hours_available"] = _int(form, "hours_available", None)
    data["age"] = parse_age(form.get("age"))
    data["wants_mentor"] = 1 if form.get("wants_mentor") else 0
    data["voice_ok"] = 1 if form.get("voice_ok") else 0

    skills = {}
    for key in SKILL_KEYS:
        value = _int(form, f"skill_{key}", 0) or 0
        if value > 0:
            skills[key] = max(1, min(5, value))
    data["skills"] = skills
    if not data.get("status"):
        data["status"] = "active"
    return data


def parse_team_form(form) -> dict:
    return {
        "name": (form.get("name") or "").strip(),
        "kind": form.get("kind") or "casual",
        "captain_id": _int(form, "captain_id", None),
        "pitch": (form.get("pitch") or "").strip(),
        "goal": (form.get("goal") or "").strip(),
        "capacity": _int(form, "capacity", 6),
        "newbie_quota": _int(form, "newbie_quota", 2),
        "voice_required": 1 if form.get("voice_required") else 0,
        "status": form.get("status") or "recruiting",
    }


def parse_event_form(form) -> dict:
    return {
        "name": (form.get("name") or "").strip(),
        "slug": (form.get("slug") or "").strip(),
        "kind": form.get("kind") or "external",
        "start_date": (form.get("start_date") or "").strip(),
        "end_date": (form.get("end_date") or "").strip(),
        "team_size_min": _int(form, "team_size_min", 1),
        "team_size_max": _int(form, "team_size_max", 6),
        "reg_deadline": (form.get("reg_deadline") or "").strip(),
        "url": (form.get("url") or "").strip(),
        "notes": (form.get("notes") or "").strip(),
    }
