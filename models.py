"""数据访问层：所有 SQL 都集中在这里，视图只调用函数，方便以后换数据库。"""
import json

from config import (
    DEFAULT_NEWBIE_QUOTA,
    DEFAULT_TEAM_CAPACITY,
    MEMBER_CODE_PREFIX,
)
from db import get_db, log, next_member_code, now

MEMBER_FIELDS = [
    "name", "real_name", "contact_qq", "contact_discord", "contact_email", "phone",
    "age", "experience", "hunts_played", "best_result", "intent", "wants_mentor",
    "mentor_capacity", "hours_available", "sleep_schedule", "voice_ok",
    "skills", "notes", "status",
]

INT_FIELDS = {"hunts_played", "wants_mentor", "mentor_capacity", "hours_available",
              "voice_ok", "age"}

# 程序化建人（脚本、测试、以后的 API）时，没传的字段用这些兜底。
# 不兜底的话会把 None 塞进 NOT NULL 列，报一个很难懂的 sqlite3.IntegrityError。
MEMBER_DEFAULTS = {
    "experience": "newbie",
    "intent": "any",
    "sleep_schedule": "flexible",
    "status": "active",
    "skills": {},
    "hunts_played": 0,
    "wants_mentor": 0,
    "mentor_capacity": 0,
    "voice_ok": 1,
}


# ================================================================== 成员
def _row_to_member(row) -> dict:
    if row is None:
        return None
    data = dict(row)
    try:
        data["skills"] = json.loads(data.get("skills") or "{}")
    except (TypeError, ValueError):
        data["skills"] = {}
    return data


def member_select_sql() -> str:
    return """
    SELECT m.*,
           t.id   AS team_id,
           t.name AS team_name,
           t.kind AS team_kind,
           tm.role AS team_role
      FROM members m
      LEFT JOIN team_members tm ON tm.member_id = m.id AND tm.left_at IS NULL
      LEFT JOIN teams t        ON t.id = tm.team_id
    """


def list_members(search="", experience="", intent="", assignment="", status="active", limit=None):
    sql = member_select_sql() + " WHERE 1=1"
    params: list = []
    if status:
        if status == "all":
            pass
        else:
            sql += " AND m.status = ?"
            params.append(status)
    if search:
        sql += (" AND (m.name LIKE ? OR m.code LIKE ? OR m.real_name LIKE ?"
                " OR m.contact_qq LIKE ? OR m.contact_discord LIKE ? OR m.notes LIKE ?)")
        like = f"%{search}%"
        params.extend([like] * 6)
    if experience:
        sql += " AND m.experience = ?"
        params.append(experience)
    if intent:
        sql += " AND m.intent = ?"
        params.append(intent)
    if assignment == "free":
        sql += " AND t.id IS NULL"
    elif assignment == "assigned":
        sql += " AND t.id IS NOT NULL"
    sql += " ORDER BY m.experience DESC, m.id ASC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [_row_to_member(r) for r in get_db().execute(sql, params).fetchall()]


def get_member(member_id: int):
    row = get_db().execute(member_select_sql() + " WHERE m.id = ?", (member_id,)).fetchone()
    return _row_to_member(row)


def get_member_by_code(code: str):
    row = get_db().execute(member_select_sql() + " WHERE m.code = ?", (code,)).fetchone()
    return _row_to_member(row)


