#!/usr/bin/env python3
"""Batch 1: Remove explained morals from HSK 7-9 passages."""
import json
import copy

EDITS = {
    # === HSK 7 ===
    "j7_observe_001": {
        "cut_zh": "我忽然明白，仪式的意义从来不取决于结果。枯萎的花盆里盛放的不是植物，而是一段不肯散场的记忆。水浇下去，蒸发了也好，渗进土里也罢，那个弯腰、倾壶、等待的姿势才是真正在生长的东西。",
        "replace_zh": "那天之后，我再也没有觉得那些花是枯死的。",
        "cut_en": "I suddenly understood that the meaning of ritual never depends on outcome. What the withered pots hold is not plants but a memory that refuses to leave. The water pours down\u2014evaporating or seeping into soil\u2014but the posture of bending, tilting the can, and waiting is what\u2019s truly growing.",
        "replace_en": "After that day, I never again thought of those flowers as dead."
    },
    "j7_urban_003": {
        "cut_zh": "那一刻我突然觉得，一栋楼就是一个垂直的村庄，而天台是村口的老槐树\u2014\u2014所有不适合在室内说的话，都会在这里找到它的听众。",
        "replace_zh": "一栋楼就是一个垂直的村庄，天台是村口的老槐树\u2014\u2014不适合在室内说的话，都到这里来找听众。",
        "cut_en": "In that moment I suddenly felt that an apartment building is a vertical village, and the rooftop is the old scholar tree at the village entrance\u2014all the words that don\u2019t fit indoors will find their audience here.",
        "replace_en": "An apartment building is a vertical village. The rooftop is the old scholar tree at the village entrance\u2014the words that don\u2019t fit indoors come here to find their audience."
    },
    "j7_inst_001": {
        "cut_zh": "那一刻我突然明白了，有些人的价值感不是来自头衔或收入，而是来自一条走了无数遍的路。",
        "replace_zh": "说完他站起来，朝左边的巷子走去。那是他邮递路线的第一段。",
        "cut_en": "In that moment I suddenly understood: some people\u2019s sense of worth comes not from titles or income, but from a road they\u2019ve walked countless times.",
        "replace_en": "He stood up and turned left into the alley. It was the first leg of his old route."
    },
    "j7_observe_008": {
        "cut_zh": "我忽然意识到，也许不是他在喂猫，而是猫在陪他\u2014\u2014每天傍晚六点半，准时赴一个无声的约定。",
        "replace_zh": "第二天傍晚六点半，我往阳台下看了一眼。他已经蹲在那里了，猫也到了。",
        "cut_en": "I suddenly realized that maybe he wasn\u2019t feeding the cats\u2014the cats were keeping him company. Every evening at 6:30, faithfully keeping a silent appointment.",
        "replace_en": "The next evening at 6:30, I glanced down from my balcony. He was already squatting there. The cats had already come."
    },
    "j7_observe_015": {
        "cut_zh": "也许这就是手工的本质\u2014\u2014它不试图改造人，只是温柔地包裹人此刻的样子。",
        "replace_zh": "",
        "cut_en": "Perhaps this is the essence of handcraft\u2014it doesn\u2019t try to remake people, only gently wraps them as they are right now.",
        "replace_en": ""
    },
    "j7_identity_006": {
        "cut_zh": "有时候我觉得，这也许就是外婆真正传给我的东西\u2014\u2014不是一个配方，而是一种注意力。",
        "replace_zh": "外婆传给我的不是配方。是看人的习惯。",
        "cut_en": "Sometimes I feel that perhaps this is what my grandmother truly passed down to me \u2014 not a recipe, but a kind of attentiveness.",
        "replace_en": "What my grandmother passed down wasn\u2019t the recipe. It was the habit of watching people."
    },
    "j7_food_003": {
        "cut_zh": "我忽然意识到，老陈每天凌晨四点起来准备不同的食材，不只是在做生意，也是在守护一个已经不在身边的人留下的秩序。那些热腾腾的早餐背后，藏着一份被日常掩盖的思念。",
        "replace_zh": "今天是星期四。他的摊位前摆着三个蒸笼。五年了，星期四永远是三个蒸笼。",
        "cut_en": "I suddenly realized that Old Chen getting up at 4 AM every morning to prepare different ingredients wasn\u2019t just business \u2014 it\u2019s guarding an order left behind by someone no longer at his side. Behind those steaming breakfasts hides a longing masked by the everyday.",
        "replace_en": "Today is Thursday. Three steamers lined up at his stall. Five years, and Thursday is always three steamers."
    },

    # === HSK 8 ===
    "j8_observe_001": {
        "cut_zh": "那一刻我突然理解了一种时间观：世界并不因为我们的忙碌而停止运转它的微小仪式。",
        "replace_zh": "位置分毫不差。",
        "cut_en": "In that moment I suddenly understood a certain view of time: the world does not stop performing its small rituals just because we are busy.",
        "replace_en": "The position hadn\u2019t shifted by a millimeter."
    },
    "j8_observe_020": {
        "cut_zh": "那一刻我意识到：我们对近在咫尺的人的了解，可能还不如对社交媒体上万里之外的博主的了解。城市创造了一种新型的亲近\u2014\u2014我们共享墙壁、天花板和地板，共享水管和电路，却共享不了最基本的问候。",
        "replace_zh": "他冲我点了点头，我也点了点头。然后他进了电梯，我走了楼梯。我们又回到了各自的声音里。",
        "cut_en": "In that moment I realized: our understanding of people mere walls away may be less than our understanding of influencers thousands of miles away on social media. Cities have created a new kind of proximity\u2014we share walls, ceilings, and floors, share plumbing and wiring, yet can\u2019t share the most basic greeting.",
        "replace_en": "He nodded at me. I nodded back. He took the elevator; I took the stairs. We went back into our separate sounds."
    },
    "j8_city_041": {
        "cut_zh": "我忽然意识到，水洼是这座城市最诚实的肖像画家\u2014\u2014它不挑选、不美化，只是忠实地记录头顶上方恰好存在的一切。而我们大多数人，终其一生都在仰望，却很少低头去看脚下这些转瞬即逝的镜子里，藏着怎样一个被颠倒过来的世界。",
        "replace_zh": "",
        "cut_en": "I suddenly realized that puddles are the city\u2019s most honest portrait painters\u2014they don\u2019t select or beautify, only faithfully record everything that happens to exist overhead. Yet most of us spend our entire lives looking up, yet rarely bow our heads to see what kind of inverted world is hidden in these fleeting mirrors at our feet.",
        "replace_en": ""
    },
    "j8_food_095": {
        "cut_zh": "那一刻我才知道，一个少年时代的善意，在对方心里放了多少年、长了多少息。",
        "replace_zh": "",
        "cut_en": "Only in that moment did I realize how many years a teenage act of kindness had sat in the other person\u2019s heart, and how much interest it had accrued.",
        "replace_en": ""
    },
    "j8_food_100": {
        "cut_zh": "也许这就是为什么，在所有的中国食物里，粥是最像母爱的那一种。",
        "replace_zh": "",
        "cut_en": "Perhaps that is why, among all Chinese foods, congee is the one most like a mother\u2019s love.",
        "replace_en": ""
    },
    "j8_identity_080": {
        "cut_zh": "也许这就是照片和记忆的根本区别\u2014\u2014记忆是可以被美化和编辑的，而照片是不讲情面的。",
        "replace_zh": "照片不讲情面。记忆可以美化、可以编辑。照片不行。",
        "cut_en": None,  # need to find the exact EN
        "replace_en": None
    },
    "j8_quiet_113": {
        "cut_zh": "它不是一件器物，而是一段被泥土记住的人生。",
        "replace_zh": "",
        "cut_en": "It was not an object, but a life remembered by earth.",
        "replace_en": ""
    },

    # === HSK 9 ===
    "j9_observe_001": {
        "cut_zh": "那一刻我突然明白，所谓现代化，有时候不过是用一层涂料抹去几十年的对话。",
        "replace_zh": "施工的人在收拾工具。下午三点的阳光照在白墙上，什么痕迹都没有了。",
        "cut_en": "In that moment I suddenly understood: what we call modernization is sometimes nothing more than a coat of paint erasing decades of dialogue.",
        "replace_en": "The workers were packing up. The three o\u2019clock sun fell on the white wall. No trace of anything."
    },
    "j9_observe_013": {
        "cut_zh": "我才恍然明白，原来我怀念的不是那栋老宅，而是那种与天气之间毫无隔阂的共处方式。",
        "replace_zh": "下雨的时候，我偶尔把窗户打开一条缝。",
        "cut_en": None,
        "replace_en": None
    },
    "j9_identity_054": {
        "cut_zh": "那一刻我意识到，我触碰的不仅仅是墨迹，而是外婆当年手指施加在这张纸上的力量本身。手写的文字是一种双重的存在\u2014\u2014它既是符号也是身体的痕迹。当我们放弃手写的时候，我们失去的不仅仅是一种书写方式，更是一种在纸上留下自己身体印记的能力。",
        "replace_zh": "我用手指沿着那一横慢慢划过。纸上有一个微微的凹痕\u2014\u2014外婆下笔重。",
        "cut_en": None,
        "replace_en": None
    },
    "j9_identity_059": {
        "cut_zh": "这个仪式的意义不在于真相，而在于锚定\u2014\u2014在一个永远不确定的世界里，给自己一个暂时确定的参照点。",
        "replace_zh": "雾气又变了。",
        "cut_en": None,
        "replace_en": None
    },
    "j9_identity_061": {
        "cut_zh": "这就是阅读最深层的意义\u2014\u2014不是获取信息，也不是消遣时间，而是在你的意识中植入无数个「别人」，让你在孤独的时候从来不只是你一个人。每一本认真读过的书都在你体内留下了一个幽灵般的存在\u2014\u2014你和它共享同一具身体，偶尔在某个安静的瞬间，你能听到它轻声对你说话。",
        "replace_zh": "每一本认真读过的书都在你体内留下了什么。不是知识。更像一个安静的房客\u2014\u2014你和它共享同一具身体，偶尔在某个安静的瞬间，你能听到它轻声对你说话。",
        "cut_en": None,
        "replace_en": None
    },
    "j9_identity_064": {
        "cut_zh": "也许这就是为什么，看一个熟睡的人总会让人心生怜惜\u2014\u2014你看到的不是他的社会面具，而是面具脱落后那个无防备的、柔软的、最初始的自己。",
        "replace_zh": "",
        "cut_en": None,
        "replace_en": None
    },
    "j9_food_067": {
        "cut_zh": "这种「无味之味」，恰恰是中国美学中最高级别的境界\u2014\u2014不是空无，而是无限的可能性。",
        "replace_zh": "无味之味。什么都没有，所以什么都放得下。",
        "cut_en": None,
        "replace_en": None
    },
    "j9_quiet_101": {
        "cut_zh": "也许这就是自然教给我们的最安静的一课：放手不是失去，而是为下一次拥有腾出空间。",
        "replace_zh": "我在银杏树下站了很久。地上已经铺了一层金色。新落下的叶子覆盖在旧叶子上面，像一封一封没有打开过的信。",
        "cut_en": None,
        "replace_en": None
    },
    "j9_quiet_108": {
        "cut_zh": "也许这就是最理想的人际关系\u2014\u2014不是不停地说话，而是默默地给予。",
        "replace_zh": "",
        "cut_en": None,
        "replace_en": None
    },
    "j9_quiet_110": {
        "cut_zh": "也许这就是为什么人们要建墓碑\u2014\u2014不是为了死者，而是为了活着的人。墓碑给了思念一个方向，",
        "replace_zh": "墓碑给了思念一个方向。",
        "cut_en": None,
        "replace_en": None
    },
}

