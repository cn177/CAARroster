"""问卷星导出文件的解析与导入。

流程是两步：先上传并预览（字段自动识别 + 人工改），确认后才写库。
问卷星只当"入口"，进来之后一律以本系统为准，不做双向同步。
"""
import csv
import io
import json
from pathlib import Path

from openpyxl import load_workbook

import models
from skills import (
    EXPERIENCE,
    normalize_experience,
    normalize_intent,
    normalize_sleep,
    normalize_yes,
    parse_age,
    parse_int,
    parse_skills,
)

# 目标字段 -> (显示名, 表头关键词)
FIELD_RULES = [
    ("phone", "手机号", ("手机", "电话", "mobile", "phone", "tel")),
    ("contact_qq", "QQ", ("qq", "企鹅")),
    ("contact_discord", "Discord", ("discord", "dc", "迪斯科", "dc号")),
    ("contact_email", "邮箱", ("邮箱", "email", "mail", "邮件")),
    ("age", "年龄", ("年龄", "岁数", "几岁", "出生", "多大")),
    ("real_name", "真实姓名", ("真实姓名", "真名", "真实名字")),
    ("name", "昵称", ("昵称", "圈名", "常用名", "称呼", "id", "名字", "姓名", "代号", "花名")),
    ("hunts_played", "参赛次数", ("参赛次数", "参加过几", "参赛场次", "场次", "参加次数")),
    ("experience", "经验等级", ("经验", "水平", "段位", "老手", "新手", "程度", "自我评价")),
    ("intent", "参赛意向", ("意向", "冲击", "摸鱼", "定位", "想加入", "参赛类型", "目标")),
    ("mentor_capacity", "可带新人数", ("带新", "能带", "愿意带", "带几", "带多少")),
    ("wants_mentor", "希望被带", ("需要带", "求带", "希望被带", "需要老手", "找老手", "想被带", "被老手", "老手带", "求大佬")),
    ("hours_available", "可投入时长", ("可投入", "小时", "时长", "在线时间", "投入时间")),
    ("sleep_schedule", "作息", ("作息", "熬夜", "睡觉", "夜猫", "起床")),
    ("voice_ok", "能否语音", ("语音", "开麦", "麦克风", "麦")),
    ("skills", "技能", ("技能", "擅长", "拿手", "会什么", "能力", "强项")),
    ("best_result", "最好成绩", ("最好成绩", "名次", "战绩", "拿过")),
    ("notes", "备注", ("备注", "其他", "补充", "想说的", "自由", "还有")),
]

FIELD_LABEL = {key: label for key, label, _ in FIELD_RULES}


# ================================================================== 读文件
def _clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _find_header_row(rows: list[list]) -> int:
    """问卷星导出的表头不一定在第一行，找第一行"有多个非空单元格"的。"""
    for idx, row in enumerate(rows[:10]):
        non_empty = sum(1 for cell in row if _clean(cell))
        if non_empty >= 2:
            return idx
    return 0


def read_table(path, sheet: str | None = None):
    """返回 (headers, rows, sheet_names)。rows 是 [{表头: 值}]。"""
    suffix = Path(path).suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".xltx"):
        return _read_xlsx(path, sheet)
    return _read_csv(path)


def _read_xlsx(path, sheet=None):
    workbook = load_workbook(path, read_only=True, data_only=True)
    names = workbook.sheetnames
    active = sheet if sheet in names else names[0]
    ws = workbook[active]
    raw = [list(r) for r in ws.iter_rows(values_only=True)]
    workbook.close()
    return _finish(raw, names)


def _read_csv(path):
    data = Path(path).read_bytes()
    text = ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    raw = [row for row in csv.reader(io.StringIO(text))]
    return _finish(raw, ["CSV"])


def _finish(raw, sheet_names):
    if not raw:
        return [], [], sheet_names
    header_idx = _find_header_row(raw)
    header_cells = raw[header_idx]
    headers, seen = [], {}
    for i, cell in enumerate(header_cells):
        name = _clean(cell) or f"未命名列{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        headers.append(name)
    rows = []
    for line in raw[header_idx + 1:]:
        if not any(_clean(c) for c in line):
            continue
        row = {}
        for i, header in enumerate(headers):
            row[header] = line[i] if i < len(line) else ""
        rows.append(row)
    return headers, rows, sheet_names


# ================================================================== 字段识别
def guess_mapping(headers: list[str]) -> dict:
    """把问卷星的题目文字猜成我们的字段。已占用的表头不会被重复分配。"""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for key, _label, keywords in FIELD_RULES:
        best = None
        for header in headers:
            if header in used:
                continue
            lowered = header.lower()
            score = sum(len(k) for k in keywords if k in lowered)
            if not score:
                continue
            if best is None or score > best[0]:
                best = (score, header)
        if best:
            mapping[key] = best[1]
            used.add(best[1])
    return mapping


