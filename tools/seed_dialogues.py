#!/usr/bin/env python3
"""Seed dialogue_scenario table with ~240 new scenarios across HSK 1-9."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from mandarin.db.core import ensure_db, connection


def _tree(setup, setup_zh, turns, note=""):
    """Build tree_json from compact turn definitions."""
    return json.dumps({
        "setup": setup,
        "setup_zh": setup_zh,
        "turns": turns,
        "cultural_note": note,
    }, ensure_ascii=False)


def npc(zh, py, en):
    return {"speaker": "npc", "text_zh": zh, "text_pinyin": py, "text_en": en}


def player(prompt, opts):
    return {
        "speaker": "player",
        "prompt_en": prompt,
        "options": [
            {"text_zh": o[0], "score": o[1], "register": o[2], "feedback": o[3]}
            for o in opts
        ],
    }


def S(title, title_zh, hsk, reg, diff, setup, setup_zh, turns, note=""):
    """Return a scenario dict."""
    return {
        "title": title, "title_zh": title_zh, "hsk_level": hsk,
        "register": reg, "difficulty": diff,
        "tree_json": _tree(setup, setup_zh, turns, note),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HSK 1 — 23 new scenarios
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HSK1 = [
    S("Greeting a classmate", "和同学打招呼", 1, "casual", 0.2,
      "You see a classmate in the hallway.", "你在走廊看到一个同学。",
      [npc("你好！你今天怎么样？", "nǐ hǎo! nǐ jīntiān zěnmeyàng?", "Hi! How are you today?"),
       player("Say you're fine and ask back.", [
           ("我很好，谢谢！你呢？", 1.0, "neutral", "Perfect — natural and polite."),
           ("好。你呢？", 0.6, "casual", "A bit short — adding 很好 sounds more natural."),
           ("我好。", 0.4, "blunt", "Too minimal — ask them back with 你呢."),
       ]),
       npc("我也很好！你去哪儿？", "wǒ yě hěn hǎo! nǐ qù nǎr?", "I'm good too! Where are you going?"),
       player("Say you're going to class.", [
           ("我去上课。", 1.0, "neutral", "Clear and natural."),
           ("上课。", 0.6, "casual", "Works but adding 我去 is more complete."),
           ("我去学校。", 0.5, "neutral", "You're already at school — 上课 is more accurate here."),
       ])],
      "你呢 is the most common way to return a question in Chinese conversation."),

    S("Ordering tea", "点茶", 1, "neutral", 0.2,
      "You're at a café and want tea.", "你在咖啡店想喝茶。",
      [npc("你好，想喝什么？", "nǐ hǎo, xiǎng hē shénme?", "Hello, what would you like to drink?"),
       player("Order green tea.", [
           ("我想要一杯绿茶，谢谢。", 1.0, "neutral", "Great — polite and clear with measure word."),
           ("绿茶。", 0.5, "blunt", "Understood but too brief for a café."),
           ("给我茶。", 0.4, "blunt", "给我 sounds demanding. Use 我想要 or 请给我."),
       ]),
       npc("好的。大杯还是小杯？", "hǎo de. dà bēi háishi xiǎo bēi?", "OK. Large or small?"),
       player("Say small.", [
           ("小杯，谢谢。", 1.0, "neutral", "Perfect."),
           ("小的。", 0.7, "casual", "Fine, but echoing 小杯 is more natural here."),
           ("小。", 0.5, "blunt", "Too terse — add 杯 or 的."),
       ])],
      "还是 is used for 'or' in questions offering a choice between options."),

    S("Asking someone's age", "问年龄", 1, "casual", 0.2,
      "You're chatting with a new friend.", "你和一个新朋友聊天。",
      [npc("你是学生吗？", "nǐ shì xuésheng ma?", "Are you a student?"),
       player("Say yes and ask how old they are.", [
           ("是的，我是学生。你今年多大？", 1.0, "neutral", "Natural — 多大 is the right age question for peers."),
           ("是。你几岁？", 0.5, "casual", "几岁 is for children — use 多大 for adults."),
           ("对。", 0.3, "blunt", "Too short — continue the conversation."),
       ]),
       npc("我二十三岁。你呢？", "wǒ èrshísān suì. nǐ ne?", "I'm 23. You?"),
       player("Say you're 25.", [
           ("我二十五岁。", 1.0, "neutral", "Clear and correct."),
           ("二十五。", 0.7, "casual", "Fine, but adding 岁 is more complete."),
           ("我二五岁。", 0.3, "neutral", "Need full number: 二十五, not 二五."),
       ])],
      "几岁 is for children under ~10. 多大 is for peers. 多大年纪 is polite for elders."),

    S("Buying a book", "买书", 1, "neutral", 0.3,
      "You're at a bookstore.", "你在书店。",
      [npc("你想买什么书？", "nǐ xiǎng mǎi shénme shū?", "What book do you want to buy?"),
       player("Ask if they have Chinese textbooks.", [
           ("你们有中文课本吗？", 1.0, "neutral", "Perfect question with 你们 for the store."),
           ("有中文书吗？", 0.7, "casual", "Good but 课本 specifies textbook."),
           ("中文书。", 0.4, "blunt", "Not a question — rephrase with 有…吗."),
       ]),
       npc("有！这本很好。三十块钱。", "yǒu! zhè běn hěn hǎo. sānshí kuài qián.", "Yes! This one is great. 30 yuan."),
       player("Say it's a bit expensive and ask if there's a cheaper one.", [
           ("有点儿贵。有便宜一点的吗？", 1.0, "neutral", "Natural haggling phrasing."),
           ("太贵了！", 0.5, "blunt", "A bit aggressive. 有点儿贵 is softer."),
           ("便宜的？", 0.4, "blunt", "Incomplete — phrase as a full question."),
       ])],
      "块 is the spoken form of 元 (yuan). 有点儿 softens a complaint."),

    S("At the hospital reception", "在医院挂号", 1, "neutral", 0.3,
      "You need to register at a hospital.", "你需要在医院挂号。",
      [npc("你好，哪里不舒服？", "nǐ hǎo, nǎlǐ bù shūfu?", "Hello, what's bothering you?"),
       player("Say your head hurts.", [
           ("我头疼。", 1.0, "neutral", "Direct and clear."),
           ("头不舒服。", 0.7, "neutral", "Also works — slightly less specific."),
           ("疼。", 0.3, "blunt", "Need to specify where — 头疼, 肚子疼, etc."),
       ]),
       npc("好的，请先挂号。你带身份证了吗？", "hǎo de, qǐng xiān guàhào. nǐ dài shēnfènzhèng le ma?", "OK, please register first. Did you bring your ID?"),
       player("Say yes, you brought it.", [
           ("带了，在这儿。", 1.0, "neutral", "Natural with 了 confirming completion."),
           ("有。", 0.5, "casual", "Works but 带了 directly answers 带…了吗."),
           ("是。", 0.3, "neutral", "是 doesn't fit — answer with 带了."),
       ])],
      "Chinese hospitals require registration (挂号) before seeing a doctor."),

    S("Calling a friend", "给朋友打电话", 1, "casual", 0.2,
      "You call a friend to make plans.", "你给朋友打电话。",
      [npc("喂？你好！", "wèi? nǐ hǎo!", "Hello?"),
       player("Say hi and ask what they're doing.", [
           ("你好！你在做什么？", 1.0, "casual", "Natural phone opener."),
           ("你好。忙吗？", 0.7, "casual", "Also natural — asking if they're busy."),
           ("你好。", 0.4, "neutral", "Need to say why you're calling."),
       ]),
       npc("我在看电视。你想出去玩儿吗？", "wǒ zài kàn diànshì. nǐ xiǎng chūqù wánr ma?", "I'm watching TV. Want to go out?"),
       player("Say yes and suggest going to eat.", [
           ("好啊！我们去吃饭吧！", 1.0, "casual", "Enthusiastic and natural with 吧 for suggestion."),
           ("好。去哪儿？", 0.7, "casual", "Fine, but make a suggestion."),
           ("可以。", 0.5, "neutral", "A bit flat — show some enthusiasm."),
       ])],
      "喂 (wèi) is the standard phone greeting in Chinese."),

    S("Shopping for clothes", "买衣服", 1, "neutral", 0.3,
      "You're at a clothing shop.", "你在服装店。",
      [npc("你好，看看什么？", "nǐ hǎo, kànkan shénme?", "Hi, looking for anything?"),
       player("Say you want to buy a shirt.", [
           ("我想买一件衬衫。", 1.0, "neutral", "Clear with correct measure word 件."),
           ("我要买衣服。", 0.7, "neutral", "OK but 衬衫 is more specific than 衣服."),
           ("衬衫。", 0.5, "blunt", "Too brief — add 我想买."),
       ]),
       npc("你喜欢什么颜色？", "nǐ xǐhuan shénme yánsè?", "What color do you like?"),
       player("Say you like blue.", [
           ("我喜欢蓝色的。", 1.0, "neutral", "Perfect with 的 for 'a blue one.'"),
           ("蓝色。", 0.7, "casual", "Fine but adding 我喜欢 is more conversational."),
           ("蓝。", 0.4, "blunt", "Use the full form 蓝色."),
       ])],
      "件 is the measure word for upper-body clothing; 条 is for pants and skirts."),

    S("At the post office", "在邮局", 1, "neutral", 0.3,
      "You need to mail a package.", "你需要寄一个包裹。",
      [npc("你好，寄什么？", "nǐ hǎo, jì shénme?", "Hello, what are you mailing?"),
       player("Say you want to mail a package to the US.", [
           ("我想寄一个包裹到美国。", 1.0, "neutral", "Complete and clear."),
           ("寄到美国。", 0.6, "casual", "Missing what you're mailing."),
           ("美国，包裹。", 0.4, "blunt", "Rephrase as a sentence."),
       ]),
       npc("好的。要快递还是普通邮件？", "hǎo de. yào kuàidì háishi pǔtōng yóujiàn?", "OK. Express or regular mail?"),
       player("Ask how long regular mail takes.", [
           ("普通邮件要多长时间？", 1.0, "neutral", "Natural question."),
           ("多长时间？", 0.6, "casual", "Works but clarify which option."),
           ("多少天？", 0.5, "casual", "OK but 多长时间 is more standard phrasing."),
       ])],
      "Chinese post offices handle packages, bills, and banking services."),

    S("Checking in at a hotel", "酒店入住", 1, "neutral", 0.3,
      "You arrive at your hotel.", "你到了酒店。",
      [npc("你好，请问有预订吗？", "nǐ hǎo, qǐngwèn yǒu yùdìng ma?", "Hello, do you have a reservation?"),
       player("Say yes, under your name.", [
           ("有，我姓王。", 1.0, "neutral", "Clear — using 姓 for surname."),
           ("有预订。", 0.6, "neutral", "Good but give your name too."),
           ("是。", 0.4, "neutral", "Too vague — confirm and provide your name."),
       ]),
       npc("好的，王先生。住几天？", "hǎo de, Wáng xiānsheng. zhù jǐ tiān?", "OK, Mr. Wang. How many nights?"),
       player("Say three nights.", [
           ("住三天。", 1.0, "neutral", "Direct and clear."),
           ("三天。", 0.7, "casual", "Fine in context."),
           ("三个晚上。", 0.6, "neutral", "Understood, but 三天 is the standard hotel phrasing."),
       ])],
      "Hotels in China often ask 住几天 (how many days) rather than 'nights.'"),

    S("Asking about pets", "聊宠物", 1, "casual", 0.2,
      "Your neighbor has a cute dog.", "你邻居有一只可爱的狗。",
      [npc("你看，这是我的狗！", "nǐ kàn, zhè shì wǒ de gǒu!", "Look, this is my dog!"),
       player("Say it's cute and ask its name.", [
           ("好可爱！它叫什么名字？", 1.0, "casual", "Enthusiastic and natural."),
           ("很可爱。叫什么？", 0.7, "casual", "OK but 它叫什么名字 is more complete."),
           ("是狗。", 0.2, "blunt", "Obviously — engage with the conversation."),
       ]),
       npc("它叫豆豆。你喜欢狗吗？", "tā jiào Dòudou. nǐ xǐhuan gǒu ma?", "Its name is Doudou. Do you like dogs?"),
       player("Say you like dogs a lot.", [
           ("我很喜欢狗！", 1.0, "casual", "Natural emphasis with 很."),
           ("喜欢。", 0.6, "casual", "Fine but a bit flat."),
           ("我也想要一只。", 0.8, "casual", "Great — shows enthusiasm and uses 只 correctly."),
       ])],
      "豆豆 (Dòudou, 'bean bean') is one of the most popular pet names in China."),

    S("Talking about hobbies", "聊爱好", 1, "casual", 0.2,
      "A new acquaintance asks about your hobbies.", "一个新认识的人问你的爱好。",
      [npc("你平时喜欢做什么？", "nǐ píngshí xǐhuan zuò shénme?", "What do you like to do in your free time?"),
       player("Say you like reading.", [
           ("我喜欢看书。", 1.0, "neutral", "Natural — 看书 is the common way to say 'read.'"),
           ("看书。", 0.6, "casual", "OK but adding 我喜欢 is more conversational."),
           ("我喜欢读书。", 0.9, "neutral", "Also correct — 读书 is slightly more formal than 看书."),
       ]),
       npc("你喜欢看什么书？", "nǐ xǐhuan kàn shénme shū?", "What kind of books do you like?"),
       player("Say you like novels.", [
           ("我喜欢看小说。", 1.0, "neutral", "Clear and natural."),
           ("小说。", 0.6, "casual", "Fine in casual chat."),
           ("什么书都看。", 0.8, "casual", "Good natural response — 'I read all kinds.'"),
       ])],
      "Chinese distinguishes 看书 (casual reading) from 读书 (study/read aloud)."),

    S("Getting a taxi", "打车", 1, "neutral", 0.3,
      "You need a taxi to the train station.", "你需要坐出租车去火车站。",
      [npc("去哪儿？", "qù nǎr?", "Where to?"),
       player("Say the train station.", [
           ("请去火车站。", 1.0, "neutral", "Polite with 请."),
           ("火车站。", 0.7, "casual", "Works but a bit curt."),
           ("去火车站，快一点。", 0.5, "blunt", "快一点 sounds pushy without context."),
       ]),
       npc("好的。大概二十分钟。", "hǎo de. dàgài èrshí fēnzhōng.", "OK. About 20 minutes."),
       player("Ask how much it costs.", [
           ("大概多少钱？", 1.0, "neutral", "Natural with 大概 for approximate."),
           ("多少钱？", 0.8, "neutral", "Direct and fine."),
           ("贵不贵？", 0.5, "casual", "Vague — asking the price directly is better."),
       ])],
      "In China, taxi drivers often estimate time rather than distance."),

    S("Ordering noodles", "点面条", 1, "casual", 0.3,
      "You're at a noodle shop.", "你在面馆。",
      [npc("吃什么面？", "chī shénme miàn?", "What noodles would you like?"),
       player("Order beef noodles.", [
           ("来一碗牛肉面。", 1.0, "casual", "Natural — 来 is common when ordering."),
           ("我要牛肉面。", 0.8, "neutral", "Also good."),
           ("牛肉面。", 0.6, "casual", "Works but 来一碗 is more natural."),
       ]),
       npc("要不要辣的？", "yào bu yào là de?", "Do you want it spicy?"),
       player("Say a little spicy.", [
           ("微辣，谢谢。", 1.0, "neutral", "Perfect — 微辣 means 'mildly spicy.'"),
           ("一点点辣。", 0.7, "casual", "Understood, but 微辣 is the standard term."),
           ("不要太辣。", 0.8, "neutral", "Good — 'not too spicy' is also natural."),
       ])],
      "来一碗 literally means 'bring a bowl' — very common when ordering at casual eateries."),

    S("At the bank", "在银行", 1, "neutral", 0.3,
      "You need to exchange money.", "你需要换钱。",
      [npc("你好，办什么业务？", "nǐ hǎo, bàn shénme yèwù?", "Hello, what can I help you with?"),
       player("Say you want to exchange dollars for yuan.", [
           ("我想换钱，美元换人民币。", 1.0, "neutral", "Complete and clear."),
           ("换钱。", 0.5, "blunt", "Specify which currencies."),
           ("我要人民币。", 0.4, "neutral", "Unclear — specify you're exchanging."),
       ]),
       npc("好的，换多少？", "hǎo de, huàn duōshao?", "OK, how much?"),
       player("Say 500 dollars.", [
           ("五百美元。", 1.0, "neutral", "Clear and precise."),
           ("五百块。", 0.5, "casual", "Ambiguous — 块 could mean yuan. Say 美元."),
           ("五百。", 0.6, "casual", "OK in context but specifying 美元 is clearer."),
       ])],
      "人民币 (RMB) is China's currency; 块 is the spoken unit, 元 is formal."),

    S("Lost and asking for help", "迷路了", 1, "neutral", 0.3,
      "You're lost and approach a stranger.", "你迷路了，找一个人问路。",
      [npc("你好，需要帮忙吗？", "nǐ hǎo, xūyào bāngmáng ma?", "Hi, do you need help?"),
       player("Say you're looking for a subway station.", [
           ("请问，地铁站在哪儿？", 1.0, "neutral", "Polite with 请问 and correct question form."),
           ("地铁站在哪儿？", 0.7, "neutral", "Fine but adding 请问 is more polite."),
           ("地铁？", 0.4, "blunt", "Too vague — ask a full question."),
       ]),
       npc("往前走，然后右转。", "wǎng qián zǒu, ránhòu yòu zhuǎn.", "Go straight, then turn right."),
       player("Thank them.", [
           ("谢谢你！", 1.0, "neutral", "Warm and natural."),
           ("谢谢。", 0.8, "neutral", "Good."),
           ("好。", 0.4, "blunt", "Say thank you — they helped you."),
       ])],
      "请问 before a question is the polite way to approach strangers in Chinese."),

    S("Renting a bike", "租自行车", 1, "neutral", 0.3,
      "You want to rent a shared bike.", "你想租一辆共享单车。",
      [npc("你好，第一次用吗？", "nǐ hǎo, dì yī cì yòng ma?", "Hi, is this your first time using it?"),
       player("Say yes and ask how to use it.", [
           ("是的，怎么用？", 1.0, "neutral", "Direct and natural."),
           ("对，教我。", 0.5, "casual", "教我 is a bit blunt — 怎么用 is smoother."),
           ("是。", 0.3, "blunt", "Ask how to use it."),
       ]),
       npc("扫这个码就可以了。一小时一块钱。", "sǎo zhè ge mǎ jiù kěyǐ le. yì xiǎoshí yí kuài qián.", "Just scan this code. One yuan per hour."),
       player("Say OK and thank them.", [
           ("好的，谢谢！", 1.0, "neutral", "Perfect."),
           ("太方便了！谢谢。", 0.9, "casual", "Great — shows appreciation."),
           ("好。", 0.5, "blunt", "Add a thank you."),
       ])],
      "Shared bikes in China use QR codes — 扫码 (scan code) is an everyday action."),

    S("Introducing family members", "介绍家人", 1, "casual", 0.2,
      "You're showing a friend photos on your phone.", "你给朋友看手机上的照片。",
      [npc("这是谁？", "zhè shì shéi?", "Who's this?"),
       player("Introduce your mom.", [
           ("这是我妈妈。", 1.0, "casual", "Natural and clear."),
           ("我妈妈。", 0.7, "casual", "Fine but 这是 makes it a full sentence."),
           ("妈妈。", 0.5, "casual", "Too brief — add 这是我."),
       ]),
       npc("她看起来很年轻！你爸爸呢？", "tā kàn qǐlai hěn niánqīng! nǐ bàba ne?", "She looks young! What about your dad?"),
       player("Say your dad is the one on the right.", [
           ("我爸爸在右边那个。", 1.0, "casual", "Clear spatial reference."),
           ("右边的是我爸爸。", 0.9, "casual", "Also natural, slightly more formal structure."),
           ("那个。", 0.3, "blunt", "Need to specify which one."),
       ])],
      "Chinese families often use 妈妈/爸爸 in casual speech, 母亲/父亲 in formal contexts."),

    S("Asking about food", "问食物", 1, "casual", 0.2,
      "You're at a friend's house and they offer food.", "你在朋友家，他们请你吃东西。",
      [npc("你想吃什么？我们有饺子和米饭。", "nǐ xiǎng chī shénme? wǒmen yǒu jiǎozi hé mǐfàn.", "What do you want to eat? We have dumplings and rice."),
       player("Say you want to try the dumplings.", [
           ("我想吃饺子！", 1.0, "casual", "Enthusiastic and clear."),
           ("饺子吧。", 0.7, "casual", "Fine — 吧 makes it a soft choice."),
           ("都可以。", 0.5, "neutral", "Polite but non-committal. Making a choice is better."),
       ]),
       npc("好！你能吃辣吗？", "hǎo! nǐ néng chī là ma?", "Great! Can you eat spicy food?"),
       player("Say you can eat a little spicy.", [
           ("我可以吃一点辣的。", 1.0, "neutral", "Measured and clear."),
           ("能吃一点点。", 0.8, "casual", "Good — 一点点 emphasizes 'just a little.'"),
           ("不怕辣！", 0.7, "casual", "Bold! 不怕辣 means 'not afraid of spicy.'"),
       ])],
      "In Chinese hospitality, hosts always offer food. Accepting enthusiastically is polite."),

    S("Weather small talk", "聊天气", 1, "casual", 0.2,
      "You're chatting with a colleague at lunch.", "你和同事在午休聊天。",
      [npc("今天好热啊！", "jīntiān hǎo rè a!", "It's so hot today!"),
       player("Agree and say tomorrow will also be hot.", [
           ("是啊，明天也会很热。", 1.0, "casual", "Natural agreement with 是啊."),
           ("对，太热了。", 0.8, "casual", "Good agreement."),
           ("热。", 0.3, "blunt", "One word isn't a conversation."),
       ]),
       npc("你喜欢夏天还是冬天？", "nǐ xǐhuan xiàtiān háishi dōngtiān?", "Do you prefer summer or winter?"),
       player("Say you prefer winter.", [
           ("我更喜欢冬天。", 1.0, "neutral", "更 for comparison is natural."),
           ("冬天。", 0.6, "casual", "Fine but adding 我更喜欢 is better."),
           ("我喜欢冬天，不热。", 0.8, "casual", "Good — adds a reason."),
       ])],
      "是啊 is one of the most common ways to agree in casual Chinese."),

    S("Saying goodbye", "告别", 1, "casual", 0.2,
      "You're leaving a friend's house after dinner.", "你吃完晚饭要离开朋友家。",
      [npc("你现在要走了吗？", "nǐ xiànzài yào zǒu le ma?", "Are you leaving now?"),
       player("Say yes, it's getting late.", [
           ("是的，太晚了。谢谢你的晚饭！", 1.0, "casual", "Polite — thanks for dinner."),
           ("对，我要回家了。", 0.8, "casual", "Natural with 了 for change of state."),
           ("走了。", 0.4, "blunt", "Thank them for dinner."),
       ]),
       npc("好的，路上小心！", "hǎo de, lùshang xiǎoxīn!", "OK, be careful on the way!"),
       player("Say goodbye.", [
           ("好的，再见！下次再来！", 1.0, "casual", "Warm goodbye with promise to return."),
           ("再见！", 0.7, "neutral", "Standard goodbye."),
           ("拜拜！", 0.7, "casual", "Casual — fine among friends."),
       ])],
      "路上小心 ('be careful on the road') is a standard Chinese farewell phrase."),

    S("Counting items", "数东西", 1, "neutral", 0.2,
      "You're buying apples at a fruit stand.", "你在水果摊买苹果。",
      [npc("苹果五块钱一斤。", "píngguǒ wǔ kuài qián yì jīn.", "Apples are 5 yuan per jin."),
       player("Ask for two jin.", [
           ("我要两斤。", 1.0, "neutral", "Correct — 两 not 二 before measure words."),
           ("给我二斤。", 0.5, "casual", "Use 两 not 二 before 斤."),
           ("两个。", 0.4, "casual", "个 is wrong — use 斤 for weight."),
       ]),
       npc("两斤，一共十块。", "liǎng jīn, yígòng shí kuài.", "Two jin, 10 yuan total."),
       player("Pay and say thanks.", [
           ("好的，给你。谢谢！", 1.0, "neutral", "Natural transaction."),
           ("十块。", 0.5, "neutral", "Just confirming the price — say thanks."),
           ("谢谢。", 0.7, "neutral", "Good, but 给你 when handing over money is natural."),
       ])],
      "一斤 (jīn) = 500 grams. Always use 两 (not 二) before measure words."),

    S("Talking about school", "聊学校", 1, "casual", 0.2,
      "You meet someone at a party.", "你在派对上认识一个新人。",
      [npc("你在哪儿上学？", "nǐ zài nǎr shàngxué?", "Where do you go to school?"),
       player("Name your university.", [
           ("我在北京大学上学。", 1.0, "neutral", "Full and clear."),
           ("北京大学。", 0.7, "casual", "Fine in casual context."),
           ("大学。", 0.3, "blunt", "Which university? Be specific."),
       ]),
       npc("你学什么专业？", "nǐ xué shénme zhuānyè?", "What's your major?"),
       player("Say you study Chinese.", [
           ("我学中文。", 1.0, "neutral", "Clear and natural."),
           ("中文。", 0.6, "casual", "OK but a full sentence is more engaging."),
           ("我的专业是中文。", 0.8, "neutral", "Slightly formal but correct."),
       ])],
      "学什么专业 is the standard way to ask about someone's major or field of study."),

    S("Complimenting someone", "夸人", 1, "casual", 0.2,
      "Your friend is wearing a nice outfit.", "你朋友穿了一件好看的衣服。",
      [npc("你觉得我今天穿的怎么样？", "nǐ juéde wǒ jīntiān chuān de zěnmeyàng?", "What do you think of what I'm wearing today?"),
       player("Say it looks great.", [
           ("很好看！这件衣服很适合你。", 1.0, "casual", "Warm compliment with 适合."),
           ("好看。", 0.6, "casual", "OK but a bit flat."),
           ("不错。", 0.5, "neutral", "Lukewarm — 好看 is warmer."),
       ]),
       npc("谢谢！我昨天刚买的。", "xièxie! wǒ zuótiān gāng mǎi de.", "Thanks! I just bought it yesterday."),
       player("Ask where they bought it.", [
           ("在哪儿买的？", 1.0, "casual", "Natural follow-up."),
           ("哪里买的？", 0.9, "casual", "Also natural — 哪里 and 哪儿 both work."),
           ("多少钱？", 0.5, "casual", "Asking the price of someone's clothes can be awkward."),
       ])],
      "在哪儿买的 is a very common follow-up question when complimenting purchases."),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HSK 2 — 21 new scenarios
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HSK2 = [
    S("Making weekend plans", "周末计划", 2, "casual", 0.4,
      "You and a friend are deciding what to do this weekend.", "你和朋友决定周末做什么。",
      [npc("这个周末你有什么计划？", "zhè ge zhōumò nǐ yǒu shénme jìhuà?", "Any plans this weekend?"),
       player("Say you don't have plans and suggest going hiking.", [
           ("还没有。我们去爬山怎么样？", 1.0, "casual", "Great — suggestion with 怎么样."),
           ("没有计划。你呢？", 0.6, "casual", "Fine but passive — make a suggestion."),
           ("没有。", 0.4, "blunt", "Engage more — suggest something."),
       ]),
       npc("好啊！可是天气预报说周六会下雨。", "hǎo a! kěshì tiānqì yùbào shuō zhōuliù huì xià yǔ.", "Sure! But the forecast says it'll rain Saturday."),
       player("Suggest going Sunday instead.", [
           ("那我们周日去吧，周日应该晴天。", 1.0, "casual", "Good alternative plan."),
           ("那周日去？", 0.7, "casual", "OK but 吧 makes suggestions softer."),
           ("那不去了。", 0.4, "casual", "Don't give up — suggest an alternative."),
       ])],
      "怎么样 at the end of a suggestion means 'how about it?' — very common in Chinese."),

    S("At the gym", "在健身房", 2, "casual", 0.4,
      "You meet someone at the gym.", "你在健身房遇到一个人。",
      [npc("你经常来这儿锻炼吗？", "nǐ jīngcháng lái zhèr duànliàn ma?", "Do you come here to exercise often?"),
       player("Say you come three times a week.", [
           ("我一个星期来三次。", 1.0, "neutral", "Clear frequency expression."),
           ("经常来。", 0.6, "casual", "Vague — being specific is better."),
           ("差不多每天。", 0.7, "casual", "差不多 (almost) every day — natural if true."),
       ]),
       npc("你一般做什么运动？", "nǐ yìbān zuò shénme yùndòng?", "What do you usually do for exercise?"),
       player("Say you like running and swimming.", [
           ("我喜欢跑步，有时候也游泳。", 1.0, "casual", "Natural with 有时候 for variety."),
           ("跑步和游泳。", 0.7, "casual", "Fine but a full sentence is better."),
           ("什么都做。", 0.5, "casual", "Too vague."),
       ])],
      "一个星期…次 is the standard pattern for expressing weekly frequency."),

    S("Discussing a movie", "讨论电影", 2, "casual", 0.4,
      "You just watched a movie with a friend.", "你刚和朋友看完一个电影。",
      [npc("你觉得这个电影怎么样？", "nǐ juéde zhè ge diànyǐng zěnmeyàng?", "What did you think of the movie?"),
       player("Say it was pretty good but a bit long.", [
           ("挺好看的，不过有点儿长。", 1.0, "casual", "Balanced opinion with 不过."),
           ("不错，就是太长了。", 0.8, "casual", "Also natural — 就是 introduces a minor complaint."),
           ("还行。", 0.5, "casual", "Non-committal — say more."),
       ]),
       npc("我觉得演员演得很好。", "wǒ juéde yǎnyuán yǎn de hěn hǎo.", "I think the actors performed well."),
       player("Agree and say the story was interesting.", [
           ("对，而且故事也很有意思。", 1.0, "casual", "Good — 而且 adds to their point."),
           ("嗯，故事不错。", 0.7, "casual", "OK but less engaged."),
           ("是。", 0.4, "blunt", "Add your own opinion."),
       ])],
      "挺…的 is a casual way to say 'quite' or 'pretty' — very common in spoken Chinese."),

    S("Returning a call", "回电话", 2, "neutral", 0.4,
      "You missed a call and are calling back.", "你错过了一个电话，现在回拨。",
      [npc("喂？", "wèi?", "Hello?"),
       player("Say you're returning their call.", [
           ("你好，我刚才看到你的未接来电。", 1.0, "neutral", "Clear and explains why you're calling."),
           ("你好，你刚打电话给我了？", 0.8, "neutral", "Also fine — confirming they called."),
           ("你打电话了？", 0.5, "casual", "A bit abrupt — add context."),
       ]),
       npc("哦对！我想问你明天的会议几点开始。", "ó duì! wǒ xiǎng wèn nǐ míngtiān de huìyì jǐ diǎn kāishǐ.", "Oh right! I wanted to ask what time tomorrow's meeting starts."),
       player("Say the meeting is at 9 AM.", [
           ("明天上午九点开始。", 1.0, "neutral", "Clear and precise."),
           ("九点。", 0.6, "casual", "Works but specifying 上午 avoids ambiguity."),
           ("明天九点吧。", 0.5, "casual", "吧 implies uncertainty — be confident."),
       ])],
      "未接来电 means 'missed call' — useful modern vocabulary."),

    S("Visiting a temple", "参观寺庙", 2, "neutral", 0.4,
      "You're visiting a temple and ask about entry.", "你参观寺庙，问入口。",
      [npc("你好，你是来参观的吗？", "nǐ hǎo, nǐ shì lái cānguān de ma?", "Hello, are you here to visit?"),
       player("Say yes and ask about the ticket price.", [
           ("是的。请问门票多少钱？", 1.0, "neutral", "Polite and direct."),
           ("对。要买票吗？", 0.7, "neutral", "Also reasonable."),
           ("要钱吗？", 0.4, "blunt", "要钱 sounds like you're asking if they want your money. Use 门票."),
       ]),
       npc("门票二十块。学生半价。", "ménpiào èrshí kuài. xuésheng bànjià.", "Tickets are 20 yuan. Half price for students."),
       player("Say you're a student and show your ID.", [
           ("我是学生，这是我的学生证。", 1.0, "neutral", "Perfect — provides proof."),
           ("学生票一张。", 0.7, "neutral", "Clear but showing ID proactively is better."),
           ("我是学生。", 0.6, "neutral", "They'll ask for proof anyway — offer it."),
       ])],
      "Many Chinese attractions offer 学生半价 (student half-price) with valid student ID."),

    S("Asking for WiFi", "问WiFi密码", 2, "casual", 0.3,
      "You're at a café and need WiFi.", "你在咖啡店需要用WiFi。",
      [npc("你好，需要什么？", "nǐ hǎo, xūyào shénme?", "Hi, what do you need?"),
       player("Ask for the WiFi password.", [
           ("请问WiFi密码是什么？", 1.0, "neutral", "Clear and polite."),
           ("WiFi密码是什么？", 0.7, "casual", "Fine but adding 请问 is more polite."),
           ("有WiFi吗？", 0.5, "casual", "They probably have it — ask for the password."),
       ]),
       npc("密码在收据上。你要先点一杯饮料。", "mìmǎ zài shōujù shang. nǐ yào xiān diǎn yì bēi yǐnliào.", "The password is on the receipt. You need to order a drink first."),
       player("Order a coffee.", [
           ("好的，我要一杯美式咖啡。", 1.0, "neutral", "Clear order with specific drink."),
           ("给我一杯咖啡。", 0.6, "casual", "OK but 给我 is a bit direct."),
           ("最便宜的。", 0.4, "blunt", "Awkward — just order normally."),
       ])],
      "Many Chinese cafés require a purchase for WiFi access."),

    S("Talking about food preferences", "聊饮食习惯", 2, "casual", 0.4,
      "A friend is planning a dinner party.", "朋友在计划一个晚餐聚会。",
      [npc("你有什么不吃的吗？", "nǐ yǒu shénme bù chī de ma?", "Is there anything you don't eat?"),
       player("Say you don't eat seafood.", [
           ("我不吃海鲜，其他都可以。", 1.0, "neutral", "Clear with 其他都可以 (everything else is fine)."),
           ("不吃海鲜。", 0.6, "casual", "OK but 我 and 其他都可以 is more helpful."),
           ("没有。", 0.4, "blunt", "If true, say 什么都能吃. Otherwise be honest."),
       ]),
       npc("好的，那我做一个红烧肉和两个青菜。", "hǎo de, nà wǒ zuò yí ge hóngshāoròu hé liǎng ge qīngcài.", "OK, I'll make braised pork and two vegetable dishes."),
       player("Offer to bring something.", [
           ("我带一个水果沙拉过来吧。", 1.0, "casual", "Helpful offer with 吧."),
           ("我带什么？", 0.7, "casual", "Good — asking what to bring."),
           ("好的。", 0.5, "neutral", "Offering to bring something is more considerate."),
       ])],
      "Chinese dinner parties are often potluck-style. Offering to bring food is appreciated."),

    S("Getting a haircut", "剪头发", 2, "neutral", 0.4,
      "You're at a barber shop.", "你在理发店。",
      [npc("你想剪什么样的？", "nǐ xiǎng jiǎn shénme yàng de?", "What style would you like?"),
       player("Say shorter on the sides, a bit longer on top.", [
           ("两边短一点，上面留长一点。", 1.0, "neutral", "Clear and specific."),
           ("短一点就好。", 0.6, "casual", "Vague — specify where."),
           ("随便。", 0.3, "casual", "Too vague for a haircut you care about."),
       ]),
       npc("要不要洗头？", "yào bu yào xǐ tóu?", "Want a hair wash?"),
       player("Say yes.", [
           ("好的，洗一下吧。", 1.0, "neutral", "Natural with 吧."),
           ("要。", 0.6, "casual", "Functional but terse."),
           ("不用。", 0.7, "neutral", "Fine if you don't want it."),
       ])],
      "Chinese barbershops usually offer a hair wash (洗头) as part of the service."),

    S("Asking about schedule", "问时间安排", 2, "neutral", 0.4,
      "You need to find out when a shop closes.", "你想知道商店几点关门。",
      [npc("你好，有什么可以帮你的？", "nǐ hǎo, yǒu shénme kěyǐ bāng nǐ de?", "Hello, how can I help?"),
       player("Ask what time they close today.", [
           ("请问你们今天几点关门？", 1.0, "neutral", "Polite and specific."),
           ("几点关门？", 0.7, "casual", "OK but 请问 and 今天 add politeness and clarity."),
           ("你们还开吗？", 0.4, "casual", "They're clearly open — ask about closing time."),
       ]),
       npc("我们晚上九点关门。", "wǒmen wǎnshang jiǔ diǎn guānmén.", "We close at 9 PM."),
       player("Say you'll come back later.", [
           ("好的，那我待会儿再来。", 1.0, "neutral", "Natural with 待会儿 (later)."),
           ("好，我晚点来。", 0.8, "casual", "Also fine."),
           ("好。", 0.5, "blunt", "Let them know your plan."),
       ])],
      "待会儿 means 'in a little while' — very common in spoken Chinese."),

    S("Comparing products", "比较产品", 2, "neutral", 0.4,
      "You're choosing between two phones.", "你在选两部手机。",
      [npc("你想看看哪一款？", "nǐ xiǎng kànkan nǎ yì kuǎn?", "Which model do you want to look at?"),
       player("Ask to compare the two on display.", [
           ("这两款有什么不同？", 1.0, "neutral", "Great comparison question."),
           ("哪个更好？", 0.6, "casual", "Subjective — asking about differences is better."),
           ("都看看。", 0.5, "casual", "OK but ask specific questions."),
       ]),
       npc("这个便宜，但是那个拍照更好。", "zhè ge piányi, dànshì nà ge pāizhào gèng hǎo.", "This one is cheaper, but that one has a better camera."),
       player("Say you care more about the camera.", [
           ("我比较在意拍照，那我选那个吧。", 1.0, "neutral", "Clear reasoning with 比较在意."),
           ("我要拍照好的。", 0.7, "casual", "Works but less nuanced."),
           ("那个。", 0.4, "blunt", "Explain your reasoning."),
       ])],
      "比较 can mean 'comparatively' — 我比较在意 means 'I care more about.'"),

    S("Describing symptoms", "描述症状", 2, "neutral", 0.5,
      "You're at a pharmacy.", "你在药店。",
      [npc("你哪里不舒服？", "nǐ nǎlǐ bù shūfu?", "What's wrong?"),
       player("Say you have a cough and sore throat.", [
           ("我咳嗽，嗓子也疼。", 1.0, "neutral", "Clear description of symptoms."),
           ("感冒了。", 0.5, "casual", "Too vague — describe specific symptoms."),
           ("不舒服。", 0.3, "blunt", "They know that — say where/what."),
       ]),
       npc("咳嗽几天了？", "késou jǐ tiān le?", "How many days have you been coughing?"),
       player("Say about three days.", [
           ("大概三天了。", 1.0, "neutral", "Clear with 了 indicating duration."),
           ("三天。", 0.7, "casual", "OK, but 了 emphasizes it's ongoing."),
           ("好几天了。", 0.6, "casual", "好几天 means 'quite a few days' — less precise."),
       ])],
      "Chinese pharmacies often act as initial health consultants before recommending medicine."),

    S("Sending a package", "寄快递", 2, "neutral", 0.4,
      "You're at a courier pickup point.", "你在快递站。",
      [npc("寄到哪里？", "jì dào nǎlǐ?", "Where are you sending it?"),
       player("Say Shanghai.", [
           ("寄到上海。", 1.0, "neutral", "Clear and direct."),
           ("上海。", 0.7, "casual", "Fine in context."),
           ("去上海。", 0.5, "casual", "去 implies going yourself — 寄到 for packages."),
       ]),
       npc("里面是什么东西？", "lǐmiàn shì shénme dōngxi?", "What's inside?"),
       player("Say it's books.", [
           ("是几本书。", 1.0, "neutral", "Clear with measure word 本."),
           ("书。", 0.6, "casual", "Fine but adding 几本 is more specific."),
           ("不知道。", 0.2, "blunt", "You packed it — you should know."),
       ])],
      "Chinese couriers always ask about contents for shipping classification."),

    S("Inviting someone to dinner", "请人吃饭", 2, "casual", 0.4,
      "You want to thank a friend for helping you.", "你想感谢帮助你的朋友。",
      [npc("谢谢你上次帮我搬家。", "xièxie nǐ shàng cì bāng wǒ bānjiā.", "Thanks for helping me move last time."),
       player("Say you want to treat them to dinner.", [
           ("不客气！我请你吃饭吧，你什么时候有空？", 1.0, "casual", "Generous offer with 请你吃饭."),
           ("没关系。我们去吃饭吧。", 0.7, "casual", "Good but 我请你 clarifies you're treating."),
           ("不用谢。", 0.5, "neutral", "Polite but doesn't advance to the invitation."),
       ]),
       npc("太好了！周五晚上可以吗？", "tài hǎo le! zhōuwǔ wǎnshang kěyǐ ma?", "Great! Is Friday evening OK?"),
       player("Say Friday works and suggest a restaurant.", [
           ("可以！你喜欢吃火锅吗？我知道一家很好的。", 1.0, "casual", "Enthusiastic with a specific suggestion."),
           ("好的，你想吃什么？", 0.8, "casual", "Good — asking their preference."),
           ("行。", 0.5, "blunt", "Show more enthusiasm."),
       ])],
      "请人吃饭 (treating someone to a meal) is a key part of Chinese social culture."),

    S("Talking about travel", "聊旅行", 2, "casual", 0.4,
      "A coworker just returned from vacation.", "同事刚度假回来。",
      [npc("我上个星期去了云南，特别漂亮！", "wǒ shàng ge xīngqī qù le Yúnnán, tèbié piàoliang!", "I went to Yunnan last week, it was beautiful!"),
       player("Ask what they did there.", [
           ("真的吗？你在那儿做了什么？", 1.0, "casual", "Interested and natural."),
           ("好玩吗？", 0.7, "casual", "Fine but less specific."),
           ("哦。", 0.3, "blunt", "Show interest in their trip."),
       ]),
       npc("我去了大理和丽江，还骑了马。", "wǒ qù le Dàlǐ hé Lìjiāng, hái qí le mǎ.", "I went to Dali and Lijiang, and even rode horses."),
       player("Say it sounds fun and you also want to go.", [
           ("听起来很好玩！我也想去云南。", 1.0, "casual", "Engaging response."),
           ("我也想去。", 0.7, "casual", "Good but 听起来 adds warmth."),
           ("不错。", 0.4, "neutral", "Flat — show more enthusiasm."),
       ])],
      "云南 (Yunnan) is one of China's most popular tourist destinations."),

    S("Ordering delivery food", "点外卖", 2, "casual", 0.4,
      "You're ordering food by phone.", "你打电话点外卖。",
      [npc("你好，想点什么？", "nǐ hǎo, xiǎng diǎn shénme?", "Hello, what would you like to order?"),
       player("Order kung pao chicken and rice.", [
           ("一份宫保鸡丁和一碗米饭。", 1.0, "neutral", "Specific with correct measure words."),
           ("宫保鸡丁加米饭。", 0.8, "casual", "Also natural — 加 means 'plus.'"),
           ("鸡肉和饭。", 0.5, "casual", "Too vague — specify the dish name."),
       ]),
       npc("好的。地址是？", "hǎo de. dìzhǐ shì?", "OK. What's the address?"),
       player("Give your address.", [
           ("和平路十二号三楼。", 1.0, "neutral", "Specific with building number and floor."),
           ("和平路十二号。", 0.7, "neutral", "Good but adding floor number helps delivery."),
           ("我家。", 0.2, "blunt", "They need a real address."),
       ])],
      "Chinese addresses go from large to small: street → building → floor → room."),

    S("Discussing weather for plans", "讨论天气影响计划", 2, "casual", 0.4,
      "You're planning an outdoor activity.", "你在计划户外活动。",
      [npc("明天的天气怎么样？", "míngtiān de tiānqì zěnmeyàng?", "What's tomorrow's weather like?"),
       player("Say the forecast says sunny.", [
           ("天气预报说明天是晴天。", 1.0, "neutral", "Informative with source."),
           ("应该是晴天。", 0.7, "casual", "应该 implies some uncertainty — fine."),
           ("不下雨。", 0.5, "casual", "OK but 晴天 is more informative."),
       ]),
       npc("太好了！那我们可以去公园烧烤。", "tài hǎo le! nà wǒmen kěyǐ qù gōngyuán shāokǎo.", "Great! Then we can have a barbecue in the park."),
       player("Say that sounds great and ask what to bring.", [
           ("太好了！我需要带什么？", 1.0, "casual", "Enthusiastic and practical."),
           ("好的，我带饮料。", 0.8, "casual", "Great — proactively offering."),
           ("好。", 0.4, "blunt", "Show more engagement."),
       ])],
      "Public barbecuing is popular in many Chinese parks, especially in spring and autumn."),

    S("Asking for restaurant recommendation", "问餐厅推荐", 2, "casual", 0.4,
      "You ask a local friend for a restaurant tip.", "你问本地朋友推荐餐厅。",
      [npc("你想吃什么菜？", "nǐ xiǎng chī shénme cài?", "What kind of food do you want?"),
       player("Say you want to try Sichuan food.", [
           ("我想试试四川菜。你知道附近有好的吗？", 1.0, "casual", "Natural with 试试 and specific ask."),
           ("四川菜。哪里有？", 0.6, "casual", "OK but 你知道…吗 is more natural."),
           ("辣的。", 0.4, "casual", "Too vague — specify the cuisine."),
       ]),
       npc("前面那条街有一家很正宗的。", "qiánmian nà tiáo jiē yǒu yì jiā hěn zhèngzōng de.", "There's a very authentic one on the street ahead."),
       player("Ask if it's expensive.", [
           ("贵不贵？人均多少？", 1.0, "neutral", "Good — 人均 means 'per person.'"),
           ("贵吗？", 0.7, "casual", "Simpler version — fine."),
           ("好，去。", 0.5, "casual", "Find out about price first."),
       ])],
      "正宗 means 'authentic' — high praise for regional Chinese restaurants."),

    S("Lending and borrowing", "借东西", 2, "casual", 0.4,
      "Your roommate needs to borrow something.", "你的室友想借东西。",
      [npc("我能借你的充电器用一下吗？我的没电了。", "wǒ néng jiè nǐ de chōngdiànqì yòng yíxià ma? wǒ de méi diàn le.", "Can I borrow your charger? Mine is dead."),
       player("Say sure, it's on the desk.", [
           ("当然可以，在桌子上。", 1.0, "casual", "Helpful and specific."),
           ("可以，拿吧。", 0.8, "casual", "Also fine — 拿吧 means 'go ahead and take it.'"),
           ("好。", 0.5, "blunt", "Tell them where it is."),
       ]),
       npc("谢谢！我用完就还你。", "xièxie! wǒ yòng wán jiù huán nǐ.", "Thanks! I'll return it when I'm done."),
       player("Say no rush.", [
           ("不着急，慢慢用。", 1.0, "casual", "Generous — 不着急 means 'no rush.'"),
           ("好的。", 0.6, "neutral", "Fine."),
           ("快点还。", 0.3, "blunt", "Too demanding between roommates."),
       ])],
      "借 means both 'lend' and 'borrow' — context determines which."),

    S("Complaining about traffic", "抱怨交通", 2, "casual", 0.4,
      "You arrive late to meet a friend.", "你迟到了，和朋友解释。",
      [npc("你怎么这么晚？我等了半个小时！", "nǐ zěnme zhème wǎn? wǒ děng le bàn ge xiǎoshí!", "Why are you so late? I waited half an hour!"),
       player("Apologize and explain there was traffic.", [
           ("对不起！路上堵车堵得很厉害。", 1.0, "casual", "Good apology with explanation."),
           ("不好意思，堵车了。", 0.8, "casual", "Shorter but still has apology + reason."),
           ("堵车。", 0.4, "blunt", "Apologize first."),
       ]),
       npc("下次早点出门吧。", "xià cì zǎo diǎn chūmén ba.", "Leave earlier next time."),
       player("Agree and suggest going to eat.", [
           ("你说得对。走吧，我请你吃饭赔罪。", 1.0, "casual", "Owns it and makes up with a meal offer."),
           ("好的，下次一定早点。", 0.7, "neutral", "Good promise."),
           ("知道了。", 0.4, "casual", "A bit dismissive — show more sincerity."),
       ])],
      "堵车 (traffic jam) is an everyday reality in Chinese cities."),

    S("Discussing a new job", "聊新工作", 2, "casual", 0.4,
      "Your friend just started a new job.", "你朋友刚开始新工作。",
      [npc("我下个月开始新工作！", "wǒ xià ge yuè kāishǐ xīn gōngzuò!", "I start a new job next month!"),
       player("Congratulate them and ask about it.", [
           ("恭喜你！在哪儿工作？", 1.0, "casual", "Warm congrats + natural follow-up."),
           ("太好了！做什么的？", 0.8, "casual", "Also good — asking about the role."),
           ("哦，好。", 0.3, "blunt", "Show excitement for your friend."),
       ]),
       npc("在一家科技公司当工程师。", "zài yì jiā kējì gōngsī dāng gōngchéngshī.", "As an engineer at a tech company."),
       player("Say that's impressive and ask about salary.", [
           ("很厉害！工资怎么样？", 0.7, "casual", "Direct — asking salary is normal among close friends in China."),
           ("听起来很棒！你喜欢这个工作吗？", 1.0, "casual", "Safer and warmer question."),
           ("不错。", 0.4, "neutral", "Too brief for a friend's big news."),
       ])],
      "In Chinese culture, asking about salary among close friends is more acceptable than in Western culture."),

    S("Lost phone", "手机丢了", 2, "neutral", 0.5,
      "You think you left your phone at a restaurant.", "你觉得手机落在餐厅了。",
      [npc("你好，有什么可以帮你的？", "nǐ hǎo, yǒu shénme kěyǐ bāng nǐ de?", "Hello, how can I help?"),
       player("Say you think you left your phone here.", [
           ("我觉得我的手机落在你们这儿了，刚才在这里吃饭的。", 1.0, "neutral", "Clear explanation with context."),
           ("我的手机不见了，可能在这儿。", 0.7, "neutral", "OK but less specific."),
           ("手机？", 0.3, "blunt", "Explain the situation properly."),
       ]),
       npc("你坐在哪个位子？什么颜色的手机？", "nǐ zuò zài nǎ ge wèizi? shénme yánsè de shǒujī?", "Which seat were you at? What color phone?"),
       player("Describe the phone and your seat.", [
           ("黑色的，我坐在靠窗的那个位子。", 1.0, "neutral", "Specific details help find it."),
           ("黑色手机。在窗户旁边。", 0.7, "neutral", "Good info, slightly less natural."),
           ("黑的。", 0.4, "blunt", "Also describe your seat location."),
       ])],
      "落 means 'to leave behind (accidentally)' — different from 放 (to place intentionally)."),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HSK 3 — 21 new scenarios
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HSK3 = [
    S("Negotiating rent", "谈房租", 3, "neutral", 0.6,
      "You want to negotiate lower rent with your landlord.", "你想和房东谈降低房租。",
      [npc("下个月开始房租要涨五百。", "xià ge yuè kāishǐ fángzū yào zhǎng wǔbǎi.", "Starting next month, rent will increase by 500."),
       player("Express concern and try to negotiate.", [
           ("涨得有点多。我已经住了两年了，能不能少涨一些？", 1.0, "neutral", "Reasonable negotiation with history."),
           ("太贵了，我不想涨。", 0.5, "blunt", "Too confrontational — negotiate instead."),
           ("好吧。", 0.3, "neutral", "Don't accept without negotiating."),
       ]),
       npc("你是老租客了，那涨三百吧。", "nǐ shì lǎo zūkè le, nà zhǎng sānbǎi ba.", "You've been here a while, let's say 300 then."),
       player("Accept the compromise.", [
           ("好的，那就三百。谢谢你的理解。", 1.0, "neutral", "Gracious acceptance."),
           ("可以，但能签长一点的合同吗？", 0.9, "neutral", "Smart — locking in the rate."),
           ("还是太贵了。", 0.4, "neutral", "You already got a concession — pushing harder may backfire."),
       ])],
      "In China, longtime tenants (老租客) often get better negotiating leverage."),

    S("Job interview small talk", "面试闲聊", 3, "neutral", 0.6,
      "You arrive early for a job interview.", "你提前到了面试地点。",
      [npc("请坐。你是怎么来的？路上还顺利吧？", "qǐng zuò. nǐ shì zěnme lái de? lùshang hái shùnlì ba?", "Please sit. How did you get here? Was the trip smooth?"),
       player("Say the commute was fine, you took the subway.", [
           ("坐地铁来的，很方便，没有堵车的问题。", 1.0, "neutral", "Shows positive attitude and practical choice."),
           ("还好，坐地铁来的。", 0.7, "neutral", "Fine but less detailed."),
           ("堵车了。", 0.3, "neutral", "Negative first impression in an interview."),
       ]),
       npc("那不错。你对我们公司了解多少？", "nà búcuò. nǐ duì wǒmen gōngsī liǎojiě duōshao?", "Good. How much do you know about our company?"),
       player("Show you did research.", [
           ("我看了你们的网站，知道你们主要做教育科技方面的产品。", 1.0, "neutral", "Shows preparation."),
           ("我了解一些，你们是做科技的。", 0.6, "neutral", "Vague — be more specific."),
           ("不太了解。", 0.3, "neutral", "Should always research before an interview."),
       ])],
      "Chinese interviews often start with casual questions to ease the atmosphere."),

    S("Reporting a problem to landlord", "跟房东报修", 3, "neutral", 0.5,
      "Your apartment has a broken water heater.", "你公寓的热水器坏了。",
      [npc("喂，你好，有什么事？", "wèi, nǐ hǎo, yǒu shénme shì?", "Hello, what's up?"),
       player("Report the broken water heater.", [
           ("你好，我家的热水器坏了，没有热水。能请人来修一下吗？", 1.0, "neutral", "Clear problem description + solution request."),
           ("热水器坏了。", 0.5, "casual", "State the problem but also ask for repair."),
           ("没热水了。", 0.4, "casual", "Be specific about the cause."),
       ]),
       npc("好的，我让师傅明天上午过去看看。你明天在家吗？", "hǎo de, wǒ ràng shīfu míngtiān shàngwǔ guòqù kànkan. nǐ míngtiān zàijiā ma?", "OK, I'll send a repairman tomorrow morning. Will you be home?"),
       player("Confirm you'll be there.", [
           ("明天上午在。大概几点来？", 1.0, "neutral", "Confirms and asks for specific time."),
           ("在。", 0.5, "blunt", "Ask what time."),
           ("可以来下午吗？", 0.7, "neutral", "Fine if morning doesn't work."),
       ])],
      "师傅 is used for repairmen, drivers, and skilled workers — a respectful term."),

    S("Returning a purchase", "退货", 3, "neutral", 0.6,
      "You bought shoes that don't fit and want to return them.", "你买的鞋子不合适，想退货。",
      [npc("你好，有什么问题？", "nǐ hǎo, yǒu shénme wèntí?", "Hello, what's the problem?"),
       player("Explain the shoes don't fit and you want to return them.", [
           ("这双鞋买小了，穿着不舒服。我想退货，这是收据。", 1.0, "neutral", "Clear reason + receipt ready."),
           ("鞋子不合适，能退吗？", 0.7, "neutral", "OK but having the receipt ready is better."),
           ("退钱。", 0.3, "blunt", "Explain the reason first."),
       ]),
       npc("可以换一双大一号的，或者退款。你选哪个？", "kěyǐ huàn yì shuāng dà yí hào de, huòzhě tuìkuǎn. nǐ xuǎn nǎ ge?", "You can exchange for one size larger, or get a refund. Which do you prefer?"),
       player("Ask to try the larger size first.", [
           ("先试试大一号的吧，如果还是不合适就退款。", 1.0, "neutral", "Smart approach — try first."),
           ("换大一号的。", 0.7, "neutral", "Fine."),
           ("退款吧。", 0.6, "neutral", "OK but trying first is often better."),
       ])],
      "Most Chinese stores accept returns within 7 days with a receipt (收据 or 发票)."),

    S("Discussing health habits", "聊健康习惯", 3, "casual", 0.5,
      "A friend asks about your health routine.", "朋友问你的健康习惯。",
      [npc("你平时怎么保持健康的？", "nǐ píngshí zěnme bǎochí jiànkāng de?", "How do you stay healthy?"),
       player("Talk about your exercise and diet habits.", [
           ("我每天早上跑步，尽量少吃油炸的东西。", 1.0, "casual", "Specific habits with 尽量 (try to)."),
           ("运动和吃好的。", 0.5, "casual", "Too vague — give specifics."),
           ("不知道，随便吧。", 0.3, "casual", "Dismissive."),
       ]),
       npc("我最近开始减肥，可是总是控制不住自己吃零食。", "wǒ zuìjìn kāishǐ jiǎnféi, kěshì zǒngshì kòngzhì bú zhù zìjǐ chī língshí.", "I've been trying to lose weight but I can't stop snacking."),
       player("Give some advice.", [
           ("你可以把零食换成水果，慢慢就习惯了。", 1.0, "casual", "Practical and encouraging advice."),
           ("少吃零食就好了。", 0.5, "casual", "Obvious — offer a practical tip."),
           ("那就别减了。", 0.3, "casual", "Not helpful."),
       ])],
      "控制不住自己 means 'can't control oneself' — a common expression for bad habits."),

    S("Giving directions", "指路", 3, "neutral", 0.5,
      "A tourist asks you for directions.", "一个游客向你问路。",
      [npc("请问，最近的地铁站怎么走？", "qǐngwèn, zuìjìn de dìtiě zhàn zěnme zǒu?", "Excuse me, how do I get to the nearest subway?"),
       player("Give clear directions.", [
           ("往前走大概两百米，在第二个路口左转就能看到了。", 1.0, "neutral", "Specific distance + turns."),
           ("往前走，左转。", 0.6, "casual", "Too vague — add distance."),
           ("用手机导航吧。", 0.4, "casual", "Unhelpful — give verbal directions."),
       ]),
       npc("走路大概要多久？", "zǒulù dàgài yào duōjiǔ?", "About how long on foot?"),
       player("Estimate the walking time.", [
           ("大概五分钟就到了。", 1.0, "neutral", "Clear estimate."),
           ("很近，几分钟。", 0.7, "casual", "OK but a specific number is better."),
           ("不远。", 0.5, "casual", "Vague — give a time estimate."),
       ])],
      "Chinese directions use 路口 (intersection) and compass or left/right references."),

    S("Ordering for the table", "帮大家点菜", 3, "neutral", 0.5,
      "You're ordering for a group at a restaurant.", "你在餐厅帮大家点菜。",
      [npc("请问几位？", "qǐngwèn jǐ wèi?", "How many people?"),
       player("Say there are six people.", [
           ("六位。有没有大一点的桌子？", 1.0, "neutral", "Specifies need and proactively asks."),
           ("六个人。", 0.7, "casual", "用位 is more polite than 个人."),
           ("六。", 0.4, "blunt", "Add the measure word."),
       ]),
       npc("好的，这边请。要先看看菜单吗？", "hǎo de, zhè biān qǐng. yào xiān kànkan càidān ma?", "This way please. Want to see the menu first?"),
       player("Order some popular dishes for the group.", [
           ("先来一个宫保鸡丁、一个鱼香肉丝、一个炒青菜，再加一份汤。", 1.0, "neutral", "Well-balanced order with variety."),
           ("你们有什么推荐的？", 0.8, "neutral", "Smart — asking for recommendations."),
           ("随便来几个菜。", 0.5, "casual", "Too vague for a group order."),
       ])],
      "Chinese group dining typically orders dishes to share — aim for variety of meat, vegetable, and soup."),

    S("Discussing a book", "聊一本书", 3, "casual", 0.5,
      "Your friend recommends a book.", "你朋友推荐一本书给你。",
      [npc("你看过《三体》吗？特别好看！", "nǐ kàn guò Sān Tǐ ma? tèbié hǎokàn!", "Have you read The Three-Body Problem? It's really good!"),
       player("Say you haven't but you've heard of it.", [
           ("没看过，但是听说过。讲什么的？", 1.0, "casual", "Shows interest + asks for details."),
           ("没有。好看吗？", 0.6, "casual", "Less engaged."),
           ("不喜欢看书。", 0.3, "casual", "Conversation killer."),
       ]),
       npc("是刘慈欣写的科幻小说。讲的是外星人和地球的故事。", "shì Liú Cíxīn xiě de kēhuàn xiǎoshuō. jiǎng de shì wàixīngrén hé dìqiú de gùshi.", "It's a sci-fi novel by Liu Cixin. About aliens and Earth."),
       player("Say it sounds interesting and ask to borrow it.", [
           ("听起来很有意思！你能借我看看吗？", 1.0, "casual", "Natural request with 借我."),
           ("好，我买一本看看。", 0.8, "casual", "Also fine — buying your own."),
           ("科幻？不太喜欢。", 0.4, "casual", "Could try it before dismissing."),
       ])],
      "《三体》(The Three-Body Problem) is one of China's most famous modern novels."),

    S("Making a doctor appointment", "预约看医生", 3, "neutral", 0.6,
      "You call a clinic to make an appointment.", "你打电话给诊所预约。",
      [npc("你好，请问挂什么科？", "nǐ hǎo, qǐngwèn guà shénme kē?", "Hello, which department would you like?"),
       player("Say you need to see a dermatologist.", [
           ("我想挂皮肤科。", 1.0, "neutral", "Correct department name."),
           ("皮肤有问题。", 0.5, "casual", "Describe the department, not the problem yet."),
           ("不知道挂什么科。我皮肤过敏了。", 0.7, "neutral", "Honest — they'll direct you."),
       ]),
       npc("皮肤科明天下午有号。你下午两点可以吗？", "pífūkē míngtiān xiàwǔ yǒu hào. nǐ xiàwǔ liǎng diǎn kěyǐ ma?", "Dermatology has slots tomorrow afternoon. Is 2 PM OK?"),
       player("Confirm the appointment.", [
           ("可以的。需要带什么材料吗？", 1.0, "neutral", "Confirms + asks practical question."),
           ("好的，两点。", 0.7, "neutral", "Clear but asking about materials is smart."),
           ("行。", 0.5, "blunt", "Too brief."),
       ])],
      "Chinese hospitals organize by 科 (department) — you choose the department when registering."),

    S("Explaining a delay", "解释迟到", 3, "neutral", 0.5,
      "You arrive late to a meeting.", "你开会迟到了。",
      [npc("会议已经开始十分钟了。", "huìyì yǐjīng kāishǐ shí fēnzhōng le.", "The meeting already started 10 minutes ago."),
       player("Apologize and explain.", [
           ("非常抱歉！电梯坏了，我只能走楼梯上来。", 1.0, "neutral", "Good apology with valid reason."),
           ("对不起，迟到了。", 0.6, "neutral", "Apologizes but no explanation."),
           ("我知道。", 0.2, "blunt", "Rude — apologize."),
       ]),
       npc("没关系，我们刚开始讨论第一个议题。", "méi guānxi, wǒmen gāng kāishǐ tǎolùn dì yī ge yìtí.", "It's OK, we just started discussing the first topic."),
       player("Thank them and sit down.", [
           ("谢谢理解。我马上跟上。", 1.0, "neutral", "Professional recovery."),
           ("好的。", 0.6, "neutral", "Fine but thanking them is better."),
           ("那我没错过什么。", 0.3, "casual", "Sounds like you don't take it seriously."),
       ])],
      "非常抱歉 is more formal than 对不起 — better for professional situations."),

    S("Asking about customs", "了解风俗", 3, "neutral", 0.5,
      "You're invited to a Chinese New Year dinner.", "你被邀请参加春节晚宴。",
      [npc("你来过春节聚会吗？", "nǐ lái guò chūnjié jùhuì ma?", "Have you been to a Spring Festival gathering before?"),
       player("Say it's your first time and ask about customs.", [
           ("没有，这是第一次。有什么需要注意的吗？", 1.0, "neutral", "Humble and eager to learn."),
           ("第一次。", 0.5, "casual", "Ask about customs."),
           ("没有。", 0.4, "casual", "Show more interest."),
       ]),
       npc("最重要的是不要说不吉利的话，多说祝福的话。", "zuì zhòngyào de shì bú yào shuō bù jílì de huà, duō shuō zhùfú de huà.", "Most important is avoid unlucky words, say more blessings."),
       player("Ask for an example blessing.", [
           ("明白了。一般说什么祝福语？", 1.0, "neutral", "Good follow-up question."),
           ("比如说什么？", 0.7, "casual", "Also fine."),
           ("好的。", 0.5, "neutral", "Ask for specifics."),
       ])],
      "Spring Festival taboos include words like 死 (death) and 破 (broken). Say 新年快乐 and 恭喜发财."),

    S("Splitting the bill", "分开付账", 3, "casual", 0.5,
      "You're finishing dinner with friends.", "你和朋友吃完饭。",
      [npc("今天谁请客？", "jīntiān shéi qǐngkè?", "Who's treating today?"),
       player("Suggest splitting the bill.", [
           ("我们AA吧，每人付自己的。", 1.0, "casual", "Direct and fair."),
           ("各付各的吧。", 0.8, "casual", "Also natural."),
           ("你请吧。", 0.3, "casual", "Presumptuous unless they offered."),
       ]),
       npc("也行。一共三百六，三个人的话每人一百二。", "yě xíng. yígòng sānbǎi liù, sān ge rén de huà měi rén yìbǎi èr.", "OK. Total 360, so 120 each for three people."),
       player("Agree and pay your share.", [
           ("好的，我转给你一百二十。你的微信收款码呢？", 1.0, "casual", "Modern and practical."),
           ("行，微信转你。", 0.7, "casual", "Also fine."),
           ("我只吃了一个菜。", 0.3, "casual", "Don't nickel-and-dime at group dinners."),
       ])],
      "AA制 (splitting the bill) is common among younger Chinese. WeChat Pay is the norm."),

    S("Talking about a TV show", "聊电视剧", 3, "casual", 0.5,
      "A coworker asks about a show you're watching.", "同事问你在看什么电视剧。",
      [npc("你最近在追什么剧？", "nǐ zuìjìn zài zhuī shénme jù?", "What show are you binge-watching lately?"),
       player("Talk about a show you're watching.", [
           ("我在看一个古装剧，叫《琅琊榜》，剧情特别好。", 1.0, "casual", "Specific with genre and opinion."),
           ("一个古装剧，挺好看的。", 0.6, "casual", "Vague — name the show."),
           ("没什么好看的。", 0.4, "casual", "Negative — answer the question."),
       ]),
       npc("我也听说过那个！一共多少集？", "wǒ yě tīngshuō guò nà ge! yígòng duōshao jí?", "I've heard of it! How many episodes total?"),
       player("Answer and recommend it.", [
           ("五十四集。节奏很快，不会觉得无聊。强烈推荐！", 1.0, "casual", "Detailed recommendation."),
           ("五十几集吧。很好看。", 0.7, "casual", "Fine."),
           ("很多集。", 0.4, "casual", "Be more specific."),
       ])],
      "追剧 means 'to binge-watch a series' — a popular modern Chinese expression."),

    S("Dealing with a noise complaint", "处理噪音投诉", 3, "neutral", 0.6,
      "Your neighbor knocks on your door about noise.", "邻居来敲门说太吵了。",
      [npc("不好意思，你们能不能小声一点？我孩子在睡觉。", "bù hǎoyìsi, nǐmen néng bù néng xiǎoshēng yìdiǎn? wǒ háizi zài shuìjiào.", "Sorry, could you keep it down? My child is sleeping."),
       player("Apologize and lower the noise.", [
           ("真不好意思，我们不知道。马上小声。", 1.0, "neutral", "Genuine apology + immediate action."),
           ("好的，对不起。", 0.7, "neutral", "Fine but less engaging."),
           ("现在才九点。", 0.3, "blunt", "Argumentative — just apologize."),
       ]),
       npc("谢谢你的理解。周末孩子都睡得早。", "xièxie nǐ de lǐjiě. zhōumò háizi dōu shuì de zǎo.", "Thanks for understanding. Kids sleep early on weekends."),
       player("Respond warmly.", [
           ("没问题。以后有什么问题随时跟我说。", 1.0, "neutral", "Builds good neighbor relations."),
           ("好的，没事。", 0.6, "neutral", "Fine."),
           ("知道了。", 0.4, "casual", "A bit cold."),
       ])],
      "Being a considerate neighbor (好邻居) is highly valued in Chinese culture."),

    S("Asking about train tickets", "买火车票", 3, "neutral", 0.5,
      "You're at the train station ticket counter.", "你在火车站售票窗口。",
      [npc("你好，去哪里？", "nǐ hǎo, qù nǎlǐ?", "Hello, where to?"),
       player("Say you're going to Shanghai, tomorrow morning.", [
           ("去上海，明天上午的。有高铁吗？", 1.0, "neutral", "Specific with preference for high-speed."),
           ("去上海。", 0.5, "casual", "Need to specify when and what type."),
           ("上海，最快的。", 0.6, "casual", "OK but be more specific."),
       ]),
       npc("明天上午九点有一班高铁，二等座两百八。", "míngtiān shàngwǔ jiǔ diǎn yǒu yì bān gāotiě, èr děng zuò liǎng bǎi bā.", "There's a 9 AM high-speed train tomorrow, second class is 280."),
       player("Buy the ticket.", [
           ("好的，买一张二等座。可以用支付宝吗？", 1.0, "neutral", "Decisive + payment method."),
           ("一张。", 0.6, "casual", "Works but specifying class is better."),
           ("有没有更便宜的？", 0.5, "neutral", "OK but high-speed is already best value for speed."),
       ])],
      "Chinese trains have 一等座 (first class) and 二等座 (second class). High-speed trains are 高铁 or 动车."),

    S("Tech support call", "技术支持", 3, "neutral", 0.6,
      "You call tech support about your internet.", "你打电话给网络技术支持。",
      [npc("你好，请问有什么问题？", "nǐ hǎo, qǐngwèn yǒu shénme wèntí?", "Hello, what's the problem?"),
       player("Describe your internet issue.", [
           ("我家的网特别慢，已经两天了。网速比以前慢了很多。", 1.0, "neutral", "Specific with duration and comparison."),
           ("网很慢。", 0.5, "casual", "Too vague — add details."),
           ("网坏了。", 0.4, "casual", "Slow ≠ broken — be precise."),
       ]),
       npc("好的，我查一下你的线路。请问你的账号是多少？", "hǎo de, wǒ chá yíxià nǐ de xiànlù. qǐngwèn nǐ de zhànghào shì duōshao?", "OK, let me check your line. What's your account number?"),
       player("Provide your account number.", [
           ("我的账号是139开头的那个，稍等我查一下…139-8825-6601。", 1.0, "neutral", "Natural flow while looking it up."),
           ("139-8825-6601。", 0.7, "neutral", "Efficient."),
           ("不知道账号。", 0.4, "neutral", "Have your account info ready before calling."),
       ])],
      "Chinese phone numbers are typically given in groups: 139-XXXX-XXXX."),

    S("Recommending a place", "推荐一个地方", 3, "casual", 0.5,
      "A friend asks where to take a date.", "朋友问你约会去哪儿好。",
      [npc("我想带女朋友去一个特别的地方，你有什么建议吗？", "wǒ xiǎng dài nǚpéngyou qù yí ge tèbié de dìfang, nǐ yǒu shénme jiànyì ma?", "I want to take my girlfriend somewhere special, any suggestions?"),
       player("Recommend a place.", [
           ("你可以去南京路附近那个露台餐厅，环境很浪漫，风景也好。", 1.0, "casual", "Specific recommendation with reasons."),
           ("去一个好餐厅吧。", 0.5, "casual", "Too vague — name a place."),
           ("不知道。", 0.3, "casual", "Try to help."),
       ]),
       npc("听起来不错！大概人均多少钱？", "tīng qǐlai búcuò! dàgài rénjūn duōshao qián?", "Sounds good! About how much per person?"),
       player("Give a price estimate.", [
           ("人均两三百吧。环境和食物都值这个价。", 1.0, "casual", "Helpful with value judgment."),
           ("不太贵。", 0.5, "casual", "Give a number."),
           ("忘了。", 0.4, "casual", "Give your best estimate."),
       ])],
      "人均 (per person average) is commonly used when discussing restaurant prices."),

    S("Discussing career plans", "聊职业规划", 3, "casual", 0.5,
      "A friend asks about your career plans.", "朋友问你的职业规划。",
      [npc("你以后想做什么工作？", "nǐ yǐhòu xiǎng zuò shénme gōngzuò?", "What kind of work do you want to do in the future?"),
       player("Talk about your career goals.", [
           ("我想在教育行业工作，希望能当一名老师。", 1.0, "neutral", "Specific industry + role."),
           ("还不确定，但是对教育感兴趣。", 0.7, "casual", "Honest with direction."),
           ("不知道。", 0.3, "casual", "Think about it — it's a normal question."),
       ]),
       npc("当老师挺好的。你打算什么时候开始找工作？", "dāng lǎoshī tǐng hǎo de. nǐ dǎsuàn shénme shíhòu kāishǐ zhǎo gōngzuò?", "Being a teacher is great. When do you plan to start looking?"),
       player("Discuss your timeline.", [
           ("毕业以后吧。现在先把中文学好。", 1.0, "casual", "Prioritized and realistic."),
           ("明年开始找。", 0.7, "casual", "Specific timeline."),
           ("不急。", 0.4, "casual", "Show some planning."),
       ])],
      "打算 means 'to plan/intend' — useful for discussing future plans."),

    S("Helping a tourist", "帮助游客", 3, "neutral", 0.5,
      "A Chinese tourist asks you for help with English.", "一个中国游客请你帮忙。",
      [npc("不好意思，你能帮我翻译一下这个吗？我看不懂英文。", "bù hǎoyìsi, nǐ néng bāng wǒ fānyì yíxià zhè ge ma? wǒ kàn bù dǒng yīngwén.", "Excuse me, can you help translate this? I can't read English."),
       player("Agree to help.", [
           ("当然可以！让我看看。这是博物馆的开放时间，上午九点到下午五点。", 1.0, "neutral", "Helpful with complete translation."),
           ("可以。这是开放时间。", 0.6, "neutral", "Helpful but incomplete."),
           ("我中文不太好。", 0.4, "neutral", "Still try to help."),
       ]),
       npc("太感谢了！你的中文说得很好！", "tài gǎnxiè le! nǐ de zhōngwén shuō de hěn hǎo!", "Thank you so much! Your Chinese is great!"),
       player("Respond modestly.", [
           ("哪里哪里，还在学习中。", 1.0, "neutral", "Appropriately modest — 哪里哪里 is the classic response."),
           ("谢谢！我还要多练习。", 0.8, "neutral", "Also modest and natural."),
           ("对，我知道。", 0.3, "blunt", "Accept compliments modestly in Chinese culture."),
       ])],
      "哪里哪里 is the classic modest response to compliments in Chinese culture."),

    S("Apartment viewing", "看房", 3, "neutral", 0.6,
      "You're viewing a rental apartment.", "你在看一个出租公寓。",
      [npc("这是客厅，阳光很好。你觉得怎么样？", "zhè shì kètīng, yángguāng hěn hǎo. nǐ juéde zěnmeyàng?", "This is the living room, great sunlight. What do you think?"),
       player("Say you like it and ask about utilities.", [
           ("客厅不错。请问水电费包在房租里吗？", 1.0, "neutral", "Practical question about costs."),
           ("挺好的。多少钱？", 0.6, "casual", "OK but 水电费 is an important detail."),
           ("还行。", 0.4, "casual", "Show more engagement if you're interested."),
       ]),
       npc("水电费另算。房租一个月四千，押一付三。", "shuǐdiàn fèi lìng suàn. fángzū yí ge yuè sìqiān, yā yī fù sān.", "Utilities are separate. Rent is 4000/month, one month deposit plus three months upfront."),
       player("Ask if the price is negotiable.", [
           ("价格能商量一下吗？三千五可以吗？", 1.0, "neutral", "Reasonable counter-offer."),
           ("太贵了。", 0.5, "blunt", "Make a counter-offer."),
           ("好的，我要了。", 0.4, "neutral", "Negotiate first — don't accept immediately."),
       ])],
      "押一付三 means deposit of one month + three months rent upfront — standard in China."),

    S("Weekend market shopping", "逛周末市场", 3, "casual", 0.5,
      "You're browsing a weekend flea market.", "你在逛周末跳蚤市场。",
      [npc("这个手工花瓶你看看，很漂亮的。", "zhè ge shǒugōng huāpíng nǐ kànkan, hěn piàoliang de.", "Take a look at this handmade vase, it's beautiful."),
       player("Show interest and ask the price.", [
           ("确实很漂亮。这个多少钱？", 1.0, "neutral", "Shows interest before asking price."),
           ("多少钱？", 0.6, "casual", "OK but complimenting first is better for negotiation."),
           ("不要。", 0.3, "blunt", "Rude if you even looked."),
       ]),
       npc("两百块。手工做的，独一无二。", "liǎng bǎi kuài. shǒugōng zuò de, dúyīwúèr.", "200 yuan. Handmade, one of a kind."),
       player("Try to negotiate.", [
           ("手工做的确实不容易。一百二可以吗？", 1.0, "casual", "Respects the craft while negotiating."),
           ("五十块。", 0.3, "casual", "Insulting offer for handmade work."),
           ("太贵了。", 0.5, "casual", "Make a counter-offer."),
       ])],
      "独一无二 means 'one of a kind' — sellers use it to justify prices at markets."),
]


def main():
    ensure_db()

    # Check existing count
    with connection() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM dialogue_scenario").fetchone()[0]
        print(f"Existing scenarios: {existing}")

    all_scenarios = HSK1 + HSK2 + HSK3

    # Check for title duplicates against existing DB
    with connection() as conn:
        existing_titles = {r[0] for r in conn.execute("SELECT title FROM dialogue_scenario").fetchall()}

    new = [s for s in all_scenarios if s["title"] not in existing_titles]
    skipped = len(all_scenarios) - len(new)
    if skipped:
        print(f"Skipping {skipped} scenarios with duplicate titles")

    if not new:
        print("No new scenarios to insert.")
        return

    with connection() as conn:
        for s in new:
            conn.execute("""
                INSERT INTO dialogue_scenario
                    (title, title_zh, hsk_level, register, scenario_type,
                     tree_json, difficulty, times_presented, avg_score, status, created_at)
                VALUES (?, ?, ?, ?, 'dialogue', ?, ?, 0, 0.0, 'active', datetime('now'))
            """, (s["title"], s["title_zh"], s["hsk_level"], s["register"],
                  s["tree_json"], s["difficulty"]))
        conn.commit()

    with connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM dialogue_scenario").fetchone()[0]
        dist = conn.execute("SELECT hsk_level, COUNT(*) FROM dialogue_scenario GROUP BY hsk_level ORDER BY hsk_level").fetchall()
        print(f"\nInserted {len(new)} new scenarios. Total: {total}")
        print("Distribution:")
        for r in dist:
            print(f"  HSK {r[0]}: {r[1]}")


if __name__ == "__main__":
    main()
