#!/usr/bin/env python3
"""Convert reading passage questions from open-answer to proper multiple choice.

Each question gets 4 options: 1 correct + 3 distractors.
Distractors are drawn from same-type answers in the corpus, falling back to
a curated pool per answer category.
"""

import json
import random
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ── Distractor pools by category ──────────────────────────────────────────────

PEOPLE_ROLES = [
    ("医生", "yīshēng", "doctor"),
    ("老师", "lǎoshī", "teacher"),
    ("学生", "xuéshēng", "student"),
    ("工程师", "gōngchéngshī", "engineer"),
    ("司机", "sījī", "driver"),
    ("服务员", "fúwùyuán", "waiter"),
    ("护士", "hùshi", "nurse"),
    ("经理", "jīnglǐ", "manager"),
    ("厨师", "chúshī", "chef"),
    ("记者", "jìzhě", "reporter"),
    ("律师", "lǜshī", "lawyer"),
    ("警察", "jǐngchá", "police officer"),
    ("作家", "zuòjiā", "writer"),
    ("歌手", "gēshǒu", "singer"),
    ("运动员", "yùndòngyuán", "athlete"),
]

LOCATIONS = [
    ("公园", "gōngyuán", "park"),
    ("学校", "xuéxiào", "school"),
    ("医院", "yīyuàn", "hospital"),
    ("超市", "chāoshì", "supermarket"),
    ("饭店", "fàndiàn", "restaurant"),
    ("图书馆", "túshūguǎn", "library"),
    ("电影院", "diànyǐngyuàn", "cinema"),
    ("银行", "yínháng", "bank"),
    ("机场", "jīchǎng", "airport"),
    ("火车站", "huǒchēzhàn", "train station"),
    ("商店", "shāngdiàn", "shop"),
    ("咖啡店", "kāfēidiàn", "café"),
    ("办公室", "bàngōngshì", "office"),
    ("博物馆", "bówùguǎn", "museum"),
    ("书店", "shūdiàn", "bookstore"),
    ("市场", "shìchǎng", "market"),
    ("北京", "Běijīng", "Beijing"),
    ("上海", "Shànghǎi", "Shanghai"),
    ("成都", "Chéngdū", "Chengdu"),
    ("广州", "Guǎngzhōu", "Guangzhou"),
]

ACTIVITIES = [
    ("跑步", "pǎobù", "running"),
    ("看书", "kàn shū", "reading"),
    ("写字", "xiě zì", "writing"),
    ("游泳", "yóuyǒng", "swimming"),
    ("唱歌", "chàng gē", "singing"),
    ("跳舞", "tiào wǔ", "dancing"),
    ("看电视", "kàn diànshì", "watching TV"),
    ("做饭", "zuò fàn", "cooking"),
    ("打篮球", "dǎ lánqiú", "playing basketball"),
    ("踢足球", "tī zúqiú", "playing football"),
    ("散步", "sànbù", "taking a walk"),
    ("画画", "huà huà", "painting"),
    ("购物", "gòuwù", "shopping"),
    ("旅行", "lǚxíng", "traveling"),
    ("喝茶", "hē chá", "drinking tea"),
    ("喝咖啡", "hē kāfēi", "drinking coffee"),
    ("听音乐", "tīng yīnyuè", "listening to music"),
    ("学中文", "xué Zhōngwén", "studying Chinese"),
    ("上网", "shàng wǎng", "going online"),
    ("骑自行车", "qí zìxíngchē", "cycling"),
]

TRANSPORT = [
    ("坐火车", "zuò huǒchē", "by train"),
    ("坐飞机", "zuò fēijī", "by plane"),
    ("坐公交车", "zuò gōngjiāochē", "by bus"),
    ("坐地铁", "zuò dìtiě", "by subway"),
    ("开车", "kāi chē", "by car"),
    ("骑自行车", "qí zìxíngchē", "by bicycle"),
    ("走路", "zǒu lù", "on foot"),
    ("打车", "dǎ chē", "by taxi"),
]

NUMBERS_PEOPLE = [
    ("三个人", "sān gè rén", "three people"),
    ("四个人", "sì gè rén", "four people"),
    ("五个人", "wǔ gè rén", "five people"),
    ("六个人", "liù gè rén", "six people"),
    ("七个人", "qī gè rén", "seven people"),
    ("两个人", "liǎng gè rén", "two people"),
]

NUMBERS_DISHES = [
    ("两个菜", "liǎng gè cài", "two dishes"),
    ("三个菜", "sān gè cài", "three dishes"),
    ("四个菜", "sì gè cài", "four dishes"),
    ("五个菜", "wǔ gè cài", "five dishes"),
]

