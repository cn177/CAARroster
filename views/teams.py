"""队伍管理与分配台：本系统的心脏。

分配台的设计目标：让运营在一个页面上把"还没队伍的人"塞进"还缺人的队伍"，
每一步都看得到系统给出的理由和硬性限制（人数上限、新手名额）。
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import matching
import models
from auth import login_required
from skills import EXPERIENCE, INTENT, SKILL_LABEL, SKILLS, TEAM_KIND, TEAM_STATUS
from views.forms import parse_team_form

bp = Blueprint("teams", __name__, url_prefix="/teams")


def _actor() -> str:
    from auth import current_user

    user = current_user()
    return user["username"] if user else "system"


def _filters():
    return {
        "experience": request.args.get("experience") or "",
        "intent": request.args.get("intent") or "",
    }


# ================================================================== 队伍列表
@bp.route("/")
@login_required
def listing():
    kind = request.args.get("kind") or ""
    status = request.args.get("status") or ""
    teams = models.teams_with_roster(status=status)
    if kind:
        teams = [t for t in teams if t["kind"] == kind]
    for team in teams:
        profile = matching.skill_profile(team["roster"])
        team["gaps"] = matching.team_gaps(profile)
        team["profile_desc"] = matching.describe_profile(profile)
        team["needs"] = matching.team_needs(team)
    return render_template(
        "teams.html",
        teams=teams,
        kind_filter=kind,
        status_filter=status,
        team_kinds=TEAM_KIND,
        team_statuses=TEAM_STATUS,
        skill_label=SKILL_LABEL,
    )


# ================================================================== 增改删
@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        data = parse_team_form(request.form)
        if not data["name"]:
            flash("队伍名不能为空。", "error")
            return _render_form(data)
        if any(t["name"] == data["name"] for t in models.list_teams()):
            flash("已经有同名队伍了。", "error")
            return _render_form(data)
        team_id = models.create_team(data, actor=_actor())
        flash(f"已创建「{data['name']}」。", "ok")
        return redirect(url_for("teams.detail", team_id=team_id))
    return _render_form({"capacity": 6, "newbie_quota": 2, "status": "recruiting", "kind": "casual"})


def _render_form(team=None, team_id=None):
    return render_template(
        "team_form.html",
        team=team or {},
        team_id=team_id,
        team_kinds=TEAM_KIND,
        team_statuses=TEAM_STATUS,
        candidates=models.list_members(status="active"),
    )


@bp.route("/<int:team_id>")
@login_required
def detail(team_id):
    team = models.get_team(team_id)
    if not team:
        abort(404)
    roster = models.team_roster(team_id)
    history = models.team_roster(team_id, active_only=False)
    former = [m for m in history if m["left_at"]]
    profile = matching.skill_profile(roster)
    gaps = matching.team_gaps(profile)
    newbie_count = sum(1 for m in roster if m["experience"] == "newbie")
    slots = models.team_slots(team_id)
    free_members = models.unassigned_members()

    # 手动加人那一栏：逐个标出"这个人为什么加不进来"，并禁掉不能加的人。
    # 光靠后端拦是不够的 —— 界面得先告诉运营为什么加不动。
    candidates = [
        {"member": member, "problem": models.team_limit_problem(team_id, member["id"])}
        for member in free_members
    ]

    suggestions = []
    for member in free_members:
        result = matching.evaluate(team, member, roster)
        if result["blockers"] or result["score"] < 0:
            continue
        suggestions.append({"member": member, **result})
    suggestions.sort(key=lambda x: -x["score"])
    return render_template(
        "team_detail.html",
        team=team,
        roster=roster,
        former=former,
        profile=profile,
        gaps=gaps,
        newbie_count=newbie_count,
        slots=slots,
        candidates=candidates,
        suggestions=suggestions[:8],
        free_members=free_members,
        skill_label=SKILL_LABEL,
        skill_keys=SKILLS,
        experience_labels=EXPERIENCE,
        intent_labels=INTENT,
        team_kinds=TEAM_KIND,
        team_statuses=TEAM_STATUS,
        events=models.list_events(),
        registered=[r["event_id"] for r in
                    models.get_db().execute(
                        "SELECT event_id FROM event_teams WHERE team_id=?", (team_id,)
                    ).fetchall()],
    )


@bp.route("/<int:team_id>/edit", methods=["GET", "POST"])
@login_required
def edit(team_id):
    team = models.get_team(team_id)
    if not team:
        abort(404)
    if request.method == "POST":
        data = parse_team_form(request.form)
        if not data["name"]:
            flash("队伍名不能为空。", "error")
            return _render_form({**team, **data}, team_id)
        models.update_team(team_id, data, actor=_actor())
        flash("已保存。", "ok")
        return redirect(url_for("teams.detail", team_id=team_id))
    return _render_form(team, team_id)


@bp.route("/<int:team_id>/delete", methods=["POST"])
@login_required
def delete(team_id):
    team = models.get_team(team_id)
    if not team:
        abort(404)
    models.delete_team(team_id, actor=_actor())
    flash(f"已删除「{team['name']}」，成员回到未分配池。", "ok")
    return redirect(url_for("teams.listing"))


# ================================================================== 队内操作
@bp.route("/<int:team_id>/members/add", methods=["POST"])
@login_required
def add_members(team_id):
    team = models.get_team(team_id)
    if not team:
        abort(404)
    ids = request.form.getlist("member_id")
    if not ids and request.form.get("member_id_single"):
        ids = [request.form["member_id_single"]]
    if not ids:
        flash("没有选择成员。", "error")
        return redirect(url_for("teams.detail", team_id=team_id))
    added, refused = 0, []
    for raw in ids:
        if not str(raw).isdigit():
            continue
        member_id = int(raw)
        try:
            models.add_to_team(team_id, member_id, actor=_actor())
            added += 1
        except models.TeamLimitError as exc:
            member = models.get_member(member_id)
            who = member["name"] if member else f"成员 {member_id}"
            refused.append(f"{who} 没加进去：{exc}")
    if added:
        flash(f"已加入 {added} 人。", "ok")
    for reason in refused:
        flash(reason, "error")
    if not added and not refused:
        flash("没有有效的成员被选中。", "error")
    return redirect(url_for("teams.detail", team_id=team_id))


@bp.route("/<int:team_id>/members/<int:member_id>/remove", methods=["POST"])
@login_required
def remove_member(team_id, member_id):
    models.remove_from_team(team_id, member_id, actor=_actor())
    flash("已移出队伍。", "ok")
    return redirect(request.form.get("back") or url_for("teams.detail", team_id=team_id))


@bp.route("/<int:team_id>/members/<int:member_id>/role", methods=["POST"])
@login_required
def set_role(team_id, member_id):
    role = request.form.get("role") or "member"
    models.set_member_role(team_id, member_id, role, actor=_actor())
    flash("已更新队内角色。", "ok")
    return redirect(url_for("teams.detail", team_id=team_id))


@bp.route("/<int:team_id>/captain", methods=["POST"])
@login_required
def set_captain(team_id):
    raw = request.form.get("captain_id")
    if not raw or not raw.isdigit():
        flash("请选择队长。", "error")
        return redirect(url_for("teams.detail", team_id=team_id))
    models.set_captain(team_id, int(raw), actor=_actor())
    flash("已指定队长。", "ok")
    return redirect(url_for("teams.detail", team_id=team_id))


# ================================================================== 分配台
@bp.route("/assign", strict_slashes=False)
@login_required
def assign():
    filters = _filters()
    free = models.unassigned_members(**filters)
    teams = models.teams_with_roster()
    live = [t for t in teams if t["status"] == "recruiting"]

    for team in live:
        profile = matching.skill_profile(team["roster"])
        team["gaps"] = matching.team_gaps(profile)
        team["needs"] = matching.team_needs(team)
        team["profile_desc"] = matching.describe_profile(profile)

    for member in free:
        member["recommendations"] = matching.recommend_teams(member, live, limit=3)
        blocked = []
        for team in live:
            result = matching.evaluate(team, member)
            if result["blockers"]:
                blocked.append({"team": team, **result})
            if len(blocked) >= 2:
                break
        member["blocked"] = blocked

    return render_template(
        "assign.html",
        free=free,
        teams=teams,
        live_teams=live,
        filters=filters,
        experience_labels=EXPERIENCE,
        intent_labels=INTENT,
        team_kinds=TEAM_KIND,
        skill_label=SKILL_LABEL,
        draft=models.load_draft(),
    )


@bp.route("/assign/apply", methods=["POST"])
@login_required
def apply_assignment():
    member_id = request.form.get("member_id", "")
    team_id = request.form.get("team_id", "")
    if not (member_id.isdigit() and team_id.isdigit()):
        flash("请选择要分配到的队伍。", "error")
    else:
        member = models.get_member(int(member_id))
        team = models.get_team(int(team_id))
        try:
            result = models.add_to_team(int(team_id), int(member_id), actor=_actor())
        except models.TeamLimitError as exc:
            flash(f"{member['name'] if member else member_id} 没分配成功：{exc}", "error")
        else:
            if result == "already":
                flash(f"{member['name']} 已经在「{team['name']}」里了。", "info")
            else:
                flash(f"{member['name']} → 「{team['name']}」", "ok")
    return redirect(url_for(
        "teams.assign",
        experience=request.form.get("keep_experience", ""),
        intent=request.form.get("keep_intent", ""),
    ))


@bp.route("/assign/draft", methods=["POST"])
@login_required
def make_draft():
    only_newbies = request.form.get("only_newbies", "1") == "1"
    free = models.unassigned_members()
    teams = models.teams_with_roster()
    result = matching.draft_allocation(free, teams, only_newbies=only_newbies)
    payload = {
        "only_newbies": only_newbies,
        "assignments": [
            {
                "member_id": a["member"]["id"],
                "member_name": a["member"]["name"],
                "member_code": a["member"]["code"],
                "team_id": a["team"]["id"],
                "team_name": a["team"]["name"],
                "score": a["score"],
                "reasons": a["reasons"],
            }
            for a in result["assignments"]
        ],
        "leftovers": [
            {"id": m["id"], "name": m["name"], "code": m["code"],
             "experience": m["experience"], "intent": m["intent"]}
            for m in result["leftovers"]
        ],
    }
    models.save_draft(payload, actor=_actor())
    if not payload["assignments"]:
        flash("没有可自动分配的人（可能队伍都满了或没人提交意向）。", "warn")
    return redirect(url_for("teams.assign"))


@bp.route("/assign/draft/apply", methods=["POST"])
@login_required
def apply_draft():
    draft = models.load_draft()
    if not draft or not draft.get("assignments"):
        flash("当前没有待确认的草案。", "error")
        return redirect(url_for("teams.assign"))
    count, refused = 0, []
    for item in draft["assignments"]:
        try:
            models.add_to_team(int(item["team_id"]), int(item["member_id"]), actor=_actor())
            count += 1
        except models.TeamLimitError as exc:
            # 草案生成之后队伍可能被人动过，所以这里要重新校验一遍
            refused.append(f"{item.get('member_name', '?')} → {item.get('team_name', '?')}：{exc}")
        except Exception:  # noqa: BLE001 - 某一条失败不影响其它
            continue
    models.clear_draft(actor=_actor())
    if count:
        flash(f"草案已执行，{count} 人入队。", "ok")
    for reason in refused:
        flash(f"有 {len(refused)} 人没进去 —— {reason}", "error")
    if not count and not refused:
        flash("草案里的人都没能入队。", "warn")
    return redirect(url_for("teams.assign"))


@bp.route("/assign/draft/clear", methods=["POST"])
@login_required
def clear_draft():
    models.clear_draft(actor=_actor())
    flash("已丢弃草案。", "info")
    return redirect(url_for("teams.assign"))
