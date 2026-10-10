"""全局配置。所有可调项都可以用环境变量覆盖，方便部署时改。"""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 数据目录：数据库和密钥都放这里，备份时整个目录拷走即可
DATA_DIR = Path(os.environ.get("ARA_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("ARA_DB", DATA_DIR / "roster.db"))

# 上传文件的临时落脚点，导入确认后可以随时清空
TMP_DIR = DATA_DIR / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# 会员号前缀，例如 CAAR-0001
MEMBER_CODE_PREFIX = os.environ.get("ARA_CODE_PREFIX", "CAAR")

# 协会名称，显示在页面上
ORG_NAME = os.environ.get("ARA_ORG_NAME", "CAAR")
ORG_SHORT = os.environ.get("ARA_ORG_SHORT", "CAAR")

# 默认队伍人数上限（可在每个队伍/赛事上单独设置）
DEFAULT_TEAM_CAPACITY = int(os.environ.get("ARA_TEAM_CAPACITY", "6"))
# 默认每队新手名额
DEFAULT_NEWBIE_QUOTA = int(os.environ.get("ARA_NEWBIE_QUOTA", "2"))
# 一个老手默认最多带几个新手
DEFAULT_MENTOR_CAPACITY = int(os.environ.get("ARA_MENTOR_CAPACITY", "3"))

# 是否收集真实姓名 / 手机号。
# 默认 0：协会只收 QQ、Discord、年龄这类弱身份信息时，界面和导出里根本不出现这两项，
# 少收集就是最有效的合规手段（《个人信息保护法》的最小必要原则）。
# 真的要收就设环境变量 ARA_COLLECT_IDENTITY=1。
COLLECT_IDENTITY = os.environ.get("ARA_COLLECT_IDENTITY", "0") == "1"

# 未满这个年龄属于《个人信息保护法》里的敏感个人信息，处理需要监护人同意。
MINOR_AGE = int(os.environ.get("ARA_MINOR_AGE", "14"))

# ---------------------------------------------------------------- 安全相关
# 登录失败几次就临时锁定。开源之后谁都知道这个登录页长什么样，这道闸必须有。
LOGIN_MAX_ATTEMPTS = int(os.environ.get("ARA_LOGIN_MAX_ATTEMPTS", "5"))
# 计数窗口（秒）：在这个时间内累计失败达到上限就锁
LOGIN_WINDOW = int(os.environ.get("ARA_LOGIN_WINDOW", "300"))
# 锁定时长（秒）
LOGIN_LOCKOUT = int(os.environ.get("ARA_LOGIN_LOCKOUT", "900"))

# 会话 Cookie 是否只走 HTTPS。只在浏览器直连域名（有证书）时打开。
# 走 SSH 隧道访问的是 http://127.0.0.1，打开会让登录直接失效，所以默认关。
COOKIE_SECURE = os.environ.get("ARA_COOKIE_SECURE", "0") == "1"

# 是否信任反向代理传来的 X-Forwarded-For。
# 放在 Nginx / Caddy 后面时打开，否则限流会把所有访客当成同一个 IP。
TRUST_PROXY = os.environ.get("ARA_TRUST_PROXY", "0") == "1"

# 上传文件大小上限（字节），问卷星导出一般很小，8MB 足够
MAX_UPLOAD_SIZE = int(os.environ.get("ARA_MAX_UPLOAD", str(8 * 1024 * 1024)))


def _load_secret_key() -> str:
    """SECRET_KEY 优先取环境变量，否则落盘保存，避免重启后所有人被登出。"""
    env_key = os.environ.get("ARA_SECRET_KEY")
    if env_key:
        return env_key
    key_file = DATA_DIR / "secret_key"
    if key_file.exists():
        value = key_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    key_file.write_text(value, encoding="utf-8")
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    return value


SECRET_KEY = _load_secret_key()

# 会话有效期（天）
SESSION_DAYS = int(os.environ.get("ARA_SESSION_DAYS", "14"))
