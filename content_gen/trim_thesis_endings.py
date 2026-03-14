#!/usr/bin/env python3
"""
Trim generic thesis/moral endings from reading passages.

For each passage ending with 也许/或许/大概/可能/说不定, decide CUT or KEEP.
CUT: remove the last sentence from text_zh and text_en.
KEEP: leave as-is.

Rules:
- CUT if the previous sentence is a strong concrete image and the thesis is generic/sentimental
- KEEP if the thesis is earned/specific, the passage would be too short, or at HSK 1-2 where simplicity fits
- More aggressive at HSK 5+
"""

import json
import re
import copy

MARKERS = ['也许', '或许', '大概', '可能', '说不定']

# Manual CUT/KEEP decisions for each passage, with rationale.
# Format: (passage_id, decision, rationale)
DECISIONS = {
    # === HSK 1 ===
    # "可能猫看到的和我不一样" — observational, IS the point, low level
    "j1_observe_014": ("KEEP", "HSK1, thesis IS the observational point, not generic"),

    # === HSK 2 ===
    # "也许那把伞不想走了" — whimsical, IS the comic point
    "j2_mystery_002": ("KEEP", "Thesis IS the comic/whimsical observation, not commentary"),
    # "也许不是面条的问题，是因为少了一个人" — earned, specific, emotional
    "j2_food_001": ("KEEP", "HSK2, thesis is specific and earned (missing person, not generic)"),
    # "也许明年，从我窗户看出去的东西就完全不一样了" — concrete-ish, continues the observation
    "j2_urban_012": ("KEEP", "HSK2, thesis extends concrete observation about city change"),
    # "也许是我不知道的时候帮的" — IS the mystery's resolution
    "j2_mystery_007": ("KEEP", "Thesis IS the point of the mystery passage"),
    # "也许对他们来说，换了音乐就不一样了" — mild, but passage would feel unfinished
    "j2_inst_014": ("KEEP", "HSK2, thesis is the observational point about the park regulars"),

    # === HSK 3 ===
    # "大概是因为大家都知道，不管多晚，只要还有一辆车，就能到家" — explains why no one complains, IS the point
    "j3_urban_005": ("KEEP", "Thesis IS the explanation/observation, not tacked on"),
    # "也许旅行中最好的时刻..." — generic sentimental, prev sentence is strong image (relaxed, content)
    "j3_travel_002": ("CUT", "Prev sentence is strong concrete image; thesis is generic travel wisdom"),

    # === HSK 4 ===
    # "也许每个大人心里都住着一个需要被叫小名的孩子" — generic sentimental
    "j4_identity_001": ("CUT", "Generic sentimental; prev sentence (work feels less tiring) is concrete"),
    # "也许长大就是这样——我们学会了把字写得漂亮，却忘了..." — generic growing-up wisdom
    "j4_identity_005": ("CUT", "Generic growing-up thesis; prev sentence is strong concrete moment"),
    # "也许同样的九十秒对不同的人来说是不一样的" — actually specific and earned, ties together two observations
    "j4_urban_008": ("KEEP", "Thesis synthesizes two concrete observations, earned and specific"),
    # "也许有时候走错路不是一件坏事" — generic 'wrong path' wisdom
    "j4_travel_002": ("CUT", "Generic life wisdom; prev sentence is strong concrete moment (sat under tree)"),
    # "也许少的就是这种让人感到安心的旧感觉" — answers the 'missing something', close call
    "j4_observe_027": ("CUT", "Prev sentence already implies this; thesis is redundant explanation"),
    # "也许每天面对同一件东西并不可怕..." — generic wisdom
    "j4_inst_007": ("CUT", "Generic wisdom; prev sentence (his understanding is deeper) is strong"),
    # "也许有些地方吸引人的不是效率..." — generic
    "j4_urban_012": ("CUT", "Generic; prev sentence (people love coming here) is concrete ending"),
    # "也许善意就是这样的，你给出一点..." — generic kindness thesis
    "j4_urban_013": ("CUT", "Generic kindness thesis; prev sentence is specific and concrete"),
    # "也许安静不只是没有声音，而是一种大家共同创造的氛围" — actually specific and interesting
    "j4_inst_009": ("KEEP", "Thesis is specific to the passage's observation about quiet spaces"),
    # "也许，真正的欣赏不需要专业知识，只需要时间和耐心" — generic
    "j4_inst_010": ("CUT", "Generic appreciation thesis; prev sentence (unexpected guard) is stronger"),
    # "也许不能，但是它能让你每天记住你想做什么样的人" — answers a question, IS the point
    "j4_identity_008": ("KEEP", "Thesis answers the preceding question, IS the punchline"),
    # "也许最好的事情就是这样——不需要答案" — generic
    "j4_observe_037": ("CUT", "Generic; prev sentence (I didn't know how to answer) is strong ending"),
    # "也许当你用一种新的语言做梦的时候，你就有了一双新的眼睛" — beautiful, specific to language learning
    "j4_identity_009": ("KEEP", "Specific to language, not generic; poetic and earned"),
    # "也许这就是最好的报复——让你生气的人笑出来" — IS the comic point
    "j4_comedy_008": ("KEEP", "Thesis IS the comic punchline, not commentary"),

    # === HSK 5 ===
    # "也许味道是最后消失的东西" — prev is 'taste is still the same', thesis explains what reader should feel
    "j5_food_001": ("CUT", "Prev sentence is strong; thesis over-explains"),
    # "也许问题不是「哪个才是真的我」..." — specific, reframes the question
    "j5_identity_002": ("KEEP", "Thesis reframes the question in a specific way, IS the insight"),
    # "也许是因为在这个地方，每个人都更容易理解什么叫脆弱" — explains the observation
    "j5_inst_006": ("CUT", "Prev sentence is concrete observation; thesis explains what reader should think"),
    # "也许再过三十年，我的切菜声也会变成..." — specific, concrete image, not generic
    "j5_observe_013": ("KEEP", "Thesis is itself a concrete image, not abstract moralizing"),
    # "也许不是所有事情都需要那么快" — generic 'slow down' wisdom
    "j5_inst_007": ("CUT", "Generic slow-down thesis; prev sentence is strong concrete description"),
    # "也许这就是一个好系统的标志：让你感觉不到系统的存在" — specific, clever
    "j5_inst_008": ("KEEP", "Thesis is specific and clever, earned observation about systems"),
    # "也许我们都需要这样的时刻，允许自己停下来" — generic
    "j5_reflect_064": ("CUT", "Generic 'stop and smell the roses'; prev sentence is concrete"),
    # "也许散步最好的状态就是没有目的地" — generic walking wisdom
    "j5_reflect_069": ("CUT", "Generic; prev sentence (mood was better) is concrete ending"),
    # "也许对待自己的成长，也应该像对待一棵植物一样有耐心" — generic growth metaphor
    "j5_reflect_071": ("CUT", "Generic growth metaphor; prev sentence is concrete and strong"),
    # "也许我们一直在追求「有意义」的生活..." — generic meaning-of-life
    "j5_reflect_072": ("CUT", "Generic meaning-of-life; prev sentence is concrete and strong"),
    # "也许等待本身就是一种训练" — generic
    "j5_system_080": ("CUT", "Generic; prev sentence (lottery feeling) is vivid and concrete"),
    # "也许不是所有事情都需要快，有些事情值得慢慢来" — generic, near-duplicate of inst_007
    "j5_system_087": ("CUT", "Generic slow-down thesis; prev sentence is concrete"),
    # "也许这就是城市生活的一种联系方式" — generic city wisdom
    "j5_urban_103": ("CUT", "Generic city-connection thesis; prev sentence is concrete"),
    # "也许雨后的城市最好的礼物就是这些积水" — specific, concrete image
    "j5_urban_108": ("KEEP", "Thesis is itself a concrete image (mirror for adults, playground for kids)"),
    # "也许正是因为短暂，所以每年春天吃到第一颗草莓..." — generic scarcity wisdom
    "j5_food_120": ("CUT", "Generic scarcity/fleeting thesis; prev sentence is concrete"),

    # === HSK 6 ===
    # "也许混乱之后的清晰，才是最值得珍惜的那种" — generic
    "j6_observe_003": ("CUT", "Generic; prev sentence is gorgeous concrete image"),
    # "也许缺少的不是配方而是那种愿意花八个小时等待..." — actually specific and earned
    "j6_food_002": ("KEEP", "Thesis is specific (8 hours, shrimp-eye bubbles), not generic"),
    # "也许不能，但他们至少能触摸到那些我从未说出口的情绪" — answers question, specific
    "j6_identity_078": ("KEEP", "Answers the preceding question, specific and earned"),
    # "也许真正的社交不是一次性的等价交换" — generic social wisdom
    "j6_food_093": ("CUT", "Generic social thesis; prev sentence (his words made me think) is concrete"),

    # === HSK 7 ===
    # "也许真正让人回避的不是死亡本身..." — specific, philosophical, earned
    "j7_observe_002": ("KEEP", "Thesis is specific (particular bench, particular afternoon), earned"),
    # "也许美有时候恰恰产生于错位" — extends the metaphor, specific
    "j7_mystery_004": ("CUT", "Prev sentence has the beautiful image (travelers in wrong time zone); thesis over-explains"),
    # "大概率又会是一个说「快点」的人" — IS the comic point, concrete
    "j7_observe_020": ("KEEP", "Thesis IS the dry punchline, concrete not abstract"),

    # === HSK 8 ===
    # "或许所谓的智慧城市..." — generic smart-city thesis
    "j8_city_046": ("CUT", "Generic; prev sentence about agency/composure is strong concrete ending"),
    # "也许我们以为自己长大了，但身体知道..." — generic growing-up
    "j8_identity_088": ("CUT", "Generic; prev sentence (absurd that a 30-year-old...) is strong concrete ending"),

    # === HSK 9 ===
    # "也许世界上最动人的款待..." — actually beautiful, specific, earned
    "j9_food_082": ("KEEP", "Thesis is specific and earned (feast for those who won't come)"),
    # "也许有一种力量，比磁力更古老..." — poetic, IS the point
    "j9_mystery_095": ("KEEP", "Thesis IS the poetic conclusion, not tacked-on commentary"),
    # "也许她的长寿和她每天雷打不动的..." — specific, ties to science
    "j9_quiet_100": ("KEEP", "Thesis is specific (brain self-repair), not generic"),
    # "也许我们需要的不是安静的环境，而是安静的色彩" — IS the point of the passage
    "j9_quiet_107": ("KEEP", "Thesis IS the central observation of the passage"),
    # "也许重新学会午睡是现代人最需要的考古实践" — specific, clever metaphor
    "j9_quiet_114": ("KEEP", "Thesis is specific (archaeology metaphor), earned and clever"),
}


