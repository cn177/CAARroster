"""端到端冒烟测试：不依赖浏览器，直接把整条主流程跑一遍。

    python tests/smoke_test.py

覆盖：建账号 → 登录 → 上传问卷星样式文件 → 字段识别 → 确认入库 →
建队 → 分配 → 自动草案 → 导出 → 各页面可用性 → CSRF 拦截。
"""
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="ara-smoke-"))
os.environ["ARA_DATA_DIR"] = str(TMP)
os.environ["ARA_SECRET_KEY"] = "smoke-test-secret"
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook, load_workbook  # noqa: E402

import auth  # noqa: E402
import importer  # noqa: E402
import matching  # noqa: E402
import models  # noqa: E402
from app import app  # noqa: E402

PASSED = []
FAILED = []


def check(condition, label):
    if condition:
        PASSED.append(label)
        print(f"  [ok]   {label}")
    else:
        FAILED.append(label)
        print(f"  [FAIL] {label}")


def csrf(client) -> str:
    with client.session_transaction() as sess:
        if "_csrf" not in sess:
            sess["_csrf"] = "smoke-csrf-token"
        return sess["_csrf"]


def build_wenjuanxing_file(path: Path) -> list[str]:
    """造一份和问卷星导出结构接近的表，含一行无关的表头干扰。"""
    workbook = Workbook()
    ws = workbook.active
    headers = [
        "提交时间", "1、你的昵称/常用称呼是？", "2、你的 puzzle hunt 经验是？",
        "3、本届参赛意向？", "4、你擅长哪些方面？", "5、你的 QQ 号？",
        "6、赛期内可投入多少小时？", "7、是否需要老手带？", "8、你的年龄是？",
    ]
    ws.append(headers)
    ws.append(["2026-01-01 10:00:00", "新手甲", "我是萌新", "摸鱼", "密码、数学", "111", "8", "是", "17"])
    ws.append(["2026-01-01 10:05:00", "老手乙", "参加过几次", "冲击", "编程5;搜索4", "222", "30", "否", "2004"])
    ws.append(["2026-01-01 10:09:00", "大佬丙", "大佬，拿过名次", "冲击", "密码5、出题4", "333", "40", "否", "22"])
    ws.append(["2026-01-01 10:20:00", "", "萌新", "摸鱼", "美术", "444", "5", "是", "16"])  # 无昵称，应被跳过
    workbook.save(path)
    return headers