MONEY = [
    ("五十块钱", "wǔshí kuài qián", "fifty yuan"),
    ("六十块钱", "liùshí kuài qián", "sixty yuan"),
    ("七十块钱", "qīshí kuài qián", "seventy yuan"),
    ("八十块钱", "bāshí kuài qián", "eighty yuan"),
    ("九十块钱", "jiǔshí kuài qián", "ninety yuan"),
    ("一百块钱", "yìbǎi kuài qián", "one hundred yuan"),
    ("一百二十块", "yìbǎi èrshí kuài", "one hundred twenty yuan"),
]

AGES = [
    ("十八岁", "shíbā suì", "eighteen years old"),
    ("十九岁", "shíjiǔ suì", "nineteen years old"),
    ("二十岁", "èrshí suì", "twenty years old"),
    ("二十一岁", "èrshíyī suì", "twenty-one years old"),
    ("二十二岁", "èrshíèr suì", "twenty-two years old"),
    ("二十三岁", "èrshísān suì", "twenty-three years old"),
    ("二十五岁", "èrshíwǔ suì", "twenty-five years old"),
    ("三十岁", "sānshí suì", "thirty years old"),
]

WEATHER = [
    ("很好", "hěn hǎo", "very good"),
    ("很热", "hěn rè", "very hot"),
    ("很冷", "hěn lěng", "very cold"),
    ("下雨了", "xià yǔ le", "it's raining"),
    ("下雪了", "xià xuě le", "it's snowing"),
    ("阴天", "yīn tiān", "cloudy"),
    ("很闷", "hěn mēn", "stuffy"),
]

SUBJECTS = [
    ("中文", "Zhōngwén", "Chinese"),
    ("数学", "shùxué", "math"),
    ("英语", "Yīngyǔ", "English"),
    ("历史", "lìshǐ", "history"),
    ("音乐", "yīnyuè", "music"),
    ("体育", "tǐyù", "P.E."),
    ("科学", "kēxué", "science"),
]

FEELINGS = [
    ("很高兴", "hěn gāoxìng", "very happy"),
    ("有意思", "yǒu yìsi", "interesting"),
    ("很难", "hěn nán", "very hard"),
    ("很累", "hěn lèi", "very tired"),
    ("很开心", "hěn kāixīn", "very happy"),
    ("不太好", "bú tài hǎo", "not great"),
    ("很紧张", "hěn jǐnzhāng", "very nervous"),
    ("很无聊", "hěn wúliáo", "very boring"),
]

TIME_EXPRESSIONS = [
    ("早上", "zǎoshang", "in the morning"),
    ("中午", "zhōngwǔ", "at noon"),
    ("下午", "xiàwǔ", "in the afternoon"),
    ("晚上", "wǎnshang", "in the evening"),
    ("星期一", "xīngqīyī", "Monday"),
    ("星期六", "xīngqīliù", "Saturday"),
    ("星期天", "xīngqītiān", "Sunday"),
]


def classify_answer(answer_zh):
    """Classify an answer to pick the right distractor pool."""
    a = answer_zh.strip()

    # Numbers / ages
    if re.search(r"[零一二三四五六七八九十百千万\d]+岁", a):
        return "age"
    if re.search(r"[零一二三四五六七八九十百千万\d]+块", a):
        return "money"
    if re.search(r"[零一二三四五六七八九十百千万\d]+个人", a):
        return "count_people"
    if re.search(r"[零一二三四五六七八九十百千万\d]+个菜", a):
        return "count_dishes"

    # Roles / people
    role_chars = {"医生", "老师", "学生", "工程师", "司机", "服务员", "护士", "经理",
                  "厨师", "记者", "律师", "警察", "作家", "歌手", "运动员"}
    for role in role_chars:
        if role in a:
            return "role"

    # Locations
    loc_chars = {"公园", "学校", "医院", "超市", "饭店", "图书馆", "电影院",
                 "银行", "机场", "火车站", "商店", "咖啡店", "办公室", "博物馆",
                 "书店", "市场", "北京", "上海", "成都", "广州"}
    for loc in loc_chars:
        if loc in a:
            return "location"

    # Transport
    transport_chars = {"火车", "飞机", "公交", "地铁", "开车", "自行车", "走路", "打车", "坐"}
    for t in transport_chars:
        if t in a:
            return "transport"

    # Activities
    act_chars = {"跑步", "看书", "写字", "游泳", "唱歌", "跳舞", "看电视", "做饭",
                 "篮球", "足球", "散步", "画画", "购物", "旅行", "喝茶", "喝咖啡",
                 "听音乐", "学中文", "上网", "骑"}
    for act in act_chars:
        if act in a:
            return "activity"

    # Weather
    if any(w in a for w in ["热", "冷", "雨", "雪", "阴", "闷", "天气"]):
        return "weather"

    # Subjects
    if any(s in a for s in ["中文", "数学", "英语", "历史", "音乐", "体育", "科学"]):
        return "subject"

    # Feelings / evaluations
    if any(f in a for f in ["高兴", "有意思", "难", "累", "开心", "紧张", "无聊", "好"]):
        return "feeling"

    # Time
    if any(t in a for t in ["早上", "中午", "下午", "晚上", "星期"]):
        return "time"

    return "generic"


