#!/usr/bin/env python3
"""Generate HSK 1-3 dialogue scenario files."""
import json
import os

OUT_DIR = "/Users/jasongerson/mandarin/content_gen/dialogues"

def write_dlg(filename, data):
    path = os.path.join(OUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"  wrote {filename}")

def dlg(title, title_zh, hsk, difficulty, setup, setup_zh, turns, cultural_note):
    return {
        "title": title,
        "title_zh": title_zh,
        "hsk_level": hsk,
        "register": "casual",
        "scenario_type": "dialogue",
        "difficulty": difficulty,
        "tree": {
            "setup": setup,
            "setup_zh": setup_zh,
            "turns": turns,
            "cultural_note": cultural_note
        }
    }

def npc(zh, pinyin, en):
    return {"speaker": "npc", "text_zh": zh, "text_pinyin": pinyin, "text_en": en}

def player(prompt_en, options):
    return {"speaker": "player", "prompt_en": prompt_en, "options": options}

def opt(zh, pinyin, en, score, feedback, register="casual"):
    o = {"text_zh": zh, "text_pinyin": pinyin, "text_en": en, "score": score, "feedback": feedback}
    if score == 1.0:
        o["register"] = register
    return o

# ============================================================
# HSK 1: j1_dlg_020 through j1_dlg_034 (15 dialogues)
# ============================================================
print("=== HSK 1 ===")

write_dlg("j1_dlg_020.json", dlg(
    "The Old Cat on the Wall", "墙上的老猫",
    1, 0.1,
    "You're sitting on a bench in your neighborhood. An elderly neighbor notices you watching a cat on a wall.",
    "你坐在小区的长椅上。一位老邻居看到你在看墙上的猫。",
    [
        npc("你也喜欢这只猫吗？它每天都在这里。", "Nǐ yě xǐhuan zhè zhī māo ma? Tā měi tiān dōu zài zhèlǐ.", "Do you like this cat too? It's here every day."),
        player("Share your feelings about the cat.", [
            opt("喜欢！它看起来很开心。", "Xǐhuan! Tā kàn qǐlái hěn kāixīn.", "Yes! It looks very happy.", 1.0, "Warm and observant — notices the cat's mood."),
            opt("今天很热。", "Jīntiān hěn rè.", "It's very hot today.", 0.0, "Off-topic — she asked about the cat."),
            opt("你家在哪里？", "Nǐ jiā zài nǎlǐ?", "Where is your home?", 0.0, "Off-topic — doesn't respond to her question about the cat.")
        ]),
        npc("是啊，它很喜欢晒太阳。我叫它「小花」。", "Shì a, tā hěn xǐhuan shài tàiyáng. Wǒ jiào tā「Xiǎo Huā」.", "Yes, it loves sunbathing. I call it Little Flower."),
        player("Respond to the cat's name.", [
            opt("「小花」！好名字。它是你的猫吗？", "「Xiǎo Huā」! Hǎo míngzi. Tā shì nǐ de māo ma?", "Little Flower! Good name. Is it your cat?", 1.0, "Friendly and curious — continues the conversation naturally."),
            opt("我不喝茶。", "Wǒ bù hē chá.", "I don't drink tea.", 0.0, "Off-topic — has nothing to do with the cat."),
            opt("现在几点？", "Xiànzài jǐ diǎn?", "What time is it now?", 0.0, "Off-topic — breaks the gentle moment about the cat.")
        ])
    ],
    "Neighborhood cats in China are often communal pets — no one officially owns them, but everyone feeds them and gives them names. They become part of the neighborhood's shared life."
))

