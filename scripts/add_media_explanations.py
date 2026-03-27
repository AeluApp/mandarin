#!/usr/bin/env python3
"""Add explanation fields to all comprehension questions in media_catalog.json."""

import json
import re
import sys

CATALOG_PATH = "data/media_catalog.json"


def get_correct_answer(q):
    """Extract the correct answer text from a question."""
    if q.get("type") == "vocab_check" or (not q.get("type") and q.get("answer")):
        return q.get("answer", "")
    for opt in q.get("options", []):
        if opt.get("correct"):
            return opt.get("text_en", opt.get("text", ""))
    return ""


def get_correct_hanzi(q):
    """Get the correct answer's hanzi for mc questions."""
    for opt in q.get("options", []):
        if opt.get("correct"):
            return opt.get("text", "")
    return ""


def extract_vocab_hanzi(q):
    """Extract the hanzi word being asked about in a vocab question."""
    qzh = q.get("q_zh", "")
    qen = q.get("q_en", "")

    # Pattern 1: hanzi followed by pinyin in parens — 早餐 (zǎocān)
    m = re.search(r'([\u4e00-\u9fff]+)\s*\(', qzh)
    if m:
        return m.group(1)

    # Pattern 2: hanzi followed by 是什么意思 directly — 发现是什么意思
    m = re.search(r'^([\u4e00-\u9fff]{1,4})是什么意思', qzh)
    if m:
        return m.group(1)

    # Pattern 3a: X在... — 关系在这个语境下, 后悔在NJ的, 内卷在教育语境下
    m = re.search(r'^([\u4e00-\u9fff]{1,4})在', qzh)
    if m:
        return m.group(1)

    # Pattern 3b: X为什么 — 无为为什么不能...
    m = re.search(r'^([\u4e00-\u9fff]{1,4})为什么', qzh)
    if m:
        return m.group(1)

    # Pattern 3c: X这个 — 意境这个概念
    m = re.search(r'^([\u4e00-\u9fff]{1,4})这个', qzh)
    if m:
        return m.group(1)

    # Pattern 3d: X的Y — contextual with 的
    m = re.search(r'^([\u4e00-\u9fff]{1,3})的', qzh)
    if m and len(m.group(1)) <= 3:
        return m.group(1)

    # Pattern 4: quoted hanzi at start — '邻居' or "邻居"
    m = re.search(r"^['\"\u2018\u2019\u201c\u201d]([\u4e00-\u9fff]+)['\"\u2018\u2019\u201c\u201d]", qzh)
    if m:
        return m.group(1)

    # Pattern 5: hanzi from q_en — What does X (hanzi) mean?
    m = re.search(r'([\u4e00-\u9fff]+)', qen)
    if m:
        return m.group(1)

    # Pattern 6: first hanzi block in qzh (short grab, max 4 chars)
    m = re.search(r'([\u4e00-\u9fff]{1,4})', qzh)
    if m:
        return m.group(1)

    return ""


def get_entry_context(entry):
    """Build a context string from whatever description fields exist."""
    seg = entry.get("segment", {})
    if seg.get("description"):
        return seg["description"]
    if entry.get("description_en"):
        return entry["description_en"]
    return entry.get("title", "")


def generate_explanation(q, entry):
    """Generate a short explanation for a question."""
    q_en = q.get("q_en", q.get("q_zh", ""))
    qtype = q.get("type", "")

    # Vocab check questions
    if qtype == "vocab_check" or (not qtype and q.get("answer")):
        hanzi = extract_vocab_hanzi(q)
        answer = q.get("answer", "")
        return _vocab_explanation(hanzi, answer, entry)

    # MC questions
    correct = get_correct_answer(q)
    correct_hanzi = get_correct_hanzi(q)
    return _mc_explanation(q_en, correct, correct_hanzi, entry)


