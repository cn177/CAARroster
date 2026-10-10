"""登录、会话与 CSRF。系统只给运营/管理用，不开放给普通会员注册。"""
import hmac
import secrets
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db, log, now

SESSION_UID = "uid"

MIN_PASSWORD_LENGTH = 8

# 太小白的密码直接拒掉。只列最烂的那批，不搞复杂规则 —— 规则越多越容易写在便利贴上。
WEAK_PASSWORDS = {
    "12345678", "123456789", "1234567890", "password", "password1", "password123",
    "passw0rd", "qwertyui", "qwerty123", "abc12345", "admin123", "admin888",
    "admin1234", "11111111", "00000000", "88888888", "iloveyou", "woaini1314",
    "a1234567", "puzzlehunt", "puzzlehunt123", "administrator", "letmein123",
    "welcome123", "roster123", "qazwsx123", "1qaz2wsx", "zxcvbnm123",
}

# 用于抹平"用户不存在"和"密码错误"的响应时间差，避免被拿来枚举用户名
_DUMMY_HASH = generate_password_hash("timing-equalizer-not-a-real-password")


# ------------------------------------------------------------------ 密码
def password_problem(password: str) -> str | None:
    """合格返回 None，不合格返回给用户看的原因。"""
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        return f"密码至少 {MIN_PASSWORD_LENGTH} 位。"
    if password.lower() in WEAK_PASSWORDS:
        return "这个密码太常见了，随便加点东西换个新的。"
    if password.isdigit():
        return "别用纯数字密码。"
    if len(set(password)) <= 3:
        return "字符重复太多了，换个复杂点的。"
    return None


def hash_password(raw: str) -> str:
    return generate_password_hash(raw)


def create_user(username: str, password: str, role: str = "admin") -> int:
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    db = get_db()
    cur = db.execute(
        "INSERT INTO users(username, password_hash, role, created_at) VALUES(?,?,?,?)",
        (username, hash_password(password), role, now()),
    )
    db.commit()
    return cur.lastrowid


def find_user(username: str):
    return get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def verify_login(username: str, password: str):
    user = find_user(username)
    if user is None:
        # 故意也做一次哈希运算，让"用户不存在"和"密码错误"耗时接近
        check_password_hash(_DUMMY_HASH, password)
        return None
    if check_password_hash(user["password_hash"], password):
        return user
    return None


def set_password(user_id: int, password: str) -> None:
    problem = password_problem(password)
    if problem:
        raise ValueError(problem)
    db = get_db()
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user_id))
    db.commit()


# ------------------------------------------------------------------ 会话
def current_user():
    uid = session.get(SESSION_UID)
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def login_user(user) -> None:
    session.clear()
    session[SESSION_UID] = user["id"]
    session.permanent = True


def logout_user() -> None:
    session.clear()


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get(SESSION_UID):
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapper


# ------------------------------------------------------------------ 限流辅助
def client_ip() -> str:
    from config import TRUST_PROXY

    if TRUST_PROXY:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def throttle_keys(username: str) -> list[str]:
    """按账号限流；只有当来源不是本机时才按 IP 限流。

    走 SSH 隧道时所有请求的 remote_addr 都是 127.0.0.1。这时候按 IP 限流等于
    "一个人输错几次就把所有人锁在外面"，反而成了攻击者的帮手，所以跳过。
    """
    keys = [f"user:{(username or '-').strip().lower()}"]
    ip = client_ip()
    if ip and not (ip.startswith("127.") or ip in ("::1", "localhost")):
        keys.append(f"ip:{ip}")
    return keys


def safe_next(target: str) -> str | None:
    """只允许跳回本站路径，防止被拿来做开放重定向。"""
    if not target or not target.startswith("/"):
        return None
    if target.startswith("//") or "\\" in target:
        return None
    return target


# ------------------------------------------------------------------ CSRF
def csrf_token() -> str:
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def csrf_protect():
    """所有写操作都必须带 _csrf，防止别人构造页面骗运营点按钮。"""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        expected = session.get("_csrf")
        supplied = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, "CSRF 校验失败，请刷新页面重试。")


def init_app(app) -> None:
    @app.before_request
    def _load_user():
        g.user = current_user()

    @app.before_request
    def _csrf():
        csrf_protect()

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["current_user"] = lambda: g.get("user")