write_dlg("j1_dlg_021.json", dlg(
    "Rain on the Window", "窗外的雨",
    1, 0.1,
    "It's raining outside. You're in a small café. The person at the next table looks out the window and speaks to you.",
    "外面下雨了。你在一家小咖啡店里。旁边的人看着窗外，跟你说话。",
    [
        npc("今天的雨好大。你有伞吗？", "Jīntiān de yǔ hǎo dà. Nǐ yǒu sǎn ma?", "The rain is really heavy today. Do you have an umbrella?"),
        player("Tell them about your umbrella situation.", [
            opt("没有，我没带伞。我想在这里等一等。", "Méiyǒu, wǒ méi dài sǎn. Wǒ xiǎng zài zhèlǐ děng yī děng.", "No, I didn't bring one. I'll wait here a bit.", 1.0, "Honest and relaxed — no rush to leave."),
            opt("我喜欢吃米饭。", "Wǒ xǐhuan chī mǐfàn.", "I like eating rice.", 0.0, "Off-topic — they asked about your umbrella."),
            opt("你是老师吗？", "Nǐ shì lǎoshī ma?", "Are you a teacher?", 0.0, "Off-topic — doesn't relate to the rain conversation.")
        ]),
        npc("我也是。下雨天在这里喝咖啡，很舒服。", "Wǒ yě shì. Xià yǔ tiān zài zhèlǐ hē kāfēi, hěn shūfu.", "Me too. Drinking coffee on a rainy day here is really nice."),
        player("Agree and share how you feel.", [
            opt("对，很安静。我很喜欢听雨的声音。", "Duì, hěn ānjìng. Wǒ hěn xǐhuan tīng yǔ de shēngyīn.", "Yes, it's very quiet. I love listening to the sound of rain.", 1.0, "Gentle and reflective — savors the rainy atmosphere."),
            opt("你有几个孩子？", "Nǐ yǒu jǐ ge háizi?", "How many children do you have?", 0.0, "Off-topic — too personal and unrelated to the moment."),
            opt("我想去北京。", "Wǒ xiǎng qù Běijīng.", "I want to go to Beijing.", 0.0, "Off-topic — breaks the cozy rainy-day mood.")
        ])
    ],
    "Rainy days in China often bring a sense of stillness. Many people use them as an excuse to slow down — sitting in a café, watching the rain, and enjoying a quiet moment with a stranger."
))

write_dlg("j1_dlg_022.json", dlg(
    "The Fruit Seller's Daughter", "水果店的女儿",
    1, 0.1,
    "You're buying fruit at a neighborhood stand. A little girl is helping her mother arrange the fruit.",
    "你在小区的水果摊买水果。一个小女孩在帮妈妈摆水果。",
    [
        npc("叔叔好！你想买什么水果？", "Shūshu hǎo! Nǐ xiǎng mǎi shénme shuǐguǒ?", "Hello, uncle! What fruit would you like to buy?"),
        player("Tell her what fruit you want.", [
            opt("我想买一些苹果。你帮妈妈做得真好！", "Wǒ xiǎng mǎi yīxiē píngguǒ. Nǐ bāng māma zuò de zhēn hǎo!", "I'd like some apples. You're really good at helping your mom!", 1.0, "Kind and encouraging — acknowledges her effort."),
            opt("你爸爸在哪里工作？", "Nǐ bàba zài nǎlǐ gōngzuò?", "Where does your dad work?", 0.0, "Off-topic — she asked what fruit you want."),
            opt("我不喜欢学习。", "Wǒ bù xǐhuan xuéxí.", "I don't like studying.", 0.0, "Off-topic — a strange thing to say to a child at a fruit stand.")
        ]),
        npc("谢谢叔叔！这些苹果很甜的！妈妈说今天的最好。", "Xièxie shūshu! Zhèxiē píngguǒ hěn tián de! Māma shuō jīntiān de zuì hǎo.", "Thank you, uncle! These apples are really sweet! Mom says today's are the best."),
        player("Respond to her recommendation.", [
            opt("好，那我买五个。谢谢你！", "Hǎo, nà wǒ mǎi wǔ ge. Xièxie nǐ!", "Okay, I'll buy five then. Thank you!", 1.0, "Warm — trusts her recommendation."),
            opt("明天会下雨吗？", "Míngtiān huì xià yǔ ma?", "Will it rain tomorrow?", 0.0, "Off-topic — she's telling you about the apples."),
            opt("我要回家了。", "Wǒ yào huí jiā le.", "I'm going home now.", 0.0, "Off-topic — abruptly ends the interaction without buying anything.")
        ])
    ],
    "Children helping at family businesses is a common sight in Chinese neighborhoods. It teaches responsibility early and strengthens family bonds. Addressing a young man as 叔叔 (uncle) is a polite convention for children."
))