def member_history(member_id: int):
    rows = get_db().execute(
        """SELECT tm.*, t.name AS team_name, t.kind AS team_kind
             FROM team_members tm JOIN teams t ON t.id = tm.team_id
            WHERE tm.member_id = ?
            ORDER BY tm.joined_at DESC""",
        (member_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def find_duplicate(name="", phone="", qq="", discord="", email="", exclude_id=None):
    """导入时的去重：手机 > QQ > Discord > 邮箱 > 昵称，逐个尝试。"""
    db = get_db()
    for column, value in (("phone", phone), ("contact_qq", qq),
                          ("contact_discord", discord), ("contact_email", email)):
        if value:
            row = db.execute(
                f"SELECT * FROM members WHERE {column} = ? AND {column} != ''", (value,)
            ).fetchone()
            if row and row["id"] != exclude_id:
                return row
    if name:
        row = db.execute("SELECT * FROM members WHERE name = ?", (name,)).fetchone()
        if row and row["id"] != exclude_id:
            return row
    return None


def create_member(data: dict, actor: str = "", batch_id=None) -> int:
    db = get_db()
    payload = {}
    for field in MEMBER_FIELDS:
        value = data.get(field)
        if value is None or value == "":
            if field in MEMBER_DEFAULTS:
                value = MEMBER_DEFAULTS[field]
        payload[field] = value
    payload["name"] = (payload.get("name") or "").strip() or "未命名"
    for f in INT_FIELDS:
        if payload.get(f) in (None, ""):
            payload[f] = 0 if f not in ("hours_available", "age") else None
        else:
            payload[f] = int(payload[f])
    if not payload.get("mentor_capacity"):
        payload["mentor_capacity"] = 0
    if isinstance(payload.get("skills"), (dict, list)):
        payload["skills"] = json.dumps(payload["skills"], ensure_ascii=False)
    elif not payload.get("skills"):
        payload["skills"] = "{}"
    if not payload.get("status"):
        payload["status"] = "active"

    stamp = now()
    columns = ["code"] + MEMBER_FIELDS + ["source_batch", "created_at", "updated_at"]
    values = [next_member_code(db, MEMBER_CODE_PREFIX)] + [payload[f] for f in MEMBER_FIELDS]
    values += [batch_id, stamp, stamp]
    placeholders = ",".join("?" * len(columns))
    cur = db.execute(
        f"INSERT INTO members({','.join(columns)}) VALUES({placeholders})", values
    )
    member_id = cur.lastrowid
    log(db, actor, "member.create", f"member:{member_id}", payload)
    db.commit()
    return member_id


def update_member(member_id: int, data: dict, actor: str = "") -> None:
    db = get_db()
    payload = {f: data.get(f) for f in MEMBER_FIELDS if f in data}
    for f in INT_FIELDS:
        if f in payload:
            payload[f] = 0 if payload[f] in (None, "") else int(payload[f])
    if "skills" in payload and isinstance(payload["skills"], (dict, list)):
        payload["skills"] = json.dumps(payload["skills"], ensure_ascii=False)
    if not payload:
        return
    payload["updated_at"] = now()
    assignments = ",".join(f"{k}=?" for k in payload)
    db.execute(f"UPDATE members SET {assignments} WHERE id=?", [*payload.values(), member_id])
    log(db, actor, "member.update", f"member:{member_id}", payload)
    db.commit()


def delete_member(member_id: int, actor: str = "") -> None:
    db = get_db()
    db.execute("DELETE FROM members WHERE id=?", (member_id,))
    log(db, actor, "member.delete", f"member:{member_id}")
    db.commit()


def member_stats() -> dict:
    db = get_db()
    total = db.execute("SELECT COUNT(*) c FROM members WHERE status='active'").fetchone()["c"]
    by_exp = {r["experience"]: r["c"] for r in db.execute(
        "SELECT experience, COUNT(*) c FROM members WHERE status='active' GROUP BY experience"
    ).fetchall()}
    by_intent = {r["intent"]: r["c"] for r in db.execute(
        "SELECT intent, COUNT(*) c FROM members WHERE status='active' GROUP BY intent"
    ).fetchall()}
    assigned = db.execute(
        """SELECT COUNT(*) c FROM members m
            JOIN team_members tm ON tm.member_id=m.id AND tm.left_at IS NULL
           WHERE m.status='active'"""
    ).fetchone()["c"]
    teams = db.execute("SELECT COUNT(*) c FROM teams WHERE status != 'archived'").fetchone()["c"]
    return {
        "total": total,
        "newbie": by_exp.get("newbie", 0),
        "veteran": by_exp.get("veteran", 0),
        "elite": by_exp.get("elite", 0),
        "by_exp": by_exp,
        "by_intent": by_intent,
        "assigned": assigned,
        "unassigned": total - assigned,
        "teams": teams,
    }


# ================================================================== 队伍
def list_teams(kind="", status="", search=""):
    sql = """
    SELECT t.*,
           c.name AS captain_name,
           (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id=t.id AND tm.left_at IS NULL) AS size,
           (SELECT COUNT(*) FROM team_members tm JOIN members m ON m.id=tm.member_id
             WHERE tm.team_id=t.id AND tm.left_at IS NULL AND m.experience='newbie') AS newbie_count,
           (SELECT COUNT(*) FROM team_members tm JOIN members m ON m.id=tm.member_id
             WHERE tm.team_id=t.id AND tm.left_at IS NULL AND m.experience!='newbie') AS veteran_count
      FROM teams t
      LEFT JOIN members c ON c.id = t.captain_id
     WHERE 1=1
    """
    params: list = []
    if kind:
        sql += " AND t.kind = ?"
        params.append(kind)
    if status:
        sql += " AND t.status = ?"
        params.append(status)
    if search:
        sql += " AND t.name LIKE ?"
        params.append(f"%{search}%")
    sql += " ORDER BY CASE t.kind WHEN 'competitive' THEN 0 WHEN 'mentor' THEN 1 ELSE 2 END, t.id"
    return [dict(r) for r in get_db().execute(sql, params).fetchall()]


def get_team(team_id: int):
    row = get_db().execute(
        """SELECT t.*, c.name AS captain_name,
                  (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id=t.id AND tm.left_at IS NULL) AS size
             FROM teams t LEFT JOIN members c ON c.id=t.captain_id WHERE t.id=?""",
        (team_id,),
    ).fetchone()
    return dict(row) if row else None


def team_roster(team_id: int, active_only=True):
    sql = """
    SELECT tm.id AS membership_id, tm.role AS team_role, tm.joined_at, tm.left_at,
           m.*
      FROM team_members tm JOIN members m ON m.id = tm.member_id
     WHERE tm.team_id = ?
    """
    if active_only:
        sql += " AND tm.left_at IS NULL"
    sql += " ORDER BY CASE tm.role WHEN 'captain' THEN 0 WHEN 'mentor' THEN 1 ELSE 2 END, m.id"
    return [_row_to_member(r) for r in get_db().execute(sql, (team_id,)).fetchall()]


def create_team(data: dict, actor: str = "") -> int:
    db = get_db()
    stamp = now()
    cur = db.execute(
        """INSERT INTO teams(name, kind, captain_id, pitch, goal, capacity, newbie_quota,
                             voice_required, status, created_at, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            (data.get("name") or "").strip() or "未命名队伍",
            data.get("kind") or "casual",
            data.get("captain_id") or None,
            data.get("pitch") or "",
            data.get("goal") or "",
            int(data.get("capacity") or DEFAULT_TEAM_CAPACITY),
            int(data.get("newbie_quota") if data.get("newbie_quota") not in (None, "")
                else DEFAULT_NEWBIE_QUOTA),
            1 if data.get("voice_required") else 0,
            data.get("status") or "recruiting",
            stamp, stamp,
        ),
    )
    team_id = cur.lastrowid
    log(db, actor, "team.create", f"team:{team_id}", data)
    db.commit()
    if data.get("captain_id"):
        set_captain(team_id, int(data["captain_id"]), actor)
    return team_id


def update_team(team_id: int, data: dict, actor: str = "") -> None:
    db = get_db()
    fields = ["name", "kind", "captain_id", "pitch", "goal", "capacity",
              "newbie_quota", "voice_required", "status"]
    payload = {}
    for f in fields:
        if f in data:
            value = data[f]
            if f in ("capacity", "newbie_quota"):
                value = int(value or 0)
            elif f in ("voice_required",):
                value = 1 if value else 0
            elif f == "captain_id":
                value = int(value) if value else None
            payload[f] = value
    if not payload:
        return
    payload["updated_at"] = now()
    db.execute(
        f"UPDATE teams SET {','.join(f'{k}=?' for k in payload)} WHERE id=?",
        [*payload.values(), team_id],
    )
    log(db, actor, "team.update", f"team:{team_id}", payload)
    db.commit()
    if payload.get("captain_id"):
        set_captain(team_id, payload["captain_id"], actor)


def delete_team(team_id: int, actor: str = "") -> None:
    db = get_db()
    db.execute("DELETE FROM teams WHERE id=?", (team_id,))
    log(db, actor, "team.delete", f"team:{team_id}")
    db.commit()


class TeamLimitError(Exception):
    """加入队伍会超出人数上限或新手名额。调用方负责把它变成给用户看的提示。"""


def team_slots(team_id: int) -> dict:
    """这支队伍还剩多少位置：总人数 + 新手名额。"""
    db = get_db()
    team = db.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
    if not team:
        return {}
    row = db.execute(
        """SELECT COUNT(*) AS size,
                  COALESCE(SUM(CASE WHEN m.experience='newbie' THEN 1 ELSE 0 END), 0) AS newbies
             FROM team_members tm JOIN members m ON m.id = tm.member_id
            WHERE tm.team_id=? AND tm.left_at IS NULL""",
        (team_id,),
    ).fetchone()
    size = row["size"] or 0
    newbies = row["newbies"] or 0
    capacity = int(team["capacity"] or 0)
    quota = int(team["newbie_quota"] or 0)
    return {
        "team": dict(team),
        "size": size,
        "capacity": capacity,
        "remaining": capacity - size,
        "newbies": newbies,
        "newbie_quota": quota,
        "newbie_remaining": quota - newbies,
    }


def team_limit_problem(team_id: int, member_id: int) -> str | None:
    """把这个人放进这支队伍会不会超限？返回拒绝原因，None 表示可以加。

    人数上限和新手名额是运营自己声明的约束，写操作必须真的守住 ——
    否则推荐算法里那些"名额已满"的提示就只是装饰品。
    """
    db = get_db()
    slots = team_slots(team_id)
    if not slots:
        return "队伍不存在。"
    already = db.execute(
        "SELECT 1 FROM team_members WHERE team_id=? AND member_id=? AND left_at IS NULL",
        (team_id, member_id),
    ).fetchone()
    if already:
        return None  # 已经在队里，不算新增

    name = slots["team"]["name"]
    if slots["remaining"] <= 0:
        return (f"「{name}」人数已满（{slots['size']}/{slots['capacity']}）。"
                f"确实要加就先调高这支队伍的人数上限，或者先移出一个人。")
    member = db.execute("SELECT experience FROM members WHERE id=?", (member_id,)).fetchone()
    if member and member["experience"] == "newbie" and slots["newbie_remaining"] <= 0:
        return (f"「{name}」的新手名额已满（{slots['newbies']}/{slots['newbie_quota']}）。"
                f"想让它多带新手，就先把新手名额调高。")
    return None


def add_to_team(team_id: int, member_id: int, role: str = "", actor: str = "",
                enforce_limits: bool = True) -> str:
    """把成员放进队伍。返回 'ok' / 'already' / 'moved'。

    超编或新手名额满时抛 TeamLimitError。只有明确知道自己在绕过的场景
    （比如指定队长）才传 enforce_limits=False。
    """
    if enforce_limits:
        problem = team_limit_problem(team_id, member_id)
        if problem:
            raise TeamLimitError(problem)

    db = get_db()
    current = db.execute(
        "SELECT * FROM team_members WHERE member_id=? AND left_at IS NULL", (member_id,)
    ).fetchone()
    if current and current["team_id"] == team_id:
        return "already"
    status = "ok"
    if current:
        # 换队：旧的记录留痕，不直接删，保留历史
        db.execute("UPDATE team_members SET left_at=? WHERE id=?", (now(), current["id"]))
        status = "moved"
    if not role:
        member = db.execute("SELECT experience, mentor_capacity FROM members WHERE id=?",
                            (member_id,)).fetchone()
        role = "newbie" if (member and member["experience"] == "newbie") else "member"
    db.execute(
        "INSERT INTO team_members(team_id, member_id, role, joined_at) VALUES(?,?,?,?)",
        (team_id, member_id, role, now()),
    )
    log(db, actor, "team.add_member", f"team:{team_id}", {"member_id": member_id, "role": role})
    db.commit()
    return status


def remove_from_team(team_id: int, member_id: int, actor: str = "") -> None:
    db = get_db()
    db.execute(
        "UPDATE team_members SET left_at=? WHERE team_id=? AND member_id=? AND left_at IS NULL",
        (now(), team_id, member_id),
    )
    db.execute("UPDATE teams SET captain_id=NULL WHERE id=? AND captain_id=?",
               (team_id, member_id))
    log(db, actor, "team.remove_member", f"team:{team_id}", {"member_id": member_id})
    db.commit()


def set_member_role(team_id: int, member_id: int, role: str, actor: str = "") -> None:
    db = get_db()
    db.execute(
        "UPDATE team_members SET role=? WHERE team_id=? AND member_id=? AND left_at IS NULL",
        (role, team_id, member_id),
    )
    log(db, actor, "team.set_role", f"team:{team_id}", {"member_id": member_id, "role": role})
    db.commit()


def set_captain(team_id: int, member_id: int, actor: str = "") -> None:
    """队长必须同时在队里。换队长时把旧队长的角色降回普通成员。"""
    db = get_db()
    old = db.execute("SELECT captain_id FROM teams WHERE id=?", (team_id,)).fetchone()
    if old and old["captain_id"] and old["captain_id"] != member_id:
        db.execute(
            "UPDATE team_members SET role='member' WHERE team_id=? AND member_id=? AND left_at IS NULL",
            (team_id, old["captain_id"]),
        )
    db.execute("UPDATE teams SET captain_id=?, updated_at=? WHERE id=?",
               (member_id, now(), team_id))
    db.commit()
    # 指定队长是明确的人事决定，不该被人数和名额挡住 —— 建队时队长往往就是第一个进来的人。
    # 万一真的因此超编，队伍卡片和仪表盘上都会亮"超编"警告，看得见。
    add_to_team(team_id, member_id, role="captain", actor=actor, enforce_limits=False)
    set_member_role(team_id, member_id, "captain", actor)


def unassigned_members(experience="", intent="", search=""):
    sql = member_select_sql() + " WHERE m.status='active' AND t.id IS NULL"
    params: list = []
    if experience:
        sql += " AND m.experience = ?"
        params.append(experience)
    if intent:
        sql += " AND m.intent = ?"
        params.append(intent)
    if search:
        sql += " AND (m.name LIKE ? OR m.code LIKE ?)"
        params.extend([f"%{search}%"] * 2)
    sql += " ORDER BY CASE m.experience WHEN 'elite' THEN 0 WHEN 'veteran' THEN 1 ELSE 2 END, m.id"
    return [_row_to_member(r) for r in get_db().execute(sql, params).fetchall()]


def teams_with_roster(status="") -> list[dict]:
    """给匹配算法用的：每个队伍带上当前在队成员。"""
    teams = []
    for team in list_teams(status=status):
        team["roster"] = team_roster(team["id"])
        teams.append(team)
    return teams


# ================================================================== 赛事
def list_events():
    rows = get_db().execute(
        """SELECT e.*,
                  (SELECT COUNT(*) FROM event_teams et WHERE et.event_id=e.id) AS team_count
             FROM events e
            ORDER BY COALESCE(e.start_date, '9999') ASC, e.id DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_event(event_id: int):
    row = get_db().execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    return dict(row) if row else None


def create_event(data: dict, actor: str = "") -> int:
    db = get_db()
    cur = db.execute(
        """INSERT INTO events(name, slug, kind, start_date, end_date, team_size_min,
                              team_size_max, reg_deadline, url, notes, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            (data.get("name") or "").strip() or "未命名赛事",
            data.get("slug") or None,
            data.get("kind") or "external",
            data.get("start_date") or None,
            data.get("end_date") or None,
            int(data.get("team_size_min") or 1),
            int(data.get("team_size_max") or DEFAULT_TEAM_CAPACITY),
            data.get("reg_deadline") or None,
            data.get("url") or "",
            data.get("notes") or "",
            now(),
        ),
    )
    log(db, actor, "event.create", f"event:{cur.lastrowid}", data)
    db.commit()
    return cur.lastrowid


def update_event(event_id: int, data: dict, actor: str = "") -> None:
    fields = ["name", "slug", "kind", "start_date", "end_date", "team_size_min",
              "team_size_max", "reg_deadline", "url", "notes"]
    payload = {}
    nullable = ("slug", "start_date", "end_date", "reg_deadline")
    for f in fields:
        if f not in data:
            continue
        value = data[f]
        if f in ("team_size_min", "team_size_max"):
            value = int(value or 0)
        elif f in nullable:
            value = value or None
        else:
            value = value or ""
        payload[f] = value
    if not payload:
        return
    db = get_db()
    db.execute(f"UPDATE events SET {','.join(f'{k}=?' for k in payload)} WHERE id=?",
               [*payload.values(), event_id])
    log(db, actor, "event.update", f"event:{event_id}", payload)
    db.commit()


def delete_event(event_id: int, actor: str = "") -> None:
    db = get_db()
    db.execute("DELETE FROM events WHERE id=?", (event_id,))
    log(db, actor, "event.delete", f"event:{event_id}")
    db.commit()


def event_registrations(event_id: int):
    rows = get_db().execute(
        """SELECT et.*, t.name AS team_name, t.kind AS team_kind,
                  (SELECT COUNT(*) FROM team_members tm WHERE tm.team_id=t.id AND tm.left_at IS NULL) AS size
             FROM event_teams et JOIN teams t ON t.id = et.team_id
            WHERE et.event_id=? ORDER BY t.id""",
        (event_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def register_team(event_id: int, team_id: int, note="", actor: str = "") -> str:
    db = get_db()
    exists = db.execute("SELECT 1 FROM event_teams WHERE event_id=? AND team_id=?",
                        (event_id, team_id)).fetchone()
    if exists:
        return "already"
    roster = [{"code": m["code"], "name": m["name"], "role": m["team_role"]}
              for m in team_roster(team_id)]
    db.execute(
        """INSERT INTO event_teams(event_id, team_id, status, roster_snapshot, note, created_at)
           VALUES(?,?,?,?,?,?)""",
        (event_id, team_id, "registered",
         json.dumps(roster, ensure_ascii=False), note or "", now()),
    )
    log(db, actor, "event.register_team", f"event:{event_id}", {"team_id": team_id})
    db.commit()
    return "ok"


def unregister_team(event_id: int, team_id: int, actor: str = "") -> None:
    db = get_db()
    db.execute("DELETE FROM event_teams WHERE event_id=? AND team_id=?", (event_id, team_id))
    log(db, actor, "event.unregister_team", f"event:{event_id}", {"team_id": team_id})
    db.commit()


# ================================================================== 分配草案
DRAFT_KEY = "allocation_draft"


def save_draft(payload: dict, actor: str = "") -> None:
    """草案存在数据库里，不放 session —— session 是签名 cookie，塞不下几百条。"""
    db = get_db()
    db.execute(
        "INSERT INTO meta(key, value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (DRAFT_KEY, json.dumps(payload, ensure_ascii=False)),
    )
    log(db, actor, "assign.draft_create", "draft",
        {"count": len(payload.get("assignments", []))})
    db.commit()


def load_draft():
    row = get_db().execute("SELECT value FROM meta WHERE key=?", (DRAFT_KEY,)).fetchone()
    if not row or not row["value"]:
        return None
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return None


def clear_draft(actor: str = "") -> None:
    db = get_db()
    db.execute("DELETE FROM meta WHERE key=?", (DRAFT_KEY,))
    log(db, actor, "assign.draft_clear", "draft")
    db.commit()


# ================================================================== 日志
def recent_logs(limit=200):
    rows = get_db().execute(
        "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def recent_batches(limit=20):
    rows = get_db().execute(
        "SELECT * FROM import_batches ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