def main() -> int:
    print(f"临时数据目录：{TMP}")
    app.config["TESTING"] = True

    with app.app_context():
        auth.create_user("admin", "SmokeTest#2026")

    client = app.test_client()

    print("\n[1] 鉴权")
    response = client.get("/", follow_redirects=False)
    check(response.status_code == 302, "未登录访问首页会被重定向到登录页")

    response = client.post("/login", data={
        "_csrf": csrf(client), "username": "admin", "password": "WrongPass#1"})
    check("用户名或密码不对" in response.get_data(as_text=True), "错误密码会被拒绝")
    check(response.status_code == 401, "登录失败的响应码是 401")

    response = client.post("/login", data={
        "_csrf": csrf(client), "username": "admin", "password": "SmokeTest#2026"},
        follow_redirects=True)
    check(response.status_code == 200, "正确密码可以登录")

    print("\n[2] 问卷星文件字段识别")
    source = TMP / "wenjuanxing.xlsx"
    headers = build_wenjuanxing_file(source)
    guessed = importer.guess_mapping(headers)
    check(guessed.get("name") == headers[1], "昵称列被正确识别")
    check(guessed.get("experience") == headers[2], "经验列被正确识别")
    check(guessed.get("intent") == headers[3], "意向列被正确识别")
    check(guessed.get("skills") == headers[4], "技能列被正确识别")
    check(guessed.get("contact_qq") == headers[5], "QQ 列被正确识别")
    check(guessed.get("hours_available") == headers[6], "可投入时长列被正确识别")
    check(guessed.get("wants_mentor") == headers[7], "求带列被正确识别")
    check(guessed.get("age") == headers[8], "年龄列被正确识别")

    with source.open("rb") as handle:
        response = client.post("/data/import/upload", data={
            "_csrf": csrf(client), "file": (handle, "wenjuanxing.xlsx")},
            content_type="multipart/form-data")
    page = response.get_data(as_text=True)
    check(response.status_code == 200, "上传后进入预览页")
    match = re.search(r'name="tmp" value="([^"]+)"', page)
    check(bool(match), "预览页带有临时文件标识")

    print("\n[3] 确认入库")
    payload = {
        "_csrf": csrf(client), "tmp": match.group(1) if match else "",
        "filename": "wenjuanxing.xlsx", "update_existing": "1",
    }
    for key, header in guessed.items():
        payload[f"map_{key}"] = header
    response = client.post("/data/import/confirm", data=payload, follow_redirects=True)
    check(response.status_code == 200, "确认导入返回 200")

    with app.app_context():
        members = models.list_members(status="all")
    check(len(members) == 3, f"入库 3 人（无昵称的那行被跳过），实际 {len(members)}")
    newbie = next((m for m in members if m["name"] == "新手甲"), None)
    veteran = next((m for m in members if m["name"] == "老手乙"), None)
    check(newbie is not None and newbie["experience"] == "newbie", "萌新被归为新手")
    check(veteran is not None and veteran["experience"] == "veteran", "『参加过几次』被归为老手")
    check(newbie is not None and newbie["intent"] == "casual", "『摸鱼』被归为休闲意向")
    check(newbie is not None and "cipher" in newbie["skills"], "『密码、数学』被解析成技能标签")
    elite = next((m for m in members if m["name"] == "大佬丙"), None)
    check(elite is not None and elite["skills"].get("cipher") == 5, "『密码5』带分数被解析成 5 分")
    check(newbie is not None and newbie["age"] == 17, "年龄列直接取数")
    expected_age = datetime.now().year - 2004
    check(veteran is not None and veteran["age"] == expected_age,
          f"出生年份 2004 被换算成年龄 {expected_age}")

    print("\n[4] 重复导入不会重复建人")
    with source.open("rb") as handle:
        response = client.post("/data/import/upload", data={
            "_csrf": csrf(client), "file": (handle, "wenjuanxing.xlsx")},
            content_type="multipart/form-data")
    match = re.search(r'name="tmp" value="([^"]+)"', response.get_data(as_text=True))
    payload["tmp"] = match.group(1) if match else ""
    client.post("/data/import/confirm", data=payload, follow_redirects=True)
    with app.app_context():
        check(len(models.list_members(status="all")) == 3, "二次导入以更新为主，人数不变")

    print("\n[5] 建队与分配")
    for name, kind, capacity, quota in [
        ("一队·冲榜", "competitive", "4", "0"),
        ("薪火队", "mentor", "6", "3"),
        ("三队·随缘", "casual", "6", "2"),
    ]:
        response = client.post("/teams/new", data={
            "_csrf": csrf(client), "name": name, "kind": kind,
            "capacity": capacity, "newbie_quota": quota, "status": "recruiting",
        }, follow_redirects=True)
    check(response.status_code == 200, "新建队伍成功")

    with app.app_context():
        teams = {t["name"]: t for t in models.list_teams()}
        check(len(teams) == 3, "三支队伍都已入库")
        rush_id = teams["一队·冲榜"]["id"]
        mentor_id = teams["薪火队"]["id"]
        elite_id = next(m["id"] for m in models.list_members() if m["name"] == "大佬丙")
        veteran_id = next(m["id"] for m in models.list_members() if m["name"] == "老手乙")

    client.post("/teams/assign/apply", data={
        "_csrf": csrf(client), "member_id": str(elite_id), "team_id": str(rush_id)},
        follow_redirects=True)
    client.post("/teams/assign/apply", data={
        "_csrf": csrf(client), "member_id": str(veteran_id), "team_id": str(mentor_id)},
        follow_redirects=True)
    with app.app_context():
        roster = models.team_roster(rush_id)
    check(len(roster) == 1 and roster[0]["name"] == "大佬丙", "成员被分配进队伍")
    with app.app_context():
        check(models.get_member(elite_id)["team_name"] == "一队·冲榜", "成员详情能看到所在队伍")

    print("\n[6] 推荐与自动草案")
    with app.app_context():
        mentor_team = models.get_team(mentor_id)
        mentor_team["roster"] = models.team_roster(mentor_id)
        candidate = models.get_member(newbie["id"])
        result = matching.evaluate(mentor_team, candidate)
        complement = matching.evaluate(mentor_team, models.get_member(elite_id),
                                       mentor_team["roster"])
        rush_team = models.get_team(rush_id)
        rush_team["roster"] = models.team_roster(rush_id)
        blocked = matching.evaluate(rush_team, candidate)
    check(not result["blockers"], "意向相符、名额未满时可以进队")
    check(any("老手" in reason for reason in result["reasons"]), "推荐理由里点出了队内有老手")
    check(any("空缺" in reason for reason in complement["reasons"]), "推荐理由里点出了技能互补")
    check(any("意向" in item for item in blocked["blockers"]), "意向冲突会被拦下并说明原因")

    response = client.post("/teams/assign/draft", data={"_csrf": csrf(client), "only_newbies": "1"},
                           follow_redirects=True)
    check("待确认的分配草案" in response.get_data(as_text=True), "生成草案后页面显示待确认")
    response = client.post("/teams/assign/draft/apply", data={"_csrf": csrf(client)},
                           follow_redirects=True)
    check("草案已执行" in response.get_data(as_text=True), "草案可以执行")
    with app.app_context():
        check(models.get_member(newbie["id"])["team_name"] is not None, "草案把新手分进了队伍")

    print("\n[7] 赛事报名")
    response = client.post("/events/new", data={
        "_csrf": csrf(client), "name": "CCBC 15", "kind": "external",
        "team_size_min": "1", "team_size_max": "4",
    }, follow_redirects=True)
    check(response.status_code == 200, "新建赛事成功")
    with app.app_context():
        event_id = models.list_events()[0]["id"]
    client.post(f"/events/{event_id}/register", data={
        "_csrf": csrf(client), "team_id": str(rush_id)}, follow_redirects=True)
    with app.app_context():
        check(len(models.event_registrations(event_id)) == 1, "队伍报名成功")

    print("\n[8] 导出")
    for url, label in [
        ("/data/export/members.xlsx", "成员总表"),
        ("/data/export/teams.xlsx", "队伍名册"),
        ("/data/export/unassigned.xlsx", "未分配名单"),
        (f"/data/export/event/{event_id}.xlsx", "赛事报名表"),
        ("/data/template.xlsx", "导入模板"),
    ]:
        response = client.get(url)
        check(response.status_code == 200 and len(response.data) > 2000,
              f"{label} 导出正常（{len(response.data)} 字节）")

    workbook = load_workbook(BytesIO(client.get("/data/export/members.xlsx").data))
    header = [cell.value for cell in workbook.active[1]]
    check("年龄" in header, "成员总表里有年龄列")
    check("真实姓名" not in header and "手机" not in header,
          "默认不收集真名和手机号，导出里根本不会出现这两列")

    print("\n[9] 各页面可访问")
    for url in ["/", "/members/", "/members/new", "/teams/", "/teams/assign", "/teams/1",
                "/events/", f"/events/{event_id}", "/data/import", "/data/export", "/logs",
                "/account"]:
        response = client.get(url)
        check(response.status_code == 200, f"GET {url} → {response.status_code}")

    print("\n[9.5] 人数上限与新手名额必须真的拦住（回归）")
    with app.app_context():
        # 注意：每支队伍用完全独立的人。add_to_team 会把人从原队移走，
        # 复用同一个成员会让后面的断言测出假结果（这个坑是测试自己暴露的）。
        limit_team = models.create_team({"name": "上限测试队", "kind": "casual",
                                         "capacity": 2, "newbie_quota": 2}, actor="test")
        quota_team = models.create_team({"name": "名额测试队", "kind": "mentor",
                                         "capacity": 6, "newbie_quota": 1}, actor="test")
        ids = {}
        for name, exp in [("上限老手甲", "veteran"), ("上限老手乙", "veteran"),
                          ("上限老手丙", "veteran"), ("名额新手甲", "newbie"),
                          ("名额新手乙", "newbie"), ("名额老手丙", "veteran")]:
            ids[name] = models.create_member({"name": name, "experience": exp}, "test")

    # --- 人数上限
    with app.app_context():
        models.add_to_team(limit_team, ids["上限老手甲"], actor="test")
        models.add_to_team(limit_team, ids["上限老手乙"], actor="test")
        check(len(models.team_roster(limit_team)) == 2, "把上限测试队填到 2/2")
        reason = None
        try:
            models.add_to_team(limit_team, ids["上限老手丙"], actor="test")
        except models.TeamLimitError as exc:
            reason = str(exc)
        check(reason is not None and "人数已满" in reason, f"满员后加人被拦下：{reason}")
        check(len(models.team_roster(limit_team)) == 2, "被拦下时队伍人数没有变")

    # --- 新手名额（老手不该被名额挡住）
    with app.app_context():
        models.add_to_team(quota_team, ids["名额新手甲"], actor="test")
        reason = None
        try:
            models.add_to_team(quota_team, ids["名额新手乙"], actor="test")
        except models.TeamLimitError as exc:
            reason = str(exc)
        check(reason is not None and "新手名额已满" in reason, f"新手名额满后被拦下：{reason}")
        models.add_to_team(quota_team, ids["名额老手丙"], actor="test")
        check(len(models.team_roster(quota_team)) == 2, "新手名额满了，老手照样能进")

    # --- 走真实的 HTTP 多选加人接口
    response = client.post(f"/teams/{limit_team}/members/add",
                           data={"_csrf": csrf(client), "member_id": str(ids["上限老手丙"])},
                           follow_redirects=True)
    html = response.get_data(as_text=True)
    check("人数已满" in html, "多选加人出错时会把原因显示给用户")
    check("已加入" not in html, "多选加人没有假装成功")
    with app.app_context():
        check(len(models.team_roster(limit_team)) == 2, "多选加人没有偷偷把人塞进去")

    # --- 界面本身也要拦住：满员时不能加的人应该是禁用的
    html = client.get(f"/teams/{limit_team}").get_data(as_text=True)
    check("加不进来" in html, "队伍页把加不进来的人标出来了")
    check("当前没有人能加进来" in html, "队伍页明确提示已经满了")

    print("\n[10] 安全边界")
    response = client.post("/teams/new", data={"name": "没有令牌的队"})
    check(response.status_code == 400, "缺少 CSRF 令牌的写操作被拒绝")
    response = client.post("/data/import/preview",
                           data={"_csrf": csrf(client), "tmp": "../../app.py"})
    check(response.status_code == 400, "构造路径读取服务器文件被拒绝")

    response = client.get("/login")
    headers = response.headers
    check(headers.get("X-Content-Type-Options") == "nosniff", "带上 nosniff 头")
    check(headers.get("X-Frame-Options") == "DENY", "禁止被 iframe 套壳")
    csp = headers.get("Content-Security-Policy", "")
    check("script-src 'self'" in csp, "CSP 只允许加载自己的脚本")
    check("frame-ancestors 'none'" in csp, "CSP 里也封了 iframe")
    check(headers.get("Cache-Control") == "no-store", "页面不进浏览器缓存")

    # 模板里一旦出现内联 on* 事件处理器，上面的 CSP 就会失效，所以这里扫一遍
    inline = []
    for path in (ROOT / "templates").glob("*.html"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\son(click|change|submit|load|input|focus|blur|error)\s*=", text):
            inline.append(f"{path.name}:{match.group(0).strip()}")
    check(not inline, f"模板里没有内联事件处理器（发现 {len(inline)} 处：{inline[:3]}）")

    # 登录限流：同一个用户名连续失败到上限后应被挡住
    for _ in range(5):
        client.post("/login", data={"_csrf": csrf(client),
                                    "username": "nosuchuser", "password": "Guess#12345"})
    response = client.post("/login", data={"_csrf": csrf(client),
                                           "username": "nosuchuser", "password": "Guess#12345"})
    check(response.status_code == 429, "连续失败 5 次后被限流（429）")
    check("等" in response.get_data(as_text=True), "限流页面告诉用户还要等多久")

    # 限流是按账号隔离的，不该误伤别的账号
    response = client.post("/login", data={"_csrf": csrf(client),
                                           "username": "admin", "password": "SmokeTest#2026"},
                           follow_redirects=True)
    check(response.status_code == 200, "一个账号被锁不影响另一个账号登录")

    # 密码策略
    check(auth.password_problem("12345678") is not None, "名单里的弱密码会被拒绝")
    check(auth.password_problem("short") is not None, "太短的密码会被拒绝")
    check(auth.password_problem("11111111") is not None, "纯数字密码会被拒绝")
    check(auth.password_problem("aaaaaaaa") is not None, "字符重复太多会被拒绝")
    check(auth.password_problem("Xk7#mQ2p") is None, "正常强度的密码可以通过")
    try:
        with app.app_context():
            auth.create_user("weakguy", "12345678")
        check(False, "弱密码建账号应该抛异常")
    except ValueError:
        check(True, "弱密码建账号会被拦下")

    print("\n" + "=" * 60)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        for label in FAILED:
            print(f"  - {label}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