# EN translations for passages where cut_en was None - need fuzzy matching
EN_FUZZY_CUTS = {
    "j9_observe_013": {
        "pattern": "suddenly understand",
        "cut_after": "what I missed was not the old house itself, but",
        "replace_en": "When it rains, I sometimes crack the window open."
    },
    "j9_identity_054": {
        "pattern": "not merely a writing method but",
        "replace_en": "I traced my finger slowly along that single stroke. There was a faint indentation in the paper\u2014Grandmother pressed hard."
    },
    "j9_identity_059": {
        "pattern": "The meaning of this ritual lies not in truth, but in anchoring",
        "replace_en": "The fog shifts again."
    },
    "j9_identity_061": {
        "pattern": "This is the deepest meaning of reading",
        "replace_en": "Every book you\u2019ve read seriously leaves something inside you. Not knowledge. More like a quiet tenant\u2014you share the same body, and occasionally, in a still moment, you hear it speak softly to you."
    },
    "j9_identity_064": {
        "pattern": "stirs tenderness",
        "replace_en": ""
    },
    "j9_food_067": {
        "pattern": "highest level in Chinese aesthetics",
        "replace_en": "The taste of no taste. Nothing there\u2014so anything can fit."
    },
    "j9_quiet_101": {
        "pattern": "quietest lesson nature teaches",
        "replace_en": "I stood under the ginkgo for a long time. The ground was already covered in gold. New leaves falling over old ones, like letters never opened."
    },
    "j9_quiet_108": {
        "pattern": "most ideal human relationship",
        "replace_en": ""
    },
    "j9_quiet_110": {
        "pattern": "not for the dead, but for the living",
        "replace_en": "A gravestone gives longing a direction."
    },
    "j8_identity_080": {
        "pattern": "fundamental difference between photographs and memory",
        "replace_en": "Photographs are merciless. Memory can be embellished and edited. Photographs can\u2019t."
    },
}


