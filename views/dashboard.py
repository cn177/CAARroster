"""仪表盘：一眼看到协会的健康状况和需要马上处理的事。"""
from flask import Blueprint, render_template

from auth import login_required
from config import MINOR_AGE
from db import get_db
from matching import skill_profile, team_gaps
from models import list_teams, member_stats, recent_batches, recent_logs
from skills import EXPERIENCE, INTENT, SKILL_LABEL, TEAM_KIND

bp = Blueprint("dashboard", __name__)


def build_alerts(stats, teams) -> list[dict]:
    from models import unassigned_members

    alerts = []
    if stats["unassigned"]:
        free = unassigned_members()
        free_newbies = [m for m in free if m["experience"] == "newbie"]
        detail = "到分配台把他们安排掉，落单的人最容易流失。"
        if free_newbies:
            detail = f"其中 {len(free_newbies)} 个是新手，需要协会分配队伍。"
        alerts.append({
            "level": "warn",
            "title": f"{stats['unassigned']} 人还没进队伍",
            "detail": detail,
            "url": ("teams.assign", {}),
        })

    minors = get_db().execute(
        "SELECT COUNT(*) c FROM members WHERE status='active' AND age IS NOT NULL AND age < ?",
        (MINOR_AGE,),
    ).fetchone()["c"]
    if minors:
        alerts.append({
            "level": "warn",
            "title": f"{minors} 位成员未满 {MINOR_AGE} 岁",
            "detail": "未满 14 周岁的个人信息属于敏感个人信息，处理前需要取得监护人同意。"
                      "建议在问卷里加上监护人同意的说明。",
            "url": ("members.listing", {"status": "active"}),
        })

    for team in teams:
        if team["size"] > team["capacity"]:
            alerts.append({
                "level": "error",
                "title": f"{team['name']} 超编（{team['size']}/{team['capacity']}）",
                "detail": "赛事对人数有上限，超了会被拒。",
                "url": ("teams.detail", {"team_id": team["id"]}),
            })
        if team["newbie_count"] > team["newbie_quota"]:
            alerts.append({
                "level": "warn",
                "title": f"{team['name']} 新手超额（{team['newbie_count']}/{team['newbie_quota']}）",
                "detail": "一个老手带太多新手，通常两边体验都差。",
                "url": ("teams.detail", {"team_id": team["id"]}),
            })
        if team["status"] == "recruiting" and not team["captain_id"]:
            alerts.append({
                "level": "info",
                "title": f"{team['name']} 还没有队长",
                "detail": "指定队长后队伍才算能自转。",
                "url": ("teams.detail", {"team_id": team["id"]}),
            })
    return alerts


@bp.route("/")
@login_required
def index():
    stats = member_stats()
    teams = list_teams()
    alerts = build_alerts(stats, teams)

    for team in teams:
        roster = get_db().execute(
            """SELECT m.* FROM team_members tm JOIN members m ON m.id=tm.member_id
                WHERE tm.team_id=? AND tm.left_at IS NULL""",
            (team["id"],),
        ).fetchall()
        roster = [dict(r) for r in roster]
        profile = skill_profile(roster)
        team["gaps"] = [skill for skill in team_gaps(profile)]

    return render_template(
        "dashboard.html",
        stats=stats,
        teams=teams,
        alerts=alerts,
        experience_labels=EXPERIENCE,
        intent_labels=INTENT,
        skill_label=SKILL_LABEL,
        team_kinds=TEAM_KIND,
        batches=recent_batches(5),
    )


@bp.route("/logs")
@login_required
def logs():
    return render_template("logs.html", logs=recent_logs(300), batches=recent_batches(20))
