#!/usr/bin/env python3
"""
Offline graded reading passage generator for Mandarin learning app.
Uses template-based slot-filling — zero LLM tokens at runtime.

Usage:
    python tools/generate_passages.py --hsk 1-3 --count 100
    python tools/generate_passages.py --hsk 2 --genre diary --count 50
    python tools/generate_passages.py --hsk 1-9 --count 100 --dry-run
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HSK_DIR = PROJECT_ROOT / "data" / "hsk"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "reading_passages.json"

# ---------------------------------------------------------------------------
# Vocabulary loader
# ---------------------------------------------------------------------------

def load_hsk_vocab(levels):
    """Load HSK vocabulary for the given levels (cumulative up to max level)."""
    vocab_by_level = {}
    for lvl in range(1, max(levels) + 1):
        path = HSK_DIR / f"hsk{lvl}.json"
        if not path.exists():
            print(f"Warning: {path} not found, skipping HSK {lvl}", file=sys.stderr)
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        vocab_by_level[lvl] = data["items"]
    return vocab_by_level


def cumulative_vocab(vocab_by_level, target_level):
    """Return all vocab items from HSK 1 up to target_level."""
    items = []
    for lvl in sorted(vocab_by_level.keys()):
        if lvl <= target_level:
            items.extend(vocab_by_level[lvl])
    return items


# ---------------------------------------------------------------------------
# Semantic word banks — hand-curated Chinese words grouped by role.
# Each entry: (hanzi, pinyin, english).
# The generator picks from these; HSK filtering happens at selection time.
# ---------------------------------------------------------------------------

WORD_BANKS = {
    "person": [
        ("我", "wǒ", "I"), ("他", "tā", "he"), ("她", "tā", "she"),
        ("小明", "Xiǎomíng", "Xiaoming"), ("小红", "Xiǎohóng", "Xiaohong"),
        ("小李", "Xiǎo Lǐ", "Xiao Li"), ("小王", "Xiǎo Wáng", "Xiao Wang"),
        ("张老师", "Zhāng lǎoshī", "Teacher Zhang"),
        ("李医生", "Lǐ yīshēng", "Doctor Li"),
        ("王先生", "Wáng xiānsheng", "Mr. Wang"),
        ("我朋友", "wǒ péngyou", "my friend"),
        ("我妈妈", "wǒ māma", "my mom"),
        ("我爸爸", "wǒ bàba", "my dad"),
        ("我同学", "wǒ tóngxué", "my classmate"),
        ("我同事", "wǒ tóngshì", "my colleague"),
        ("我姐姐", "wǒ jiějie", "my older sister"),
        ("我哥哥", "wǒ gēge", "my older brother"),
        ("邻居", "línjū", "neighbor"),
    ],
    "place": [
        ("学校", "xuéxiào", "school"), ("公园", "gōngyuán", "park"),
        ("医院", "yīyuàn", "hospital"), ("图书馆", "túshūguǎn", "library"),
        ("超市", "chāoshì", "supermarket"), ("饭店", "fàndiàn", "restaurant"),
        ("家", "jiā", "home"), ("公司", "gōngsī", "company"),
        ("火车站", "huǒchēzhàn", "train station"),
        ("机场", "jīchǎng", "airport"), ("银行", "yínháng", "bank"),
        ("咖啡馆", "kāfēiguǎn", "cafe"), ("电影院", "diànyǐngyuàn", "cinema"),
        ("商店", "shāngdiàn", "shop"), ("市场", "shìchǎng", "market"),
        ("博物馆", "bówùguǎn", "museum"), ("体育馆", "tǐyùguǎn", "gym"),
        ("书店", "shūdiàn", "bookstore"), ("邮局", "yóujú", "post office"),
    ],
    "time": [
        ("今天", "jīntiān", "today"), ("昨天", "zuótiān", "yesterday"),
        ("明天", "míngtiān", "tomorrow"), ("上午", "shàngwǔ", "morning"),
        ("下午", "xiàwǔ", "afternoon"), ("晚上", "wǎnshang", "evening"),
        ("星期一", "xīngqī yī", "Monday"), ("星期六", "xīngqī liù", "Saturday"),
        ("周末", "zhōumò", "weekend"), ("上个月", "shàng gè yuè", "last month"),
        ("去年", "qùnián", "last year"), ("每天", "měi tiān", "every day"),
        ("早上", "zǎoshang", "morning"), ("中午", "zhōngwǔ", "noon"),
        ("最近", "zuìjìn", "recently"), ("以前", "yǐqián", "before"),
    ],
    "food": [
        ("米饭", "mǐfàn", "rice"), ("面条", "miàntiáo", "noodles"),
        ("饺子", "jiǎozi", "dumplings"), ("鸡蛋", "jīdàn", "egg"),
        ("牛奶", "niúnǎi", "milk"), ("水果", "shuǐguǒ", "fruit"),
        ("苹果", "píngguǒ", "apple"), ("茶", "chá", "tea"),
        ("咖啡", "kāfēi", "coffee"), ("鱼", "yú", "fish"),
        ("鸡肉", "jīròu", "chicken"), ("蔬菜", "shūcài", "vegetables"),
        ("面包", "miànbāo", "bread"), ("蛋糕", "dàngāo", "cake"),
        ("汤", "tāng", "soup"), ("啤酒", "píjiǔ", "beer"),
    ],
    "activity": [
        ("看书", "kàn shū", "read"), ("跑步", "pǎobù", "run"),
        ("游泳", "yóuyǒng", "swim"), ("唱歌", "chànggē", "sing"),
        ("跳舞", "tiàowǔ", "dance"), ("画画", "huàhuà", "paint"),
        ("做饭", "zuòfàn", "cook"), ("打篮球", "dǎ lánqiú", "play basketball"),
        ("看电影", "kàn diànyǐng", "watch movies"),
        ("听音乐", "tīng yīnyuè", "listen to music"),
        ("学中文", "xué zhōngwén", "study Chinese"),
        ("上网", "shàngwǎng", "go online"), ("旅游", "lǚyóu", "travel"),
        ("拍照", "pāizhào", "take photos"), ("爬山", "páshān", "climb mountain"),
        ("打电话", "dǎ diànhuà", "make a phone call"),
        ("写作业", "xiě zuòyè", "do homework"),
        ("散步", "sànbù", "take a walk"),
    ],
    "weather": [
        ("晴天", "qíngtiān", "sunny"), ("下雨", "xiàyǔ", "rainy"),
        ("下雪", "xiàxuě", "snowy"), ("刮风", "guāfēng", "windy"),
        ("很热", "hěn rè", "very hot"), ("很冷", "hěn lěng", "very cold"),
        ("暖和", "nuǎnhuo", "warm"), ("凉快", "liángkuai", "cool"),
        ("阴天", "yīntiān", "overcast"), ("多云", "duōyún", "cloudy"),
    ],
    "emotion": [
        ("高兴", "gāoxìng", "happy"), ("难过", "nánguò", "sad"),
        ("生气", "shēngqì", "angry"), ("紧张", "jǐnzhāng", "nervous"),
        ("累", "lèi", "tired"), ("开心", "kāixīn", "happy"),
        ("着急", "zháojí", "anxious"), ("放松", "fàngsōng", "relaxed"),
        ("满意", "mǎnyì", "satisfied"), ("失望", "shīwàng", "disappointed"),
        ("激动", "jīdòng", "excited"), ("担心", "dānxīn", "worried"),
    ],
    "object": [
        ("手机", "shǒujī", "phone"), ("电脑", "diànnǎo", "computer"),
        ("书", "shū", "book"), ("自行车", "zìxíngchē", "bicycle"),
        ("衣服", "yīfu", "clothes"), ("钱包", "qiánbāo", "wallet"),
        ("钥匙", "yàoshi", "key"), ("雨伞", "yǔsǎn", "umbrella"),
        ("照相机", "zhàoxiàngjī", "camera"), ("行李箱", "xínglixiāng", "suitcase"),
        ("礼物", "lǐwù", "gift"), ("地图", "dìtú", "map"),
        ("药", "yào", "medicine"), ("眼镜", "yǎnjìng", "glasses"),
    ],
    "transport": [
        ("公共汽车", "gōnggòng qìchē", "bus"), ("地铁", "dìtiě", "subway"),
        ("出租车", "chūzūchē", "taxi"), ("飞机", "fēijī", "airplane"),
        ("火车", "huǒchē", "train"), ("自行车", "zìxíngchē", "bicycle"),
        ("走路", "zǒulù", "walk"), ("开车", "kāichē", "drive"),
    ],
    "color": [
        ("红色", "hóngsè", "red"), ("白色", "báisè", "white"),
        ("蓝色", "lánsè", "blue"), ("绿色", "lǜsè", "green"),
        ("黑色", "hēisè", "black"), ("黄色", "huángsè", "yellow"),
    ],
    "number_phrase": [
        ("一个", "yí gè", "one"), ("两个", "liǎng gè", "two"),
        ("三个", "sān gè", "three"), ("几个", "jǐ gè", "several"),
        ("很多", "hěn duō", "many"), ("一些", "yìxiē", "some"),
    ],
    "duration": [
        ("一个小时", "yí gè xiǎoshí", "one hour"),
        ("半个小时", "bàn gè xiǎoshí", "half an hour"),
        ("两个小时", "liǎng gè xiǎoshí", "two hours"),
        ("二十分钟", "èrshí fēnzhōng", "twenty minutes"),
        ("一天", "yì tiān", "one day"), ("一个星期", "yí gè xīngqī", "one week"),
        ("三天", "sān tiān", "three days"),
    ],
    "adjective": [
        ("好", "hǎo", "good"), ("大", "dà", "big"), ("小", "xiǎo", "small"),
        ("多", "duō", "many"), ("少", "shǎo", "few"), ("新", "xīn", "new"),
        ("旧", "jiù", "old"), ("远", "yuǎn", "far"), ("近", "jìn", "near"),
        ("快", "kuài", "fast"), ("慢", "màn", "slow"), ("贵", "guì", "expensive"),
        ("便宜", "piányi", "cheap"), ("干净", "gānjìng", "clean"),
        ("漂亮", "piàoliang", "beautiful"), ("方便", "fāngbiàn", "convenient"),
        ("重要", "zhòngyào", "important"), ("有意思", "yǒu yìsi", "interesting"),
        ("舒服", "shūfu", "comfortable"), ("安全", "ānquán", "safe"),
    ],
    "topic_abstract": [
        ("健康", "jiànkāng", "health"), ("环境", "huánjìng", "environment"),
        ("教育", "jiàoyù", "education"), ("文化", "wénhuà", "culture"),
        ("经济", "jīngjì", "economy"), ("科技", "kējì", "technology"),
        ("社会", "shèhuì", "society"), ("历史", "lìshǐ", "history"),
        ("传统", "chuántǒng", "tradition"), ("发展", "fāzhǎn", "development"),
        ("交通", "jiāotōng", "transportation"), ("生活", "shēnghuó", "life"),
    ],
}


# ---------------------------------------------------------------------------
# Genre templates — keyed by genre name.
# Each template has:
#   - title_pattern / title_en_pattern: for the title
#   - sentences: list of sentence templates with {slot} placeholders
#   - slots: mapping from slot name to word-bank category
#   - hsk_range: (min, max) HSK levels this template is appropriate for
#   - pinyin / english variants are built dynamically from chosen words
# ---------------------------------------------------------------------------

TEMPLATES = {
    "diary": [
        {
            "id": "diary_daily",
            "title_pattern": "{time}的日记",
            "title_en_pattern": "{time_en} Diary",
            "hsk_range": (1, 2),
            "slots": {"person": "person", "time": "time", "place": "place",
                       "activity": "activity", "food": "food", "emotion": "emotion"},
            "sentences": [
                "{time}，天气很好。",
                "{person}去了{place}。",
                "在那里，{person}{activity}了。",
                "中午吃了{food}，觉得很好吃。",
                "{person}今天很{emotion}。",
            ],
            "sentences_en": [
                "{time_en}, the weather was nice.",
                "{person_en} went to {place_en}.",
                "There, {person_en} {activity_en}.",
                "At noon, ate {food_en}, thought it was delicious.",
                "{person_en} was very {emotion_en} today.",
            ],
        },
        {
            "id": "diary_weekend",
            "title_pattern": "周末日记",
            "title_en_pattern": "Weekend Diary",
            "hsk_range": (1, 3),
            "slots": {"person": "person", "place": "place", "place2": "place",
                       "activity": "activity", "activity2": "activity",
                       "food": "food", "emotion": "emotion",
                       "duration": "duration"},
            "sentences": [
                "周末到了，{person}不用上班。",
                "上午{person}去了{place}，{activity}了{duration}。",
                "下午又去了{place2}。",
                "在{place2}{activity2}，觉得很{emotion}。",
                "晚上回家吃了{food}，这个周末过得很开心。",
            ],
            "sentences_en": [
                "The weekend arrived, {person_en} didn't have to work.",
                "In the morning, {person_en} went to {place_en} and {activity_en} for {duration_en}.",
                "In the afternoon, went to {place2_en} again.",
                "At {place2_en}, {activity2_en}, felt very {emotion_en}.",
                "In the evening, went home and ate {food_en}. This weekend was very happy.",
            ],
        },
        {
            "id": "diary_sick",
            "title_pattern": "生病的一天",
            "title_en_pattern": "A Sick Day",
            "hsk_range": (2, 3),
            "slots": {"person": "person", "emotion": "emotion", "food": "food"},
            "sentences": [
                "今天{person}不舒服，头很疼。",
                "{person}没有去上班，在家休息了一天。",
                "中午只喝了一碗{food}。",
                "下午睡了两个小时，觉得好了一点。",
                "晚上{person}很{emotion}，希望明天能好起来。",
            ],
            "sentences_en": [
                "Today {person_en} didn't feel well, had a headache.",
                "{person_en} didn't go to work, rested at home all day.",
                "At noon, only drank a bowl of {food_en}.",
                "In the afternoon, slept for two hours and felt a bit better.",
                "In the evening, {person_en} was very {emotion_en}, hoping to feel better tomorrow.",
            ],
        },
        {
            "id": "diary_travel",
            "title_pattern": "旅行日记",
            "title_en_pattern": "Travel Diary",
            "hsk_range": (3, 5),
            "slots": {"person": "person", "place": "place", "transport": "transport",
                       "activity": "activity", "food": "food", "emotion": "emotion",
                       "weather": "weather", "object": "object"},
            "sentences": [
                "今天是旅行的第一天，{person}坐{transport}到了{place}。",
                "到{place}的时候，天气{weather}。",
                "虽然有点累，但是{person}觉得很{emotion}。",
                "放下{object}以后，{person}就出去{activity}了。",
                "晚上在一家小饭店吃了当地的{food}，味道非常好。",
                "因为明天还有很多地方要去，所以{person}早早地睡了。",
            ],
            "sentences_en": [
                "Today was the first day of the trip. {person_en} took {transport_en} to {place_en}.",
                "When arriving at {place_en}, the weather was {weather_en}.",
                "Although a bit tired, {person_en} felt very {emotion_en}.",
                "After putting down {object_en}, {person_en} went out to {activity_en}.",
                "In the evening, ate local {food_en} at a small restaurant. The taste was excellent.",
                "Because there were many places to visit tomorrow, {person_en} went to sleep early.",
            ],
        },
        {
            "id": "diary_reflection",
            "title_pattern": "一年的回顾",
            "title_en_pattern": "Year in Review",
            "hsk_range": (4, 8),
            "slots": {"person": "person", "place": "place", "activity": "activity",
                       "topic": "topic_abstract", "emotion": "emotion", "emotion2": "emotion"},
            "sentences": [
                "今年过得很快，{person}回想起来，觉得收获很多。",
                "在{topic}方面，{person}有了很大的进步。",
                "特别是在{place}的那段经历，让{person}学到了很多。",
                "虽然中间也遇到了不少困难，有时候感到{emotion}，",
                "但是{person}没有放弃，一直坚持{activity}。",
                "现在回头看，那些困难反而变成了宝贵的经验。",
                "{person}对明年充满了期待，希望能继续成长。",
                "最重要的是，{person}学会了感恩，感到{emotion2}。",
            ],
            "sentences_en": [
                "This year passed quickly. Looking back, {person_en} gained a lot.",
                "In terms of {topic_en}, {person_en} made great progress.",
                "Especially the experience at {place_en}, which taught {person_en} a lot.",
                "Although there were quite a few difficulties along the way, sometimes feeling {emotion_en},",
                "but {person_en} didn't give up and kept {activity_en}.",
                "Now looking back, those difficulties became valuable experience.",
                "{person_en} is full of expectations for next year, hoping to keep growing.",
                "Most importantly, {person_en} learned to be grateful, feeling {emotion2_en}.",
            ],
        },
    ],

    "news_brief": [
        {
            "id": "news_weather",
            "title_pattern": "天气预报",
            "title_en_pattern": "Weather Forecast",
            "hsk_range": (1, 2),
            "slots": {"weather": "weather", "weather2": "weather"},
            "sentences": [
                "今天的天气{weather}。",
                "明天会{weather2}。",
                "请大家注意身体，多喝水。",
            ],
            "sentences_en": [
                "Today's weather is {weather_en}.",
                "Tomorrow it will be {weather2_en}.",
                "Please everyone take care of your health and drink more water.",
            ],
        },
        {
            "id": "news_event",
            "title_pattern": "{place}的新闻",
            "title_en_pattern": "News from {place_en}",
            "hsk_range": (2, 3),
            "slots": {"place": "place", "person": "person", "number": "number_phrase",
                       "activity": "activity"},
            "sentences": [
                "昨天在{place}发生了一件有意思的事。",
                "{number}人在那里{activity}。",
                "很多人来看，大家都觉得很有意思。",
                "一位{person}说：\"这是我第一次看到这样的事。\"",
            ],
            "sentences_en": [
                "Yesterday something interesting happened at {place_en}.",
                "{number_en} people {activity_en} there.",
                "Many people came to watch, everyone thought it was very interesting.",
                "A {person_en} said: 'This is the first time I've seen something like this.'",
            ],
        },
        {
            "id": "news_city",
            "title_pattern": "城市新变化",
            "title_en_pattern": "New Changes in the City",
            "hsk_range": (3, 5),
            "slots": {"place": "place", "place2": "place", "topic": "topic_abstract",
                       "adjective": "adjective"},
            "sentences": [
                "据报道，我们城市最近在{topic}方面有了新的变化。",
                "新的{place}已经建好了，下个月就会开放。",
                "市民们对此非常期待，因为以前的{place}太旧了。",
                "不仅如此，{place2}附近的交通也变得更{adjective}了。",
                "有关部门表示，这些变化会让市民的生活更方便。",
            ],
            "sentences_en": [
                "According to reports, our city has recently seen changes in {topic_en}.",
                "The new {place_en} has been completed and will open next month.",
                "Citizens are very excited, because the old {place_en} was too run-down.",
                "Not only that, the traffic near {place2_en} has also become more {adjective_en}.",
                "Authorities say these changes will make citizens' lives more convenient.",
            ],
        },
        {
            "id": "news_tech",
            "title_pattern": "科技新闻",
            "title_en_pattern": "Technology News",
            "hsk_range": (4, 8),
            "slots": {"topic": "topic_abstract", "person": "person", "adjective": "adjective"},
            "sentences": [
                "最近，{topic}领域出现了一项重要的新发展。",
                "专家们认为，这项技术将会改变人们的生活方式。",
                "虽然目前还在研究阶段，但是已经引起了广泛的关注。",
                "一位专家表示：\"这个发现非常{adjective}，意义重大。\"",
                "不过也有人担心，新技术可能会带来一些问题。",
                "无论如何，这个消息让很多人感到期待。",
            ],
            "sentences_en": [
                "Recently, an important new development has appeared in {topic_en}.",
                "Experts believe this technology will change people's lifestyles.",
                "Although still in the research stage, it has attracted wide attention.",
                "An expert said: 'This discovery is very {adjective_en} and significant.'",
                "However, some worry that new technology might bring some problems.",
                "In any case, this news made many people excited.",
            ],
        },
    ],

    "dialogue": [
        {
            "id": "dialogue_meeting",
            "title_pattern": "初次见面",
            "title_en_pattern": "First Meeting",
            "hsk_range": (1, 1),
            "slots": {"person": "person", "person2": "person", "place": "place",
                       "activity": "activity"},
            "sentences": [
                "A：你好！你叫什么名字？",
                "B：你好！我叫{person}。你呢？",
                "A：我叫{person2}。很高兴认识你！",
                "B：我也很高兴。你喜欢{activity}吗？",
                "A：喜欢！我们一起去{place}吧。",
            ],
            "sentences_en": [
                "A: Hello! What's your name?",
                "B: Hello! I'm {person_en}. And you?",
                "A: I'm {person2_en}. Nice to meet you!",
                "B: Nice to meet you too. Do you like to {activity_en}?",
                "A: Yes! Let's go to {place_en} together.",
            ],
        },
        {
            "id": "dialogue_shopping",
            "title_pattern": "在{place}",
            "title_en_pattern": "At the {place_en}",
            "hsk_range": (1, 2),
            "slots": {"place": "place", "object": "object", "color": "color",
                       "adjective": "adjective"},
            "sentences": [
                "A：你好，我想买一个{object}。",
                "B：好的，您想要什么颜色的？",
                "A：有{color}的吗？",
                "B：有的。您看这个怎么样？",
                "A：这个很{adjective}。多少钱？",
                "B：一百块钱。",
                "A：好的，我要这个。",
            ],
            "sentences_en": [
                "A: Hello, I'd like to buy a {object_en}.",
                "B: OK, what color would you like?",
                "A: Do you have {color_en}?",
                "B: Yes. What do you think of this one?",
                "A: This one is very {adjective_en}. How much?",
                "B: One hundred yuan.",
                "A: OK, I'll take this one.",
            ],
        },
        {
            "id": "dialogue_directions",
            "title_pattern": "问路",
            "title_en_pattern": "Asking for Directions",
            "hsk_range": (2, 3),
            "slots": {"person": "person", "place": "place", "transport": "transport",
                       "duration": "duration"},
            "sentences": [
                "A：请问，{place}怎么走？",
                "B：从这里往前走，然后往右拐。",
                "A：远不远？",
                "B：不太远，{transport}大概{duration}就到了。",
                "A：好的，谢谢你！",
                "B：不客气。",
            ],
            "sentences_en": [
                "A: Excuse me, how do I get to {place_en}?",
                "B: Go straight from here, then turn right.",
                "A: Is it far?",
                "B: Not too far, by {transport_en} it's about {duration_en}.",
                "A: OK, thank you!",
                "B: You're welcome.",
            ],
        },
        {
            "id": "dialogue_plan",
            "title_pattern": "周末的计划",
            "title_en_pattern": "Weekend Plans",
            "hsk_range": (2, 4),
            "slots": {"person": "person", "place": "place", "activity": "activity",
                       "activity2": "activity", "food": "food", "time": "time"},
            "sentences": [
                "A：{time}你有什么计划？",
                "B：我想去{place}{activity}。你想一起去吗？",
                "A：好啊！什么时候出发？",
                "B：上午十点怎么样？",
                "A：没问题。我们中午可以一起吃{food}。",
                "B：太好了！下午我们还可以{activity2}。",
                "A：听起来很不错，那就这么定了。",
            ],
            "sentences_en": [
                "A: What plans do you have for {time_en}?",
                "B: I want to go to {place_en} to {activity_en}. Want to come?",
                "A: Sure! When should we leave?",
                "B: How about 10 AM?",
                "A: No problem. We can eat {food_en} together at noon.",
                "B: Great! In the afternoon we can also {activity2_en}.",
                "A: Sounds great, then it's settled.",
            ],
        },
        {
            "id": "dialogue_advice",
            "title_pattern": "给朋友建议",
            "title_en_pattern": "Giving a Friend Advice",
            "hsk_range": (3, 5),
            "slots": {"person": "person", "topic": "topic_abstract",
                       "activity": "activity", "emotion": "emotion"},
            "sentences": [
                "A：最近我在{topic}方面遇到了一些困难。",
                "B：怎么了？跟我说说。",
                "A：我不知道应该怎么做，有点{emotion}。",
                "B：我觉得你可以先{activity}，慢慢来。",
                "A：可是我怕做不好。",
                "B：别担心，谁都是从不会到会的。",
                "A：你说得对。我会试试的，谢谢你。",
                "B：不用谢，有什么问题随时找我。",
            ],
            "sentences_en": [
                "A: Recently I've encountered some difficulties with {topic_en}.",
                "B: What happened? Tell me about it.",
                "A: I don't know what to do, feeling a bit {emotion_en}.",
                "B: I think you can start by {activity_en}, take it slow.",
                "A: But I'm afraid I won't do it well.",
                "B: Don't worry, everyone starts from not knowing.",
                "A: You're right. I'll give it a try, thank you.",
                "B: You're welcome, come to me anytime if you have questions.",
            ],
        },
    ],

    "letter": [
        {
            "id": "letter_friend",
            "title_pattern": "给朋友的信",
            "title_en_pattern": "Letter to a Friend",
            "hsk_range": (2, 3),
            "slots": {"person": "person", "place": "place", "activity": "activity",
                       "weather": "weather", "food": "food"},
            "sentences": [
                "亲爱的{person}：",
                "你好！好久不见，你最近怎么样？",
                "我现在在{place}，这里天气{weather}。",
                "每天我都{activity}，过得很开心。",
                "这里的{food}特别好吃，下次一定要带你来尝尝。",
                "你什么时候有时间？我们见个面吧！",
                "祝你一切顺利！",
            ],
            "sentences_en": [
                "Dear {person_en},",
                "Hello! Long time no see, how have you been?",
                "I'm now at {place_en}, the weather here is {weather_en}.",
                "Every day I {activity_en}, having a great time.",
                "The {food_en} here is especially delicious. Next time I'll bring you to try it.",
                "When are you free? Let's meet up!",
                "Wishing you all the best!",
            ],
        },
        {
            "id": "letter_thank",
            "title_pattern": "感谢信",
            "title_en_pattern": "Thank You Letter",
            "hsk_range": (3, 4),
            "slots": {"person": "person", "topic": "topic_abstract",
                       "emotion": "emotion", "activity": "activity"},
            "sentences": [
                "尊敬的{person}：",
                "您好！我写这封信是为了感谢您。",
                "在{topic}方面，您给了我很大的帮助。",
                "如果没有您的支持，我不可能取得这样的进步。",
                "每次遇到困难的时候，您都鼓励我继续{activity}。",
                "我真的非常感动，心里很{emotion}。",
                "希望以后有机会能报答您的帮助。",
                "再次感谢！祝您身体健康！",
            ],
            "sentences_en": [
                "Respected {person_en},",
                "Hello! I'm writing to thank you.",
                "In terms of {topic_en}, you have helped me greatly.",
                "Without your support, I couldn't have made such progress.",
                "Every time I encountered difficulties, you encouraged me to keep {activity_en}.",
                "I'm truly moved, feeling very {emotion_en}.",
                "I hope there will be a chance to repay your help in the future.",
                "Thank you again! Wishing you good health!",
            ],
        },
        {
            "id": "letter_formal",
            "title_pattern": "给公司的信",
            "title_en_pattern": "Letter to a Company",
            "hsk_range": (4, 8),
            "slots": {"person": "person", "topic": "topic_abstract",
                       "adjective": "adjective", "place": "place"},
            "sentences": [
                "尊敬的{person}：",
                "您好！我是一名对{topic}非常感兴趣的求职者。",
                "我在贵公司的网站上看到了招聘信息，所以写信来咨询。",
                "我曾经在{place}工作了三年，积累了丰富的经验。",
                "在工作中，我一直保持着认真{adjective}的态度。",
                "我相信自己能够胜任这个职位，为公司做出贡献。",
                "如果您方便的话，我希望能有一次面试的机会。",
                "期待您的回复。谢谢！",
            ],
            "sentences_en": [
                "Respected {person_en},",
                "Hello! I am a job seeker very interested in {topic_en}.",
                "I saw the recruitment information on your company's website, so I'm writing to inquire.",
                "I worked at {place_en} for three years and accumulated rich experience.",
                "At work, I always maintained a serious and {adjective_en} attitude.",
                "I believe I can fulfill this position and contribute to the company.",
                "If it's convenient for you, I hope to have an interview opportunity.",
                "Looking forward to your reply. Thank you!",
            ],
        },
    ],

    "description": [
        {
            "id": "desc_room",
            "title_pattern": "我的房间",
            "title_en_pattern": "My Room",
            "hsk_range": (1, 2),
            "slots": {"adjective": "adjective", "adjective2": "adjective",
                       "object": "object", "color": "color"},
            "sentences": [
                "我的房间不太大，但是很{adjective}。",
                "房间里有一张床、一张桌子和一把椅子。",
                "桌子上有一个{object}和几本书。",
                "窗户旁边有一个{color}的花。",
                "我很喜欢我的房间，觉得很{adjective2}。",
            ],
            "sentences_en": [
                "My room isn't very big, but it's very {adjective_en}.",
                "There's a bed, a desk, and a chair in the room.",
                "On the desk there's a {object_en} and some books.",
                "Next to the window there's a {color_en} flower.",
                "I really like my room, it feels very {adjective2_en}.",
            ],
        },
        {
            "id": "desc_person",
            "title_pattern": "我的好朋友",
            "title_en_pattern": "My Good Friend",
            "hsk_range": (1, 3),
            "slots": {"person": "person", "activity": "activity",
                       "activity2": "activity", "food": "food", "emotion": "emotion"},
            "sentences": [
                "我有一个好朋友叫{person}。",
                "{person}个子不高，眼睛大大的。",
                "{person}最喜欢{activity}，每天都会做。",
                "我们经常一起{activity2}。",
                "{person}最喜欢吃{food}。",
                "{person}是一个很{emotion}的人，大家都喜欢和{person}在一起。",
            ],
            "sentences_en": [
                "I have a good friend called {person_en}.",
                "{person_en} isn't very tall, with big eyes.",
                "{person_en} loves to {activity_en} most, does it every day.",
                "We often {activity2_en} together.",
                "{person_en}'s favorite food is {food_en}.",
                "{person_en} is a very {emotion_en} person; everyone likes being with {person_en}.",
            ],
        },
        {
            "id": "desc_city",
            "title_pattern": "我住的城市",
            "title_en_pattern": "The City I Live In",
            "hsk_range": (3, 5),
            "slots": {"place": "place", "place2": "place", "adjective": "adjective",
                       "food": "food", "weather": "weather", "activity": "activity",
                       "transport": "transport"},
            "sentences": [
                "我住的城市不算大，但是非常{adjective}。",
                "城市里有很多{place}，人们经常去那里。",
                "这里的交通比较方便，大家一般坐{transport}出行。",
                "说到美食，这里最有名的是{food}，很多游客都来尝。",
                "天气方面，夏天比较{weather}，冬天不太冷。",
                "我最喜欢去{place2}{activity}，那是我放松的方式。",
                "虽然这个城市不如大城市热闹，但是生活节奏很舒服。",
            ],
            "sentences_en": [
                "The city I live in isn't very big, but it's very {adjective_en}.",
                "There are many {place_en}s in the city; people often go there.",
                "Transportation here is convenient; people usually take {transport_en}.",
                "Speaking of food, the most famous here is {food_en}; many tourists come to try it.",
                "Weather-wise, summer is quite {weather_en}, winter isn't too cold.",
                "I like going to {place2_en} to {activity_en} most; that's how I relax.",
                "Although this city isn't as lively as big cities, the pace of life is comfortable.",
            ],
        },
        {
            "id": "desc_season",
            "title_pattern": "四季的变化",
            "title_en_pattern": "The Four Seasons",
            "hsk_range": (2, 4),
            "slots": {"activity": "activity", "activity2": "activity",
                       "food": "food", "place": "place"},
            "sentences": [
                "一年有四个季节：春天、夏天、秋天和冬天。",
                "春天天气暖和，公园里的花都开了。",
                "夏天很热，人们喜欢去{place}。",
                "秋天很凉快，树叶变成了黄色和红色。",
                "冬天很冷，大家喜欢在家里{activity}。",
                "我最喜欢的季节是秋天，因为可以{activity2}。",
            ],
            "sentences_en": [
                "There are four seasons in a year: spring, summer, autumn, and winter.",
                "Spring weather is warm; the flowers in the park are blooming.",
                "Summer is very hot; people like to go to {place_en}.",
                "Autumn is cool; the leaves turn yellow and red.",
                "Winter is very cold; everyone likes to {activity_en} at home.",
                "My favorite season is autumn, because you can {activity2_en}.",
            ],
        },
    ],

    "how_to": [
        {
            "id": "howto_cook",
            "title_pattern": "怎么做{food}",
            "title_en_pattern": "How to Make {food_en}",
            "hsk_range": (2, 3),
            "slots": {"food": "food", "duration": "duration"},
            "sentences": [
                "今天我来教大家怎么做{food}。",
                "首先，准备好需要的东西。",
                "然后，把它们洗干净。",
                "接下来，放在锅里煮{duration}。",
                "最后，放一点盐就好了。",
                "做{food}不难，大家试试吧！",
            ],
            "sentences_en": [
                "Today I'll teach everyone how to make {food_en}.",
                "First, prepare the needed ingredients.",
                "Then, wash them clean.",
                "Next, put them in a pot and cook for {duration_en}.",
                "Finally, add a little salt and you're done.",
                "Making {food_en} isn't hard. Everyone give it a try!",
            ],
        },
        {
            "id": "howto_learn",
            "title_pattern": "怎么学{topic}",
            "title_en_pattern": "How to Learn {topic_en}",
            "hsk_range": (3, 5),
            "slots": {"topic": "topic_abstract", "activity": "activity",
                       "duration": "duration", "adjective": "adjective"},
            "sentences": [
                "很多人问我怎么学好{topic}。",
                "我觉得最重要的是每天坚持练习。",
                "首先，每天至少花{duration}来{activity}。",
                "其次，要多看、多听、多说。",
                "另外，找一个好的学习环境也很{adjective}。",
                "如果遇到不懂的地方，不要害怕问别人。",
                "只要坚持，一定会有进步的。",
            ],
            "sentences_en": [
                "Many people ask me how to learn {topic_en} well.",
                "I think the most important thing is to practice every day.",
                "First, spend at least {duration_en} every day to {activity_en}.",
                "Second, read more, listen more, and speak more.",
                "Also, finding a good learning environment is very {adjective_en}.",
                "If you encounter something you don't understand, don't be afraid to ask others.",
                "As long as you persist, you'll definitely make progress.",
            ],
        },
        {
            "id": "howto_health",
            "title_pattern": "保持健康的方法",
            "title_en_pattern": "Ways to Stay Healthy",
            "hsk_range": (3, 5),
            "slots": {"activity": "activity", "food": "food", "duration": "duration"},
            "sentences": [
                "健康是最重要的。这里有几个保持健康的方法。",
                "第一，要每天运动。{activity}是一个很好的选择。",
                "第二，注意饮食，多吃{food}和蔬菜。",
                "第三，每天至少睡{duration}。",
                "第四，少看手机，让眼睛休息。",
                "第五，保持好的心情，不要给自己太大的压力。",
                "如果能做到这些，身体一定会越来越好。",
            ],
            "sentences_en": [
                "Health is the most important thing. Here are some ways to stay healthy.",
                "First, exercise every day. {activity_en} is a great choice.",
                "Second, watch your diet; eat more {food_en} and vegetables.",
                "Third, sleep at least {duration_en} every day.",
                "Fourth, use your phone less; let your eyes rest.",
                "Fifth, maintain a good mood; don't put too much pressure on yourself.",
                "If you can do these things, your health will definitely get better.",
            ],
        },
        {
            "id": "howto_travel",
            "title_pattern": "旅行准备指南",
            "title_en_pattern": "Travel Preparation Guide",
            "hsk_range": (4, 8),
            "slots": {"place": "place", "object": "object", "transport": "transport",
                       "duration": "duration"},
            "sentences": [
                "出发旅行之前，做好准备是非常重要的。",
                "首先，你需要提前预订{transport}的票。",
                "其次，准备好必要的物品，比如{object}和换洗的衣服。",
                "另外，最好提前了解目的地的天气情况。",
                "到了{place}以后，建议先去酒店放好行李。",
                "如果时间充足，可以花{duration}在附近逛一逛。",
                "记得带够现金和银行卡，以防万一。",
                "最后，保持好的心态，享受旅途中的每一刻。",
            ],
            "sentences_en": [
                "Before setting off on a trip, good preparation is very important.",
                "First, you need to book {transport_en} tickets in advance.",
                "Second, prepare necessary items like {object_en} and a change of clothes.",
                "Also, it's best to check the weather at the destination beforehand.",
                "After arriving at {place_en}, it's advisable to go to the hotel first to drop off luggage.",
                "If there's enough time, you can spend {duration_en} exploring the area.",
                "Remember to bring enough cash and bank cards, just in case.",
                "Finally, maintain a good attitude and enjoy every moment of the journey.",
            ],
        },
    ],

    "opinion": [
        {
            "id": "opinion_phone",
            "title_pattern": "手机的好处和坏处",
            "title_en_pattern": "Pros and Cons of Phones",
            "hsk_range": (2, 3),
            "slots": {"activity": "activity", "person": "person"},
            "sentences": [
                "现在很多人每天都用手机。",
                "手机可以帮我们做很多事，比如{activity}。",
                "但是用手机太多对身体不好。",
                "有的人看手机看到很晚，第二天很累。",
                "我觉得我们应该少用手机，多出去走走。",
            ],
            "sentences_en": [
                "Nowadays many people use their phones every day.",
                "Phones can help us do many things, like {activity_en}.",
                "But using phones too much is bad for health.",
                "Some people look at their phones until very late, and are tired the next day.",
                "I think we should use phones less and go outside more.",
            ],
        },
        {
            "id": "opinion_city_country",
            "title_pattern": "城市和农村",
            "title_en_pattern": "City vs. Countryside",
            "hsk_range": (3, 5),
            "slots": {"adjective": "adjective", "adjective2": "adjective",
                       "activity": "activity", "place": "place"},
            "sentences": [
                "有人喜欢住在城市，有人喜欢住在农村。",
                "城市的生活很方便，有很多{place}。",
                "但是城市空气不太{adjective}，而且人太多了。",
                "农村的环境比较{adjective2}，空气也好。",
                "不过农村的交通不太方便，买东西也不容易。",
                "我觉得最好是住在城市附近的小地方，",
                "这样既可以{activity}，又不会太吵闹。",
            ],
            "sentences_en": [
                "Some people like living in the city; others prefer the countryside.",
                "City life is convenient, with many {place_en}s.",
                "But city air isn't very {adjective_en}, and there are too many people.",
                "The countryside environment is more {adjective2_en}, and the air is better.",
                "However, countryside transportation isn't convenient, and shopping isn't easy.",
                "I think the best is to live in a small area near the city,",
                "so you can {activity_en}, and it won't be too noisy.",
            ],
        },
        {
            "id": "opinion_education",
            "title_pattern": "关于{topic}的看法",
            "title_en_pattern": "Views on {topic_en}",
            "hsk_range": (4, 8),
            "slots": {"topic": "topic_abstract", "adjective": "adjective",
                       "activity": "activity", "person": "person"},
            "sentences": [
                "关于{topic}，每个人都有不同的看法。",
                "有人认为{topic}对社会的发展非常{adjective}。",
                "他们觉得应该投入更多的时间和资源。",
                "但是也有人持不同的意见。",
                "他们认为现在的方式已经足够了。",
                "在我看来，两种观点各有道理。",
                "最重要的是，我们应该根据实际情况来做决定。",
                "只有这样，才能真正解决{topic}方面的问题。",
            ],
            "sentences_en": [
                "Regarding {topic_en}, everyone has different views.",
                "Some think {topic_en} is very {adjective_en} for social development.",
                "They feel more time and resources should be invested.",
                "But others hold different opinions.",
                "They think the current approach is sufficient.",
                "In my view, both perspectives have merit.",
                "Most importantly, we should make decisions based on actual circumstances.",
                "Only this way can we truly solve problems in {topic_en}.",
            ],
        },
    ],

    "story": [
        {
            "id": "story_lost",
            "title_pattern": "丢了{object}",
            "title_en_pattern": "Lost {object_en}",
            "hsk_range": (1, 2),
            "slots": {"person": "person", "object": "object", "place": "place",
                       "emotion": "emotion"},
            "sentences": [
                "{person}的{object}不见了。",
                "{person}很{emotion}，到处找。",
                "先去了{place}，没有找到。",
                "后来问了朋友，朋友说在桌子上看到了。",
                "{person}回去一看，{object}真的在那里！",
            ],
            "sentences_en": [
                "{person_en}'s {object_en} went missing.",
                "{person_en} was very {emotion_en} and looked everywhere.",
                "First went to {place_en}, didn't find it.",
                "Then asked a friend, who said they saw it on the table.",
                "{person_en} went back to check, and the {object_en} was really there!",
            ],
        },
        {
            "id": "story_rain",
            "title_pattern": "下雨天",
            "title_en_pattern": "Rainy Day",
            "hsk_range": (2, 3),
            "slots": {"person": "person", "place": "place", "person2": "person",
                       "food": "food", "emotion": "emotion"},
            "sentences": [
                "{person}今天出门没带伞，突然下起了大雨。",
                "{person}跑到{place}里躲雨。",
                "在那里遇到了{person2}，他们以前就认识。",
                "两个人一边等雨停，一边聊天。",
                "后来雨停了，他们一起去吃了{food}。",
                "虽然开始觉得不开心，但后来{person}觉得很{emotion}。",
            ],
            "sentences_en": [
                "{person_en} went out today without an umbrella, and suddenly it started raining heavily.",
                "{person_en} ran into {place_en} to take shelter.",
                "There, met {person2_en}; they had known each other before.",
                "The two chatted while waiting for the rain to stop.",
                "Later the rain stopped, and they went to eat {food_en} together.",
                "Although unhappy at first, {person_en} ended up feeling very {emotion_en}.",
            ],
        },
        {
            "id": "story_challenge",
            "title_pattern": "一次挑战",
            "title_en_pattern": "A Challenge",
            "hsk_range": (3, 5),
            "slots": {"person": "person", "activity": "activity", "emotion": "emotion",
                       "emotion2": "emotion", "place": "place", "person2": "person"},
            "sentences": [
                "{person}一直想学{activity}，但是觉得太难了。",
                "有一天，{person2}说：\"你一定可以的，我来教你。\"",
                "刚开始的时候，{person}觉得很{emotion}，什么都做不好。",
                "但是{person}没有放弃，每天都去{place}练习。",
                "一个月以后，{person}终于学会了。",
                "{person}非常{emotion2}，明白了一个道理：",
                "只要不放弃，没有做不到的事情。",
            ],
            "sentences_en": [
                "{person_en} always wanted to learn {activity_en}, but thought it was too hard.",
                "One day, {person2_en} said: 'You can do it. I'll teach you.'",
                "In the beginning, {person_en} felt very {emotion_en} and couldn't do anything well.",
                "But {person_en} didn't give up and went to {place_en} to practice every day.",
                "After one month, {person_en} finally learned it.",
                "{person_en} was very {emotion2_en} and understood a lesson:",
                "As long as you don't give up, there's nothing you can't achieve.",
            ],
        },
        {
            "id": "story_misunderstanding",
            "title_pattern": "一场误会",
            "title_en_pattern": "A Misunderstanding",
            "hsk_range": (4, 8),
            "slots": {"person": "person", "person2": "person", "place": "place",
                       "object": "object", "emotion": "emotion", "emotion2": "emotion"},
            "sentences": [
                "{person}和{person2}是多年的好朋友。",
                "有一天，{person}发现自己的{object}不见了。",
                "后来听说{person2}最近去过{person}的{place}。",
                "{person}心里开始怀疑{person2}，觉得很{emotion}。",
                "两个人因为这件事好几天没有说话。",
                "后来{person}在家里的角落找到了{object}。",
                "{person}感到非常后悔，马上去向{person2}道歉。",
                "{person2}笑着说：\"没关系，朋友之间最重要的是信任。\"",
                "从那以后，{person}学会了不轻易怀疑别人，心里很{emotion2}。",
            ],
            "sentences_en": [
                "{person_en} and {person2_en} had been good friends for many years.",
                "One day, {person_en} discovered that their {object_en} was missing.",
                "Later heard that {person2_en} had recently visited {person_en}'s {place_en}.",
                "{person_en} started to suspect {person2_en}, feeling very {emotion_en}.",
                "The two didn't speak for several days because of this.",
                "Later {person_en} found the {object_en} in a corner at home.",
                "{person_en} felt very regretful and immediately went to apologize to {person2_en}.",
                "{person2_en} smiled and said: 'It's OK, trust is most important between friends.'",
                "From then on, {person_en} learned not to easily suspect others, feeling very {emotion2_en}.",
            ],
        },
        {
            "id": "story_journey",
            "title_pattern": "一段旅程的启示",
            "title_en_pattern": "Lessons from a Journey",
            "hsk_range": (5, 9),
            "slots": {"person": "person", "place": "place", "transport": "transport",
                       "emotion": "emotion", "emotion2": "emotion", "topic": "topic_abstract",
                       "activity": "activity"},
            "sentences": [
                "多年以来，{person}一直过着平淡的生活，直到那次旅行改变了一切。",
                "那年秋天，{person}独自乘{transport}前往{place}。",
                "一路上，{person}遇到了各种各样的人，听到了许多不同的故事。",
                "有一位老人告诉{person}：\"人生最宝贵的不是金钱，而是经历。\"",
                "这句话让{person}深受触动，开始重新思考自己的{topic}。",
                "在{place}的那段日子里，{person}每天{activity}，过得非常充实。",
                "虽然过程中也有{emotion}的时候，但收获远大于付出。",
                "回来以后，{person}的整个人都变了，朋友们都注意到了这个变化。",
                "{person}常常对别人说：\"有机会一定要出去走走看看。\"",
                "因为正是那段旅程，让{person}明白了什么是真正{emotion2}的生活。",
            ],
            "sentences_en": [
                "For many years, {person_en} lived an ordinary life, until that trip changed everything.",
                "That autumn, {person_en} traveled alone by {transport_en} to {place_en}.",
                "Along the way, {person_en} met all kinds of people and heard many different stories.",
                "An old man told {person_en}: 'The most precious thing in life isn't money, but experience.'",
                "This deeply moved {person_en}, who began rethinking their own {topic_en}.",
                "During those days in {place_en}, {person_en} {activity_en} every day, living a very fulfilling life.",
                "Although there were {emotion_en} moments, the gains far outweighed the costs.",
                "After returning, {person_en}'s whole demeanor changed; friends all noticed the difference.",
                "{person_en} often tells others: 'If you get the chance, definitely go out and explore.'",
                "Because it was that journey that taught {person_en} what a truly {emotion2_en} life means.",
            ],
        },
    ],

    "essay": [
        {
            "id": "essay_society",
            "title_pattern": "论{topic}的意义",
            "title_en_pattern": "On the Significance of {topic_en}",
            "hsk_range": (6, 9),
            "slots": {"topic": "topic_abstract", "topic2": "topic_abstract",
                       "adjective": "adjective", "emotion": "emotion",
                       "person": "person", "place": "place",
                       "activity": "activity"},
            "sentences": [
                "当今社会，{topic}已经成为人们广泛关注的话题。",
                "从某种程度上来说，一个国家的{topic}水平反映了其整体发展状况。",
                "然而，我们不得不承认，在这一领域仍然存在着不少挑战。",
                "首先，许多人对{topic}的认识还停留在比较浅显的层面。",
                "其次，现有的制度和政策在推动{topic}发展方面还有很大的改善空间。",
                "值得注意的是，{topic2}与{topic}之间存在着密不可分的联系。",
                "要想从根本上解决这些问题，就需要社会各界的共同努力。",
                "政府应当制定更加{adjective}的政策，为{topic}的发展提供有力的保障。",
                "与此同时，每个公民也应当提高自身的意识，积极参与其中。",
                "正如一位学者所言：\"只有全社会共同关注，{topic}才能真正得到改善。\"",
                "展望未来，我们有理由相信，通过持续的努力，情况一定会越来越好。",
                "让我们携手并进，为建设一个更加美好的社会贡献自己的力量。",
            ],
            "sentences_en": [
                "In today's society, {topic_en} has become a widely discussed topic.",
                "To a certain extent, a country's level of {topic_en} reflects its overall development.",
                "However, we must acknowledge that there are still many challenges in this field.",
                "First, many people's understanding of {topic_en} remains at a superficial level.",
                "Second, existing systems and policies have much room for improvement in promoting {topic_en}.",
                "It is worth noting that {topic2_en} and {topic_en} are inextricably linked.",
                "To fundamentally solve these problems requires joint effort from all sectors of society.",
                "The government should formulate more {adjective_en} policies to provide strong support for {topic_en}.",
                "At the same time, every citizen should raise their awareness and actively participate.",
                "As one scholar said: 'Only when the whole society pays attention can {topic_en} truly improve.'",
                "Looking ahead, we have reason to believe that through sustained effort, things will get better.",
                "Let us join hands and contribute to building a better society.",
            ],
        },
        {
            "id": "essay_tradition",
            "title_pattern": "{topic}与现代化",
            "title_en_pattern": "{topic_en} and Modernization",
            "hsk_range": (7, 9),
            "slots": {"topic": "topic_abstract", "topic2": "topic_abstract",
                       "place": "place", "emotion": "emotion",
                       "adjective": "adjective", "person": "person"},
            "sentences": [
                "在全球化浪潮的冲击下，如何平衡{topic}与现代化成为了一个关键议题。",
                "一方面，现代化为社会带来了前所未有的便利和效率；",
                "另一方面，传统的{topic}正面临着被边缘化甚至消失的风险。",
                "以{place}为例，当地独特的文化遗产曾经是居民引以为傲的精神财富。",
                "然而随着城市化进程的加快，许多宝贵的传统正在逐渐流失。",
                "有学者指出，{topic}并非与现代化水火不容，两者之间可以找到平衡点。",
                "关键在于我们能否以一种{adjective}的方式来传承和创新。",
                "例如，利用现代{topic2}的手段来保护和传播传统文化，就是一种值得推广的做法。",
                "在这个过程中，年轻一代的参与至关重要。",
                "他们既是传统的继承者，也是创新的推动者。",
                "只有当整个社会都认识到这一点，{topic}的保护才能取得实质性的进展。",
                "最终，一个既拥有现代文明又保留丰富传统的社会，才是我们共同追求的理想。",
            ],
            "sentences_en": [
                "Under the impact of globalization, how to balance {topic_en} and modernization has become a key issue.",
                "On one hand, modernization has brought unprecedented convenience and efficiency to society;",
                "on the other hand, traditional {topic_en} faces the risk of being marginalized or even disappearing.",
                "Take {place_en} for example: the local unique cultural heritage was once a spiritual treasure residents were proud of.",
                "However, with accelerating urbanization, many precious traditions are gradually being lost.",
                "Scholars point out that {topic_en} is not incompatible with modernization; a balance can be found.",
                "The key lies in whether we can carry on tradition and innovate in a {adjective_en} way.",
                "For example, using modern {topic2_en} methods to protect and disseminate traditional culture is a practice worth promoting.",
                "In this process, the participation of the younger generation is crucial.",
                "They are both inheritors of tradition and drivers of innovation.",
                "Only when the whole society recognizes this can the protection of {topic_en} make substantive progress.",
                "Ultimately, a society that possesses both modern civilization and rich traditions is the ideal we all pursue.",
            ],
        },
        {
            "id": "essay_personal",
            "title_pattern": "回忆与成长",
            "title_en_pattern": "Memories and Growth",
            "hsk_range": (6, 8),
            "slots": {"person": "person", "place": "place", "activity": "activity",
                       "emotion": "emotion", "emotion2": "emotion",
                       "topic": "topic_abstract", "food": "food"},
            "sentences": [
                "人的一生中，总有一些经历会在记忆深处留下不可磨灭的痕迹。",
                "对{person}来说，那段在{place}度过的时光便是如此。",
                "那时候的生活虽然简朴，却充满了温暖和希望。",
                "每天清晨，{person}都会早起{activity}，这个习惯一直保持至今。",
                "邻居们淳朴善良，经常互相帮助，分享自家做的{food}。",
                "正是这种人与人之间的真诚，让{person}学会了什么是{emotion}。",
                "随着年龄的增长，{person}逐渐离开了那个熟悉的地方，踏上了新的旅程。",
                "在外面的世界里，{person}遇到了更多的挑战，也收获了更多的成长。",
                "关于{topic}，{person}有了更加深刻的理解。",
                "如今再回想起来，那些看似平凡的日子其实塑造了{person}的整个人生观。",
                "正如一句老话所说：\"不忘初心，方得始终。\"",
                "{person}心中始终怀着那份{emotion2}，继续前行。",
            ],
            "sentences_en": [
                "In one's life, certain experiences leave indelible marks deep in memory.",
                "For {person_en}, the time spent at {place_en} was exactly that.",
                "Although life was simple then, it was full of warmth and hope.",
                "Every morning, {person_en} would wake up early to {activity_en} — a habit maintained to this day.",
                "The neighbors were kind and honest, often helping each other and sharing homemade {food_en}.",
                "It was this sincere connection between people that taught {person_en} what {emotion_en} truly means.",
                "As the years passed, {person_en} gradually left that familiar place and embarked on a new journey.",
                "In the outside world, {person_en} encountered more challenges and gained more growth.",
                "Regarding {topic_en}, {person_en} developed a much deeper understanding.",
                "Looking back now, those seemingly ordinary days actually shaped {person_en}'s entire outlook on life.",
                "As the old saying goes: 'Stay true to your original aspiration, and you will achieve your goals.'",
                "{person_en} carries that sense of {emotion2_en} in their heart and continues moving forward.",
            ],
        },
    ],
}

GENRES = list(TEMPLATES.keys())


# ---------------------------------------------------------------------------
# Slot filler — picks words from the bank, respecting HSK level
# ---------------------------------------------------------------------------

def pick_word(bank_name, used, rng):
    """Pick a random word from a bank, avoiding recent duplicates."""
    bank = WORD_BANKS.get(bank_name, [])
    if not bank:
        return ("???", "???", "???")
    # Try to avoid duplicates within a passage
    available = [w for w in bank if w[0] not in used]
    if not available:
        available = bank
    choice = rng.choice(available)
    used.add(choice[0])
    return choice


class _SafeDict(dict):
    """Dict subclass that returns the key placeholder for missing keys."""
    def __missing__(self, key):
        return "{" + key + "}"


def fill_template(template, rng):
    """Fill a template's slots and return passage data dict."""
    slot_defs = template["slots"]
    used = set()
    filled = {}  # slot_name -> (hanzi, pinyin, english)

    for slot_name, bank_name in slot_defs.items():
        word = pick_word(bank_name, used, rng)
        filled[slot_name] = word

    # Build substitution dicts — every slot gets both base and _en keys
    zh_subs = _SafeDict()
    en_subs = _SafeDict()
    pinyin_subs = _SafeDict()
    vocab_items = []
    for slot_name, (hanzi, pinyin, english) in filled.items():
        zh_subs[slot_name] = hanzi
        zh_subs[slot_name + "_en"] = english
        en_subs[slot_name] = english
        en_subs[slot_name + "_en"] = english
        pinyin_subs[slot_name] = pinyin
        pinyin_subs[slot_name + "_en"] = english
        if hanzi not in ("我", "他", "她", "???"):
            vocab_items.append(hanzi)

    # Fill sentence templates (format_map tolerates missing keys via _SafeDict)
    sentences_zh = [s.format_map(zh_subs) for s in template["sentences"]]
    sentences_en = [s.format_map(en_subs) for s in template.get("sentences_en", [])]

    # Fill title
    title_zh = template["title_pattern"].format_map(zh_subs)
    title_en = template["title_en_pattern"].format_map(en_subs)
    title_pinyin = template["title_pattern"].format_map(pinyin_subs)

    return {
        "title_zh": title_zh,
        "title_en": title_en,
        "title_pinyin": title_pinyin,
        "text_zh": "".join(sentences_zh),
        "text_en": " ".join(sentences_en),
        "vocab_items": list(set(vocab_items)),
        "filled": filled,
    }


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------

