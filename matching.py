"""组队匹配与分配草案。

这里只做"给人看的建议"：每条推荐都带理由，最终由运营拍板。
不做黑箱自动分配，puzzle hunt 队伍的默契度比技能互补重要得多。
"""
from skills import INTENT, SKILL_KEYS, SKILL_LABEL, STRONG_RATING, TEAM_KIND


# ------------------------------------------------------------------ 队伍画像
def skill_profile(roster) -> dict:
    """把队伍现有成员折算成技能画像：{key: {"max": 最高自评, "strong": 强手人数}}"""
    profile = {k: {"max": 0, "strong": 0} for k in SKILL_KEYS}
    for member in roster:
        skills = member.get("skills") or {}
        if isinstance(skills, str):
            continue
        for key, rating in skills.items():
            if key not in profile:
                continue
            rating = int(rating or 0)
            profile[key]["max"] = max(profile[key]["max"], rating)
            if rating >= STRONG_RATING:
                profile[key]["strong"] += 1
    return profile


def team_gaps(profile) -> list[str]:
    """队伍里没人能扛的技能，就是缺口。"""
    return [k for k in SKILL_KEYS if profile[k]["strong"] == 0]


def member_strengths(member) -> list[str]:
    skills = member.get("skills") or {}
    if isinstance(skills, str):
        return []
    return [k for k, v in skills.items() if k in SKILL_LABEL and int(v or 0) >= STRONG_RATING]


def describe_profile(profile, limit=4) -> list[str]:
    """画出队伍的能力条，给运营一眼看强弱。"""
    items = [(SKILL_LABEL[k], profile[k]["max"]) for k in SKILL_KEYS if profile[k]["max"] > 0]
    items.sort(key=lambda x: -x[1])
    return [f"{name} {score}" for name, score in items[:limit]]


# ------------------------------------------------------------------ 单队打分
def evaluate(team: dict, member: dict, roster=None) -> dict:
    """给"把某个成员放进某队"打分。返回 score / reasons / blockers。"""
    roster = team.get("roster") if roster is None else roster
    roster = roster or []
    profile = skill_profile(roster)
    reasons: list[str] = []
    blockers: list[str] = []
    score = 0

    size = len(roster)
    capacity = int(team.get("capacity") or 6)
    newbie_count = sum(1 for m in roster if m.get("experience") == "newbie")
    newbie_quota = int(team.get("newbie_quota") or 0)
    is_newbie = member.get("experience") == "newbie"

    if team.get("status") not in (None, "", "recruiting"):
        blockers.append(f"队伍已{team.get('status')}，不再招人")
    if size >= capacity:
        blockers.append(f"人数已满（{size}/{capacity}）")
    if is_newbie and newbie_count >= newbie_quota:
        blockers.append(f"新手名额已满（{newbie_count}/{newbie_quota}）")

    # ---- 意向匹配（权重最高，因为这是本人明确说过的偏好）
    kind = team.get("kind")
    intent = member.get("intent") or "any"
    if kind == "competitive":
        if intent in ("competitive", "any"):
            score += 35
            reasons.append("想冲击 × 冲击队")
        else:
            score -= 40
            blockers.append("本人意向不是冲击，进冲击队大概会痛苦")
    elif kind == "casual":
        if intent in ("casual", "any"):
            score += 28
            reasons.append("想摸鱼 × 摸鱼队")
        elif intent == "competitive":
            score -= 30
            reasons.append("意向偏冲击，摸鱼队可能吃不饱")
    elif kind == "mentor":
        if intent in ("mentor", "casual", "any"):
            score += 22
            reasons.append("带新队，适合新老混编")
        elif intent == "competitive":
            score -= 10

    # ---- 技能互补
    gaps = team_gaps(profile)
    strengths = member_strengths(member)
    filled = [k for k in strengths if k in gaps]
    if filled:
        bonus = min(30, 14 * len(filled))
        score += bonus
        names = "、".join(SKILL_LABEL[k] for k in filled[:3])
        reasons.append(f"补上队伍「{names}」的空缺")
    elif strengths:
        covered = [k for k in strengths if k not in gaps]
        if covered:
            score += 4
            reasons.append(f"专长（{SKILL_LABEL[covered[0]]}）队伍里已有人能扛，属于加深")

    # ---- 时间与沟通
    hours = member.get("hours_available")
    if hours:
        team_hours = [m.get("hours_available") or 0 for m in roster if m.get("hours_available")]
        if team_hours:
            avg = sum(team_hours) / len(team_hours)
            diff = abs(avg - hours)
            if diff <= 3:
                score += 12
                reasons.append(f"可投入时长接近队伍均值（约 {avg:.0f} 小时）")
            elif diff >= 12:
                score -= 12
                reasons.append(f"时长差距大（本人 {hours} 小时 vs 队伍均值 {avg:.0f}）")
        else:
            score += 6
    sleep = member.get("sleep_schedule")
    if sleep and sleep != "flexible":
        same = [m for m in roster if m.get("sleep_schedule") == sleep]
        if same:
            score += 5
            reasons.append("作息一致，深更半夜能凑上人")

    if team.get("voice_required") and not member.get("voice_ok"):
        score -= 20
        blockers.append("队伍要求开麦，本人不方便")
    elif member.get("voice_ok") and any(m.get("voice_ok") for m in roster):
        score += 4

    # ---- 队伍结构
    if is_newbie:
        veterans = [m for m in roster if m.get("experience") in ("veteran", "elite")]
        willing = [m for m in veterans
                   if m.get("team_role") in ("mentor", "captain") or m.get("mentor_capacity")]
        if willing:
            score += 15
            reasons.append(f"队里有 {len(willing)} 位愿意带新的老手")
        elif veterans:
            score += 8
            reasons.append(f"队里有 {len(veterans)} 位老手（没写明带新，但通常能问）")
        elif roster:
            score -= 8
            reasons.append("队里暂时没有老手，新手可能没人可问")
        if member.get("wants_mentor"):
            score += 6
    else:
        # 老手：往缺老手的队伍引
        vets = sum(1 for m in roster if m.get("experience") in ("veteran", "elite"))
        if vets == 0 and roster:
            score += 14
            reasons.append("队里还没有老手，你进去就是主心骨")
        if member.get("mentor_capacity") and kind in ("mentor", "casual"):
            load = sum(1 for m in roster if m.get("experience") == "newbie")
            if load < int(member.get("mentor_capacity") or 0):
                score += 12
                reasons.append(f"你愿意带 {member['mentor_capacity']} 人，这队只有 {load} 个新手")

    # ---- 队伍还差多少人（越缺越优先补）
    if roster and size < capacity:
        score += max(0, 6 - abs(capacity - size))
    if not roster:
        score += 10
        reasons.append("空队，正好当班底")

    return {"score": score, "reasons": reasons, "blockers": blockers, "gap": gaps}