# Character breakdowns for common vocab
BREAKDOWNS = {
    "早餐": "早 (early) + 餐 (meal) — literally 'early meal.'",
    "午餐": "午 (noon) + 餐 (meal) — literally 'noon meal.'",
    "晚餐": "晚 (evening) + 餐 (meal) — literally 'evening meal.'",
    "好吃": "好 (good) + 吃 (eat) — literally 'good to eat.'",
    "好喝": "好 (good) + 喝 (drink) — literally 'good to drink.'",
    "好看": "好 (good) + 看 (look) — literally 'good to look at.'",
    "同学": "同 (same) + 学 (study) — people who study together.",
    "同学们": "同学 (classmate) + 们 (plural) — a group of students.",
    "老师": "老 (venerable) + 师 (master) — a respectful term for teacher.",
    "学生": "学 (study) + 生 (person) — literally 'studying person.'",
    "朋友": "朋 and 友 both relate to companionship — a friend.",
    "生活": "生 (life) + 活 (living) — daily life or livelihood.",
    "工作": "工 (work) + 作 (do/make) — a job or to work.",
    "觉得": "觉 (feel) + 得 (obtain) — to feel or think something.",
    "喜欢": "喜 (joy) + 欢 (happiness) — to like or enjoy.",
    "漂亮": "Both characters together mean beautiful or pretty.",
    "高兴": "高 (high) + 兴 (mood) — happy, in high spirits.",
    "认识": "认 (recognize) + 识 (know) — to know or be acquainted with.",
    "开心": "开 (open) + 心 (heart) — 'open heart,' meaning happy.",
    "米粉": "米 (rice) + 粉 (noodle) — rice noodles.",
    "鸡蛋": "鸡 (chicken) + 蛋 (egg) — a chicken egg.",
    "煎饼": "煎 (pan-fry) + 饼 (flatbread) — a pan-fried crepe.",
    "拉面": "拉 (pull) + 面 (noodles) — hand-pulled noodles.",
    "豆腐": "豆 (bean) + 腐 (curd) — bean curd, tofu.",
    "饺子": "饺 (dumpling) + 子 (small thing) — dumplings.",
    "包子": "包 (wrap) + 子 (small thing) — steamed filled buns.",
    "火锅": "火 (fire) + 锅 (pot) — literally 'fire pot,' hot pot.",
    "牛肉": "牛 (cow) + 肉 (meat) — beef.",
    "猪肉": "猪 (pig) + 肉 (meat) — pork.",
    "人生": "人 (person) + 生 (life) — one's life path.",
    "后悔": "后 (after) + 悔 (regret) — to regret, looking back.",
    "选择": "选 (select) + 择 (choose) — a choice or to choose.",
    "照顾": "照 (look after) + 顾 (care for) — to take care of someone.",
    "孤独": "孤 (alone) + 独 (solitary) — loneliness or isolation.",
    "习惯": "习 (practice) + 惯 (accustomed) — a habit.",
    "舆论": "舆 (public) + 论 (opinion) — public opinion.",
    "话语权": "话语 (speech) + 权 (power) — the right to speak.",
    "价值观": "价值 (value) + 观 (view) — values or worldview.",
    "嫌疑人": "嫌疑 (suspicion) + 人 (person) — a suspect.",
    "证据": "证 (proof) + 据 (evidence) — evidence.",
    "幸福": "幸 (fortunate) + 福 (blessing) — happiness.",
    "回忆": "回 (return) + 忆 (memory) — to recall, a memory.",
    "旅行": "旅 (travel) + 行 (go) — a trip or to travel.",
    "风景": "风 (wind) + 景 (scenery) — landscape or scenery.",
    "故事": "故 (old) + 事 (matter) — a story.",
    "电影": "电 (electric) + 影 (shadow) — 'electric shadow,' a movie.",
    "音乐": "音 (sound) + 乐 (music) — music.",
    "安静": "安 (peaceful) + 静 (quiet) — quiet or tranquil.",
    "危险": "危 (danger) + 险 (peril) — dangerous.",
    "紧张": "紧 (tight) + 张 (stretch) — tense or nervous.",
    "害怕": "害 (harm) + 怕 (fear) — to be afraid.",
    "努力": "努 (exert) + 力 (strength) — to work hard.",
    "帮助": "帮 (help) + 助 (assist) — to help.",
    "重要": "重 (important) + 要 (need) — important.",
    "方便": "方 (way) + 便 (convenient) — convenient.",
    "健康": "健 (strong) + 康 (well-being) — healthy.",
    "感动": "感 (feel) + 动 (move) — to be moved emotionally.",
    "责任": "责 (duty) + 任 (responsibility) — responsibility.",
    "秘密": "秘 (secret) + 密 (hidden) — a secret.",
    "信任": "信 (believe) + 任 (trust) — trust.",
    "命运": "命 (fate) + 运 (fortune) — destiny or fate.",
    "压力": "压 (press) + 力 (force) — pressure or stress.",
    "温暖": "温 (warm) + 暖 (warm) — warmth, physical or emotional.",
    "距离": "距 (distance) + 离 (apart) — distance or gap.",
    "矛盾": "矛 (spear) + 盾 (shield) — contradiction.",
    "真相": "真 (true) + 相 (appearance) — the truth.",
    "勇气": "勇 (brave) + 气 (spirit) — courage.",
    "梦想": "梦 (dream) + 想 (think) — a dream or aspiration.",
    "自由": "自 (self) + 由 (from) — freedom.",
    "沉默": "沉 (sink) + 默 (silent) — silence.",
    "坚持": "坚 (firm) + 持 (hold) — to persist or insist.",
    "误会": "误 (mistake) + 会 (understanding) — a misunderstanding.",
    "表达": "表 (express) + 达 (reach) — to express.",
    "陪伴": "陪 (accompany) + 伴 (companion) — to keep company.",
    "成长": "成 (become) + 长 (grow) — to grow up or mature.",
    "善良": "善 (good) + 良 (fine) — kind-hearted.",
    "牺牲": "牺 and 牲 both refer to sacrificial animals — sacrifice.",
    "希望": "希 (hope) + 望 (look) — hope or to hope.",
    "记忆": "记 (record) + 忆 (recall) — memory.",
    "放弃": "放 (release) + 弃 (abandon) — to give up.",
    "原谅": "原 (original) + 谅 (understand) — to forgive.",
    "尊重": "尊 (revere) + 重 (important) — respect.",
    "沟通": "沟 (channel) + 通 (through) — communication.",
    "挑战": "挑 (provoke) + 战 (battle) — a challenge.",
    "偏见": "偏 (slanted) + 见 (view) — bias or prejudice.",
    "困境": "困 (trapped) + 境 (situation) — a predicament.",
    "身份": "身 (body) + 份 (role) — identity.",
    "传统": "传 (pass on) + 统 (system) — tradition.",
    "现代": "现 (present) + 代 (era) — modern.",
    "乡愁": "乡 (hometown) + 愁 (sorrow) — homesickness.",
    "归属感": "归属 (belonging) + 感 (feeling) — sense of belonging.",
    "代沟": "代 (generation) + 沟 (gap) — generation gap.",
    "关系": "关 (connect) + 系 (tie) — relationship or connection.",
    "离开": "离 (leave) + 开 (open/away) — to leave or depart.",
    "建筑": "建 (build) + 筑 (construct) — building or architecture.",
    "发现": "发 (send out) + 现 (appear) — to discover.",
    "难过": "难 (difficult) + 过 (pass) — sad, hard to get through.",
    "海鲜": "海 (sea) + 鲜 (fresh) — seafood.",
    "朝廷": "朝 (court/dynasty) + 廷 (hall) — the imperial court.",
    "腐败": "腐 (rotten) + 败 (ruined) — corruption or decay.",
    "批判": "批 (criticize) + 判 (judge) — critique, deeper than mere criticism.",
    "地缘": "地 (land) + 缘 (connection) — geographic ties.",
    "内卷": "内 (inward) + 卷 (curl) — involution, exhausting competition.",
    "屈辱": "屈 (bend/submit) + 辱 (disgrace) — humiliation.",
    "维权": "维 (protect) + 权 (rights) — defending one's rights.",
    "污名化": "污名 (stigma) + 化 (turn into) — stigmatization.",
    "意境": "意 (meaning) + 境 (realm) — an artistic mood beyond words.",
    "超脱": "超 (transcend) + 脱 (escape) — detachment, transcendence.",
    "现代性": "现代 (modern) + 性 (nature) — modernity as a condition.",
    "务工": "务 (engage in) + 工 (labor) — migrant labor.",
    "克制": "克 (restrain) + 制 (control) — restraint, emotional control.",
    "无为": "无 (without) + 为 (action) — non-action, not laziness but conscious non-interference.",
    "迷失": "迷 (lost) + 失 (lose) — to be lost, disoriented.",
    "碎片化": "碎片 (fragment) + 化 (turn into) — fragmentation.",
    "修辞": "修 (refine) + 辞 (words) — rhetoric, the craft of language.",
    "作业": "作 (do) + 业 (work) — homework or assignments.",
    "邻居": "邻 (neighbor) + 居 (reside) — neighbor.",
    "手艺": "手 (hand) + 艺 (skill) — craftsmanship, a manual skill.",
    "体制": "体 (body/system) + 制 (structure) — system or institution.",
    "雾": "A single character meaning fog or mist.",
    "环卫": "环 (environment) + 卫 (protect) — sanitation work.",
    "贷款": "贷 (lend) + 款 (funds) — a loan.",
    "新鲜": "新 (new) + 鲜 (fresh) — fresh.",
    "熟客": "熟 (familiar) + 客 (guest) — a regular customer.",
    "赶集": "赶 (hurry to) + 集 (market) — going to a rural market.",
    "便宜": "便 (convenient) + 宜 (suitable) — cheap, inexpensive.",
    "障碍": "障 (block) + 碍 (hinder) — barrier or obstacle.",
    "层级": "层 (layer) + 级 (rank) — hierarchy.",
    "气氛": "气 (air) + 氛 (atmosphere) — atmosphere, mood.",
    "经营": "经 (manage) + 营 (operate) — to run a business.",
    "共鸣": "共 (together) + 鸣 (sound) — resonance, shared feeling.",
    "审美": "审 (examine) + 美 (beauty) — aesthetic sense.",
    "潜规则": "潜 (hidden) + 规则 (rules) — unwritten rules.",
    "地缘政治": "地缘 (geographic ties) + 政治 (politics) — geopolitics.",
}