QUESTION_TYPES = ["main_idea", "detail", "inference", "vocab_context", "true_false"]


def generate_questions(passage_data, genre, template, rng):
    """Generate 3-5 comprehension questions for a filled passage."""
    filled = passage_data["filled"]
    questions = []

    # 1. Main idea question — always included
    genre_labels = {
        "diary": ("日记", "diary entry"),
        "news_brief": ("新闻", "news brief"),
        "dialogue": ("对话", "dialogue"),
        "letter": ("信", "letter"),
        "description": ("描写", "description"),
        "how_to": ("指南", "how-to guide"),
        "opinion": ("看法", "opinion piece"),
        "story": ("故事", "story"),
        "essay": ("文章", "essay"),
    }
    zh_label, en_label = genre_labels.get(genre, ("文章", "passage"))
    questions.append({
        "type": "main_idea",
        "q_zh": f"这篇{zh_label}主要说了什么？",
        "q_en": f"What is this {en_label} mainly about?",
        "answer": passage_data["title_en"],
    })

    # 2. Detail questions based on filled slots
    slot_questions = {
        "person": ("这篇文章提到了谁？", "Who is mentioned in this passage?"),
        "place": ("文章提到了什么地方？", "What place is mentioned?"),
        "time": ("这件事是什么时候发生的？", "When did this happen?"),
        "food": ("文章提到了什么食物？", "What food is mentioned?"),
        "object": ("文章提到了什么东西？", "What object is mentioned?"),
        "activity": ("文章里的人做了什么？", "What did the person do?"),
        "weather": ("天气怎么样？", "What was the weather like?"),
        "emotion": ("文章里的人感觉怎么样？", "How did the person feel?"),
        "transport": ("他们坐什么去的？", "How did they travel?"),
    }

    detail_slots = [s for s in filled if s in slot_questions]
    rng.shuffle(detail_slots)
    for slot_name in detail_slots[:2]:
        q_zh, q_en = slot_questions[slot_name]
        hanzi, pinyin, english = filled[slot_name]
        questions.append({
            "type": "detail",
            "q_zh": q_zh,
            "q_en": q_en,
            "answer": f"{hanzi} ({english})",
        })

    # 3. Vocab context question — if we have vocab items
    if passage_data["vocab_items"]:
        target = rng.choice(passage_data["vocab_items"])
        # Find the english meaning
        target_en = ""
        for slot_name, (hanzi, pinyin, english) in filled.items():
            if hanzi == target:
                target_en = english
                break
        if target_en:
            questions.append({
                "type": "vocab_context",
                "q_zh": f"在这篇文章里，\"{target}\"是什么意思？",
                "q_en": f"In this passage, what does \"{target}\" mean?",
                "answer": target_en,
            })

    # 4. True/false question
    if filled:
        # Pick a slot and make a true statement
        tf_slot = rng.choice(list(filled.keys()))
        hanzi, pinyin, english = filled[tf_slot]
        questions.append({
            "type": "true_false",
            "q_zh": f"文章里提到了\"{hanzi}\"。对不对？",
            "q_en": f"The passage mentions \"{hanzi}\" ({english}). True or false?",
            "answer": "True",
        })

    # 5. Inference question (for HSK 3+)
    inference_prompts = {
        "diary": ("从这篇日记可以看出，作者今天过得怎么样？",
                  "From this diary entry, how was the author's day?"),
        "news_brief": ("根据这则新闻，你觉得接下来会怎么样？",
                       "Based on this news, what do you think will happen next?"),
        "dialogue": ("从对话中可以看出，两个人的关系怎么样？",
                     "From the dialogue, what is the relationship between the two people?"),
        "letter": ("写信的人为什么写这封信？",
                   "Why did the writer write this letter?"),
        "description": ("作者对描写的对象是什么态度？",
                        "What is the author's attitude toward the subject?"),
        "how_to": ("这篇文章最重要的建议是什么？",
                   "What is the most important advice in this passage?"),
        "opinion": ("作者的主要观点是什么？",
                    "What is the author's main opinion?"),
        "story": ("这个故事想告诉我们什么道理？",
                  "What lesson does this story teach us?"),
        "essay": ("作者在这篇文章中想表达什么核心观点？",
                  "What is the core viewpoint the author expresses in this essay?"),
    }
    if genre in inference_prompts:
        q_zh, q_en = inference_prompts[genre]
        questions.append({
            "type": "inference",
            "q_zh": q_zh,
            "q_en": q_en,
            "answer": passage_data["title_en"],
        })

    # Add difficulty and MC options to each question
    hsk = passage_data.get("hsk_level", 1)
    for i, q in enumerate(questions):
        # Difficulty scales with question type and position
        base_diff = {"main_idea": 0.2, "detail": 0.3, "vocab_context": 0.4,
                     "true_false": 0.3, "inference": 0.6}
        q["difficulty"] = round(base_diff.get(q["type"], 0.3) + (hsk - 1) * 0.05, 2)

        # Generate MC options
        correct = q["answer"]
        if q["type"] == "true_false":
            q["options"] = [
                {"text": "对", "pinyin": "duì", "text_en": "True", "correct": True},
                {"text": "不对", "pinyin": "bú duì", "text_en": "False", "correct": False},
            ]
        else:
            # Build distractor options from other filled slots or generic
            distractors = []
            for slot_name, (hanzi, pinyin, english) in filled.items():
                d_text = f"{hanzi} ({english})"
                if d_text != correct and d_text not in distractors:
                    distractors.append(d_text)
            # Pad with generic distractors if needed
            generic = ["不知道 (unknown)", "没有 (none)", "其他 (other)"]
            for g in generic:
                if g not in distractors and g != correct:
                    distractors.append(g)
            rng.shuffle(distractors)
            opts = [{"text": correct.split(" (")[0] if " (" in correct else correct,
                     "pinyin": "", "text_en": correct, "correct": True}]
            for d in distractors[:3]:
                opts.append({"text": d.split(" (")[0] if " (" in d else d,
                            "pinyin": "", "text_en": d, "correct": False})
            rng.shuffle(opts)
            q["options"] = opts

    return questions[:5]  # Cap at 5