def recommend_teams(member: dict, teams: list[dict], limit: int = 5,
                    include_blocked: bool = False, min_score: int = 0):
    """给出推荐队伍。默认只给非负分的（分数为负说明处处将就，不如让人工判断）。"""
    scored = []
    for team in teams:
        result = evaluate(team, member)
        if result["blockers"] and not include_blocked:
            continue
        if result["score"] < min_score and not include_blocked:
            continue
        scored.append({"team": team, **result})
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]


# ------------------------------------------------------------------ 分配草案
def draft_allocation(members: list[dict], teams: list[dict], only_newbies: bool = True):
    """贪心生成一份分配草案，交给运营确认。

    思路：先处理"选择最少"的人（可行队伍数最少的），避免最后剩下一堆没人要的。
    """
    pool = [m for m in members if m.get("team_id") is None]
    if only_newbies:
        pool = [m for m in pool if m.get("experience") == "newbie"]

    live = []
    for team in teams:
        if team.get("status") != "recruiting":
            continue
        live.append({"team": team, "roster": list(team.get("roster") or [])})

    # 计算每个人的可行队伍数，最受限的先安排
    def feasible_count(member):
        return sum(1 for slot in live if not evaluate(slot["team"], member, slot["roster"])["blockers"])

    pool.sort(key=lambda m: (feasible_count(m), 0 if m.get("experience") == "newbie" else 1))

    assignments, leftovers = [], []
    for member in pool:
        best = None
        for slot in live:
            result = evaluate(slot["team"], member, slot["roster"])
            if result["blockers"]:
                continue
            if best is None or result["score"] > best["score"]:
                best = {"score": result["score"], "reasons": result["reasons"], "slot": slot}
        # 分数为负说明只是"硬塞得进去"，与其塞进去不如留给人工处理
        if best is None or best["score"] < 0:
            leftovers.append(member)
            continue
        slot = best["slot"]
        assignments.append({
            "member": member,
            "team": slot["team"],
            "score": best["score"],
            "reasons": best["reasons"],
        })
        # 更新模拟状态，让后面的推荐看到最新人数
        slot["roster"].append({**member, "team_role": "newbie"
                               if member.get("experience") == "newbie" else "member"})

    return {"assignments": assignments, "leftovers": leftovers}


def team_needs(team: dict) -> list[str]:
    """队伍缺口 + 还差多少人，用于分配台右侧卡片。"""
    profile = skill_profile(team.get("roster") or [])
    gaps = team_gaps(profile)
    size = len(team.get("roster") or [])
    capacity = int(team.get("capacity") or 6)
    needs = []
    if size < capacity:
        needs.append(f"还差 {capacity - size} 人")
    else:
        needs.append("人数已满")
    if gaps:
        needs.append("缺 " + "、".join(SKILL_LABEL[k] for k in gaps[:3]))
    return needs


def intent_match_label(team_kind: str, intent: str) -> str:
    return f"{TEAM_KIND.get(team_kind, team_kind)} / 意向{INTENT.get(intent, intent)}"
