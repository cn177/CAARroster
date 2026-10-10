"""赛事管理：把队伍挂到具体赛事上，并按赛事的人数规则做校验。"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import models
from auth import login_required
from skills import TEAM_KIND
from views.forms import parse_event_form

bp = Blueprint("events", __name__, url_prefix="/events")

KIND_LABEL = {"external": "外部赛事", "internal": "自办赛事", "training": "内部训练"}


def _actor() -> str:
    from auth import current_user

    user = current_user()
    return user["username"] if user else "system"


@bp.route("/")
@login_required
def listing():
    return render_template("events.html", events=models.list_events(), kind_labels=KIND_LABEL)


def _render_form(event=None, event_id=None):
    return render_template("event_form.html", event=event or {}, event_id=event_id,
                           kind_labels=KIND_LABEL)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        data = parse_event_form(request.form)
        if not data["name"]:
            flash("赛事名不能为空。", "error")
            return _render_form(data)
        event_id = models.create_event(data, actor=_actor())
        flash(f"已创建「{data['name']}」。", "ok")
        return redirect(url_for("events.detail", event_id=event_id))
    return _render_form({"team_size_min": 1, "team_size_max": 6, "kind": "external"})


@bp.route("/<int:event_id>")
@login_required
def detail(event_id):
    event = models.get_event(event_id)
    if not event:
        abort(404)
    registrations = models.event_registrations(event_id)
    registered_ids = {r["team_id"] for r in registrations}
    teams = models.list_teams()
    for team in teams:
        size = team["size"]
        problems = []
        if size < event["team_size_min"]:
            problems.append(f"人数不够（{size} < {event['team_size_min']}）")
        if size > event["team_size_max"]:
            problems.append(f"人数超限（{size} > {event['team_size_max']}）")
        team["problems"] = problems
    return render_template(
        "event_detail.html",
        event=event,
        registrations=registrations,
        teams=teams,
        registered_ids=registered_ids,
        team_kinds=TEAM_KIND,
        kind_labels=KIND_LABEL,
    )


@bp.route("/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit(event_id):
    event = models.get_event(event_id)
    if not event:
        abort(404)
    if request.method == "POST":
        data = parse_event_form(request.form)
        if not data["name"]:
            flash("赛事名不能为空。", "error")
            return _render_form({**event, **data}, event_id)
        models.update_event(event_id, data, actor=_actor())
        flash("已保存。", "ok")
        return redirect(url_for("events.detail", event_id=event_id))
    return _render_form(event, event_id)


@bp.route("/<int:event_id>/delete", methods=["POST"])
@login_required
def delete(event_id):
    event = models.get_event(event_id)
    if not event:
        abort(404)
    models.delete_event(event_id, actor=_actor())
    flash("赛事已删除。", "ok")
    return redirect(url_for("events.listing"))


@bp.route("/<int:event_id>/register", methods=["POST"])
@login_required
def register(event_id):
    event = models.get_event(event_id)
    if not event:
        abort(404)
    raw = request.form.get("team_id", "")
    if not raw.isdigit():
        flash("请选择队伍。", "error")
        return redirect(url_for("events.detail", event_id=event_id))
    team_id = int(raw)
    team = models.get_team(team_id)
    if team["size"] < event["team_size_min"] or team["size"] > event["team_size_max"]:
        flash(
            f"「{team['name']}」当前 {team['size']} 人，"
            f"该赛事要求 {event['team_size_min']}–{event['team_size_max']} 人，先调整队伍再报名。",
            "error",
        )
        return redirect(url_for("events.detail", event_id=event_id))
    result = models.register_team(event_id, team_id, request.form.get("note", ""), actor=_actor())
    flash("已报名。" if result == "ok" else "这支队已经报过了。", "ok" if result == "ok" else "info")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.route("/<int:event_id>/unregister/<int:team_id>", methods=["POST"])
@login_required
def unregister(event_id, team_id):
    models.unregister_team(event_id, team_id, actor=_actor())
    flash("已取消报名。", "ok")
    return redirect(url_for("events.detail", event_id=event_id))