write_dlg("j1_dlg_023.json", dlg(
    "Lost in the Park", "在公园迷路了",
    1, 0.1,
    "You're walking in a park and realize you don't know which way is the exit. A jogger stops nearby.",
    "你在公园散步，发现不知道出口在哪里。一个跑步的人停下来。",
    [
        npc("你好！你在找什么吗？", "Nǐ hǎo! Nǐ zài zhǎo shénme ma?", "Hello! Are you looking for something?"),
        player("Ask for directions to the exit.", [
            opt("你好！请问出口在哪里？", "Nǐ hǎo! Qǐngwèn chūkǒu zài nǎlǐ?", "Hello! Could you tell me where the exit is?", 1.0, "Polite and direct — asks clearly for help."),
            opt("你喜欢什么颜色？", "Nǐ xǐhuan shénme yánsè?", "What color do you like?", 0.0, "Off-topic — you need to ask for directions."),
            opt("我有两个哥哥。", "Wǒ yǒu liǎng ge gēge.", "I have two older brothers.", 0.0, "Off-topic — doesn't help you find the exit.")
        ]),
        npc("出口啊？你往前走，然后往左，就到了。很近。", "Chūkǒu a? Nǐ wǎng qián zǒu, ránhòu wǎng zuǒ, jiù dào le. Hěn jìn.", "The exit? Walk forward, then turn left, and you're there. Very close."),
        player("Thank them for the help.", [
            opt("太好了，谢谢你！这个公园很大。", "Tài hǎo le, xièxie nǐ! Zhège gōngyuán hěn dà.", "Great, thank you! This park is really big.", 1.0, "Grateful and natural — adds a small observation."),
            opt("你几岁了？", "Nǐ jǐ suì le?", "How old are you?", 0.0, "Off-topic — an odd question to ask a stranger who just helped you."),
            opt("我不想去。", "Wǒ bù xiǎng qù.", "I don't want to go.", 0.0, "Off-topic — you just asked for the exit.")
        ])
    ],
    "Chinese parks are often large and maze-like by design, with winding paths meant to encourage wandering. Getting a little lost is part of the experience. People are generally very willing to help with directions."
))

write_dlg("j1_dlg_024.json", dlg(
    "A Quiet Library Morning", "安静的图书馆早上",
    1, 0.1,
    "You arrive at the neighborhood library early. The librarian is shelving books and smiles at you.",
    "你一早就到了社区图书馆。图书管理员在整理书，对你微笑。",
    [
        npc("早上好！今天来得很早啊。你想看什么书？", "Zǎoshang hǎo! Jīntiān lái de hěn zǎo a. Nǐ xiǎng kàn shénme shū?", "Good morning! You're here early today. What kind of book would you like to read?"),
        player("Tell the librarian what you'd like to read.", [
            opt("我想看一本中文书。有没有很简单的？", "Wǒ xiǎng kàn yī běn Zhōngwén shū. Yǒu méiyǒu hěn jiǎndān de?", "I'd like to read a Chinese book. Do you have a very simple one?", 1.0, "Honest and clear — asks for something at your level."),
            opt("你的电话号码是多少？", "Nǐ de diànhuà hàomǎ shì duōshao?", "What's your phone number?", 0.0, "Off-topic — she asked what book you want to read."),
            opt("我昨天没吃饭。", "Wǒ zuótiān méi chī fàn.", "I didn't eat yesterday.", 0.0, "Off-topic — unrelated to choosing a book.")
        ]),
        npc("有的！这本是写给小朋友的，很好看。你试试？", "Yǒu de! Zhè běn shì xiě gěi xiǎopéngyou de, hěn hǎokàn. Nǐ shìshi?", "Yes! This one is written for children, it's very good. Want to try it?"),
        player("Respond to her suggestion.", [
            opt("好的，谢谢你！我在这里看。", "Hǎo de, xièxie nǐ! Wǒ zài zhèlǐ kàn.", "Okay, thank you! I'll read it here.", 1.0, "Appreciative — accepts the recommendation gracefully."),
            opt("我的狗很大。", "Wǒ de gǒu hěn dà.", "My dog is very big.", 0.0, "Off-topic — she's recommending a book to you."),
            opt("今天星期三。", "Jīntiān xīngqīsān.", "Today is Wednesday.", 0.0, "Off-topic — doesn't respond to her suggestion.")
        ])
    ],
    "Community libraries (社区图书馆) in China are quiet refuges. Librarians often take a personal interest in helping readers, especially those learning Chinese. Reading children's books is a respected way to build literacy."
))