def apply_edits(filename, level):
    with open(filename) as f:
        passages = json.load(f)

    edited_count = 0
    for p in passages:
        pid = p["id"]
        if pid not in EDITS:
            continue

        edit = EDITS[pid]
        text_zh = p["text_zh"]
        text_en = p["text_en"]

        # Apply ZH edit
        cut_zh = edit["cut_zh"]
        if cut_zh and cut_zh in text_zh:
            new_zh = text_zh.replace(cut_zh, edit["replace_zh"])
            # Clean up double spaces or trailing spaces
            new_zh = new_zh.replace("  ", " ").strip()
            # Clean up orphaned punctuation
            new_zh = new_zh.replace("。。", "。").replace("，。", "。")
            p["text_zh"] = new_zh
            edited_count += 1
            print(f"  [ZH] {pid}: cut '{cut_zh[:30]}...' -> '{edit['replace_zh'][:30]}...'")
        elif cut_zh:
            print(f"  [ZH] WARNING: could not find cut text in {pid}")

        # Apply EN edit
        cut_en = edit.get("cut_en")
        replace_en = edit.get("replace_en")
        if cut_en and replace_en is not None and cut_en in text_en:
            new_en = text_en.replace(cut_en, replace_en)
            new_en = new_en.replace("  ", " ").strip()
            p["text_en"] = new_en
            print(f"  [EN] {pid}: cut '{cut_en[:30]}...' -> '{replace_en[:30]}...'")
        elif cut_en is None and pid in EN_FUZZY_CUTS:
            # Fuzzy match for EN
            fuzzy = EN_FUZZY_CUTS[pid]
            pattern = fuzzy["pattern"]
            if pattern in text_en:
                # Find the sentence containing the pattern and replace
                # Strategy: find the sentence, cut from start of that sentence to end
                idx = text_en.index(pattern)
                # Walk back to find sentence start
                sent_start = idx
                while sent_start > 0 and text_en[sent_start-1] not in '.!?")\u2019':
                    sent_start -= 1
                # If we backed up to a quote/period, move forward past whitespace
                while sent_start < len(text_en) and text_en[sent_start] in ' ':
                    sent_start += 1

                old_ending = text_en[sent_start:]
                new_en = text_en[:sent_start].strip()
                if fuzzy["replace_en"]:
                    new_en = new_en + " " + fuzzy["replace_en"]
                new_en = new_en.strip()
                p["text_en"] = new_en
                print(f"  [EN-fuzzy] {pid}: replaced from '{pattern[:25]}...'")
            else:
                print(f"  [EN-fuzzy] WARNING: pattern '{pattern[:25]}' not found in {pid}")

    with open(filename, "w") as f:
        json.dump(passages, f, ensure_ascii=False, indent=2)

    return edited_count


total = 0
for level in range(7, 10):
    fname = f"passages_hsk{level}.json"
    print(f"\n=== Processing {fname} ===")
    count = apply_edits(fname, level)
    total += count
    print(f"  Edited {count} passages")

print(f"\nTotal passages edited: {total}")