def _vocab_explanation(hanzi, answer, entry):
    """Generate explanation for vocab_check questions."""
    if hanzi in BREAKDOWNS:
        return f"{hanzi} combines {BREAKDOWNS[hanzi]}"

    # For answers in Chinese (interpretive questions), give a concise gloss
    if answer and re.search(r'[\u4e00-\u9fff]', answer):
        ctx = get_entry_context(entry)
        brief = _brief_desc(ctx)
        return f"Here {hanzi} carries a layered meaning — {brief}."

    # Simple English answer
    if answer:
        return f"{hanzi} means {answer}."

    return f"{hanzi} is a key term in this segment."


def _mc_explanation(q_en, correct, correct_hanzi, entry):
    """Generate explanation for multiple-choice questions."""
    q_lower = q_en.lower()
    seg = entry.get("segment", {})
    desc = seg.get("description", "")
    brief = _brief_desc(desc)

    # Check if the correct answer is in Chinese
    is_cn_answer = bool(re.search(r'[\u4e00-\u9fff]', correct))
    bool(re.search(r'[\u4e00-\u9fff]', q_en))

    # For Chinese answers, use the answer with context reference
    if is_cn_answer:
        return f"{correct} — {brief}."

    # Food/cooking questions
    if any(w in q_lower for w in ["what breakfast", "what food", "what do they make",
                                   "what do they eat", "what dish", "what meal"]):
        return f"The episode features {correct.lower()} as the main dish."

    if any(w in q_lower for w in ["what is inside", "what ingredient", "what is added",
                                   "what crunchy", "what item"]):
        return f"You can see {correct.lower()} being added during the preparation."

    if any(w in q_lower for w in ["first step", "how do they make", "what method",
                                   "what motion", "what technique"]):
        return f"The clip shows the process starting with {correct.lower()}."

    if "what subject" in q_lower or "what does he teach" in q_lower:
        return f"The scene takes place in {correct.lower()} class."

    if "what is" in q_lower and "job" in q_lower:
        return f"His role is {correct.lower()} — {brief}."

    if "what is" in q_lower and ("looking" in q_lower or "searching" in q_lower):
        return f"He's searching for {correct.lower()} at the scene."

    # How many
    if "how many" in q_lower:
        return f"The segment shows {correct.lower()} — {brief}."

    # Appearance/behavior/attitude/mood
    if any(w in q_lower for w in ["how does", "how would you describe",
                                   "what attitude", "what tone", "what mood"]):
        return f"The scene reads as {correct.lower()} — {brief}."

    # What is the biggest/core/main
    if any(w in q_lower for w in ["biggest", "core", "main", "primary", "characterize"]):
        return f"{_cap(correct)} — {brief}."

    # Where/location — avoid "at at home"
    if any(w in q_lower for w in ["where", "what city", "what place", "what location"]):
        c = correct.lower()
        if c.startswith(("at ", "in ", "on ")):
            return f"The segment is set {c}."
        return f"The segment is set at {c}."

    # Who
    if any(w in q_lower for w in ["who ", "whose"]):
        return f"{correct} — {brief}."

    # Why
    if "why" in q_lower:
        return f"{_cap(correct)} — {brief}."

    # When
    if "when" in q_lower:
        return f"{_cap(correct)} — {brief}."

    # What want / what does
    if any(w in q_lower for w in ["what does", "what do", "what want",
                                   "what is the"]):
        return f"{_cap(correct)} — {brief}."

    # What happens
    if "what" in q_lower:
        return f"{_cap(correct)} — {brief}."

    # Fallback
    return f"{_cap(correct)} — {brief}."