# ---------------------------------------------------------------------------
# Passage generator
# ---------------------------------------------------------------------------

def select_hsk_level(template, target_level):
    """Return the actual HSK level to assign, clamped to template range."""
    lo, hi = template["hsk_range"]
    return max(lo, min(hi, target_level))


def generate_passages(levels, count_per_level, genre_filter, seed=None):
    """Generate passages for each requested HSK level."""
    rng = random.Random(seed if seed is not None else 42)
    passages = []

    for level in levels:
        # Gather eligible templates
        eligible = []
        for genre, tmpls in TEMPLATES.items():
            if genre_filter and genre != genre_filter:
                continue
            for tmpl in tmpls:
                lo, hi = tmpl["hsk_range"]
                if lo <= level <= hi:
                    eligible.append((genre, tmpl))

        if not eligible:
            print(f"Warning: no templates available for HSK {level}"
                  f"{' genre=' + genre_filter if genre_filter else ''}",
                  file=sys.stderr)
            continue

        for i in range(count_per_level):
            genre, tmpl = rng.choice(eligible)
            data = fill_template(tmpl, rng)
            passage_num = str(i + 1).zfill(3)
            passage_id = f"gen_{level}_{genre}_{passage_num}"

            questions = generate_questions(data, genre, tmpl, rng)

            passage = {
                "id": passage_id,
                "hsk_level": level,
                "genre": genre,
                "title": data["title_en"],
                "title_zh": data["title_zh"],
                "text_zh": data["text_zh"],
                "text_pinyin": "",  # Pinyin generation would need a full dict; left empty
                "text_en": data["text_en"],
                "vocab_items": data["vocab_items"],
                "questions": questions,
            }
            passages.append(passage)

    return passages


