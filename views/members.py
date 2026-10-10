"""成员管理：列表、增删改、详情。"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import models
from auth import login_required
from skills import EXPERIENCE, INTENT, MEMBER_STATUS, RATING_LABEL, SKILL_LABEL, SKILLS, SLEEP
from views.forms import parse_member_form

bp = Blueprint("members", __name__, url_prefix="/members")


@bp.route("/")
@login_required
def listing():
    filters = {
        "search": (request.args.get("q") or "").strip(),
        "experience": request.args.get("experience") or "",
        "intent": request.args.get("intent") or "",
        "assignment": request.args.get("assignment") or "",
        "status": request.args.get("status") or "active",
    }
    members = models.list_members(**filters)
    return render_template(
        "members.html",
        members=members,
        filters=filters,
        experience_labels=EXPERIENCE,
        intent_labels=INTENT,
        status_labels=MEMBER_STATUS,
        skill_label=SKILL_LABEL,
        teams=models.list_teams(status="recruiting"),
    )


def _render_form(member=None):
    return render_template(
        "member_form.html",
        member=member,
        experience_labels=EXPERIENCE,
        intent_labels=INTENT,
        status_labels=MEMBER_STATUS,
        sleep_labels=SLEEP,
        skills=SKILLS,
        rating_labels=RATING_LABEL,
        teams=models.list_teams(),
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        data = parse_member_form(request.form)
        if not data["name"]:
            flash("昵称不能为空。", "error")
            return _render_form(data)
        member_id = models.create_member(data, actor=_actor())
        flash(f"已创建 {data['name']}。", "ok")
        return redirect(url_for("members.detail", member_id=member_id))
    return _render_form()


@bp.route("/<int:member_id>")
@login_required
def detail(member_id):
    member = models.get_member(member_id)
    if not member:
        abort(404)
    return render_template(
        "member_detail.html",
        member=member,
        history=models.member_history(member_id),
        experience_labels=EXPERIENCE,
        intent_labels=INTENT,
        skill_label=dict(SKILLS),
        sleep_labels=SLEEP,
        status_labels=MEMBER_STATUS,
        teams=models.list_teams(),
    )


@bp.route("/<int:member_id>/edit", methods=["GET", "POST"])
@login_required
def edit(member_id):
    member = models.get_member(member_id)
    if not member:
        abort(404)
    if request.method == "POST":
        data = parse_member_form(request.form)
        if not data["name"]:
            flash("昵称不能为空。", "error")
            return _render_form({**member, **data, "id": member_id})
        models.update_member(member_id, data, actor=_actor())
        flash("已保存。", "ok")
        return redirect(url_for("members.detail", member_id=member_id))
    return _render_form(member)


@bp.route("/<int:member_id>/delete", methods=["POST"])
@login_required
def delete(member_id):
    member = models.get_member(member_id)
    if not member:
        abort(404)
    models.delete_member(member_id, actor=_actor())
    flash(f"已删除 {member['name']}（同时也退出了所在队伍）。", "ok")
    return redirect(url_for("members.listing"))


@bp.route("/<int:member_id>/assign", methods=["POST"])
@login_required
def assign(member_id):
    """在成员详情页直接把一个人塞进队伍，或让他退队。"""
    member = models.get_member(member_id)
    if not member:
        abort(404)
    back = request.form.get("back") or url_for("members.detail", member_id=member_id)

    if request.form.get("action") == "leave":
        if member.get("team_id"):
            models.remove_from_team(member["team_id"], member_id, actor=_actor())
            flash(f"{member['name']} 已退出「{member['team_name']}」。", "ok")
        return redirect(back)

    team_id = request.form.get("team_id")
    if not team_id:
        flash("没有选择队伍。", "error")
        return redirect(back)
    result = models.add_to_team(int(team_id), member_id, actor=_actor())
    team = models.get_team(int(team_id))
    if not team:
        flash("队伍不存在。", "error")
        return redirect(back)
    if result == "already":
        flash(f"{member['name']} 已经在「{team['name']}」里了。", "info")
    elif result == "moved":
        flash(f"{member['name']} 已转到「{team['name']}」。", "ok")
    else:
        flash(f"{member['name']} 已加入「{team['name']}」。", "ok")
    return redirect(back)


def _actor() -> str:
    from auth import current_user

    user = current_user()
    return user["username"] if user else "system"