POOL_MAP = {
    "age": AGES,
    "money": MONEY,
    "count_people": NUMBERS_PEOPLE,
    "count_dishes": NUMBERS_DISHES,
    "role": PEOPLE_ROLES,
    "location": LOCATIONS,
    "transport": TRANSPORT,
    "activity": ACTIVITIES,
    "weather": WEATHER,
    "subject": SUBJECTS,
    "feeling": FEELINGS,
    "time": TIME_EXPRESSIONS,
}


def generate_distractors(answer_zh, category, all_answers_in_passage):
    """Generate 3 plausible distractors for a given answer."""
    pool = POOL_MAP.get(category)

    if pool:
        # Filter out the correct answer from pool
        candidates = [item for item in pool if item[0] != answer_zh]
        random.shuffle(candidates)
        return candidates[:3]

    # Generic fallback: use other answers from same passage + generic pool
    other_answers = [a for a in all_answers_in_passage if a != answer_zh]

    # Build generic distractors from passage context
    generic_pool = FEELINGS + ACTIVITIES[:5] + LOCATIONS[:5]
    candidates = []

    for ans in other_answers:
        # Try to find this answer in any pool
        for pool_list in POOL_MAP.values():
            for item in pool_list:
                if item[0] == ans:
                    candidates.append(item)
                    break

    # Fill from generic if needed
    for item in generic_pool:
        if item[0] != answer_zh and item not in candidates:
            candidates.append(item)

    random.shuffle(candidates)
    return candidates[:3]


def make_option(text_zh, pinyin, text_en, correct=False):
    """Create a single MC option."""
    return {
        "text": text_zh,
        "pinyin": pinyin,
        "text_en": text_en,
        "correct": correct,
    }


def find_in_pools(answer_zh):
    """Try to find the answer in any pool to get pinyin/en."""
    for pool_list in POOL_MAP.values():
        for item in pool_list:
            if item[0] == answer_zh:
                return item
    return None


# ── Pinyin approximation for answers not in pools ────────────────────────────
# For complex answers, we store a manual mapping
ANSWER_PINYIN_MAP = {
    "有意思但是比英文难": ("yǒu yìsi dànshì bǐ Yīngwén nán", "interesting but harder than English"),
    "颜色跟照片不一样": ("yánsè gēn zhàopiàn bù yíyàng", "the color didn't match the photos"),
    "换一件新的": ("huàn yí jiàn xīn de", "exchange for a new one"),
    "去公园散步": ("qù gōngyuán sànbù", "go for a walk in the park"),
    "写字": ("xiě zì", "writing"),
    "很好": ("hěn hǎo", "very good"),
}


def get_answer_info(answer_zh):
    """Get pinyin and English for an answer."""
    found = find_in_pools(answer_zh)
    if found:
        return found[1], found[2]

    if answer_zh in ANSWER_PINYIN_MAP:
        return ANSWER_PINYIN_MAP[answer_zh]

    # Return empty — frontend will handle display appropriately
    return "", answer_zh


def convert_question(q, all_answers_in_passage):
    """Convert a single question to MC format."""
    answer_zh = q["answer"]
    category = classify_answer(answer_zh)
    distractors = generate_distractors(answer_zh, category, all_answers_in_passage)

    # Build correct option
    ans_pinyin, ans_en = get_answer_info(answer_zh)
    options = [make_option(answer_zh, ans_pinyin, ans_en, correct=True)]

    # Build distractor options
    for d in distractors:
        options.append(make_option(d[0], d[1], d[2], correct=False))

    # Pad to 4 if needed
    while len(options) < 4:
        fallback = random.choice(FEELINGS + ACTIVITIES[:5])
        if fallback[0] != answer_zh and all(o["text"] != fallback[0] for o in options):
            options.append(make_option(fallback[0], fallback[1], fallback[2], correct=False))

    # Shuffle options
    random.shuffle(options)

    # Return new question format
    return {
        "type": "mc",
        "q_zh": q.get("q_zh", ""),
        "q_en": q.get("q_en", ""),
        "options": options,
        "difficulty": q.get("difficulty", 0.3),
    }


def main():
    random.seed(42)  # Reproducible output

    input_path = DATA_DIR / "reading_passages.json"
    with open(input_path) as f:
        data = json.load(f)

    total_converted = 0
    for passage in data["passages"]:
        questions = passage.get("questions", [])
        if not questions:
            continue

        all_answers = [q["answer"] for q in questions]

        new_questions = []
        for q in questions:
            new_q = convert_question(q, all_answers)
            new_questions.append(new_q)
            total_converted += 1

        passage["questions"] = new_questions

    # Write back
    with open(input_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Converted {total_converted} questions to MC format across {len(data['passages'])} passages.")


if __name__ == "__main__":
    main()
