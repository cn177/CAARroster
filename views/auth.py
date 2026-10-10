"""登录、登出、改密码。系统只服务于运营，不开放注册。"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

import throttle
from auth import (client_ip, current_user, login_required, login_user, logout_user,
                  password_problem, safe_next, set_password, throttle_keys,
                  verify_login)
from config import LOGIN_LOCKOUT
from db import get_db, log

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method != "POST":
        return render_template("login.html")

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    keys = throttle_keys(username)

    # 先看有没有被锁
    for key in keys:
        allowed, wait = throttle.check(key)
        if not allowed:
            return render_template(
                "login.html",
                locked_message=f"尝试次数太多了，请等 {throttle.humanize(wait)} 后再试。",
            ), 429

    user = verify_login(username, password)
    if user:
        for key in keys:
            throttle.reset(key)
        login_user(user)
        db = get_db()
        log(db, username, "auth.login", "session", {"ip": client_ip()})
        db.commit()
        target = safe_next(request.args.get("next", ""))
        return redirect(target or url_for("dashboard.index"))

    # 失败：记账 + 审计
    just_locked = False
    for key in keys:
        just_locked = throttle.record_failure(key) or just_locked
    db = get_db()
    log(db, username or "-", "auth.login_failed", "session",
        {"ip": client_ip(), "locked": just_locked})
    db.commit()

    left = min(throttle.remaining(key) for key in keys)
    message = "用户名或密码不对。"
    if just_locked:
        message += f" 失败次数过多，已临时锁定 {throttle.humanize(LOGIN_LOCKOUT)}。"
    elif left <= 2:
        message += f" 还能再试 {left} 次。"
    flash(message, "error")
    return render_template("login.html"), 401


@bp.route("/logout", methods=["POST"])
def logout():
    user = current_user()
    if user:
        db = get_db()
        log(db, user["username"], "auth.logout", "session")
        db.commit()
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        old = request.form.get("old_password") or ""
        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        user = current_user()
        problem = None
        if not verify_login(user["username"], old):
            problem = "原密码不对。"
        elif new != confirm:
            problem = "两次输入的新密码不一致。"
        else:
            problem = password_problem(new)
        if problem:
            flash(problem, "error")
        else:
            set_password(user["id"], new)
            db = get_db()
            log(db, user["username"], "auth.change_password", f"user:{user['id']}")
            db.commit()
            flash("密码已更新。", "ok")
            return redirect(url_for("dashboard.index"))
    return render_template("account.html", user=current_user())