write_dlg("j1_dlg_025.json", dlg(
    "Waiting for the Bus", "等公交车",
    1, 0.1,
    "You're at a bus stop in the morning. An old man is also waiting. He starts a conversation.",
    "早上你在公交车站等车。一位老爷爷也在等车。他开始聊天。",
    [
        npc("今天天气真好。你去哪里？", "Jīntiān tiānqì zhēn hǎo. Nǐ qù nǎlǐ?", "The weather is really nice today. Where are you going?"),
        player("Tell him where you're headed.", [
            opt("我去学校。今天有中文课。", "Wǒ qù xuéxiào. Jīntiān yǒu Zhōngwén kè.", "I'm going to school. I have Chinese class today.", 1.0, "Friendly and specific — shares your plan."),
            opt("你有几只猫？", "Nǐ yǒu jǐ zhī māo?", "How many cats do you have?", 0.0, "Off-topic — he asked where you're going."),
            opt("这个不好吃。", "Zhège bù hǎochī.", "This doesn't taste good.", 0.0, "Off-topic — makes no sense at a bus stop.")
        ]),
        npc("学中文？好啊！我年轻的时候也喜欢学东西。", "Xué Zhōngwén? Hǎo a! Wǒ niánqīng de shíhou yě xǐhuan xué dōngxi.", "Learning Chinese? Great! When I was young, I also loved learning things."),
        player("Respond to his kind words.", [
            opt("中文很有意思。您每天都坐这路车吗？", "Zhōngwén hěn yǒu yìsi. Nín měi tiān dōu zuò zhè lù chē ma?", "Chinese is very interesting. Do you take this bus every day?", 1.0, "Polite and engaging — uses 您 respectfully and shows interest."),
            opt("我想买手机。", "Wǒ xiǎng mǎi shǒujī.", "I want to buy a phone.", 0.0, "Off-topic — he's sharing a personal memory."),
            opt("再见。", "Zàijiàn.", "Goodbye.", 0.0, "Off-topic — abruptly ends a nice conversation.")
        ])
    ],
    "Bus stops in Chinese cities are natural social spaces, especially for older residents. The elderly often enjoy chatting with younger people. Using 您 instead of 你 shows respect for elders."
))

write_dlg("j1_dlg_026.json", dlg(
    "The Neighbor's Dog", "邻居的狗",
    1, 0.1,
    "You're coming home and see your neighbor walking a small dog in the courtyard.",
    "你回家的时候看到邻居在院子里遛一只小狗。",
    [
        npc("你回来了！你看，我家新买了一只小狗。", "Nǐ huílái le! Nǐ kàn, wǒ jiā xīn mǎi le yī zhī xiǎo gǒu.", "You're back! Look, we got a new puppy."),
        player("React to the new puppy.", [
            opt("好可爱啊！它叫什么名字？", "Hǎo kě'ài a! Tā jiào shénme míngzi?", "So cute! What's its name?", 1.0, "Natural and warm — shows genuine interest."),
            opt("我今天很忙。", "Wǒ jīntiān hěn máng.", "I'm very busy today.", 0.0, "Off-topic — dismisses their excitement about the puppy."),
            opt("你会做饭吗？", "Nǐ huì zuòfàn ma?", "Can you cook?", 0.0, "Off-topic — they're showing you their new dog.")
        ]),
        npc("它叫「豆豆」。才两个月大。你想摸摸它吗？", "Tā jiào「Dòudou」. Cái liǎng ge yuè dà. Nǐ xiǎng mō mo tā ma?", "Its name is Doudou. Only two months old. Do you want to pet it?"),
        player("Respond to the offer to pet the puppy.", [
            opt("好啊！「豆豆」，你好！真的好小。", "Hǎo a!「Dòudou」, nǐ hǎo! Zhēn de hǎo xiǎo.", "Sure! Hello, Doudou! Really so small.", 1.0, "Playful and gentle — engages with the puppy directly."),
            opt("我要去超市。", "Wǒ yào qù chāoshì.", "I need to go to the supermarket.", 0.0, "Off-topic — ignores the offer to pet the puppy."),
            opt("明天下雨。", "Míngtiān xià yǔ.", "It'll rain tomorrow.", 0.0, "Off-topic — a strange response to being offered to pet a puppy.")
        ])
    ],
    "Chinese neighborhood courtyards (院子) are communal spaces where neighbors naturally interact. Pets, especially small dogs, are popular conversation starters. Cute names like 豆豆 (Doudou, 'little bean') are very common."
))