def _cap(s):
    """Capitalize first letter."""
    if not s:
        return s
    return s[0].upper() + s[1:]


def _brief_desc(desc):
    """Create a brief reference to the segment description, max ~8 words."""
    if not desc:
        return "as shown in the clip"
    desc = desc.strip().rstrip(".")
    # Take first clause, keep short
    for sep in [". ", "; ", " — "]:
        idx = desc.find(sep)
        if 0 < idx < 50:
            desc = desc[:idx]
            break
    # If still too long, cut at a comma
    if len(desc) > 45:
        idx = desc.find(", ", 0, 45)
        if idx > 0:
            desc = desc[:idx]
    if len(desc) > 45:
        desc = desc[:40].rsplit(" ", 1)[0]
    return desc[0].lower() + desc[1:] if desc else "as shown in the clip"


def main():
    with open(CATALOG_PATH, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "entries" in data:
        entries = data["entries"]
    elif isinstance(data, list):
        entries = data
    else:
        print("Unexpected format")
        sys.exit(1)

    total_questions = 0
    total_explained = 0
    by_type = {"mc": 0, "vocab_check": 0, "other": 0}

    for entry in entries:
        for q in entry.get("questions", []):
            total_questions += 1
            explanation = generate_explanation(q, entry)
            q["explanation"] = explanation
            total_explained += 1
            t = q.get("type", "")
            if t in by_type:
                by_type[t] += 1
            else:
                by_type["other"] += 1

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Total questions: {total_questions}")
    print(f"Explanations added: {total_explained}")
    print(f"By type: {by_type}")

    # Verify
    with open(CATALOG_PATH, encoding="utf-8") as f:
        check = json.load(f)
    check_entries = check.get("entries", check) if isinstance(check, dict) else check
    missing = 0
    too_long = 0
    for e in check_entries:
        for q in e.get("questions", []):
            if "explanation" not in q:
                missing += 1
            else:
                words = len(q["explanation"].split())
                if words > 25:
                    too_long += 1
    print(f"Missing explanations: {missing}")
    print(f"Over 25 words: {too_long}")

    # Show samples across the catalog
    print("\n--- Sample explanations (first 6, middle 4, last 4) ---")
    all_qs = []
    for e in check_entries:
        for q in e.get("questions", []):
            all_qs.append(q)

    indices = list(range(6)) + [len(all_qs)//2 + i for i in range(4)] + [len(all_qs)-4+i for i in range(4)]
    for i in indices:
        if i < len(all_qs):
            q = all_qs[i]
            print(f"  [{q.get('type','')}] {q.get('q_en', q.get('q_zh',''))}")
            print(f"    -> {q['explanation']}")


if __name__ == "__main__":
    main()