# ---------------------------------------------------------------------------
# Merge with existing file
# ---------------------------------------------------------------------------

def load_existing(path):
    """Load existing passages file or return empty structure."""
    if not os.path.exists(path):
        return {
            "source": "generated by tools/generate_passages.py",
            "description": "HSK-graded reading passages with comprehension questions",
            "passages": [],
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_passages(existing_data, new_passages):
    """Merge new passages, skipping duplicates by ID."""
    existing_ids = {p["id"] for p in existing_data["passages"]}
    added = 0
    skipped = 0
    for p in new_passages:
        if p["id"] in existing_ids:
            skipped += 1
        else:
            existing_data["passages"].append(p)
            existing_ids.add(p["id"])
            added += 1
    return added, skipped


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_hsk_range(value):
    """Parse '3' or '1-5' into a list of levels."""
    if "-" in value:
        parts = value.split("-", 1)
        lo, hi = int(parts[0]), int(parts[1])
        if lo < 1 or hi > 9 or lo > hi:
            raise argparse.ArgumentTypeError(
                f"Invalid HSK range: {value} (must be 1-9)")
        return list(range(lo, hi + 1))
    else:
        lvl = int(value)
        if lvl < 1 or lvl > 9:
            raise argparse.ArgumentTypeError(
                f"Invalid HSK level: {value} (must be 1-9)")
        return [lvl]


def main():
    parser = argparse.ArgumentParser(
        description="Generate graded reading passages for Mandarin learning")
    parser.add_argument("--hsk", type=parse_hsk_range, default=[1, 2, 3],
                        help="HSK level(s): single number or range like 1-3 (default: 1-3)")
    parser.add_argument("--count", type=int, default=100,
                        help="Passages per level (default: 100)")
    parser.add_argument("--genre", type=str, default=None, choices=GENRES,
                        help="Filter to a specific genre")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT),
                        help=f"Output file (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be generated without writing")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    args = parser.parse_args()

    levels = args.hsk
    print(f"Generating passages for HSK levels: {levels}")
    print(f"Count per level: {args.count}")
    if args.genre:
        print(f"Genre filter: {args.genre}")
    print(f"Output: {args.output}")
    print()

    # Generate
    new_passages = generate_passages(
        levels, args.count, args.genre, seed=args.seed)

    # Summary by level and genre
    by_level = {}
    by_genre = {}
    for p in new_passages:
        lvl = p["hsk_level"]
        by_level[lvl] = by_level.get(lvl, 0) + 1
        genre = p.get("genre", "unknown")
        by_genre[genre] = by_genre.get(genre, 0) + 1

    print(f"Generated {len(new_passages)} new passages:")
    for lvl in sorted(by_level):
        print(f"  HSK {lvl}: {by_level[lvl]}")
    print(f"By genre:")
    for genre in sorted(by_genre):
        print(f"  {genre}: {by_genre[genre]}")
    print()

    if args.dry_run:
        # Show a few samples
        print("--- Sample passages (first 3) ---")
        for p in new_passages[:3]:
            print(f"\n[{p['id']}] HSK {p['hsk_level']} — {p['title']}")
            print(f"  ZH: {p['text_zh'][:120]}...")
            print(f"  EN: {p['text_en'][:120]}...")
            print(f"  Vocab: {p['vocab_items']}")
            print(f"  Questions: {len(p['questions'])}")
            for q in p["questions"]:
                print(f"    [{q['type']}] {q['q_en']}")
        print("\nDry run complete. No file written.")
        return

    # Load existing and merge
    existing = load_existing(args.output)
    added, skipped = merge_passages(existing, new_passages)

    print(f"Merged: {added} added, {skipped} duplicates skipped")
    print(f"Total passages in file: {len(existing['passages'])}")

    # Write
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