write_dlg("j1_dlg_027.json", dlg(
    "Sharing Tangerines", "分橘子",
    1, 0.1,
    "Your colleague brings a bag of tangerines to the office. She offers you some.",
    "你的同事带了一袋橘子到办公室。她给你一些。",
    [
        npc("我妈妈给了我很多橘子。你要不要吃一个？", "Wǒ māma gěi le wǒ hěn duō júzi. Nǐ yào bú yào chī yī ge?", "My mom gave me lots of tangerines. Want to have one?"),
        player("Respond to her offer.", [
            opt("好啊，谢谢！你妈妈真好。", "Hǎo a, xièxie! Nǐ māma zhēn hǎo.", "Sure, thanks! Your mom is really kind.", 1.0, "Warm and grateful — appreciates the gesture."),
            opt("你会开车吗？", "Nǐ huì kāichē ma?", "Can you drive?", 0.0, "Off-topic — she's offering you fruit."),
            opt("我不认识他。", "Wǒ bú rènshi tā.", "I don't know him.", 0.0, "Off-topic — doesn't relate to the tangerines.")
        ]),
        npc("她家有很多橘子树。每年都会给我很多。这些特别甜。", "Tā jiā yǒu hěn duō júzi shù. Měi nián dōu huì gěi wǒ hěn duō. Zhèxiē tèbié tián.", "She has lots of tangerine trees at home. Every year she gives me a lot. These are especially sweet."),
        player("Continue the conversation about the tangerines.", [
            opt("真的好甜！我很喜欢。你妈妈家在哪里？", "Zhēn de hǎo tián! Wǒ hěn xǐhuan. Nǐ māma jiā zài nǎlǐ?", "Really sweet! I like them a lot. Where is your mom's home?", 1.0, "Engaged and warm — shows interest in her family."),
            opt("我想睡觉。", "Wǒ xiǎng shuìjiào.", "I want to sleep.", 0.0, "Off-topic — she's sharing something nice with you."),
            opt("今天是星期五。", "Jīntiān shì xīngqīwǔ.", "Today is Friday.", 0.0, "Off-topic — doesn't connect to the tangerine conversation.")
        ])
    ],
    "Sharing food from home is a deep Chinese social ritual. When a parent sends fruit or homemade food, sharing it with colleagues strengthens workplace bonds. Refusing would be slightly awkward — accepting graciously is the warm response."
))

write_dlg("j1_dlg_028.json", dlg(
    "Evening Walk by the River", "河边的晚走",
    1, 0.1,
    "You're taking an evening walk along a small river. A woman is sitting on a bench, feeding fish.",
    "你在小河边散步。一位女士坐在长椅上喂鱼。",
    [
        npc("你也来散步吗？这里的鱼很多。你看！", "Nǐ yě lái sànbù ma? Zhèlǐ de yú hěn duō. Nǐ kàn!", "Are you here for a walk too? There are so many fish here. Look!"),
        player("Respond to her observation about the fish.", [
            opt("哇，真的好多！你每天都来喂鱼吗？", "Wā, zhēn de hǎo duō! Nǐ měi tiān dōu lái wèi yú ma?", "Wow, really so many! Do you come to feed the fish every day?", 1.0, "Enthusiastic and curious — connects over a shared moment."),
            opt("我不会游泳。", "Wǒ bú huì yóuyǒng.", "I can't swim.", 0.0, "Off-topic — she's talking about fish, not swimming."),
            opt("你的衣服很好看。", "Nǐ de yīfu hěn hǎokàn.", "Your clothes look nice.", 0.0, "Off-topic — she's pointing out the fish to you.")
        ]),
        npc("差不多每天都来。吃完饭以后走一走，看看鱼，心情很好。", "Chàbuduō měi tiān dōu lái. Chī wán fàn yǐhòu zǒu yī zǒu, kàn kan yú, xīnqíng hěn hǎo.", "Almost every day. After dinner I walk a bit, watch the fish, and it puts me in a good mood."),
        player("Share your feelings about the evening.", [
            opt("我也觉得。晚上在这里走走很舒服。", "Wǒ yě juéde. Wǎnshang zài zhèlǐ zǒu zou hěn shūfu.", "I think so too. Walking here in the evening is really comfortable.", 1.0, "Gentle agreement — shares the peaceful feeling."),
            opt("我要去买东西。", "Wǒ yào qù mǎi dōngxi.", "I need to go shopping.", 0.0, "Off-topic — breaks the quiet evening mood."),
            opt("你会说英文吗？", "Nǐ huì shuō Yīngwén ma?", "Can you speak English?", 0.0, "Off-topic — an abrupt shift from the peaceful conversation.")
        ])
    ],
    "Evening riverside walks (散步) are a beloved Chinese ritual, especially after dinner. Feeding fish in neighborhood ponds is a meditative activity. These quiet encounters between strangers are ordinary but deeply restorative."
))