def split_zh_sentences(text):
    """Split Chinese text into sentences on 。！？"""
    sents = re.split(r'(?<=[。！？])', text)
    return [s.strip() for s in sents if s.strip()]


def split_en_sentences(text):
    """Split English text into sentences. Handle em-dashes and quotes carefully."""
    # Split on sentence-ending punctuation followed by space or end-of-string
    # But be careful not to split on abbreviations or mid-sentence periods
    sents = re.split(r'(?<=[.!?])(?:\s+|$)', text)
    return [s.strip() for s in sents if s.strip()]


def remove_last_zh_sentence(text):
    """Remove the last sentence from Chinese text."""
    sents = split_zh_sentences(text)
    if len(sents) <= 1:
        return text  # Don't remove if only one sentence
    return ''.join(sents[:-1]).strip()


def remove_last_en_sentence(text):
    """Remove the last sentence from English text."""
    sents = split_en_sentences(text)
    if len(sents) <= 1:
        return text
    return ' '.join(sents[:-1]).strip()


def main():
    cut_count = 0
    keep_count = 0
    unknown_count = 0

    report_cuts = []
    report_keeps = []
    report_unknown = []

    for level in range(1, 10):
        fn = f'passages_hsk{level}.json'
        try:
            with open(fn) as f:
                passages = json.load(f)
        except FileNotFoundError:
            continue

        modified = False

        for p in passages:
            zh = p.get('text_zh', '')
            sents = split_zh_sentences(zh)
            if not sents:
                continue

            last = sents[-1]
            if not any(last.startswith(m) for m in MARKERS):
                continue

            pid = p['id']
            title = p.get('title', '???')

            if pid not in DECISIONS:
                unknown_count += 1
                report_unknown.append(f"  HSK{level} | {pid} | {title}")
                continue

            decision, rationale = DECISIONS[pid]

            if decision == "KEEP":
                keep_count += 1
                report_keeps.append(f"  HSK{level} | {pid} | {title}: {rationale}")
                continue

            # CUT
            en = p.get('text_en', '')
            en_sents = split_en_sentences(en)

            old_zh = zh
            old_en = en
            new_zh = remove_last_zh_sentence(zh)
            new_en = remove_last_en_sentence(en)

            # Verify we actually removed something
            if new_zh == old_zh:
                print(f"WARNING: ZH unchanged for {pid}")
                continue

            p['text_zh'] = new_zh
            p['text_en'] = new_en
            modified = True
            cut_count += 1

            cut_zh = sents[-1]
            cut_en = en_sents[-1] if en_sents else '???'
            report_cuts.append(
                f"  HSK{level} | {pid} | {title}\n"
                f"    Rationale: {rationale}\n"
                f"    Cut ZH: {cut_zh}\n"
                f"    Cut EN: {cut_en}\n"
                f"    New ending ZH: {split_zh_sentences(new_zh)[-1] if split_zh_sentences(new_zh) else '???'}\n"
                f"    New ending EN: {split_en_sentences(new_en)[-1] if split_en_sentences(new_en) else '???'}"
            )

        if modified:
            with open(fn, 'w', encoding='utf-8') as f:
                json.dump(passages, f, ensure_ascii=False, indent=2)
                f.write('\n')

    # Print report
    print("=" * 70)
    print(f"THESIS ENDING TRIM REPORT")
    print(f"=" * 70)
    print(f"\nTotal found: {cut_count + keep_count + unknown_count}")
    print(f"  CUT:     {cut_count}")
    print(f"  KEPT:    {keep_count}")
    if unknown_count:
        print(f"  UNKNOWN: {unknown_count}")
    print()

    print(f"--- CUT ({cut_count}) ---")
    for line in report_cuts:
        print(line)
    print()

    print(f"--- KEPT ({keep_count}) ---")
    for line in report_keeps:
        print(line)

    if report_unknown:
        print()
        print(f"--- UNKNOWN ({unknown_count}) ---")
        for line in report_unknown:
            print(line)

    print()
    print("Done. Files saved.")


if __name__ == '__main__':
    main()
