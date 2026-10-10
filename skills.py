"""协会的固定词表：经验等级、参赛意向、队伍类型、技能分类，以及问卷文本归一化。

这些是"业务字典"，页面上的下拉框、导入时的自动识别、推荐算法都读这里，
要加技能或改叫法只需要改这一个文件。
"""

# ---------- 经验等级 ----------
EXPERIENCE = {
    "newbie": "新手",
    "veteran": "老手",
    "elite": "大佬",
}
EXPERIENCE_ORDER = ["newbie", "veteran", "elite"]

# ---------- 参赛意向 ----------
INTENT = {
    "competitive": "冲击",
    "casual": "摸鱼",
    "mentor": "带新",
    "any": "都可",
}

# ---------- 队伍类型 ----------
TEAM_KIND = {
    "competitive": "冲击队",
    "casual": "摸鱼队",
    "mentor": "带新队",
}

# ---------- 队伍状态 ----------
TEAM_STATUS = {
    "recruiting": "招募中",
    "locked": "已锁定",
    "archived": "已归档",
}

# ---------- 成员状态 ----------
MEMBER_STATUS = {
    "active": "在册",
    "paused": "暂离",
    "alumni": "退役",
}

# ---------- 作息 ----------
SLEEP = {
    "night_owl": "夜猫子",
    "early_bird": "早起型",
    "flexible": "弹性/无所谓",
}

# ---------- 技能分类（key, 显示名） ----------
SKILLS = [
    ("cipher", "密码与古典密码"),
    ("math", "数学与逻辑"),
    ("code", "编程与自动化"),
    ("search", "搜索与信息检索"),
    ("media", "图像与音频"),
    ("hands", "拼图与动手"),
    ("lang", "翻译与语言"),
    ("art", "美术与制图"),
    ("authoring", "出题与审题"),
]
SKILL_LABEL = dict(SKILLS)
SKILL_KEYS = [k for k, _ in SKILLS]

# 自评等级
RATING_LABEL = {0: "不会", 1: "入门", 2: "能凑合", 3: "熟练", 4: "很强", 5: "能扛队"}
STRONG_RATING = 4  # 达到这个自评就算"这个技能我们能靠他"


# ---------------------------------------------------------------- 文本归一化
def normalize_experience(raw: str, hunts_played: int | None = None) -> str:
    """把问卷里的自由文本变成等级。

    顺序很重要：先排除"没参加过"这类否定说法，否则会被"参加过"误判成老手。
    """
    text = (raw or "").strip().lower()
    if text:
        # 1) 明确的"零经验"说法优先
        never = ("没参加过", "没有参加过", "没参加", "未参加", "没玩过", "第一次",
                 "新手", "萌新", "新人", "零基础", "newbie", "纯萌新", "菜鸡")
        if any(k in text for k in never):
            return "newbie"
        # 2) 高手
        if any(k in text for k in ("大佬", "巨佬", "elite", "顶级", "榜一", "冠军", "出过题")):
            return "elite"
        # 3) 有经验
        if any(k in text for k in ("老手", "老兵", "有经验", "veteran", "参加过", "老屁股", "带队")):
            return "veteran"
    if hunts_played is not None:
        if hunts_played >= 8:
            return "elite"
        if hunts_played >= 2:
            return "veteran"
    return "newbie"


def normalize_intent(raw: str) -> str:
    text = (raw or "").strip().lower()
    if not text:
        return "any"
    wants_mentor = "带新" in text or "带人" in text
    wants_comp = any(k in text for k in ("冲击", "冲榜", "认真", "竞技", "全力", "compete", "排名"))
    wants_casual = any(k in text for k in ("摸鱼", "休闲", "随便", "轻松", "casual", "躺"))
    if wants_comp and wants_casual:
        return "any"
    if wants_comp:
        return "competitive"
    if wants_casual:
        return "casual"
    if wants_mentor:
        return "mentor"
    if "都" in text or "any" in text or "看情况" in text:
        return "any"
    return "any"


def normalize_sleep(raw: str) -> str:
    text = (raw or "").strip().lower()
    if any(k in text for k in ("夜", "晚", "通宵", "凌晨", "owl")):
        return "night_owl"
    if any(k in text for k in ("早", "晨", "morning", "bird")):
        return "early_bird"
    return "flexible"


def normalize_yes(raw) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw > 0
    text = str(raw).strip().lower()
    if not text:
        return False
    negative = ("不", "否", "no", "无", "没有", "不能", "算了", "拒绝")
    positive = ("是", "可以", "能", "yes", "ok", "行", "愿意", "有")
    if any(k in text for k in negative):
        return False
    return any(k in text for k in positive)


def parse_int(raw, default=None):
    if raw is None or raw == "":
        return default
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def parse_age(raw, current_year: int | None = None):
    """把"年龄"或"出生年份"统一成年龄。大于 100 的数字当成出生年份。

    问卷里两种问法都很常见，统一成年龄之后才好做年龄段匹配和未成年人提醒。
    """
    value = parse_int(raw, None)
    if value is None or value <= 0:
        return None
    if value > 100:
        from datetime import datetime

        age = (current_year or datetime.now().year) - value
        return age if 0 < age < 120 else None
    return value


# ---------------------------------------------------------------- 技能解析
_SKILL_KEYWORDS = {
    "cipher": ("密码", "cipher", "crypt", "凯撒", "维吉尼亚", "古典"),
    "math": ("数学", "逻辑", "数论", "math", "logic", "推理", "几何"),
    "code": ("编程", "代码", "程序", "脚本", "python", "code", "自动化", "爬虫", "regex", "正则"),
    "search": ("搜索", "检索", "搜索引", "search", "google", "wiki", "查资料", "信息检索"),
    "media": ("图像", "图片", "音频", "声音", "视频", "media", "image", "audio", "频谱", "二维码"),
    "hands": ("拼图", "动手", "手工", "实体", "折纸", "hands", "physical", "魔方"),
    "lang": ("翻译", "语言", "日语", "英语", "多语", "lang", "translat"),
    "art": ("美术", "绘图", "设计", "ps", "photosh", "画画", "art", "design"),
    "authoring": ("出题", "写题", "审题", "命题", "authoring", "测试题", "做题"),
}


def parse_skills(raw) -> dict:
    """把问卷里的技能列解析成 {skill_key: rating}。

    支持的写法：
      "密码,数学,编程"            -> 三个技能各 3 分
      "密码5;数学3"               -> 密码 5 分，数学 3 分
      "密码（很强）"              -> 密码 4 分
    """
    if raw is None:
        return {}
    if isinstance(raw, (list, tuple, set)):
        parts = [str(x) for x in raw]
    else:
        text = str(raw).strip()
        if not text:
            return {}
        for sep in ("；", ";", "、", "，", ",", "/", "|", "\n"):
            text = text.replace(sep, "\x00")
        parts = [p.strip() for p in text.split("\x00") if p.strip()]

    result: dict[str, int] = {}
    for part in parts:
        lowered = part.lower()
        rating = None
        for ch in part:
            if ch.isdigit():
                digit = int(ch)
                if 1 <= digit <= 5:
                    rating = digit
                break  # 只取第一个出现的数字
        if rating is None:
            if any(k in part for k in ("很强", "精通", "擅长", "大神", "熟练")):
                rating = 4
            elif any(k in part for k in ("入门", "一点点", "略懂", "会一点", "浅")):
                rating = 2
            else:
                rating = 3
        for key, words in _SKILL_KEYWORDS.items():
            if any(w in lowered for w in words):
                result[key] = max(result.get(key, 0), rating)
                break
    return result