write_dlg("j1_dlg_029.json", dlg(
    "The Tea Shop", "茶店",
    1, 0.1,
    "You wander into a small tea shop. The owner is an older man who looks up from his teapot.",
    "你走进一家小茶店。老板是一位老先生，他从茶壶旁抬头看你。",
    [
        npc("进来坐坐！你喝过中国茶吗？", "Jìnlái zuò zuo! Nǐ hē guò Zhōngguó chá ma?", "Come in and sit! Have you tried Chinese tea?"),
        player("Tell him about your tea experience.", [
            opt("喝过一点。我很喜欢，但是不太懂。", "Hē guò yīdiǎn. Wǒ hěn xǐhuan, dànshì bú tài dǒng.", "I've had a little. I like it a lot, but I don't know much about it.", 1.0, "Honest and humble — opens the door to learning."),
            opt("这个椅子不舒服。", "Zhège yǐzi bù shūfu.", "This chair is uncomfortable.", 0.0, "Off-topic — rude to say when he just invited you to sit."),
            opt("我想学做饭。", "Wǒ xiǎng xué zuòfàn.", "I want to learn to cook.", 0.0, "Off-topic — he's asking about tea, not cooking.")
        ]),
        npc("没关系！来，我给你泡一杯。这个是绿茶，很好喝。", "Méi guānxi! Lái, wǒ gěi nǐ pào yī bēi. Zhège shì lǜchá, hěn hǎo hē.", "No worries! Here, I'll brew you a cup. This is green tea, it's very good."),
        player("Respond after tasting the tea.", [
            opt("真的很好喝！谢谢您。", "Zhēn de hěn hǎo hē! Xièxie nín.", "It's really delicious! Thank you.", 1.0, "Appreciative and polite — uses 您 to show respect."),
            opt("太贵了。", "Tài guì le.", "Too expensive.", 0.0, "Off-topic — he offered it to you, not sold it."),
            opt("我要走了。", "Wǒ yào zǒu le.", "I need to go.", 0.0, "Off-topic — leaving right after he brewed tea would be impolite.")
        ])
    ],
    "Tea shops in China are places of rest and conversation. Shop owners often invite passersby to sit and taste tea with no obligation to buy. It's a generous tradition rooted in hospitality. Using 您 shows respect for elders."
))

write_dlg("j1_dlg_030.json", dlg(
    "Flowers at the Market", "菜市场的花",
    1, 0.1,
    "You're at the morning market and notice a flower stall. The seller is arranging bouquets.",
    "你在早市上看到一个花摊。卖花的人在整理花束。",
    [
        npc("你好！想买花吗？今天的花很新鲜。", "Nǐ hǎo! Xiǎng mǎi huā ma? Jīntiān de huā hěn xīnxiān.", "Hello! Want to buy flowers? Today's flowers are very fresh."),
        player("Respond to the flower seller.", [
            opt("好漂亮！这些是什么花？", "Hǎo piàoliang! Zhèxiē shì shénme huā?", "So beautiful! What kind of flowers are these?", 1.0, "Curious and appreciative — asks to learn more."),
            opt("我不喜欢早起。", "Wǒ bù xǐhuan zǎo qǐ.", "I don't like waking up early.", 0.0, "Off-topic — she's asking if you want flowers."),
            opt("这里有厕所吗？", "Zhèlǐ yǒu cèsuǒ ma?", "Is there a restroom here?", 0.0, "Off-topic — unrelated to the flower stall.")
        ]),
        npc("这些是百合花。你可以买几枝回家，放在桌子上很好看。", "Zhèxiē shì bǎihé huā. Nǐ kěyǐ mǎi jǐ zhī huí jiā, fàng zài zhuōzi shàng hěn hǎokàn.", "These are lilies. You can buy a few to take home — they look lovely on a table."),
        player("Decide whether to buy.", [
            opt("好，我买三枝。多少钱？", "Hǎo, wǒ mǎi sān zhī. Duōshao qián?", "Okay, I'll buy three. How much?", 1.0, "Decisive and friendly — follows through on the purchase."),
            opt("我的老师很好。", "Wǒ de lǎoshī hěn hǎo.", "My teacher is very good.", 0.0, "Off-topic — she's telling you about the lilies."),
            opt("你认识我的朋友吗？", "Nǐ rènshi wǒ de péngyou ma?", "Do you know my friend?", 0.0, "Off-topic — a strange question for a flower seller.")
        ])
    ],
    "Morning wet markets (菜市场) in China often have flower stalls alongside vegetables and meat. Buying fresh flowers for the home is an affordable daily pleasure, not reserved for special occasions. Lilies (百合) symbolize harmony."
))