# ================================================================== 行 -> 成员
def parse_row(row: dict, mapping: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    data: dict = {}

    for key, header in mapping.items():
        raw = row.get(header)
        if key == "skills":
            data["skills"] = parse_skills(raw)
        elif key == "experience":
            hunts = parse_int(row.get(mapping.get("hunts_played", ""), ""), None)
            data["experience"] = normalize_experience(_clean(raw), hunts)
        elif key == "intent":
            data["intent"] = normalize_intent(_clean(raw))
        elif key == "sleep_schedule":
            data["sleep_schedule"] = normalize_sleep(_clean(raw))
        elif key in ("wants_mentor", "voice_ok"):
            data[key] = 1 if normalize_yes(raw) else 0
        elif key in ("hunts_played", "mentor_capacity", "hours_available"):
            data[key] = parse_int(raw, 0 if key != "hours_available" else None)
        elif key == "age":
            data["age"] = parse_age(raw)
        else:
            data[key] = _clean(raw)

    data.setdefault("skills", {})
    data.setdefault("name", "")
    data.setdefault("experience", "newbie")
    data.setdefault("intent", "any")
    data.setdefault("sleep_schedule", "flexible")
    data.setdefault("wants_mentor", 0)
    data.setdefault("voice_ok", 1)
    data.setdefault("mentor_capacity", 0)
    data.setdefault("hunts_played", 0)

    if not data["name"]:
        warnings.append("没有昵称，已跳过")
    if data["experience"] != "newbie" and not data.get("mentor_capacity"):
        warnings.append("老手但没填可带新人数")
    return data, warnings


def build_members(rows: list[dict], mapping: dict, limit: int | None = None):
    parsed, all_warnings = [], []
    for index, row in enumerate(rows):
        if limit is not None and index >= limit:
            break
        data, warnings = parse_row(row, mapping)
        if data["name"]:
            parsed.append(data)
        else:
            all_warnings.append(f"第 {index + 2} 行：没有昵称，跳过")
    return parsed, all_warnings


# ================================================================== 入库
def run_import(parsed: list[dict], filename: str, mapping: dict, actor: str,
               update_existing: bool = True) -> dict:
    from db import get_db, log, now

    db = get_db()
    cur = db.execute(
        "INSERT INTO import_batches(filename, mapping, created_at) VALUES(?,?,?)",
        (filename, json.dumps(mapping, ensure_ascii=False), now()),
    )
    batch_id = cur.lastrowid
    db.commit()

    created = updated = skipped = 0
    details: list[str] = []
    for data in parsed:
        duplicate = models.find_duplicate(
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            qq=data.get("contact_qq", ""),
            discord=data.get("contact_discord", ""),
            email=data.get("contact_email", ""),
        )
        if duplicate and not update_existing:
            skipped += 1
            continue
        if duplicate:
            # 只覆盖有值的字段；技能/经验/意向属于"本人最新自述"，以导入为准
            patch = {}
            for k, v in data.items():
                if k in ("experience", "intent"):
                    patch[k] = v
                elif v not in ("", None, {}, 0, []):
                    patch[k] = v
            if not patch.get("skills"):
                patch.pop("skills", None)
            try:
                models.update_member(duplicate["id"], patch, actor)
                updated += 1
            except Exception as exc:  # noqa: BLE001 - 单行失败不该中断整批导入
                skipped += 1
                details.append(f"{data.get('name')}: 更新失败 {exc}")
        else:
            try:
                models.create_member(data, actor, batch_id=batch_id)
                created += 1
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                details.append(f"{data.get('name')}: 写入失败 {exc}")

    db.execute(
        """UPDATE import_batches SET total_rows=?, created_count=?, updated_count=?,
                                    skipped_count=?, detail=? WHERE id=?""",
        (len(parsed), created, updated, skipped,
         json.dumps(details[:50], ensure_ascii=False), batch_id),
    )
    log(db, actor, "import.run", f"batch:{batch_id}",
        {"file": filename, "created": created, "updated": updated, "skipped": skipped})
    db.commit()
    return {"batch_id": batch_id, "created": created, "updated": updated,
            "skipped": skipped, "total": len(parsed), "details": details}


# ================================================================== 模板
def write_template(path) -> str:
    """导出一份带表头的空白模板，方便手工填或对齐问卷星字段。"""
    from openpyxl import Workbook

    workbook = Workbook()
    ws = workbook.active
    ws.title = "成员导入模板"
    headers = [label for _key, label, _kw in FIELD_RULES]
    ws.append(headers)
    example = ["示例：小明", "", "", "", "", "", "2", "老手", "冲击", "2", "0",
               "20", "夜猫子", "是", "密码5;数学4;编程3", "第3名", "随便写点什么"]
    ws.append(example)
    for i, header in enumerate(headers, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = max(12, len(header) + 4)
    workbook.save(path)
    return str(path)


def field_labels() -> dict:
    return dict(FIELD_LABEL)


def experience_label(key: str) -> str:
    return EXPERIENCE.get(key, key)
