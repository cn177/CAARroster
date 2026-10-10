"""CAAR —— 会员与队伍管理系统

启动：
    python app.py                      # 开发/内网直接跑
    python app.py --create-admin 名字 密码   # 先建一个运营账号
生产建议：
    gunicorn -w 2 -b 127.0.0.1:8000 app:app
"""
import argparse
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

from flask import Flask, g, render_template, request

import auth
import db as database
import views
from config import (
    COLLECT_IDENTITY,
    COOKIE_SECURE,
    DATA_DIR,
    DEFAULT_MENTOR_CAPACITY,
    MAX_UPLOAD_SIZE,
    MINOR_AGE,
    ORG_NAME,
    ORG_SHORT,
    SECRET_KEY,
    SESSION_DAYS,
)

TZ_OFFSET = float(os.environ.get("ARA_TZ_OFFSET", "8"))
LOCAL_TZ = timezone(timedelta(hours=TZ_OFFSET))


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=SECRET_KEY,
        MAX_CONTENT_LENGTH=MAX_UPLOAD_SIZE,
        PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=COOKIE_SECURE,
        JSON_AS_ASCII=False,
        TEMPLATES_AUTO_RELOAD=os.environ.get("ARA_DEBUG") == "1",
    )

    database.init_db()
    auth.init_app(app)
    views.register(app)

    # ------------------------------------------------------------ 安全响应头
    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # style 放开 inline，是因为模板里用了大量 style="..." 属性；
        # script 不允许 inline，模板里也没有任何内联事件处理器（冒烟测试会检查这一点）。
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        if response.mimetype == "text/html":
            # 成员名单不该躺在浏览器缓存和"后退"里
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # ------------------------------------------------------------ 模板辅助
    @app.template_filter("localtime")
    def localtime(value, fmt="%Y-%m-%d %H:%M"):
        if not value:
            return ""
        text = str(value)
        try:
            if text.endswith("Z"):
                moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
            else:
                moment = datetime.fromisoformat(text)
        except ValueError:
            return text
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(LOCAL_TZ).strftime(fmt)

    @app.template_filter("shortdate")
    def shortdate(value):
        return localtime(value, "%m-%d %H:%M")

    @app.context_processor
    def inject_globals():
        return {
            "ORG_NAME": ORG_NAME,
            "ORG_SHORT": ORG_SHORT,
            "COLLECT_IDENTITY": COLLECT_IDENTITY,
            "MINOR_AGE": MINOR_AGE,
            "DEFAULT_MENTOR_CAPACITY": DEFAULT_MENTOR_CAPACITY,
            "now": datetime.now(LOCAL_TZ),
        }

    # ------------------------------------------------------------ 错误页
    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", code=400, message=getattr(error, "description", "请求有误")), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("error.html", code=403, message="没有权限"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("error.html", code=404, message="页面不存在"), 404

    @app.errorhandler(413)
    def too_large(error):
        return render_template("error.html", code=413, message="文件太大了"), 413

    @app.errorhandler(500)
    def server_error(error):
        app.logger.exception("未处理的错误: %s", error)
        return render_template("error.html", code=500, message="服务器内部错误，看一眼日志"), 500

    @app.teardown_appcontext
    def _close(exc):
        database.close_db(exc)

    return app


app = create_app()


# ==================================================================== CLI
def _cli_create_admin(username: str, password: str, role: str = "admin") -> int:
    problem = auth.password_problem(password)
    if problem:
        print(f"密码不合格：{problem}")
        return 1
    with app.app_context():
        if auth.find_user(username):
            # 已经存在不算失败：容器启动脚本靠退出码判断要不要报错
            print(f"用户 {username} 已存在，想改密码用 --reset-password。")
            return 0
        auth.create_user(username, password, role)
        print(f"已创建运营账号：{username}")
        return 0


def _cli_reset_password(username: str, password: str) -> int:
    problem = auth.password_problem(password)
    if problem:
        print(f"密码不合格：{problem}")
        return 1
    with app.app_context():
        user = auth.find_user(username)
        if not user:
            print(f"没有找到用户 {username}。")
            return 1
        auth.set_password(user["id"], password)
        print(f"已重置 {username} 的密码。")
        return 0


def _cli_seed_demo() -> None:
    import seed_demo

    with app.app_context():
        seed_demo.run()


def _cli_check_admin() -> int:
    """有没有管理账号。给容器启动脚本用：没有就打印建账号的指引。"""
    with app.app_context():
        row = database.get_db().execute("SELECT COUNT(*) c FROM users").fetchone()
        return 0 if row["c"] else 1


def _ensure_admin() -> None:
    """第一次启动时自动建一个 admin，随机密码打在控制台，避免默认弱口令。"""
    with app.app_context():
        row = database.get_db().execute("SELECT COUNT(*) c FROM users").fetchone()
        if row["c"]:
            return
        password = secrets.token_urlsafe(9)
        auth.create_user("admin", password)
        print("=" * 58)
        print("  首次启动，已创建运营账号")
        print("    用户名: admin")
        print(f"    密码:   {password}")
        print("  登录后请立刻到「账号」页改密码。")
        print("=" * 58)


def _run_production(host: str, port: int) -> None:
    """生产模式：Windows 上用 waitress，Linux 上其实用 gunicorn 更好（见 README）。"""
    try:
        from waitress import serve
    except ImportError:
        print("没装 waitress，退回 Flask 自带服务器。")
        print("建议执行：pip install waitress")
        app.run(host=host, port=port, debug=False)
        return
    print(f"waitress 已启动：http://{host}:{port}")
    print("关闭这个窗口就是停止服务。按 Ctrl+C 也可以。")
    serve(app, host=host, port=port, threads=8, ident="CAAR-Roster")


def main(argv=None):
    parser = argparse.ArgumentParser(description="CAAR 会员与队伍管理系统")
    parser.add_argument("--host", default=os.environ.get("ARA_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("ARA_PORT", "8000")))
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--production", action="store_true",
                        help="用 waitress 启动（Windows 上就用这个）")
    parser.add_argument("--create-admin", nargs=2, metavar=("USERNAME", "PASSWORD"))
    parser.add_argument("--reset-password", nargs=2, metavar=("USERNAME", "PASSWORD"))
    parser.add_argument("--seed-demo", action="store_true", help="写入一批演示数据")
    parser.add_argument("--init-db", action="store_true", help="只建表然后退出")
    parser.add_argument("--check-admin", action="store_true",
                        help="已有管理账号则退出码 0，否则 1")
    args = parser.parse_args(argv)

    if args.check_admin:
        return _cli_check_admin()

    if args.init_db:
        with app.app_context():
            database.init_db()
        print(f"数据库已就绪：{DATA_DIR}")
        return 0
    if args.create_admin:
        return _cli_create_admin(*args.create_admin)
    if args.reset_password:
        return _cli_reset_password(*args.reset_password)
    if args.seed_demo:
        _cli_seed_demo()
        return 0

    _ensure_admin()
    print(f"数据目录：{DATA_DIR}")
    print(f"启动地址：http://{args.host}:{args.port}")
    if args.production:
        _run_production(args.host, args.port)
    else:
        if os.name == "nt":
            print("提示：Windows 上长期运行请加 --production（走 waitress），或者双击 start-windows.bat")
        app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