write_dlg("j1_dlg_031.json", dlg(
    "A Photo of Home", "家的照片",
    1, 0.2,
    "Your classmate sees you looking at a photo on your phone during break. It's a photo from your hometown.",
    "课间休息时，你的同学看到你在看手机上的照片。那是你家乡的照片。",
    [
        npc("你在看什么？那是哪里？好漂亮！", "Nǐ zài kàn shénme? Nà shì nǎlǐ? Hǎo piàoliang!", "What are you looking at? Where is that? So pretty!"),
        player("Tell them about the photo.", [
            opt("这是我的家。那里有很多树，很安静。", "Zhè shì wǒ de jiā. Nàlǐ yǒu hěn duō shù, hěn ānjìng.", "This is my home. There are many trees there, it's very quiet.", 1.0, "Warm and personal — shares something meaningful."),
            opt("我不知道。", "Wǒ bù zhīdào.", "I don't know.", 0.0, "Off-topic — it's your own photo."),
            opt("你想喝水吗？", "Nǐ xiǎng hē shuǐ ma?", "Do you want water?", 0.0, "Off-topic — they asked about the photo.")
        ]),
        npc("好想去看看。你想家吗？", "Hǎo xiǎng qù kànkan. Nǐ xiǎng jiā ma?", "I'd love to visit. Do you miss home?"),
        player("Share your feelings about home.", [
            opt("有时候想。但是我在这里也很开心。", "Yǒu shíhou xiǎng. Dànshì wǒ zài zhèlǐ yě hěn kāixīn.", "Sometimes. But I'm also happy here.", 1.0, "Honest and balanced — acknowledges both feelings."),
            opt("我喜欢吃鸡肉。", "Wǒ xǐhuan chī jīròu.", "I like eating chicken.", 0.0, "Off-topic — they asked if you miss home."),
            opt("你的书在哪里？", "Nǐ de shū zài nǎlǐ?", "Where is your book?", 0.0, "Off-topic — doesn't respond to the emotional question.")
        ])
    ],
    "Homesickness (想家) is a deeply understood feeling in Chinese culture, where many people live far from their hometowns for work or study. Sharing photos from home is a way to keep connections alive."
))

write_dlg("j1_dlg_032.json", dlg(
    "The Sound of a Piano", "钢琴的声音",
    1, 0.2,
    "Walking through your apartment hallway, you hear someone playing piano. Your neighbor opens her door.",
    "你走在公寓走廊里，听到有人弹钢琴。你的邻居开了门。",
    [
        npc("不好意思，太吵了吗？我女儿在练琴。", "Bù hǎo yìsi, tài chǎo le ma? Wǒ nǚ'ér zài liàn qín.", "Sorry, is it too loud? My daughter is practicing piano."),
        player("Reassure your neighbor.", [
            opt("没有没有！弹得很好听。", "Méiyǒu méiyǒu! Tán de hěn hǎotīng.", "Not at all! It sounds really beautiful.", 1.0, "Kind and reassuring — puts the neighbor at ease."),
            opt("我想买一只猫。", "Wǒ xiǎng mǎi yī zhī māo.", "I want to buy a cat.", 0.0, "Off-topic — she's asking if the piano is too loud."),
            opt("你是哪里人？", "Nǐ shì nǎlǐ rén?", "Where are you from?", 0.0, "Off-topic — doesn't address her concern.")
        ]),
        npc("真的吗？她才学了三个月。她听到你这样说会很高兴的。", "Zhēn de ma? Tā cái xué le sān ge yuè. Tā tīng dào nǐ zhèyàng shuō huì hěn gāoxìng de.", "Really? She's only been learning for three months. She'll be so happy to hear that."),
        player("Respond warmly.", [
            opt("三个月就这么好！请告诉她加油。", "Sān ge yuè jiù zhème hǎo! Qǐng gàosu tā jiāyóu.", "This good after only three months! Please tell her to keep it up.", 1.0, "Encouraging — supports the child's effort genuinely."),
            opt("我明天不在家。", "Wǒ míngtiān bú zài jiā.", "I won't be home tomorrow.", 0.0, "Off-topic — sounds like you're hinting the noise bothers you."),
            opt("你家有几个人？", "Nǐ jiā yǒu jǐ ge rén?", "How many people are in your family?", 0.0, "Off-topic — she's sharing her daughter's achievement.")
        ])
    ],
    "Piano practice is extremely common in Chinese apartments. Neighbors often worry about noise, so reassuring them is a kindness. 加油 (jiāyóu) is the standard encouragement, meaning 'keep going' or 'you can do it.'"
))

