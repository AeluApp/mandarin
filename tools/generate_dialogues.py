#!/usr/bin/env python3
"""Generate graded dialogue scenarios for Mandarin learning.

Template-based scenario generation across genres and HSK levels.
Uses deterministic slot-filling — zero LLM tokens.

Usage:
    python tools/generate_dialogues.py                    # Generate 200+ dialogues
    python tools/generate_dialogues.py --hsk 1-3          # HSK 1-3 only
    python tools/generate_dialogues.py --genre restaurant  # One genre
    python tools/generate_dialogues.py --count 50          # 50 total
    python tools/generate_dialogues.py --dry-run           # Preview only
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT / "data" / "scenarios"
SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)


# ── Genre templates ─────────────────────────────────────────────

# Each template defines: title, title_zh, register, setup, setup_zh,
# turns (npc/player alternating), cultural_note, and HSK range.
# Player options have 1 correct + 2 off-topic distractors.

GENRES = {
    "restaurant": {
        "titles": [
            ("Ordering takeout", "点外卖"),
            ("Asking for the bill", "买单"),
            ("Special dietary request", "特殊饮食要求"),
            ("Complaining about food", "投诉食物"),
            ("Making a reservation", "预订餐厅"),
        ],
        "hsk_range": (1, 6),
    },
    "shopping": {
        "titles": [
            ("Bargaining at a market", "在市场讨价还价"),
            ("Returning a purchase", "退货"),
            ("Asking about sizes", "询问尺码"),
            ("Comparing products", "比较商品"),
            ("Online shopping help", "网购帮助"),
        ],
        "hsk_range": (1, 6),
    },
    "doctor": {
        "titles": [
            ("Describing symptoms", "描述症状"),
            ("Getting a prescription", "拿处方"),
            ("Scheduling a checkup", "预约体检"),
            ("At the pharmacy", "在药店"),
        ],
        "hsk_range": (2, 6),
    },
    "travel": {
        "titles": [
            ("Booking a hotel", "订酒店"),
            ("At the train station", "在火车站"),
            ("Asking for directions", "问路"),
            ("At the airport", "在机场"),
            ("Renting a car", "租车"),
        ],
        "hsk_range": (1, 6),
    },
    "school": {
        "titles": [
            ("Talking to a teacher", "和老师谈话"),
            ("Study group planning", "学习小组计划"),
            ("Library help", "图书馆帮助"),
            ("Exam preparation", "考试准备"),
        ],
        "hsk_range": (1, 5),
    },
    "business": {
        "titles": [
            ("Job interview", "面试"),
            ("Team meeting", "团队会议"),
            ("Client presentation", "客户演示"),
            ("Salary negotiation", "薪资谈判"),
        ],
        "hsk_range": (3, 9),
    },
    "social": {
        "titles": [
            ("Meeting a friend's friend", "认识朋友的朋友"),
            ("Birthday party invitation", "生日聚会邀请"),
            ("Small talk at a party", "聚会闲聊"),
            ("Apologizing for being late", "为迟到道歉"),
            ("Weekend plans", "周末计划"),
        ],
        "hsk_range": (1, 5),
    },
    "phone": {
        "titles": [
            ("Making an appointment", "预约"),
            ("Leaving a voicemail", "留言"),
            ("Customer service call", "客服电话"),
            ("Calling a friend", "给朋友打电话"),
        ],
        "hsk_range": (2, 6),
    },
    "bank": {
        "titles": [
            ("Opening an account", "开户"),
            ("Transferring money", "转账"),
            ("Reporting a lost card", "挂失银行卡"),
            ("Currency exchange", "兑换外币"),
        ],
        "hsk_range": (2, 6),
    },
    "emergency": {
        "titles": [
            ("Calling for help", "求助"),
            ("Reporting a problem", "报告问题"),
            ("Lost passport", "护照丢失"),
            ("Car breakdown", "汽车故障"),
        ],
        "hsk_range": (2, 6),
    },
}

# Dialogue turn templates by HSK level
# Each has NPC line + player correct response + 2 off-topic distractors
TURN_BANKS = {
    1: {
        "greetings": [
            {"npc": ("你好！", "nǐ hǎo!", "Hello!"),
             "player": ("你好！", "nǐ hǎo!", "Hello!"),
             "prompt": "Greet them back.",
             "distractors": [
                 ("我不知道。", "wǒ bù zhīdào.", "I don't know."),
                 ("再见！", "zàijiàn!", "Goodbye!"),
             ]},
            {"npc": ("你好，请问你叫什么名字？", "nǐ hǎo, qǐngwèn nǐ jiào shénme míngzi?", "Hello, what's your name?"),
             "player": ("我叫小明。", "wǒ jiào xiǎo míng.", "My name is Xiao Ming."),
             "prompt": "Tell them your name.",
             "distractors": [
                 ("我想买一个。", "wǒ xiǎng mǎi yī gè.", "I want to buy one."),
                 ("今天天气很好。", "jīntiān tiānqì hěn hǎo.", "The weather is nice today."),
             ]},
        ],
        "numbers": [
            {"npc": ("多少钱？", "duōshao qián?", "How much?"),
             "player": ("二十块钱。", "èrshí kuài qián.", "Twenty yuan."),
             "prompt": "Tell them the price.",
             "distractors": [
                 ("我是学生。", "wǒ shì xuéshēng.", "I'm a student."),
                 ("在右边。", "zài yòubiān.", "It's on the right."),
             ]},
        ],
        "thanks": [
            {"npc": ("好的，给你。", "hǎo de, gěi nǐ.", "OK, here you go."),
             "player": ("谢谢！", "xièxie!", "Thank you!"),
             "prompt": "Thank them.",
             "distractors": [
                 ("对不起。", "duìbuqǐ.", "I'm sorry."),
                 ("我不要。", "wǒ bú yào.", "I don't want it."),
             ]},
        ],
        "location": [
            {"npc": ("请问，地铁站在哪儿？", "qǐngwèn, dìtiě zhàn zài nǎr?", "Excuse me, where's the subway station?"),
             "player": ("一直走，在左边。", "yìzhí zǒu, zài zuǒbiān.", "Go straight, it's on the left."),
             "prompt": "Give them directions.",
             "distractors": [
                 ("我想喝茶。", "wǒ xiǎng hē chá.", "I want to drink tea."),
                 ("他是我朋友。", "tā shì wǒ péngyou.", "He's my friend."),
             ]},
        ],
    },
    2: {
        "plans": [
            {"npc": ("你周末有什么计划？", "nǐ zhōumò yǒu shénme jìhuà?", "What are your plans for the weekend?"),
             "player": ("我想去公园散步。", "wǒ xiǎng qù gōngyuán sànbù.", "I want to go for a walk in the park."),
             "prompt": "Tell them your weekend plans.",
             "distractors": [
                 ("这个多少钱？", "zhège duōshao qián?", "How much is this?"),
                 ("我叫小王。", "wǒ jiào xiǎo wáng.", "My name is Xiao Wang."),
             ]},
        ],
        "opinions": [
            {"npc": ("你觉得这个怎么样？", "nǐ juéde zhège zěnmeyàng?", "What do you think of this?"),
             "player": ("我觉得很好。", "wǒ juéde hěn hǎo.", "I think it's great."),
             "prompt": "Give your opinion.",
             "distractors": [
                 ("我要一杯水。", "wǒ yào yī bēi shuǐ.", "I want a glass of water."),
                 ("在三楼。", "zài sān lóu.", "On the third floor."),
             ]},
        ],
        "requests": [
            {"npc": ("请问有什么可以帮您的？", "qǐngwèn yǒu shénme kěyǐ bāng nín de?", "How can I help you?"),
             "player": ("我想换一个大一点的。", "wǒ xiǎng huàn yī gè dà yīdiǎn de.", "I'd like to exchange for a bigger one."),
             "prompt": "Make your request.",
             "distractors": [
                 ("今天星期三。", "jīntiān xīngqī sān.", "Today is Wednesday."),
                 ("他在北京工作。", "tā zài běijīng gōngzuò.", "He works in Beijing."),
             ]},
        ],
    },
    3: {
        "explanation": [
            {"npc": ("为什么你选这个？", "wèishéme nǐ xuǎn zhège?", "Why did you choose this one?"),
             "player": ("因为这个质量比较好，而且价格也不贵。", "yīnwèi zhège zhìliàng bǐjiào hǎo, érqiě jiàgé yě bú guì.", "Because the quality is better, and the price isn't expensive either."),
             "prompt": "Explain your reasoning.",
             "distractors": [
                 ("我不舒服，想看医生。", "wǒ bù shūfu, xiǎng kàn yīshēng.", "I'm not feeling well, I want to see a doctor."),
                 ("请给我一杯咖啡。", "qǐng gěi wǒ yī bēi kāfēi.", "Please give me a cup of coffee."),
             ]},
        ],
        "negotiation": [
            {"npc": ("这个价格不能再低了。", "zhège jiàgé bù néng zài dī le.", "This price can't go any lower."),
             "player": ("如果我买两个，可以打折吗？", "rúguǒ wǒ mǎi liǎng gè, kěyǐ dǎzhé ma?", "If I buy two, can I get a discount?"),
             "prompt": "Try to negotiate.",
             "distractors": [
                 ("明天下午三点见。", "míngtiān xiàwǔ sān diǎn jiàn.", "See you tomorrow at 3 PM."),
                 ("我已经毕业了。", "wǒ yǐjīng bìyè le.", "I've already graduated."),
             ]},
        ],
    },
    4: {
        "formal": [
            {"npc": ("关于这个项目，您有什么建议？", "guānyú zhège xiàngmù, nín yǒu shénme jiànyì?", "Regarding this project, do you have any suggestions?"),
             "player": ("我建议我们先做一个市场调查，然后再决定下一步。", "wǒ jiànyì wǒmen xiān zuò yī gè shìchǎng diàochá, ránhòu zài juédìng xià yī bù.", "I suggest we do a market survey first, then decide on the next step."),
             "prompt": "Give your professional suggestion.",
             "distractors": [
                 ("你知道附近有没有超市？", "nǐ zhīdào fùjìn yǒu méiyǒu chāoshì?", "Do you know if there's a supermarket nearby?"),
                 ("我周末想去爬山。", "wǒ zhōumò xiǎng qù páshān.", "I want to go hiking this weekend."),
             ]},
        ],
        "problem": [
            {"npc": ("我们遇到了一个问题。", "wǒmen yùdào le yī gè wèntí.", "We've encountered a problem."),
             "player": ("别担心，让我们一起想办法解决。", "bié dānxīn, ràng wǒmen yīqǐ xiǎng bànfǎ jiějué.", "Don't worry, let's figure out a solution together."),
             "prompt": "Reassure them and suggest working together.",
             "distractors": [
                 ("我要退房。", "wǒ yào tuì fáng.", "I want to check out."),
                 ("请问洗手间在哪儿？", "qǐngwèn xǐshǒujiān zài nǎr?", "Where is the bathroom?"),
             ]},
        ],
    },
    5: {
        "debate": [
            {"npc": ("你不觉得网上购物比实体店更方便吗？", "nǐ bù juéde wǎngshàng gòuwù bǐ shítǐ diàn gèng fāngbiàn ma?", "Don't you think online shopping is more convenient than physical stores?"),
             "player": ("方便是方便，但是你没法亲手摸到东西，而且退货也很麻烦。", "fāngbiàn shì fāngbiàn, dànshì nǐ méi fǎ qīnshǒu mōdào dōngxi, érqiě tuìhuò yě hěn máfan.", "It is convenient, but you can't touch things in person, and returns are also troublesome."),
             "prompt": "Give a nuanced counterargument.",
             "distractors": [
                 ("我想学开车。", "wǒ xiǎng xué kāi chē.", "I want to learn to drive."),
                 ("这个电影真好看。", "zhège diànyǐng zhēn hǎokàn.", "This movie is really good."),
             ]},
        ],
    },
    6: {
        "academic": [
            {"npc": ("请您谈谈对这个研究方向的看法。", "qǐng nín tántan duì zhège yánjiū fāngxiàng de kànfǎ.", "Please share your views on this research direction."),
             "player": ("从目前的文献来看，这个领域还有很多值得探索的空间，尤其是在应用层面。", "cóng mùqián de wénxiàn lái kàn, zhège lǐngyù hái yǒu hěn duō zhíde tànsuǒ de kōngjiān, yóuqí shì zài yìngyòng céngmiàn.", "Looking at the current literature, there's still much room for exploration in this field, especially at the application level."),
             "prompt": "Share your academic perspective.",
             "distractors": [
                 ("我昨天去了一个很好的餐厅。", "wǒ zuótiān qù le yī gè hěn hǎo de cāntīng.", "I went to a great restaurant yesterday."),
                 ("你能帮我拿一下那个吗？", "nǐ néng bāng wǒ ná yīxià nàge ma?", "Can you help me grab that?"),
             ]},
        ],
    },
}

# Cultural notes by genre
CULTURAL_NOTES = {
    "restaurant": "In China, it's common to fight over who pays the bill (抢着买单). The host usually insists on paying. Saying 我请你 (wǒ qǐng nǐ, 'my treat') is a common gesture of hospitality.",
    "shopping": "Bargaining (讨价还价, tǎo jià huán jià) is expected at markets but not in malls or chain stores. Starting at 50-60% of the asking price is reasonable.",
    "doctor": "In Chinese hospitals, patients often go directly to specialists without a GP referral. 挂号 (guàhào, 'register') is the first step at any hospital visit.",
    "travel": "Chinese train stations are divided into 候车室 (hòuchēshì, 'waiting rooms') by train number. Arrive 30+ minutes early for high-speed rail (高铁, gāotiě).",
    "school": "Teachers are highly respected in Chinese culture. Address them as 老师 (lǎoshī) even outside class. Students typically stand when a teacher enters.",
    "business": "Exchange business cards (名片, míngpiàn) with both hands. Never write on someone's card in front of them. Seniority matters in meetings.",
    "social": "When invited to someone's home, bring a gift (水果 or 茶, fruit or tea are safe choices). Don't open gifts in front of the giver — it's polite to wait.",
    "phone": "Chinese phone etiquette: say 喂 (wèi) when answering. For formal calls, state your name and company immediately.",
    "bank": "Chinese banks often require a 身份证 (shēnfènzhèng, ID card) or passport for any transaction. Take a number and wait — 排队 (páiduì) is essential.",
    "emergency": "The Chinese emergency numbers are 110 (police), 120 (ambulance), 119 (fire). English-speaking operators may be available in major cities.",
}


def _difficulty_for_hsk(hsk: int) -> float:
    """Map HSK level to difficulty score."""
    return min(1.0, round(0.1 + (hsk - 1) * 0.1, 2))


def _register_for_hsk(hsk: int, genre: str) -> str:
    """Determine register based on HSK level and genre."""
    if genre in ("business",) and hsk >= 4:
        return "formal"
    if hsk <= 2:
        return "casual"
    if hsk <= 4:
        return "neutral"
    return "formal"


def _get_turns_for_level(hsk: int) -> list:
    """Get appropriate turn templates for an HSK level."""
    # Use turns from this level and one below
    available = []
    for lvl in range(max(1, hsk - 1), min(hsk + 1, max(TURN_BANKS.keys()) + 1)):
        if lvl in TURN_BANKS:
            for category_turns in TURN_BANKS[lvl].values():
                available.extend(category_turns)
    return available


def _build_turns(hsk: int, num_turns: int, rng: random.Random) -> list:
    """Build a sequence of dialogue turns for a scenario."""
    available = _get_turns_for_level(hsk)
    if not available:
        return []

    turns = []
    used = set()

    for _ in range(num_turns):
        candidates = [t for i, t in enumerate(available) if i not in used]
        if not candidates:
            candidates = available  # Reuse if exhausted

        template = rng.choice(candidates)
        idx = available.index(template)
        used.add(idx)

        npc_zh, npc_py, npc_en = template["npc"]
        player_zh, player_py, player_en = template["player"]

        # NPC turn
        turns.append({
            "speaker": "npc",
            "text_zh": npc_zh,
            "text_pinyin": npc_py,
            "text_en": npc_en,
        })

        # Player turn with options
        distractors = template.get("distractors", [])
        options = [{
            "text_zh": player_zh,
            "text_pinyin": player_py,
            "text_en": player_en,
            "score": 1.0,
            "register": _register_for_hsk(hsk, ""),
            "feedback": "Correct response.",
        }]
        for d_zh, d_py, d_en in distractors:
            options.append({
                "text_zh": d_zh,
                "text_pinyin": d_py,
                "text_en": d_en,
                "score": 0.0,
                "feedback": f"Off-topic — you were asked to {template['prompt'].lower().rstrip('.')}, but this doesn't fit the conversation.",
            })
        rng.shuffle(options)

        turns.append({
            "speaker": "player",
            "prompt_en": template["prompt"],
            "options": options,
        })

    return turns


def _turns_count_for_hsk(hsk: int) -> tuple:
    """Return (min_turns, max_turns) for an HSK level."""
    if hsk <= 2:
        return (2, 3)
    elif hsk <= 4:
        return (3, 5)
    elif hsk <= 6:
        return (4, 6)
    else:
        return (5, 7)


def generate_dialogue(genre: str, title_idx: int, hsk: int,
                      variant: int, rng: random.Random) -> dict:
    """Generate one dialogue scenario."""
    genre_info = GENRES[genre]
    title_en, title_zh = genre_info["titles"][title_idx % len(genre_info["titles"])]

    # Add variant suffix to title if not the first
    if variant > 0:
        title_en = f"{title_en} ({variant + 1})"
        title_zh = f"{title_zh}（{variant + 1}）"

    min_t, max_t = _turns_count_for_hsk(hsk)
    num_turns = rng.randint(min_t, max_t)

    turns = _build_turns(hsk, num_turns, rng)
    if not turns:
        return None

    scenario_id = f"gen_{genre}_{hsk}_{title_idx:02d}_v{variant}"

    return {
        "title": title_en,
        "title_zh": title_zh,
        "hsk_level": hsk,
        "register": _register_for_hsk(hsk, genre),
        "scenario_type": "dialogue",
        "difficulty": _difficulty_for_hsk(hsk),
        "id": scenario_id,
        "tree": {
            "setup": f"A {genre} scenario at HSK {hsk} level.",
            "setup_zh": f"HSK {hsk} 级{genre}场景。",
            "turns": turns,
            "cultural_note": CULTURAL_NOTES.get(genre, ""),
        },
    }


def generate_all(hsk_levels: list, count: int = 200,
                 genre_filter: str = None, seed: int = 42) -> list:
    """Generate dialogue scenarios."""
    rng = random.Random(seed)
    dialogues = []

    genres_to_use = {genre_filter: GENRES[genre_filter]} if genre_filter else GENRES

    # Distribute count across genres and levels
    genre_list = []
    for genre, info in genres_to_use.items():
        lo, hi = info["hsk_range"]
        for hsk in hsk_levels:
            if lo <= hsk <= hi:
                for title_idx in range(len(info["titles"])):
                    genre_list.append((genre, title_idx, hsk))

    if not genre_list:
        return []

    # Generate enough variants to reach count
    variants_needed = (count + len(genre_list) - 1) // len(genre_list)
    variants_needed = max(1, variants_needed)

    for variant in range(variants_needed):
        if len(dialogues) >= count:
            break
        rng.shuffle(genre_list)
        for genre, title_idx, hsk in genre_list:
            if len(dialogues) >= count:
                break
            d = generate_dialogue(genre, title_idx, hsk, variant, rng)
            if d:
                dialogues.append(d)

    return dialogues[:count]


def write_dialogues(dialogues: list, output_dir: Path):
    """Write dialogue scenarios as individual JSON files."""
    existing = set(f.stem for f in output_dir.glob("*.json"))
    written = 0
    skipped = 0

    for d in dialogues:
        scenario_id = d.get("id", "")
        fname = f"{scenario_id}.json"
        fpath = output_dir / fname

        if scenario_id in existing or fpath.exists():
            skipped += 1
            continue

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=4)
        written += 1

    return written, skipped


def main():
    parser = argparse.ArgumentParser(description="Generate dialogue scenarios")
    parser.add_argument("--hsk", default="1-6", help="HSK levels (e.g., '1-3' or '1,2,3')")
    parser.add_argument("--count", type=int, default=200, help="Total dialogues to generate")
    parser.add_argument("--genre", help="Filter to one genre")
    parser.add_argument("--output-dir", default=str(SCENARIOS_DIR), help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    # Parse HSK levels
    if "-" in args.hsk:
        start, end = args.hsk.split("-")
        hsk_levels = list(range(int(start), int(end) + 1))
    elif "," in args.hsk:
        hsk_levels = [int(x) for x in args.hsk.split(",")]
    else:
        hsk_levels = [int(args.hsk)]

    print(f"\n  Dialogue Generator")
    print(f"  HSK levels: {hsk_levels}")
    print(f"  Target count: {args.count}")
    if args.genre:
        print(f"  Genre filter: {args.genre}")

    dialogues = generate_all(hsk_levels, count=args.count,
                             genre_filter=args.genre, seed=args.seed)

    print(f"\n  Generated {len(dialogues)} dialogues:")

    # Count by genre
    by_genre = {}
    by_hsk = {}
    for d in dialogues:
        genre = d["id"].split("_")[1]
        hsk = d["hsk_level"]
        by_genre[genre] = by_genre.get(genre, 0) + 1
        by_hsk[hsk] = by_hsk.get(hsk, 0) + 1

    for hsk in sorted(by_hsk.keys()):
        print(f"    HSK {hsk}: {by_hsk[hsk]}")
    print()
    for genre in sorted(by_genre.keys()):
        print(f"    {genre}: {by_genre[genre]}")

    if args.dry_run:
        print("\n  Dry run — no files written.")
        # Show a few samples
        for d in dialogues[:3]:
            print(f"\n  [{d['id']}] {d['title']} (HSK {d['hsk_level']})")
            turns = d["tree"]["turns"]
            for t in turns[:4]:
                if t["speaker"] == "npc":
                    print(f"    NPC: {t['text_zh']}")
                else:
                    print(f"    Player: [{t['prompt_en']}]")
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written, skipped = write_dialogues(dialogues, output_dir)

    existing = len(list(output_dir.glob("*.json")))
    print(f"\n  Written: {written} new files, {skipped} duplicates skipped")
    print(f"  Total scenarios in {output_dir}: {existing}")


if __name__ == "__main__":
    main()
