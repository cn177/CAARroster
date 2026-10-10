"""写入一批演示数据，方便第一眼看到界面长什么样。

    python app.py --seed-demo

只在你想先看看效果时用；正式库别跑，会混进假人。
"""
import random

import models
from skills import INTENT, SKILL_KEYS

HANDLES = [
    "纸鸢", "阿黎", "猫头鹰", "半夜三点", "老陈", "小满", "花生", "铁盒",
    "十七", "海盐", "摆烂王", "谜之微笑", "沉舟", "咕咕咕", "灯下黑", "白噪音",
    "算术家", "沉默的螺旋", "青鸟", "橘子汽水", "两点半", "拆解者", "空想家", "北极星",
    "咸鱼翻身", "莫比乌斯", "小键盘", "夜航船", "罐头", "老张", "糖霜", "逆向工程",
    "格温", "饼干", "阿基米德", "慢半拍", "镜面", "河图", "洛书", "打桩机",
    "菠萝油", "失忆症", "无名氏", "云上", "断线", "橘子头", "隐函数", "矩阵",
    "星号", "倒带",
]

TEAM_PLAN = [
    ("一队·冲榜", "competitive", 8, 1),
    ("二队·攻坚", "competitive", 8, 1),
    ("三队·随缘", "casual", 7, 2),
    ("四队·摸鱼", "casual", 8, 3),
    ("五队·养生", "casual", 8, 3),
    ("薪火队", "mentor", 6, 3),
]


def run(member_count: int = 50, seed: int = 20260101) -> None:
    random.seed(seed)

    members = []
    for index, handle in enumerate(HANDLES[:member_count]):
        if index < 8:
            experience, intent, mentor_capacity, wants_mentor = "elite", "competitive", 2, 0
        elif index < 22:
            experience = "veteran"
            intent = random.choice(["competitive", "casual", "mentor", "any"])
            mentor_capacity = random.choice([1, 2, 3])
            wants_mentor = 0
        else:
            experience, intent, mentor_capacity = "newbie", random.choice(
                ["casual", "casual", "competitive", "any"]), 0
            wants_mentor = 1

        skills = {}
        for key in random.sample(SKILL_KEYS, random.randint(2, 4)):
            base = 4 if experience in ("veteran", "elite") else 2
            skills[key] = max(1, min(5, base + random.choice([-1, 0, 1])))

        data = {
            "name": f"{handle}",
            "age": random.randint(15, 28),
            "contact_qq": str(random.randint(100000000, 999999999)),
            "contact_discord": f"{handle}#{random.randint(1000, 9999)}",
            "experience": experience,
            "hunts_played": {"elite": random.randint(8, 20),
                             "veteran": random.randint(2, 7)}.get(experience, 0),
            "intent": intent,
            "wants_mentor": wants_mentor,
            "mentor_capacity": mentor_capacity,
            "hours_available": random.choice([4, 8, 12, 16, 20, 30]),
            "sleep_schedule": random.choice(["night_owl", "night_owl", "flexible", "early_bird"]),
            "voice_ok": 1 if random.random() < 0.75 else 0,
            "skills": skills,
            "notes": "" if random.random() < 0.7 else "演示数据",
            "status": "active",
        }
        members.append(models.create_member(data, actor="seed"))

    created_teams = []
    for name, kind, capacity, quota in TEAM_PLAN:
        team_id = models.create_team({
            "name": name, "kind": kind, "capacity": capacity, "newbie_quota": quota,
            "pitch": {"competitive": "目标冲榜，赛期内基本全程在线。",
                      "casual": "节奏随缘，能来就来，重点是玩得开心。",
                      "mentor": "老手带新手，赛前会过一次练习题。"}[kind],
            "goal": "进前 30" if kind == "competitive" else "完赛就好",
            "voice_required": 1 if kind == "competitive" else 0,
            "status": "recruiting",
        }, actor="seed")
        created_teams.append((team_id, kind, capacity, quota))

    # 先把老手安排进冲击队，再让摸鱼队/带新队各有一个主心骨
    def experience_of(member_id):
        return models.get_member(member_id)["experience"]

    veterans = [m for m in members if experience_of(m) != "newbie"]
    newbies = [m for m in members if experience_of(m) == "newbie"]
    random.shuffle(veterans)

    for team_id, kind, capacity, quota in created_teams:
        if kind != "competitive":
            continue
        take = min(len(veterans), random.randint(4, max(4, capacity - 1)))
        for member_id in veterans[:take]:
            models.add_to_team(team_id, member_id, actor="seed")
        del veterans[:take]
        roster = models.team_roster(team_id)
        if roster:
            models.set_captain(team_id, roster[0]["id"], actor="seed")

    for team_id, kind, capacity, quota in created_teams:
        if kind == "competitive" or not veterans:
            continue
        models.add_to_team(team_id, veterans.pop(), actor="seed")
        if kind == "mentor":
            roster = models.team_roster(team_id)
            if roster:
                models.set_captain(team_id, roster[0]["id"], actor="seed")

    # 只给冲击队和带新队配新手，摸鱼队故意留空 —— 好让你在分配台上有得玩
    for team_id, kind, capacity, quota in created_teams:
        if kind not in ("competitive", "mentor"):
            continue
        room = capacity - len(models.team_roster(team_id))
        take = min(room, quota, len(newbies))
        for member_id in newbies[:take]:
            models.add_to_team(team_id, member_id, actor="seed")
        del newbies[:take]

    models.create_event({
        "name": "CCBC 15", "kind": "external", "team_size_min": 1, "team_size_max": 8,
        "notes": "演示数据：按实际规则改。",
    }, actor="seed")
    models.create_event({
        "name": "MIT Mystery Hunt 2027", "kind": "external",
        "team_size_min": 1, "team_size_max": 50,
        "notes": "演示数据：MITMH 队伍可以很大。",
    }, actor="seed")
    models.create_event({
        "name": "协会内部训练赛", "kind": "training",
        "team_size_min": 2, "team_size_max": 6,
    }, actor="seed")

    print(f"演示数据已写入：{len(members)} 名成员、{len(created_teams)} 支队伍、3 个赛事。")
    print("其中一部分人故意留作未分配，方便你在分配台上试手。")
