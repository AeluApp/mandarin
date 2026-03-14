#!/usr/bin/env python3
"""Expand graded reading passages programmatically.

Usage:
    python scripts/expand_content.py [--hsk-levels 1,2,3] [--topics food,travel] [--count 5] [--output FILE]
    python scripts/expand_content.py --batch  # generate a full batch across all levels/topics
    python scripts/expand_content.py --stats  # show current passage coverage

Generates new reading passages using templates and vocabulary from the
content_item seed data. Each passage includes:
- Title (Chinese + English)
- Main text at the target HSK level
- Pinyin transliteration
- English translation
- 2 comprehension questions with MC options

Passages are deterministic given the same seed — no LLM needed.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_DATA_DIR = Path(__file__).parent.parent / "data"
_PASSAGES_FILE = _DATA_DIR / "reading_passages.json"


# ── Topic templates ──────────────────────────────────────────────────────
# Each template is a sentence pattern with {slots} for vocabulary.
# Patterns are tagged by HSK level and topic.

TEMPLATES = {
    "daily_life": {
        1: [
            {
                "pattern": "{time}，{person}在{place}{verb}。{pronoun}很{adj}。",
                "pinyin_pattern": "{time_py}，{person_py} zài {place_py} {verb_py}。{pronoun_py} hěn {adj_py}。",
                "en_pattern": "At {time_en}, {person_en} {verb_en} at {place_en}. {pronoun_en} is very {adj_en}.",
                "slots": {
                    "time": {"field": "hanzi", "filter": "category=time", "fallback": ["早上", "下午", "晚上"]},
                    "person": {"field": "hanzi", "filter": "category=person", "fallback": ["我", "他", "她"]},
                    "place": {"field": "hanzi", "filter": "category=place", "fallback": ["家", "学校", "商店"]},
                    "verb": {"field": "hanzi", "filter": "category=verb", "fallback": ["吃饭", "看书", "喝茶"]},
                    "adj": {"field": "hanzi", "filter": "category=adj", "fallback": ["高兴", "忙", "累"]},
                },
            },
            {
                "pattern": "今天{weather}。我想去{place}{verb}。{person}说{quote}。",
                "pinyin_pattern": "Jīntiān {weather_py}。Wǒ xiǎng qù {place_py} {verb_py}。{person_py} shuō {quote_py}。",
                "en_pattern": "Today is {weather_en}. I want to go to {place_en} to {verb_en}. {person_en} says {quote_en}.",
                "slots": {
                    "weather": {"fallback": ["下雨了", "很热", "很冷", "天气很好"]},
                    "place": {"fallback": ["商店", "公园", "学校", "医院"]},
                    "verb": {"fallback": ["买东西", "散步", "学习", "看病"]},
                    "person": {"fallback": ["妈妈", "朋友", "老师"]},
                    "quote": {"fallback": ['"好的"', '"不行"', '"太好了"']},
                },
            },
        ],
        2: [
            {
                "pattern": "{person}每天{time}都会去{place}。今天{pronoun}比较{adj}，所以{action}。{place}里的人不多，{pronoun}觉得很{feeling}。",
                "pinyin_pattern": "{person_py} měi tiān {time_py} dōu huì qù {place_py}。Jīntiān {pronoun_py} bǐjiào {adj_py}，suǒyǐ {action_py}。{place_py} lǐ de rén bù duō，{pronoun_py} juéde hěn {feeling_py}。",
                "en_pattern": "{person_en} goes to {place_en} every day at {time_en}. Today {pronoun_en} is quite {adj_en}, so {action_en}. There aren't many people in {place_en}, {pronoun_en} feels very {feeling_en}.",
                "slots": {
                    "person": {"fallback": ["小王", "李老师", "我的朋友"]},
                    "time": {"fallback": ["早上", "中午", "下午"]},
                    "place": {"fallback": ["图书馆", "咖啡店", "公园"]},
                    "adj": {"fallback": ["累", "忙", "开心"]},
                    "action": {"fallback": ["去得比较晚", "没有去", "早一点去了"]},
                    "feeling": {"fallback": ["舒服", "安静", "自在"]},
                },
            },
        ],
        3: [
            {
                "pattern": "虽然{situation}，但是{person}还是决定{action}。{reason}。到了{place}以后，{pronoun}发现{discovery}。这件事让{pronoun}明白了{lesson}。",
                "pinyin_pattern": "Suīrán {situation_py}，dànshì {person_py} háishì juédìng {action_py}。{reason_py}。Dào le {place_py} yǐhòu，{pronoun_py} fāxiàn {discovery_py}。Zhè jiàn shì ràng {pronoun_py} míngbai le {lesson_py}。",
                "en_pattern": "Although {situation_en}, {person_en} still decided to {action_en}. {reason_en}. After arriving at {place_en}, {pronoun_en} discovered {discovery_en}. This made {pronoun_en} understand {lesson_en}.",
                "slots": {
                    "situation": {"fallback": ["外面下着大雨", "已经很晚了", "路上很堵"]},
                    "person": {"fallback": ["小张", "我", "她"]},
                    "action": {"fallback": ["出门", "继续工作", "去看朋友"]},
                    "reason": {"fallback": ["因为她已经答应了", "因为这件事很重要", "因为机会难得"]},
                    "place": {"fallback": ["那里", "朋友家", "公司"]},
                    "discovery": {"fallback": ["一切都很顺利", "大家都已经到了", "情况比想象的好"]},
                    "lesson": {"fallback": ["不要太担心", "行动比等待重要", "有些事值得坚持"]},
                },
            },
        ],
    },
    "food": {
        1: [
            {
                "pattern": "我喜欢吃{food}。{food}很{adj}。我{frequency}吃{food}。你喜欢吃什么？",
                "pinyin_pattern": "Wǒ xǐhuān chī {food_py}。{food_py} hěn {adj_py}。Wǒ {frequency_py} chī {food_py}。Nǐ xǐhuān chī shénme？",
                "en_pattern": "I like to eat {food_en}. {food_en} is very {adj_en}. I {frequency_en} eat {food_en}. What do you like to eat?",
                "slots": {
                    "food": {"fallback": ["米饭", "面条", "水果", "鸡蛋"]},
                    "adj": {"fallback": ["好吃", "便宜", "好"]},
                    "frequency": {"fallback": ["每天", "常常", "有时候"]},
                },
            },
        ],
        2: [
            {
                "pattern": "昨天我和{person}一起去了一家{type}餐厅。我们点了{dish1}和{dish2}。{dish1}的味道{taste1}，{dish2}{taste2}。服务员很{service_adj}。下次我还想去。",
                "pinyin_pattern": "Zuótiān wǒ hé {person_py} yìqǐ qù le yì jiā {type_py} cāntīng。Wǒmen diǎn le {dish1_py} hé {dish2_py}。{dish1_py} de wèidào {taste1_py}，{dish2_py} {taste2_py}。Fúwùyuán hěn {service_adj_py}。Xià cì wǒ hái xiǎng qù。",
                "en_pattern": "Yesterday {person_en} and I went to a {type_en} restaurant together. We ordered {dish1_en} and {dish2_en}. The {dish1_en} tasted {taste1_en}, and the {dish2_en} was {taste2_en}. The server was very {service_adj_en}. I want to go again next time.",
                "slots": {
                    "person": {"fallback": ["朋友", "同事", "家人"]},
                    "type": {"fallback": ["中国", "日本", "意大利"]},
                    "dish1": {"fallback": ["炒饭", "牛肉面", "宫保鸡丁"]},
                    "dish2": {"fallback": ["汤", "沙拉", "饺子"]},
                    "taste1": {"fallback": ["很好", "不错", "特别香"]},
                    "taste2": {"fallback": ["也很好吃", "有一点咸", "刚刚好"]},
                    "service_adj": {"fallback": ["热情", "客气", "有礼貌"]},
                },
            },
        ],
        3: [
            {
                "pattern": "中国不同地方的人吃的东西很不一样。{region1}人喜欢吃{food1}，因为{reason1}。{region2}人更喜欢{food2}，{reason2}。虽然口味不同，但是大家都觉得{conclusion}。",
                "pinyin_pattern": "Zhōngguó bùtóng dìfāng de rén chī de dōngxī hěn bù yíyàng。{region1_py} rén xǐhuān chī {food1_py}，yīnwèi {reason1_py}。{region2_py} rén gèng xǐhuān {food2_py}，{reason2_py}。Suīrán kǒuwèi bùtóng，dànshì dàjiā dōu juéde {conclusion_py}。",
                "en_pattern": "People from different parts of China eat very different things. People from {region1_en} like to eat {food1_en} because {reason1_en}. People from {region2_en} prefer {food2_en}, {reason2_en}. Although tastes differ, everyone agrees {conclusion_en}.",
                "slots": {
                    "region1": {"fallback": ["四川", "广东", "北方"]},
                    "food1": {"fallback": ["辣的菜", "海鲜", "面食"]},
                    "reason1": {"fallback": ["那里天气潮湿", "靠近海边", "小麦比较多"]},
                    "region2": {"fallback": ["上海", "湖南", "南方"]},
                    "food2": {"fallback": ["甜一点的菜", "酸辣的菜", "米饭"]},
                    "reason2": {"fallback": ["和他们的文化有关", "这是当地的传统", "因为那里种稻子"]},
                    "conclusion": {"fallback": ["吃饭是最开心的事", "好吃最重要", "家乡的味道最好"]},
                },
            },
        ],
    },
    "travel": {
        1: [
            {
                "pattern": "我想去{place}。{place}很{adj}。从这里到{place}要{duration}。我想{time}去。",
                "pinyin_pattern": "Wǒ xiǎng qù {place_py}。{place_py} hěn {adj_py}。Cóng zhèlǐ dào {place_py} yào {duration_py}。Wǒ xiǎng {time_py} qù。",
                "en_pattern": "I want to go to {place_en}. {place_en} is very {adj_en}. It takes {duration_en} to get from here to {place_en}. I want to go {time_en}.",
                "slots": {
                    "place": {"fallback": ["北京", "上海", "公园"]},
                    "adj": {"fallback": ["大", "好看", "有名"]},
                    "duration": {"fallback": ["两个小时", "三天", "一个小时"]},
                    "time": {"fallback": ["明天", "下个月", "周末"]},
                },
            },
        ],
        2: [
            {
                "pattern": "上个月我去了{destination}旅游。我坐{transport}去的，路上用了{duration}。到了以后，我先去了{sight1}，然后去了{sight2}。{destination}的{feature}让我印象很深。我拍了很多{photos}。",
                "pinyin_pattern": "Shàng gè yuè wǒ qù le {destination_py} lǚyóu。Wǒ zuò {transport_py} qù de，lùshàng yòng le {duration_py}。Dào le yǐhòu，wǒ xiān qù le {sight1_py}，ránhòu qù le {sight2_py}。{destination_py} de {feature_py} ràng wǒ yìnxiàng hěn shēn。Wǒ pāi le hěn duō {photos_py}。",
                "en_pattern": "Last month I traveled to {destination_en}. I went by {transport_en}, it took {duration_en} on the way. After arriving, I first went to {sight1_en}, then went to {sight2_en}. {destination_en}'s {feature_en} left a deep impression on me. I took many {photos_en}.",
                "slots": {
                    "destination": {"fallback": ["西安", "成都", "杭州"]},
                    "transport": {"fallback": ["高铁", "飞机", "火车"]},
                    "duration": {"fallback": ["四个小时", "两个小时", "六个小时"]},
                    "sight1": {"fallback": ["博物馆", "古城", "老街"]},
                    "sight2": {"fallback": ["公园", "寺庙", "夜市"]},
                    "feature": {"fallback": ["历史", "美食", "风景"]},
                    "photos": {"fallback": ["照片", "风景照", "美食照片"]},
                },
            },
        ],
    },
    "work": {
        2: [
            {
                "pattern": "我在一家{company_type}工作。每天{time}上班，{time2}下班。我的工作是{job_desc}。同事们都很{colleague_adj}。虽然有时候很{difficulty}，但是我{feeling}。",
                "pinyin_pattern": "Wǒ zài yì jiā {company_type_py} gōngzuò。Měi tiān {time_py} shàngbān，{time2_py} xiàbān。Wǒ de gōngzuò shì {job_desc_py}。Tóngshìmen dōu hěn {colleague_adj_py}。Suīrán yǒushíhòu hěn {difficulty_py}，dànshì wǒ {feeling_py}。",
                "en_pattern": "I work at a {company_type_en}. Every day I start work at {time_en} and finish at {time2_en}. My job is {job_desc_en}. My colleagues are all very {colleague_adj_en}. Although sometimes it's very {difficulty_en}, I {feeling_en}.",
                "slots": {
                    "company_type": {"fallback": ["小公司", "大公司", "学校"]},
                    "time": {"fallback": ["早上八点", "九点", "八点半"]},
                    "time2": {"fallback": ["下午五点", "六点", "五点半"]},
                    "job_desc": {"fallback": ["写报告", "教学生", "做设计"]},
                    "colleague_adj": {"fallback": ["友好", "认真", "有趣"]},
                    "difficulty": {"fallback": ["忙", "累", "紧张"]},
                    "feeling": {"fallback": ["很喜欢这份工作", "觉得还不错", "学到了很多"]},
                },
            },
        ],
        3: [
            {
                "pattern": "最近公司来了一个新{role}。{pronoun}以前在{prev_place}工作过，经验很{exp_adj}。第一天上班的时候，{pronoun}看起来有点{emotion}，{action}。过了一个星期，{pronoun}已经{adaptation}了。大家都觉得{evaluation}。",
                "pinyin_pattern": "Zuìjìn gōngsī lái le yí gè xīn {role_py}。{pronoun_py} yǐqián zài {prev_place_py} gōngzuò guò，jīngyàn hěn {exp_adj_py}。Dì yī tiān shàngbān de shíhòu，{pronoun_py} kàn qǐlái yǒudiǎn {emotion_py}，{action_py}。Guò le yí gè xīngqī，{pronoun_py} yǐjīng {adaptation_py} le。Dàjiā dōu juéde {evaluation_py}。",
                "en_pattern": "Recently a new {role_en} joined the company. {pronoun_en} used to work at {prev_place_en}, and has very {exp_adj_en} experience. On the first day, {pronoun_en} looked a bit {emotion_en} and {action_en}. After a week, {pronoun_en} had already {adaptation_en}. Everyone thinks {evaluation_en}.",
                "slots": {
                    "role": {"fallback": ["同事", "经理", "设计师"]},
                    "pronoun": {"fallback": ["他", "她"]},
                    "prev_place": {"fallback": ["北京", "一家大公司", "国外"]},
                    "exp_adj": {"fallback": ["丰富", "多", "专业"]},
                    "emotion": {"fallback": ["紧张", "害羞", "不太自在"]},
                    "action": {"fallback": ["不太说话", "问了很多问题", "很安静"]},
                    "adaptation": {"fallback": ["完全适应", "和大家很熟了", "开始参加各种活动"]},
                    "evaluation": {"fallback": ["这个人很不错", "我们团队更强了", "新来的人很努力"]},
                },
            },
        ],
    },
    "nature": {
        1: [
            {
                "pattern": "今天天气{weather}。我看到了{sight}。{sight}很{adj}。我很{feeling}。",
                "pinyin_pattern": "Jīntiān tiānqì {weather_py}。Wǒ kàn dào le {sight_py}。{sight_py} hěn {adj_py}。Wǒ hěn {feeling_py}。",
                "en_pattern": "Today the weather is {weather_en}. I saw {sight_en}. The {sight_en} is very {adj_en}. I am very {feeling_en}.",
                "slots": {
                    "weather": {"fallback": ["很好", "不太好", "晴天"]},
                    "sight": {"fallback": ["花", "鸟", "山"]},
                    "adj": {"fallback": ["好看", "大", "漂亮"]},
                    "feeling": {"fallback": ["高兴", "开心", "喜欢"]},
                },
            },
        ],
    },
}

# Question templates for comprehension questions
QUESTION_TEMPLATES = {
    "who": {
        "q_zh": "这个故事里有谁？",
        "q_en": "Who is in this story?",
    },
    "what": {
        "q_zh": "发生了什么事？",
        "q_en": "What happened?",
    },
    "where": {
        "q_zh": "这件事发生在哪里？",
        "q_en": "Where did this take place?",
    },
    "feeling": {
        "q_zh": "主人公有什么感受？",
        "q_en": "How does the main character feel?",
    },
    "reason": {
        "q_zh": "为什么会这样？",
        "q_en": "Why is this the case?",
    },
}


def _generate_passage_id(topic: str, hsk_level: int, variant: int) -> str:
    """Generate a deterministic passage ID."""
    return f"gen_{topic}_hsk{hsk_level}_{variant:03d}"


def _pick_slot_values(template: dict, seed: int) -> dict:
    """Pick slot values from fallback lists using a deterministic seed."""
    import random as _random
    rng = _random.Random(seed)
    slots = template.get("slots", {})
    values = {}
    for slot_name, slot_cfg in slots.items():
        fallback = slot_cfg.get("fallback", [""])
        values[slot_name] = rng.choice(fallback)
    return values


def _fill_template(pattern: str, values: dict, suffix: str = "") -> str:
    """Fill a template pattern with values.

    If suffix is provided (e.g. "_py"), tries {key_py} first, falls back to {key}.
    This allows Chinese values to be reused in pinyin/English templates where no
    separate translation is provided.
    """
    result = pattern
    if suffix:
        # Replace suffixed slots with the base value (since we use Chinese in all templates)
        for key, val in values.items():
            result = result.replace("{" + key + suffix + "}", val)
    # Also replace base slots
    for key, val in values.items():
        result = result.replace("{" + key + "}", val)
    # Clean up any remaining unfilled slots
    result = re.sub(r"\{[^}]+\}", "", result)
    return result.strip()


def _generate_questions(text_zh: str, values: dict, topic: str,
                        hsk_level: int, seed: int) -> list:
    """Generate 2 comprehension questions for a passage."""
    import random as _random
    rng = _random.Random(seed + 1000)

    questions = []

    # Question 1: factual (what/where/who)
    q_types = ["what", "where", "who"]
    q_type = rng.choice(q_types)
    qt = QUESTION_TEMPLATES[q_type]

    # Generate correct answer from the passage content
    # Extract a key phrase as the correct answer
    sentences = re.split(r"[。！？]", text_zh)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return []

    correct_sentence = rng.choice(sentences) if len(sentences) > 1 else sentences[0]
    # Truncate for answer option
    correct_answer = correct_sentence[:15] if len(correct_sentence) > 15 else correct_sentence

    # Generate distractors
    distractors = []
    distractor_pool = [
        "去了商店", "在家休息", "和朋友聊天", "看了电影",
        "吃了晚饭", "去了公园", "学了中文", "买了东西",
        "坐了公交车", "打了电话", "写了作业", "听了音乐",
    ]
    rng.shuffle(distractor_pool)
    for d in distractor_pool:
        if d != correct_answer and d not in distractors:
            distractors.append(d)
        if len(distractors) >= 3:
            break

    options = [{"text": correct_answer, "correct": True}]
    for d in distractors:
        options.append({"text": d, "correct": False})
    rng.shuffle(options)

    questions.append({
        "type": "mc",
        "q_zh": qt["q_zh"],
        "q_en": qt["q_en"],
        "options": options,
        "difficulty": 0.3 + hsk_level * 0.1,
    })

    # Question 2: feeling/reason
    q_type2 = rng.choice(["feeling", "reason"])
    qt2 = QUESTION_TEMPLATES[q_type2]

    feeling_options_pool = [
        "很高兴", "很累", "有点紧张", "很舒服",
        "不太开心", "觉得有意思", "很满意", "有点担心",
    ]
    reason_options_pool = [
        "因为天气好", "因为很忙", "因为喜欢", "因为需要",
        "因为朋友请客", "因为时间不够", "因为便宜", "因为好奇",
    ]

    pool = feeling_options_pool if q_type2 == "feeling" else reason_options_pool
    rng.shuffle(pool)
    correct2 = pool[0]  # First option after shuffle is "correct"
    options2 = [{"text": correct2, "correct": True}]
    for d in pool[1:4]:
        options2.append({"text": d, "correct": False})
    rng.shuffle(options2)

    questions.append({
        "type": "mc",
        "q_zh": qt2["q_zh"],
        "q_en": qt2["q_en"],
        "options": options2,
        "difficulty": 0.4 + hsk_level * 0.1,
    })

    return questions


def generate_passages(hsk_levels: list[int] = None,
                      topics: list[str] = None,
                      count_per_combo: int = 3) -> list[dict]:
    """Generate reading passages from templates.

    Args:
        hsk_levels: Which HSK levels to generate for (default: 1-3)
        topics: Which topics to generate (default: all)
        count_per_combo: How many passages per level+topic combination

    Returns:
        List of passage dicts compatible with reading_passages.json
    """
    if hsk_levels is None:
        hsk_levels = [1, 2, 3]
    if topics is None:
        topics = list(TEMPLATES.keys())

    passages = []
    for topic in topics:
        topic_templates = TEMPLATES.get(topic, {})
        for level in hsk_levels:
            templates_at_level = topic_templates.get(level, [])
            if not templates_at_level:
                continue

            for variant in range(count_per_combo):
                # Deterministic seed from topic + level + variant
                seed_str = f"{topic}:{level}:{variant}"
                seed = int(hashlib.md5(seed_str.encode(), usedforsecurity=False).hexdigest()[:8], 16)

                template = templates_at_level[variant % len(templates_at_level)]
                values = _pick_slot_values(template, seed)

                # Fill templates
                text_zh = _fill_template(template["pattern"], values)
                text_pinyin = _fill_template(template.get("pinyin_pattern", ""), values, "_py")
                text_en = _fill_template(template.get("en_pattern", ""), values, "_en")

                # Generate ID and title
                passage_id = _generate_passage_id(topic, level, variant)
                # Use first sentence as title
                first_sentence = text_zh.split("。")[0] if "。" in text_zh else text_zh[:20]
                title_zh = first_sentence[:20]
                title = f"{topic.replace('_', ' ').title()} (HSK {level})"

                # Generate questions
                questions = _generate_questions(text_zh, values, topic, level, seed)

                passages.append({
                    "id": passage_id,
                    "title": title,
                    "title_zh": title_zh,
                    "hsk_level": level,
                    "text_zh": text_zh,
                    "text_pinyin": text_pinyin,
                    "text_en": text_en,
                    "topic": topic,
                    "generated": True,
                    "questions": questions,
                })

    return passages


def show_stats():
    """Show current passage coverage statistics."""
    if not _PASSAGES_FILE.exists():
        print("No reading_passages.json found.")
        return

    with open(_PASSAGES_FILE) as f:
        data = json.load(f)
    passages = data.get("passages", [])

    print(f"\nTotal passages: {len(passages)}")
    print()

    # By HSK level
    levels = {}
    for p in passages:
        lvl = p.get("hsk_level", 0)
        levels[lvl] = levels.get(lvl, 0) + 1
    print("By HSK level:")
    for lvl in sorted(levels):
        print(f"  HSK {lvl}: {levels[lvl]} passages")

    # By topic
    topics = {}
    for p in passages:
        t = p.get("topic", "hand-written")
        topics[t] = topics.get(t, 0) + 1
    print("\nBy topic:")
    for t in sorted(topics):
        print(f"  {t}: {topics[t]} passages")

    # Generated vs hand-written
    generated = sum(1 for p in passages if p.get("generated"))
    print(f"\nHand-written: {len(passages) - generated}")
    print(f"Generated: {generated}")


def merge_passages(new_passages: list[dict], output_path: Path = None) -> int:
    """Merge new passages into the existing reading_passages.json.

    Returns the number of new passages added (skips duplicates by ID).
    """
    if output_path is None:
        output_path = _PASSAGES_FILE

    existing = []
    if output_path.exists():
        with open(output_path) as f:
            data = json.load(f)
        existing = data.get("passages", [])

    existing_ids = {p.get("id") for p in existing}
    added = 0
    for p in new_passages:
        if p.get("id") not in existing_ids:
            existing.append(p)
            existing_ids.add(p["id"])
            added += 1

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"passages": existing}, f, ensure_ascii=False, indent=2)

    return added


def main():
    parser = argparse.ArgumentParser(
        description="Generate graded reading passages from templates.",
    )
    parser.add_argument("--hsk-levels", default="1,2,3",
                        help="Comma-separated HSK levels (default: 1,2,3)")
    parser.add_argument("--topics", default=None,
                        help="Comma-separated topics (default: all)")
    parser.add_argument("--count", type=int, default=3,
                        help="Passages per level+topic combination (default: 3)")
    parser.add_argument("--output", "-o",
                        help="Output file (default: merge into reading_passages.json)")
    parser.add_argument("--batch", action="store_true",
                        help="Generate a full batch across all levels and topics")
    parser.add_argument("--stats", action="store_true",
                        help="Show current passage coverage statistics")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview passages without writing")

    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    levels = [int(x) for x in args.hsk_levels.split(",")]
    topics = args.topics.split(",") if args.topics else None

    if args.batch:
        levels = [1, 2, 3]
        topics = None
        count = 5
    else:
        count = args.count

    passages = generate_passages(hsk_levels=levels, topics=topics,
                                 count_per_combo=count)

    print(f"Generated {len(passages)} passages", file=sys.stderr)

    if args.dry_run:
        for p in passages[:3]:
            print(f"\n--- {p['id']} (HSK {p['hsk_level']}) ---")
            print(f"  {p['text_zh']}")
            print(f"  {p['text_pinyin']}")
            print(f"  {p['text_en']}")
            print(f"  Questions: {len(p.get('questions', []))}")
        if len(passages) > 3:
            print(f"\n... and {len(passages) - 3} more")
        return

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"passages": passages}, f, ensure_ascii=False, indent=2)
        print(f"Written {len(passages)} passages to {output_path}", file=sys.stderr)
    else:
        added = merge_passages(passages)
        print(f"Added {added} new passages to {_PASSAGES_FILE}", file=sys.stderr)
        print(f"(Skipped {len(passages) - added} duplicates)", file=sys.stderr)


if __name__ == "__main__":
    main()