write_dlg("j1_dlg_033.json", dlg(
    "A Warm Bowl of Noodles", "一碗热面条",
    1, 0.2,
    "You sit down at a tiny noodle shop on a cold day. The owner comes to take your order.",
    "天气很冷，你走进一家很小的面馆坐下。老板来问你要吃什么。",
    [
        npc("外面好冷吧？来碗热面？我们有牛肉面和鸡蛋面。", "Wàimiàn hǎo lěng ba? Lái wǎn rè miàn? Wǒmen yǒu niúròu miàn hé jīdàn miàn.", "It's cold outside, right? How about a hot bowl of noodles? We have beef noodles and egg noodles."),
        player("Order your noodles.", [
            opt("我要一碗牛肉面，谢谢！", "Wǒ yào yī wǎn niúròu miàn, xièxie!", "I'll have a bowl of beef noodles, thanks!", 1.0, "Clear and polite — a satisfying order."),
            opt("你们有WiFi吗？", "Nǐmen yǒu WiFi ma?", "Do you have WiFi?", 0.0, "Off-topic — he's asking what noodles you want."),
            opt("我不冷。", "Wǒ bù lěng.", "I'm not cold.", 0.0, "Off-topic — you came in from the cold and sat down to eat.")
        ]),
        npc("好的！很快。你第一次来我们这里吗？", "Hǎo de! Hěn kuài. Nǐ dì yī cì lái wǒmen zhèlǐ ma?", "Okay! It'll be quick. Is this your first time here?"),
        player("Tell him about your visit.", [
            opt("是第一次。朋友说这里的面很好吃。", "Shì dì yī cì. Péngyou shuō zhèlǐ de miàn hěn hǎochī.", "Yes, first time. A friend said the noodles here are really good.", 1.0, "Friendly — a compliment that will make the owner happy."),
            opt("我不喜欢下雨。", "Wǒ bù xǐhuan xià yǔ.", "I don't like rain.", 0.0, "Off-topic — he asked if you've been here before."),
            opt("我要回家了。", "Wǒ yào huí jiā le.", "I'm going home now.", 0.0, "Off-topic — you just ordered noodles.")
        ])
    ],
    "Tiny noodle shops (面馆) are the soul of Chinese street food culture. Owners often chat with customers like old friends. Coming in from the cold for a bowl of hot noodles is one of life's simple comforts."
))

write_dlg("j1_dlg_034.json", dlg(
    "Stars from the Balcony", "阳台上看星星",
    1, 0.2,
    "Late at night, you step onto your balcony. Your neighbor is also on theirs, looking up at the sky.",
    "很晚了，你走到阳台上。你的邻居也在阳台上，看着天空。",
    [
        npc("今天晚上的星星好多啊。你也看到了吗？", "Jīntiān wǎnshang de xīngxing hǎo duō a. Nǐ yě kàn dào le ma?", "There are so many stars tonight. Can you see them too?"),
        player("Share your observation.", [
            opt("看到了！好漂亮。平时看不到这么多。", "Kàn dào le! Hǎo piàoliang. Píngshí kàn bú dào zhème duō.", "I see them! So beautiful. Usually you can't see this many.", 1.0, "Observant and present — savors the rare sight."),
            opt("我明天要考试。", "Wǒ míngtiān yào kǎoshì.", "I have an exam tomorrow.", 0.0, "Off-topic — they're talking about the beautiful stars."),
            opt("你吃晚饭了吗？", "Nǐ chī wǎnfàn le ma?", "Have you eaten dinner?", 0.0, "Off-topic — it's late at night and the moment is about the sky.")
        ]),
        npc("是啊。我小时候在老家，每天晚上都能看到。在城市里很难看到。", "Shì a. Wǒ xiǎo shíhou zài lǎojiā, měi tiān wǎnshang dōu néng kàn dào. Zài chéngshì lǐ hěn nán kàn dào.", "Yes. When I was a child in my hometown, I could see them every night. In the city it's hard to see them."),
        player("Respond to their memory.", [
            opt("你的老家一定很美。今晚很特别。", "Nǐ de lǎojiā yīdìng hěn měi. Jīn wǎn hěn tèbié.", "Your hometown must be beautiful. Tonight is special.", 1.0, "Gentle and thoughtful — honors their memory while savoring the moment."),
            opt("我想买一台电脑。", "Wǒ xiǎng mǎi yī tái diànnǎo.", "I want to buy a computer.", 0.0, "Off-topic — a jarring shift from the intimate conversation."),
            opt("几点了？", "Jǐ diǎn le?", "What time is it?", 0.0, "Off-topic — breaks the quiet spell of stargazing.")
        ])
    ],
    "Light pollution in Chinese cities makes starry nights rare. When the stars do appear, they stir nostalgia for rural hometowns (老家) where the sky was always clear. These balcony conversations between neighbors are fleeting but meaningful."
))

print("HSK 1 complete: 15 files written")
