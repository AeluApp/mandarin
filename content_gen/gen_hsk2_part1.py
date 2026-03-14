#!/usr/bin/env python3
"""Generate HSK 2 dialogue scenarios, part 1 (001-022)."""
import json, os

OUT_DIR = "/Users/jasongerson/mandarin/content_gen/dialogues"

def write_dlg(filename, data):
    with open(os.path.join(OUT_DIR, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"  wrote {filename}")

def dlg(title, title_zh, hsk, difficulty, setup, setup_zh, turns, cultural_note):
    return {"title": title, "title_zh": title_zh, "hsk_level": hsk, "register": "casual",
            "scenario_type": "dialogue", "difficulty": difficulty,
            "tree": {"setup": setup, "setup_zh": setup_zh, "turns": turns, "cultural_note": cultural_note}}

def npc(zh, pinyin, en):
    return {"speaker": "npc", "text_zh": zh, "text_pinyin": pinyin, "text_en": en}

def player(prompt_en, options):
    return {"speaker": "player", "prompt_en": prompt_en, "options": options}

def opt(zh, pinyin, en, score, feedback, register="casual"):
    o = {"text_zh": zh, "text_pinyin": pinyin, "text_en": en, "score": score, "feedback": feedback}
    if score == 1.0: o["register"] = register
    return o

print("=== HSK 2 Part 1 (001-022) ===")

write_dlg("j2_dlg_001.json", dlg(
    "The Bookshop Around the Corner", "转角的书店",
    2, 0.3,
    "You discover a small second-hand bookshop in a quiet alley. The owner is reading behind the counter.",
    "你在一条安静的小巷里发现了一家二手书店。老板在柜台后面看书。",
    [
        npc("欢迎！随便看看。你喜欢看什么样的书？", "Huānyíng! Suíbiàn kànkan. Nǐ xǐhuan kàn shénme yàng de shū?", "Welcome! Feel free to browse. What kind of books do you like?"),
        player("Tell him what kind of books interest you.", [
            opt("我喜欢看故事书。有没有比较简单的中文小说？", "Wǒ xǐhuan kàn gùshi shū. Yǒu méiyǒu bǐjiào jiǎndān de Zhōngwén xiǎoshuō?", "I like storybooks. Do you have any relatively simple Chinese novels?", 1.0, "Honest about your level — opens a helpful conversation."),
            opt("这条路怎么走？", "Zhè tiáo lù zěnme zǒu?", "How do I get down this road?", 0.0, "Off-topic — you just walked into the shop."),
            opt("我的手机没电了。", "Wǒ de shǒujī méi diàn le.", "My phone is out of battery.", 0.0, "Off-topic — he asked about your reading preferences.")
        ]),
        npc("有的。这本不错，是一个很温暖的故事。很多外国朋友都喜欢。", "Yǒu de. Zhè běn búcuò, shì yī ge hěn wēnnuǎn de gùshi. Hěn duō wàiguó péngyou dōu xǐhuan.", "Yes. This one is nice — it's a warm story. Many foreign friends like it."),
        player("Respond to his recommendation.", [
            opt("看起来很有意思。多少钱一本？", "Kàn qǐlái hěn yǒu yìsi. Duōshao qián yī běn?", "It looks interesting. How much per copy?", 1.0, "Engaged — shows genuine interest."),
            opt("我不想买东西。", "Wǒ bù xiǎng mǎi dōngxi.", "I don't want to buy anything.", 0.0, "Off-topic — dismissive when he's being helpful."),
            opt("你结婚了吗？", "Nǐ jiéhūn le ma?", "Are you married?", 0.0, "Off-topic — a very personal question for a shopkeeper.")
        ]),
        npc("这本只要十块钱。二手书便宜。你要是喜欢，下次来我帮你找更多。", "Zhè běn zhǐ yào shí kuài qián. Èrshǒu shū piányi. Nǐ yàoshi xǐhuan, xià cì lái wǒ bāng nǐ zhǎo gèng duō.", "This one is only ten yuan. Second-hand books are cheap. If you like it, next time I'll find more for you."),
        player("Accept his kind offer.", [
            opt("太好了！我一定会再来。谢谢你推荐。", "Tài hǎo le! Wǒ yīdìng huì zài lái. Xièxie nǐ tuījiàn.", "Great! I'll definitely come back. Thanks for the recommendation.", 1.0, "Warm and grateful — builds a connection."),
            opt("我不喜欢这个颜色。", "Wǒ bù xǐhuan zhège yánsè.", "I don't like this color.", 0.0, "Off-topic — he's offering to help you find more books."),
            opt("外面下雨了吗？", "Wàimiàn xià yǔ le ma?", "Is it raining outside?", 0.0, "Off-topic — he just made a kind offer.")
        ])
    ],
    "Second-hand bookshops (二手书店) are quiet havens in Chinese cities. Owners often curate personal collections and love recommending books. The low prices make reading accessible, and returning customers become friends."
))

write_dlg("j2_dlg_002.json", dlg(
    "Morning Tai Chi in the Park", "公园里的早操",
    2, 0.3,
    "You're jogging in the park and notice a group of elderly people doing tai chi. One of them waves you over.",
    "你在公园跑步，看到一群老人在打太极拳。其中一位向你招手。",
    [
        npc("年轻人，过来一起练练！太极拳对身体很好。", "Niánqīng rén, guòlái yīqǐ liàn lian! Tàijí quán duì shēntǐ hěn hǎo.", "Young person, come practice with us! Tai chi is very good for the body."),
        player("Respond to the invitation.", [
            opt("好啊！但是我没学过，可以教我吗？", "Hǎo a! Dànshì wǒ méi xué guò, kěyǐ jiāo wǒ ma?", "Sure! But I've never learned — can you teach me?", 1.0, "Open and enthusiastic — willing to try something new."),
            opt("我跑步比较快。", "Wǒ pǎobù bǐjiào kuài.", "I run pretty fast.", 0.0, "Off-topic — he's inviting you to do tai chi, not run."),
            opt("这个公园有厕所吗？", "Zhège gōngyuán yǒu cèsuǒ ma?", "Is there a restroom in this park?", 0.0, "Off-topic — ignores his kind invitation.")
        ]),
        npc("当然可以！你跟着我做就行了。慢慢来，不着急。", "Dāngrán kěyǐ! Nǐ gēnzhe wǒ zuò jiù xíng le. Mànmàn lái, bù zháojí.", "Of course! Just follow me. Take it slow, no rush."),
        player("Try and share how it feels.", [
            opt("感觉很放松。难怪你们每天都来。", "Gǎnjué hěn fàngsōng. Nánguài nǐmen měi tiān dōu lái.", "It feels very relaxing. No wonder you all come every day.", 1.0, "Genuine observation — connects to their daily practice."),
            opt("我觉得跑步更好。", "Wǒ juéde pǎobù gèng hǎo.", "I think running is better.", 0.0, "Off-topic — dismisses what they're sharing with you."),
            opt("现在几点了？", "Xiànzài jǐ diǎn le?", "What time is it?", 0.0, "Off-topic — seems like you're trying to leave.")
        ])
    ],
    "Morning tai chi (太极拳) groups in parks are a beloved Chinese tradition. The elderly practitioners often welcome newcomers warmly. The phrase 慢慢来 (take it slow) reflects a core philosophy of patience in Chinese wellness culture."
))

write_dlg("j2_dlg_003.json", dlg(
    "The Dumpling Lesson", "包饺子",
    2, 0.3,
    "Your landlady invites you to help make dumplings for the weekend. You sit together at the kitchen table.",
    "房东阿姨邀请你周末一起包饺子。你们坐在厨房桌子旁。",
    [
        npc("你包过饺子吗？不难的，我教你。", "Nǐ bāo guò jiǎozi ma? Bù nán de, wǒ jiāo nǐ.", "Have you ever made dumplings? It's not hard — I'll teach you."),
        player("Tell her about your dumpling experience.", [
            opt("没包过，但是我很想学！看起来很有意思。", "Méi bāo guò, dànshì wǒ hěn xiǎng xué! Kàn qǐlái hěn yǒu yìsi.", "Never made them, but I really want to learn! It looks fun.", 1.0, "Eager and honest — ready to learn."),
            opt("我不饿。", "Wǒ bú è.", "I'm not hungry.", 0.0, "Off-topic — she's inviting you to make dumplings, not eat right now."),
            opt("你家的厨房很大。", "Nǐ jiā de chúfáng hěn dà.", "Your kitchen is very big.", 0.0, "Off-topic — she asked about dumpling experience.")
        ]),
        npc("你看，先把馅放在皮上，然后这样捏。你试试。", "Nǐ kàn, xiān bǎ xiàn fàng zài pí shàng, ránhòu zhèyàng niē. Nǐ shìshi.", "See, first put the filling on the wrapper, then pinch like this. You try."),
        player("Try making a dumpling and respond.", [
            opt("我的饺子不太好看，但是很好玩！", "Wǒ de jiǎozi bú tài hǎokàn, dànshì hěn hǎowán!", "My dumpling doesn't look great, but it's so fun!", 1.0, "Self-deprecating humor — keeps the mood light."),
            opt("我想看电视。", "Wǒ xiǎng kàn diànshì.", "I want to watch TV.", 0.0, "Off-topic — you're in the middle of making dumplings together."),
            opt("你几岁了？", "Nǐ jǐ suì le?", "How old are you?", 0.0, "Off-topic — a rude question that ignores the cooking lesson.")
        ])
    ],
    "Making dumplings (包饺子) together is one of the most intimate domestic activities in Chinese life. It's often how neighbors and landlords bond with tenants. The imperfect shapes of a beginner's dumplings always bring laughter and warmth."
))

write_dlg("j2_dlg_004.json", dlg(
    "A Lost Glove", "丢了一只手套",
    2, 0.3,
    "On a cold morning, you find a single knitted glove on a bench. A woman nearby seems to be looking for something.",
    "一个冷天的早上，你在长椅上发现了一只手套。旁边有位女士好像在找什么。",
    [
        npc("你有没有看到一只红色的手套？我刚才坐在这里……", "Nǐ yǒu méiyǒu kàn dào yī zhī hóngsè de shǒutào? Wǒ gāngcái zuò zài zhèlǐ……", "Have you seen a red glove? I was sitting here just now..."),
        player("Help her find the glove.", [
            opt("是这只吗？我在长椅上看到的。", "Shì zhè zhī ma? Wǒ zài chángyǐ shàng kàn dào de.", "Is it this one? I found it on the bench.", 1.0, "Helpful and direct — solves her problem immediately."),
            opt("今天很冷。", "Jīntiān hěn lěng.", "It's cold today.", 0.0, "Off-topic — she's looking for her glove."),
            opt("你要去哪里？", "Nǐ yào qù nǎlǐ?", "Where are you going?", 0.0, "Off-topic — doesn't help her find the glove.")
        ]),
        npc("就是这只！太感谢了！这是我妈妈织的，对我很重要。", "Jiù shì zhè zhī! Tài gǎnxiè le! Zhè shì wǒ māma zhī de, duì wǒ hěn zhòngyào.", "That's the one! Thank you so much! My mom knitted it — it's very important to me."),
        player("Respond to her gratitude.", [
            opt("太好了，找到就好。妈妈织的东西很珍贵。", "Tài hǎo le, zhǎo dào jiù hǎo. Māma zhī de dōngxi hěn zhēnguì.", "Wonderful, glad you found it. Things mom made are precious.", 1.0, "Empathetic — recognizes the sentimental value."),
            opt("手套多少钱？", "Shǒutào duōshao qián?", "How much was the glove?", 0.0, "Off-topic — misses the point about sentimental value."),
            opt("我不喜欢红色。", "Wǒ bù xǐhuan hóngsè.", "I don't like red.", 0.0, "Off-topic — insensitive when she's emotional about her mom's glove.")
        ])
    ],
    "Handmade gifts from family carry deep sentimental value in Chinese culture. A knitted glove from a mother represents love and care. Finding and returning such items creates small but meaningful connections between strangers."
))

write_dlg("j2_dlg_005.json", dlg(
    "The Night Market Painter", "夜市的画家",
    2, 0.3,
    "At a night market, you see an artist drawing portraits. He has an empty seat in front of him.",
    "在夜市上，你看到一位画家在画人像。他面前有一个空位。",
    [
        npc("来，坐下吧！我给你画一张，十五分钟就好。", "Lái, zuò xià ba! Wǒ gěi nǐ huà yī zhāng, shíwǔ fēnzhōng jiù hǎo.", "Come, sit down! I'll draw you one — only fifteen minutes."),
        player("Respond to his offer.", [
            opt("好啊，我从来没有让人画过。要多少钱？", "Hǎo a, wǒ cónglái méiyǒu ràng rén huà guò. Yào duōshao qián?", "Sure, I've never had anyone draw me before. How much?", 1.0, "Curious and practical — tries something new."),
            opt("我不喜欢夜市。", "Wǒ bù xǐhuan yèshì.", "I don't like night markets.", 0.0, "Off-topic — you're already at the night market."),
            opt("你是哪里人？", "Nǐ shì nǎlǐ rén?", "Where are you from?", 0.0, "Off-topic — doesn't respond to his offer to draw you.")
        ]),
        npc("三十块。你别动，放轻松就好。你在中国住了多长时间了？", "Sānshí kuài. Nǐ bié dòng, fàng qīngsōng jiù hǎo. Nǐ zài Zhōngguó zhù le duō cháng shíjiān le?", "Thirty yuan. Don't move — just relax. How long have you been living in China?"),
        player("Tell him about your time in China while he draws.", [
            opt("差不多半年了。我越来越喜欢这里的生活。", "Chàbuduō bàn nián le. Wǒ yuè lái yuè xǐhuan zhèlǐ de shēnghuó.", "About half a year. I like the life here more and more.", 1.0, "Reflective and genuine — shares a real feeling."),
            opt("你画得快不快？", "Nǐ huà de kuài bú kuài?", "Do you draw fast?", 0.0, "Off-topic — he already said fifteen minutes."),
            opt("我想吃烤串。", "Wǒ xiǎng chī kǎo chuàn.", "I want to eat skewers.", 0.0, "Off-topic — he asked about your time in China.")
        ])
    ],
    "Night market portrait artists are a charming tradition. They capture a moment in time while conversation flows naturally. The casual intimacy of sitting still while a stranger draws you creates a unique connection."
))

write_dlg("j2_dlg_006.json", dlg(
    "The Hospital Waiting Room", "医院的候诊室",
    2, 0.3,
    "You're at a small clinic with a minor cold. An elderly man next to you starts chatting.",
    "你因为小感冒去了一家小诊所。旁边的一位老人开始跟你聊天。",
    [
        npc("你也感冒了吗？最近很多人都生病了。", "Nǐ yě gǎnmào le ma? Zuìjìn hěn duō rén dōu shēngbìng le.", "You caught a cold too? A lot of people have been getting sick lately."),
        player("Tell him about how you feel.", [
            opt("是啊，有点咳嗽。不太严重，但是想让医生看看。", "Shì a, yǒudiǎn késou. Bú tài yánzhòng, dànshì xiǎng ràng yīshēng kànkan.", "Yes, a bit of a cough. Not too serious, but I want the doctor to check.", 1.0, "Calm and reasonable — not overdramatic."),
            opt("我不喜欢医院。", "Wǒ bù xǐhuan yīyuàn.", "I don't like hospitals.", 0.0, "Off-topic — he asked about your symptoms."),
            opt("你的衣服很好看。", "Nǐ de yīfu hěn hǎokàn.", "Your clothes look nice.", 0.0, "Off-topic — a strange thing to say in a clinic waiting room.")
        ]),
        npc("多喝热水，好好休息，很快就会好的。你一个人来的？", "Duō hē rè shuǐ, hǎohāo xiūxi, hěn kuài jiù huì hǎo de. Nǐ yī ge rén lái de?", "Drink more hot water, rest well, and you'll recover soon. Did you come alone?"),
        player("Answer his question.", [
            opt("是一个人来的。谢谢您的关心，我会多喝水的。", "Shì yī ge rén lái de. Xièxie nín de guānxīn, wǒ huì duō hē shuǐ de.", "Yes, I came alone. Thank you for your concern — I'll drink more water.", 1.0, "Grateful and polite — accepts his care gracefully."),
            opt("我不想喝水。", "Wǒ bù xiǎng hē shuǐ.", "I don't want to drink water.", 0.0, "Off-topic — dismisses his sincere advice."),
            opt("这个诊所很小。", "Zhège zhěnsuǒ hěn xiǎo.", "This clinic is very small.", 0.0, "Off-topic — he asked if you came alone.")
        ])
    ],
    "「多喝热水」(drink more hot water) is the quintessential Chinese health advice, given for nearly every ailment. It reflects a deeply caring culture where strangers offer unsolicited but well-meaning health tips. Accepting the advice graciously is the polite response."
))

write_dlg("j2_dlg_007.json", dlg(
    "The Bicycle Repair Shop", "修自行车",
    2, 0.3,
    "Your bicycle has a flat tire. You find a small repair shop run by an old man under a tree.",
    "你的自行车轮胎没气了。你找到了一个老爷爷在树下开的修车铺。",
    [
        npc("自行车坏了？让我看看。哦，是轮胎没气了，小问题。", "Zìxíngchē huài le? Ràng wǒ kànkan. Ó, shì lúntāi méi qì le, xiǎo wèntí.", "Bike broken? Let me see. Oh, the tire is flat — small problem."),
        player("Ask about the repair.", [
            opt("太好了！修好要多长时间？", "Tài hǎo le! Xiū hǎo yào duō cháng shíjiān?", "Great! How long will it take to fix?", 1.0, "Practical and relieved — gets to the point."),
            opt("我想买一辆新的。", "Wǒ xiǎng mǎi yī liàng xīn de.", "I want to buy a new one.", 0.0, "Off-topic — he just said it's a small problem."),
            opt("你在这里多少年了？", "Nǐ zài zhèlǐ duōshao nián le?", "How many years have you been here?", 0.0, "Off-topic — your bike needs fixing first.")
        ]),
        npc("十分钟就好。你坐这儿等一会儿。你是骑车上班吗？", "Shí fēnzhōng jiù hǎo. Nǐ zuò zhèr děng yīhuǐr. Nǐ shì qí chē shàngbān ma?", "Ten minutes. Sit here and wait. Do you bike to work?"),
        player("Chat while he fixes your bike.", [
            opt("对，每天骑车去。又方便又可以锻炼身体。", "Duì, měi tiān qí chē qù. Yòu fāngbiàn yòu kěyǐ duànliàn shēntǐ.", "Yes, I bike every day. It's convenient and good exercise.", 1.0, "Friendly conversation — shares your routine naturally."),
            opt("我不想等。", "Wǒ bù xiǎng děng.", "I don't want to wait.", 0.0, "Off-topic — impatient when he said only ten minutes."),
            opt("你有孩子吗？", "Nǐ yǒu háizi ma?", "Do you have children?", 0.0, "Off-topic — he asked about your commute.")
        ])
    ],
    "Roadside bicycle repair shops (修车铺) are a disappearing but beloved part of Chinese urban life. Often run by elderly men under trees or awnings, they fix any bike cheaply and quickly. The chat while waiting is part of the experience."
))

write_dlg("j2_dlg_008.json", dlg(
    "The New Café", "新开的咖啡店",
    2, 0.3,
    "A new café opened in your neighborhood. You go in to try it. The barista greets you warmly.",
    "你的小区新开了一家咖啡店。你走进去尝尝。咖啡师热情地跟你打招呼。",
    [
        npc("欢迎光临！我们刚开的。今天所有咖啡打八折。你想喝什么？", "Huānyíng guānglín! Wǒmen gāng kāi de. Jīntiān suǒyǒu kāfēi dǎ bā zhé. Nǐ xiǎng hē shénme?", "Welcome! We just opened. All coffee is 20% off today. What would you like?"),
        player("Order something.", [
            opt("那我要一杯热的拿铁。这个地方看起来很舒服。", "Nà wǒ yào yī bēi rè de ná tiě. Zhège dìfang kàn qǐlái hěn shūfu.", "I'll have a hot latte then. This place looks really cozy.", 1.0, "Friendly and complimentary — good first impression."),
            opt("以前这里是什么？", "Yǐqián zhèlǐ shì shénme?", "What was here before?", 0.0, "Off-topic — she asked what you'd like to drink."),
            opt("我不喜欢打折。", "Wǒ bù xǐhuan dǎzhé.", "I don't like discounts.", 0.0, "Off-topic — an odd thing to say about a promotional offer.")
        ]),
        npc("好的！你是住在附近吗？希望你以后经常来。", "Hǎo de! Nǐ shì zhù zài fùjìn ma? Xīwàng nǐ yǐhòu jīngcháng lái.", "Okay! Do you live nearby? I hope you'll come often."),
        player("Tell her about yourself.", [
            opt("对，我就住在旁边。走路两分钟就到了。以后一定常来。", "Duì, wǒ jiù zhù zài pángbiān. Zǒu lù liǎng fēnzhōng jiù dào le. Yǐhòu yīdìng cháng lái.", "Yes, I live right next door. Two-minute walk. I'll definitely come often.", 1.0, "Warm and encouraging — supports a new local business."),
            opt("你这里有WiFi吗？", "Nǐ zhèlǐ yǒu WiFi ma?", "Do you have WiFi?", 0.0, "Off-topic — she asked where you live and hoped you'd return."),
            opt("我不太出门。", "Wǒ bú tài chūmén.", "I don't go out much.", 0.0, "Off-topic — contradicts the fact that you just came in.")
        ])
    ],
    "New neighborhood cafés in China work hard to build regular customers. The personal touch — chatting, discounts, remembering orders — makes them feel like extensions of home. 打八折 means 80% of the original price (20% off)."
))

write_dlg("j2_dlg_009.json", dlg(
    "Feeding Stray Cats", "喂流浪猫",
    2, 0.3,
    "After dinner, you see a neighbor putting out food for stray cats in the courtyard. You stop to watch.",
    "吃完晚饭后，你看到邻居在院子里给流浪猫放吃的。你停下来看。",
    [
        npc("你也喜欢猫吧？这些猫每天晚上都来。它们认识我了。", "Nǐ yě xǐhuan māo ba? Zhèxiē māo měi tiān wǎnshang dōu lái. Tāmen rènshi wǒ le.", "You like cats too, right? These cats come every night. They know me now."),
        player("Share your feelings about the cats.", [
            opt("它们看起来很信任你。你喂了多长时间了？", "Tāmen kàn qǐlái hěn xìnrèn nǐ. Nǐ wèi le duō cháng shíjiān le?", "They seem to trust you a lot. How long have you been feeding them?", 1.0, "Observant and warm — notices the bond."),
            opt("流浪猫很脏。", "Liúlàng māo hěn zāng.", "Stray cats are dirty.", 0.0, "Off-topic — insensitive to someone who cares for them."),
            opt("你家有空调吗？", "Nǐ jiā yǒu kōngtiáo ma?", "Does your place have AC?", 0.0, "Off-topic — she's talking about the cats.")
        ]),
        npc("快两年了。刚开始它们很怕人，现在看到我就跑过来。那只灰色的最亲人。", "Kuài liǎng nián le. Gāng kāishǐ tāmen hěn pà rén, xiànzài kàn dào wǒ jiù pǎo guòlái. Nà zhī huīsè de zuì qīn rén.", "Almost two years. At first they were scared of people — now they run to me. The grey one is the friendliest."),
        player("Respond to her story.", [
            opt("两年了！你真有耐心。我可以帮你一起喂吗？", "Liǎng nián le! Nǐ zhēn yǒu nàixīn. Wǒ kěyǐ bāng nǐ yīqǐ wèi ma?", "Two years! You're so patient. Can I help you feed them?", 1.0, "Admiring and willing to join — builds community."),
            opt("我不想养猫。", "Wǒ bù xiǎng yǎng māo.", "I don't want to keep a cat.", 0.0, "Off-topic — she's not asking you to adopt one."),
            opt("明天我要上班。", "Míngtiān wǒ yào shàngbān.", "I have work tomorrow.", 0.0, "Off-topic — sounds like you want to leave.")
        ])
    ],
    "Community cat feeders (喂流浪猫的人) are unsung heroes of Chinese neighborhoods. Their patience transforms fearful strays into friendly companions. This quiet care reflects the iyashikei spirit — small acts of kindness that heal."
))

write_dlg("j2_dlg_010.json", dlg(
    "The School Gate at Pickup Time", "放学时间的校门口",
    2, 0.3,
    "You walk past a school gate at pickup time. A parent waiting outside starts chatting with you.",
    "你路过一所学校的门口，正是放学时间。一位等孩子的家长跟你聊天。",
    [
        npc("你也来接孩子吗？还是路过？", "Nǐ yě lái jiē háizi ma? Háishi lùguò?", "Are you here to pick up a child too? Or just passing by?"),
        player("Explain why you're here.", [
            opt("我路过的。这里每天都这么热闹吗？", "Wǒ lùguò de. Zhèlǐ měi tiān dōu zhème rènao ma?", "I'm just passing by. Is it this lively every day?", 1.0, "Friendly and curious — engages naturally."),
            opt("我不认识你。", "Wǒ bú rènshi nǐ.", "I don't know you.", 0.0, "Off-topic — unfriendly response to a casual conversation."),
            opt("这个学校好不好？", "Zhège xuéxiào hǎo bù hǎo?", "Is this school good?", 0.0, "Off-topic — doesn't answer whether you're picking up a child or passing by.")
        ]),
        npc("每天都这样！孩子们出来的时候最开心了。你看，那边卖糖葫芦的老爷爷也每天都来。", "Měi tiān dōu zhèyàng! Háizimen chūlái de shíhou zuì kāixīn le. Nǐ kàn, nàbiān mài tánghúlu de lǎoyéye yě měi tiān dōu lái.", "Every day! The kids are happiest when they come out. See, the old man selling candied hawthorns over there comes every day too."),
        player("React to the scene.", [
            opt("真的很温馨。小时候我也很期待放学。", "Zhēn de hěn wēnxīn. Xiǎo shíhou wǒ yě hěn qīdài fàngxué.", "It's really heartwarming. When I was little, I also looked forward to getting out of school.", 1.0, "Reflective — connects to a universal childhood feeling."),
            opt("糖葫芦好吃吗？", "Tánghúlu hǎochī ma?", "Are candied hawthorns tasty?", 0.0, "Off-topic — misses the emotional beat of the moment."),
            opt("我要走了。", "Wǒ yào zǒu le.", "I need to go.", 0.0, "Off-topic — leaves abruptly during a warm moment.")
        ])
    ],
    "School pickup time (放学) is a daily ritual that transforms quiet streets into joyful scenes. Grandparents, parents, and snack vendors all converge. The tanghulu (糖葫芦) seller is an iconic figure — a thread of continuity across generations."
))

write_dlg("j2_dlg_011.json", dlg(
    "The Slow Train", "慢火车",
    2, 0.35,
    "You're on a slow train through the countryside. The passenger across from you opens a conversation.",
    "你坐慢车穿过乡下。对面的乘客跟你聊了起来。",
    [
        npc("你去哪里？这趟车走得很慢，不过可以看风景。", "Nǐ qù nǎlǐ? Zhè tàng chē zǒu de hěn màn, búguò kěyǐ kàn fēngjǐng.", "Where are you going? This train is very slow, but you can see the scenery."),
        player("Tell him your destination and how you feel about the trip.", [
            opt("我去下一站。慢一点也好，窗外的风景真好看。", "Wǒ qù xià yī zhàn. Màn yīdiǎn yě hǎo, chuāng wài de fēngjǐng zhēn hǎokàn.", "I'm going to the next stop. Slow is fine — the scenery outside is beautiful.", 1.0, "Relaxed and present — enjoys the journey."),
            opt("我不喜欢坐火车。", "Wǒ bù xǐhuan zuò huǒchē.", "I don't like taking trains.", 0.0, "Off-topic — you're already on the train."),
            opt("你的行李很多。", "Nǐ de xíngli hěn duō.", "You have a lot of luggage.", 0.0, "Off-topic — a bit rude and doesn't answer his question.")
        ]),
        npc("是啊，现在大家都坐高铁了。但是我觉得慢车有慢车的好。能看到很多小地方。", "Shì a, xiànzài dàjiā dōu zuò gāotiě le. Dànshì wǒ juéde màn chē yǒu màn chē de hǎo. Néng kàn dào hěn duō xiǎo dìfang.", "Yeah, everyone takes the high-speed train now. But I think slow trains have their own charm. You can see lots of small places."),
        player("Share your perspective on slow travel.", [
            opt("我也这样觉得。有时候慢一点，反而能看到更多。", "Wǒ yě zhèyàng juéde. Yǒu shíhou màn yīdiǎn, fǎn'ér néng kàn dào gèng duō.", "I feel the same. Sometimes going slower, you actually see more.", 1.0, "Thoughtful — connects with his philosophy."),
            opt("高铁比较贵。", "Gāotiě bǐjiào guì.", "High-speed trains are more expensive.", 0.0, "Off-topic — he's talking about the charm of slow travel, not cost."),
            opt("我想睡觉了。", "Wǒ xiǎng shuìjiào le.", "I want to sleep.", 0.0, "Off-topic — ends the conversation abruptly.")
        ])
    ],
    "China's slow trains (慢车/绿皮车) are a nostalgic counterpoint to the high-speed rail network. They stop at small towns the bullet trains skip, carrying farmers, students, and travelers who prefer the unhurried pace. Conversations between strangers flow easily."
))

write_dlg("j2_dlg_012.json", dlg(
    "A Rainy Day at the Temple", "雨天的寺庙",
    2, 0.35,
    "You duck into a small Buddhist temple to escape the rain. A monk is sweeping the courtyard slowly, unbothered by the rain.",
    "你躲进一座小寺庙避雨。一位僧人在院子里慢慢扫地，一点也不介意下雨。",
    [
        npc("进来避雨吧。不着急，雨很快就停了。要不要喝杯茶？", "Jìnlái bì yǔ ba. Bù zháojí, yǔ hěn kuài jiù tíng le. Yào bú yào hē bēi chá?", "Come in out of the rain. No rush — it'll stop soon. Would you like a cup of tea?"),
        player("Accept his offer.", [
            opt("好的，谢谢您。这里好安静，我很喜欢。", "Hǎo de, xièxie nín. Zhèlǐ hǎo ānjìng, wǒ hěn xǐhuan.", "Yes, thank you. It's so peaceful here — I really like it.", 1.0, "Gracious and reflective — appreciates the calm."),
            opt("雨什么时候停？", "Yǔ shénme shíhou tíng?", "When will the rain stop?", 0.0, "Off-topic — he just said no rush, and this sounds impatient."),
            opt("附近有地铁站吗？", "Fùjìn yǒu dìtiě zhàn ma?", "Is there a subway station nearby?", 0.0, "Off-topic — you just arrived and he's offering tea.")
        ]),
        npc("雨天来寺庙的人不多。你平时喜欢去什么样的地方？", "Yǔ tiān lái sìmiào de rén bù duō. Nǐ píngshí xǐhuan qù shénme yàng de dìfang?", "Not many people visit temples on rainy days. What kind of places do you usually like to go?"),
        player("Share what kind of places you enjoy.", [
            opt("我喜欢安静的地方。书店、公园……像这里一样的。", "Wǒ xǐhuan ānjìng de dìfang. Shūdiàn, gōngyuán…… xiàng zhèlǐ yīyàng de.", "I like quiet places. Bookshops, parks... places like this.", 1.0, "Honest and resonant — fits the temple atmosphere."),
            opt("我喜欢KTV。", "Wǒ xǐhuan KTV.", "I like karaoke.", 0.0, "Off-topic — a jarring contrast to the temple setting."),
            opt("我没有时间。", "Wǒ méiyǒu shíjiān.", "I don't have time.", 0.0, "Off-topic — you literally just sat down for tea.")
        ])
    ],
    "Buddhist temples welcome anyone seeking shelter or quiet. Monks often offer tea and conversation without any religious expectation. Rain amplifies the meditative quality of these spaces — the sound of rain on old tiles is its own kind of music."
))

write_dlg("j2_dlg_013.json", dlg(
    "The Vegetable Garden", "菜园子",
    2, 0.35,
    "Your neighbor has a small vegetable garden on the rooftop. She invites you up to see it.",
    "你的邻居在楼顶有一个小菜园。她邀请你上去看看。",
    [
        npc("快看，这些都是我自己种的。有西红柿、黄瓜，还有一些葱。", "Kuài kàn, zhèxiē dōu shì wǒ zìjǐ zhǒng de. Yǒu xīhóngshì, huángguā, hái yǒu yīxiē cōng.", "Look, I grew all of these myself. Tomatoes, cucumbers, and some scallions."),
        player("React to her garden.", [
            opt("太厉害了！你每天都要浇水吗？", "Tài lìhai le! Nǐ měi tiān dōu yào jiāo shuǐ ma?", "That's amazing! Do you water them every day?", 1.0, "Admiring and curious — asks about her routine."),
            opt("我不会种菜。", "Wǒ bú huì zhǒng cài.", "I don't know how to grow vegetables.", 0.0, "Off-topic — doesn't engage with what she's showing you."),
            opt("楼顶好热。", "Lóudǐng hǎo rè.", "The rooftop is very hot.", 0.0, "Off-topic — she's proudly showing her garden.")
        ]),
        npc("差不多每天。你要不要拿一些回去？自己种的，没有农药，吃着放心。", "Chàbuduō měi tiān. Nǐ yào bú yào ná yīxiē huíqù? Zìjǐ zhǒng de, méiyǒu nóngyào, chī zhe fàngxīn.", "Almost every day. Want to take some home? Home-grown, no pesticides — you can eat with peace of mind."),
        player("Respond to her generosity.", [
            opt("真的可以吗？太谢谢你了！我今晚用它做一道菜。", "Zhēn de kěyǐ ma? Tài xièxie nǐ le! Wǒ jīn wǎn yòng tā zuò yī dào cài.", "Really? Thank you so much! I'll make a dish with them tonight.", 1.0, "Grateful and specific — shows you'll use the gift."),
            opt("我一般在超市买菜。", "Wǒ yībān zài chāoshì mǎi cài.", "I usually buy vegetables at the supermarket.", 0.0, "Off-topic — dismisses her offer of fresh produce."),
            opt("你种了多少年了？", "Nǐ zhǒng le duōshao nián le?", "How many years have you been growing?", 0.0, "Off-topic — she just offered you vegetables and you didn't respond.")
        ])
    ],
    "Rooftop gardens (楼顶菜园) are common in Chinese apartment buildings. Growing your own vegetables is a point of pride, and sharing the harvest with neighbors strengthens community bonds. 放心 (peace of mind) about food safety is a major value."
))

write_dlg("j2_dlg_014.json", dlg(
    "The Photo Booth", "照相馆",
    2, 0.35,
    "You need a passport photo. You find a small, old-fashioned photo studio run by an elderly couple.",
    "你需要拍证件照。你找到了一家老式照相馆，老板是一对老夫妻。",
    [
        npc("拍证件照？好，你坐这里。不要紧张，笑一笑。", "Pāi zhèngjiàn zhào? Hǎo, nǐ zuò zhèlǐ. Bú yào jǐnzhāng, xiào yī xiào.", "Passport photo? Okay, sit here. Don't be nervous — smile a little."),
        player("React to the photo session.", [
            opt("好的。我每次拍照都不太自然，不好意思。", "Hǎo de. Wǒ měi cì pāi zhào dōu bú tài zìrán, bù hǎo yìsi.", "Okay. I'm always a bit unnatural in photos, sorry about that.", 1.0, "Honest and endearing — relatable admission."),
            opt("你们这里有WiFi吗？", "Nǐmen zhèlǐ yǒu WiFi ma?", "Do you have WiFi here?", 0.0, "Off-topic — you're about to have your photo taken."),
            opt("外面的路很难找。", "Wàimiàn de lù hěn nán zhǎo.", "The road outside was hard to find.", 0.0, "Off-topic — he's trying to help you pose.")
        ]),
        npc("没关系，很多人都这样。你看旁边，对，就这样。好了！你要看看吗？", "Méi guānxi, hěn duō rén dōu zhèyàng. Nǐ kàn pángbiān, duì, jiù zhèyàng. Hǎo le! Nǐ yào kànkan ma?", "No worries, lots of people are like that. Look to the side — yes, just like that. Done! Want to see?"),
        player("Look at the photo and respond.", [
            opt("拍得真好！比我以前拍的好多了。谢谢您。", "Pāi de zhēn hǎo! Bǐ wǒ yǐqián pāi de hǎo duō le. Xièxie nín.", "It came out great! Much better than ones I've had before. Thank you.", 1.0, "Genuine compliment — makes the photographer happy."),
            opt("可以便宜一点吗？", "Kěyǐ piányi yīdiǎn ma?", "Can it be cheaper?", 0.0, "Off-topic — he's showing you the result, not quoting a price."),
            opt("我不太满意。", "Wǒ bú tài mǎnyì.", "I'm not very satisfied.", 0.0, "Off-topic — unlikely for such a kind interaction, and impolite.")
        ])
    ],
    "Old-fashioned photo studios (照相馆) are disappearing but still cherished. The owners' patience and warmth turn a mundane task into a human moment. Their skill with lighting often produces surprisingly good portraits."
))

write_dlg("j2_dlg_015.json", dlg(
    "Morning Fog", "早上的雾",
    2, 0.35,
    "You step outside early and find the neighborhood wrapped in fog. A security guard is at his post, drinking tea.",
    "你一大早出门，发现整个小区都被雾笼罩了。保安在他的岗位上喝茶。",
    [
        npc("这么早出门？今天雾很大，走路小心点。", "Zhème zǎo chūmén? Jīntiān wù hěn dà, zǒu lù xiǎoxīn diǎn.", "Out this early? The fog is heavy today — be careful walking."),
        player("Respond to his concern.", [
            opt("谢谢提醒。雾好大，对面都看不清。但是很漂亮。", "Xièxie tíxǐng. Wù hǎo dà, duìmiàn dōu kàn bù qīng. Dànshì hěn piàoliang.", "Thanks for the reminder. The fog is so thick I can't see across the street. But it's beautiful.", 1.0, "Grateful and observant — finds beauty in the fog."),
            opt("我每天都很早。", "Wǒ měi tiān dōu hěn zǎo.", "I'm always early.", 0.0, "Off-topic — doesn't engage with his concern about the fog."),
            opt("你喝的是什么茶？", "Nǐ hē de shì shénme chá?", "What tea are you drinking?", 0.0, "Off-topic — he's warning you about the fog.")
        ]),
        npc("是挺漂亮的。我在这里工作十几年了，每年冬天都有这样的雾。像住在云里一样。", "Shì tǐng piàoliang de. Wǒ zài zhèlǐ gōngzuò shí jǐ nián le, měi nián dōngtiān dōu yǒu zhèyàng de wù. Xiàng zhù zài yún lǐ yīyàng.", "It is beautiful. I've worked here over ten years — every winter there's fog like this. Like living in the clouds."),
        player("Respond to his poetic observation.", [
            opt("「住在云里」，说得真好。您在这里一定看过很多风景。", "「Zhù zài yún lǐ」, shuō de zhēn hǎo. Nín zài zhèlǐ yīdìng kàn guò hěn duō fēngjǐng.", "Living in the clouds — beautifully put. You must have seen many sights here.", 1.0, "Appreciative — honors his words and experience."),
            opt("十几年太长了。", "Shí jǐ nián tài cháng le.", "Ten-plus years is too long.", 0.0, "Off-topic — dismissive of his dedication."),
            opt("我得走了，不然要迟到了。", "Wǒ děi zǒu le, bùrán yào chídào le.", "I need to go or I'll be late.", 0.0, "Off-topic — cuts short a lovely moment.")
        ])
    ],
    "Security guards (保安) are the quiet sentinels of Chinese neighborhoods. Often overlooked, they observe the seasons change from their posts year after year. Their observations can be surprisingly poetic — they see the neighborhood in ways residents miss."
))

write_dlg("j2_dlg_016.json", dlg(
    "The Homework Question", "写作业的问题",
    2, 0.35,
    "You're studying at a café. A university student at the next table politely asks you a question.",
    "你在咖啡店学习。旁边桌的大学生礼貌地问你一个问题。",
    [
        npc("不好意思打扰你。你的中文书看起来很有意思。你也在学中文吗？", "Bù hǎo yìsi dǎrǎo nǐ. Nǐ de Zhōngwén shū kàn qǐlái hěn yǒu yìsi. Nǐ yě zài xué Zhōngwén ma?", "Sorry to bother you. Your Chinese book looks interesting. Are you studying Chinese too?"),
        player("Tell her about your studies.", [
            opt("是的，我在学中文。学了差不多半年了，还不太好。", "Shì de, wǒ zài xué Zhōngwén. Xué le chàbuduō bàn nián le, hái bú tài hǎo.", "Yes, I'm studying Chinese. About half a year now — still not very good.", 1.0, "Humble and open — invites conversation."),
            opt("这不是中文书。", "Zhè bú shì Zhōngwén shū.", "This isn't a Chinese book.", 0.0, "Off-topic — the setup says it's a Chinese book."),
            opt("我在工作。", "Wǒ zài gōngzuò.", "I'm working.", 0.0, "Off-topic — comes off as a brush-off.")
        ]),
        npc("半年已经很不错了！我也在写关于语言的作业。你觉得中文最难的是什么？", "Bàn nián yǐjīng hěn búcuò le! Wǒ yě zài xiě guānyú yǔyán de zuòyè. Nǐ juéde Zhōngwén zuì nán de shì shénme?", "Half a year is already great! I'm writing a homework assignment about language too. What do you think is the hardest part of Chinese?"),
        player("Share what you find most challenging.", [
            opt("声调最难。有时候我说的，别人听不懂。", "Shēngdiào zuì nán. Yǒu shíhou wǒ shuō de, biérén tīng bù dǒng.", "Tones are the hardest. Sometimes people can't understand what I say.", 1.0, "Honest and specific — a relatable language-learning struggle."),
            opt("都不难。", "Dōu bù nán.", "None of it is hard.", 0.0, "Off-topic — not believable and shuts down conversation."),
            opt("你的作业什么时候交？", "Nǐ de zuòyè shénme shíhou jiāo?", "When is your homework due?", 0.0, "Off-topic — deflects her question.")
        ])
    ],
    "Chinese university students are often curious about foreigners learning their language. These café encounters lead to genuine exchanges about the challenges and joys of language learning. Mutual vulnerability about learning creates fast bonds."
))

write_dlg("j2_dlg_017.json", dlg(
    "The Broken Elevator", "电梯坏了",
    2, 0.35,
    "The elevator in your apartment building is broken. You meet your neighbor on the stairs, both of you climbing with groceries.",
    "你住的楼的电梯坏了。你在楼梯上遇到邻居，你们都提着菜。",
    [
        npc("电梯又坏了！我住十二楼，每次都累死了。你住几楼？", "Diàntī yòu huài le! Wǒ zhù shí'èr lóu, měi cì dōu lèi sǐ le. Nǐ zhù jǐ lóu?", "The elevator's broken again! I live on the twelfth floor — I'm exhausted every time. What floor do you live on?"),
        player("Tell her your floor and commiserate.", [
            opt("我住八楼。也够累的了。你提的东西好多。", "Wǒ zhù bā lóu. Yě gòu lèi de le. Nǐ tí de dōngxi hǎo duō.", "I'm on the eighth floor. That's tiring enough. You've got a lot of stuff.", 1.0, "Empathetic — acknowledges shared struggle."),
            opt("我喜欢爬楼梯。", "Wǒ xǐhuan pá lóutī.", "I like climbing stairs.", 0.0, "Off-topic — dismisses her complaint in an annoying way."),
            opt("你买了什么菜？", "Nǐ mǎi le shénme cài?", "What vegetables did you buy?", 0.0, "Off-topic — she's talking about the broken elevator problem.")
        ]),
        npc("没办法，只能慢慢爬。你要不要我帮你拿一个袋子？", "Méi bànfǎ, zhǐ néng mànmàn pá. Nǐ yào bú yào wǒ bāng nǐ ná yī ge dàizi?", "Nothing we can do — just climb slowly. Want me to carry one of your bags?"),
        player("Respond to her kind offer.", [
            opt("不用不用，我还好。我们一起慢慢走吧。", "Bú yòng bú yòng, wǒ hái hǎo. Wǒmen yīqǐ mànmàn zǒu ba.", "No no, I'm fine. Let's walk up slowly together.", 1.0, "Considerate — declines but suggests togetherness."),
            opt("你应该搬到低楼层。", "Nǐ yīnggāi bān dào dī lóucéng.", "You should move to a lower floor.", 0.0, "Off-topic — unhelpful advice when she just offered to help you."),
            opt("电梯什么时候修好？", "Diàntī shénme shíhou xiū hǎo?", "When will the elevator be fixed?", 0.0, "Off-topic — she can't answer that, and she just offered to help you.")
        ])
    ],
    "Broken elevators in Chinese apartment buildings create unexpected neighborly moments. The shared inconvenience bonds people — carrying groceries up many flights together turns strangers into friends. 没办法 (nothing we can do) is a resigned but warm acceptance."
))

write_dlg("j2_dlg_018.json", dlg(
    "The Old Photograph", "老照片",
    2, 0.4,
    "You visit a flea market and find a vendor selling old photographs. He picks one up and tells you about it.",
    "你去了一个跳蚤市场，看到一位摊主在卖老照片。他拿起一张跟你说。",
    [
        npc("你看这张照片，是八十年代的。那时候这条街完全不一样。", "Nǐ kàn zhè zhāng zhàopiàn, shì bāshí niándài de. Nà shíhou zhè tiáo jiē wánquán bù yīyàng.", "Look at this photo — it's from the 1980s. This street looked completely different back then."),
        player("Show interest in the photo.", [
            opt("真的吗？看起来很不一样。那时候这里有什么？", "Zhēn de ma? Kàn qǐlái hěn bù yīyàng. Nà shíhou zhèlǐ yǒu shénme?", "Really? It looks so different. What was here back then?", 1.0, "Curious and engaged — invites a story."),
            opt("这张多少钱？", "Zhè zhāng duōshao qián?", "How much is this one?", 0.0, "Off-topic — jumps to price before appreciating the story."),
            opt("我不喜欢老东西。", "Wǒ bù xǐhuan lǎo dōngxi.", "I don't like old things.", 0.0, "Off-topic — rude at a vintage market.")
        ]),
        npc("那时候都是小平房，门口有大树。到了晚上大家就搬椅子出来聊天。现在都是高楼了。", "Nà shíhou dōu shì xiǎo píngfáng, ménkǒu yǒu dà shù. Dào le wǎnshang dàjiā jiù bān yǐzi chūlái liáotiān. Xiànzài dōu shì gāolóu le.", "Back then it was all small houses with big trees out front. In the evenings, everyone brought chairs out to chat. Now it's all high-rises."),
        player("Respond to his memory.", [
            opt("听起来那时候邻居之间更亲近。我想看看更多的老照片。", "Tīng qǐlái nà shíhou línjū zhī jiān gèng qīnjìn. Wǒ xiǎng kànkan gèng duō de lǎo zhàopiàn.", "It sounds like neighbors were closer back then. I'd like to see more old photos.", 1.0, "Thoughtful — perceives the loss and wants to learn more."),
            opt("高楼比较好。", "Gāolóu bǐjiào hǎo.", "High-rises are better.", 0.0, "Off-topic — dismisses his nostalgia."),
            opt("我要走了。", "Wǒ yào zǒu le.", "I need to go.", 0.0, "Off-topic — leaves abruptly during his story.")
        ])
    ],
    "China's rapid urbanization transformed neighborhoods within a generation. Old photographs at flea markets preserve memories of a slower pace — small houses, shared courtyards, and evening conversations under trees. These images carry deep nostalgia."
))

write_dlg("j2_dlg_019.json", dlg(
    "The Streetlight Repairman", "修路灯的人",
    2, 0.4,
    "Late afternoon, you notice a man fixing a broken streetlight on your block. You stop to watch.",
    "傍晚时分，你看到一个人在你家这条街修坏了的路灯。你停下来看。",
    [
        npc("这个灯坏了好几天了，今天终于来修了。你住在这条街上吗？", "Zhège dēng huài le hǎo jǐ tiān le, jīntiān zhōngyú lái xiū le. Nǐ zhù zài zhè tiáo jiē shàng ma?", "This light has been broken for days — finally came to fix it today. Do you live on this street?"),
        player("Tell him you've noticed the broken light.", [
            opt("对，我住这里。我也注意到了，晚上这里特别黑。", "Duì, wǒ zhù zhèlǐ. Wǒ yě zhùyì dào le, wǎnshang zhèlǐ tèbié hēi.", "Yes, I live here. I noticed too — it's really dark here at night.", 1.0, "Observant — validates his work."),
            opt("你修了多长时间了？", "Nǐ xiū le duō cháng shíjiān le?", "How long have you been fixing it?", 0.0, "Off-topic — he just started and asked if you live here."),
            opt("我不知道。", "Wǒ bù zhīdào.", "I don't know.", 0.0, "Off-topic — a flat non-answer to a simple question.")
        ]),
        npc("是啊，路灯很重要。大家回家的路上需要光。这个工作不起眼，但是我觉得有意思。", "Shì a, lùdēng hěn zhòngyào. Dàjiā huí jiā de lù shàng xūyào guāng. Zhège gōngzuò bù qǐyǎn, dànshì wǒ juéde yǒu yìsi.", "Yeah, streetlights are important. People need light on their way home. This job isn't glamorous, but I find it meaningful."),
        player("Respond to his perspective on his work.", [
            opt("我觉得这个工作很了不起。谢谢你让我们回家的路亮起来。", "Wǒ juéde zhège gōngzuò hěn liǎobuqǐ. Xièxie nǐ ràng wǒmen huí jiā de lù liàng qǐlái.", "I think this work is admirable. Thank you for lighting our way home.", 1.0, "Sincere — recognizes the value of unseen labor."),
            opt("你工资高不高？", "Nǐ gōngzī gāo bù gāo?", "Is your salary high?", 0.0, "Off-topic — reduces his heartfelt words to money."),
            opt("我不怕黑。", "Wǒ bú pà hēi.", "I'm not afraid of the dark.", 0.0, "Off-topic — misses his point entirely.")
        ])
    ],
    "The people who maintain urban infrastructure — streetlight repairers, plumbers, electricians — are often invisible. In the iyashikei spirit, recognizing the dignity and meaning in 'small' work transforms how we see our neighborhoods."
))

write_dlg("j2_dlg_020.json", dlg(
    "A Letter from Home", "家里的信",
    2, 0.4,
    "At the post office, the clerk notices you received a letter from abroad. She chats with you while you sign.",
    "在邮局，工作人员发现你收到了一封国外的信。她一边让你签名一边跟你聊。",
    [
        npc("国外来的信！现在很少有人寄信了。是家人寄的吧？", "Guówài lái de xìn! Xiànzài hěn shǎo yǒu rén jì xìn le. Shì jiārén jì de ba?", "A letter from abroad! Very few people send letters anymore. From family, right?"),
        player("Tell her about the letter.", [
            opt("是我妈妈寄的。她不太会用手机，喜欢写信。", "Shì wǒ māma jì de. Tā bú tài huì yòng shǒujī, xǐhuan xiě xìn.", "It's from my mom. She's not great with phones — she likes writing letters.", 1.0, "Warm and personal — shares a sweet detail."),
            opt("我不知道是谁寄的。", "Wǒ bù zhīdào shì shéi jì de.", "I don't know who sent it.", 0.0, "Off-topic — you can see who it's from on the envelope."),
            opt("寄信很贵吗？", "Jì xìn hěn guì ma?", "Is it expensive to send a letter?", 0.0, "Off-topic — she asked who sent it.")
        ]),
        npc("你妈妈真好。我妈妈以前也喜欢给我写信。收到信的感觉和收到消息不一样。", "Nǐ māma zhēn hǎo. Wǒ māma yǐqián yě xǐhuan gěi wǒ xiě xìn. Shōu dào xìn de gǎnjué hé shōu dào xiāoxi bù yīyàng.", "Your mom is so sweet. My mom used to write me letters too. Getting a letter feels different from getting a message."),
        player("Agree and share your feelings.", [
            opt("对，信是慢的，但是更有温度。拿在手里感觉不一样。", "Duì, xìn shì màn de, dànshì gèng yǒu wēndù. Ná zài shǒu lǐ gǎnjué bù yīyàng.", "Yes, letters are slow, but they have more warmth. Holding them in your hand feels different.", 1.0, "Poetic and genuine — captures the magic of handwritten letters."),
            opt("我更喜欢微信。", "Wǒ gèng xǐhuan Wēixìn.", "I prefer WeChat.", 0.0, "Off-topic — dismisses the emotional moment she's sharing."),
            opt("你们邮局几点关门？", "Nǐmen yóujú jǐ diǎn guānmén?", "What time does the post office close?", 0.0, "Off-topic — she's sharing a personal memory.")
        ])
    ],
    "Handwritten letters carry emotional weight that digital messages cannot replicate. In China, where WeChat dominates communication, receiving a physical letter is increasingly rare and precious. Post office clerks often notice and appreciate these moments."
))

write_dlg("j2_dlg_021.json", dlg(
    "The Kite on the Hill", "山坡上的风筝",
    2, 0.4,
    "On a windy afternoon, you walk to a hill where a grandfather is flying a kite with his granddaughter.",
    "一个有风的下午，你走到一个小山坡，看到一位爷爷在和孙女放风筝。",
    [
        npc("你也来放风筝吗？今天的风很好！", "Nǐ yě lái fàng fēngzhēng ma? Jīntiān de fēng hěn hǎo!", "Are you here to fly kites too? The wind is great today!"),
        player("Tell him why you're here.", [
            opt("我来散步的。你们的风筝飞得好高！", "Wǒ lái sànbù de. Nǐmen de fēngzhēng fēi de hǎo gāo!", "I'm here for a walk. Your kite is flying so high!", 1.0, "Friendly and observant — compliments their kite."),
            opt("我没有风筝。", "Wǒ méiyǒu fēngzhēng.", "I don't have a kite.", 0.0, "Off-topic — he asked if you're here to fly kites, and a simple no would be better."),
            opt("这个山不高。", "Zhège shān bù gāo.", "This hill isn't very high.", 0.0, "Off-topic — irrelevant to the conversation about kites.")
        ]),
        npc("这个风筝是我自己做的。小时候我爷爷教我做的。现在我教我孙女。", "Zhège fēngzhēng shì wǒ zìjǐ zuò de. Xiǎo shíhou wǒ yéye jiāo wǒ zuò de. Xiànzài wǒ jiāo wǒ sūnnǚ.", "I made this kite myself. My grandfather taught me when I was little. Now I'm teaching my granddaughter."),
        player("Respond to the generational story.", [
            opt("三代人传下来的，真好。她一定很开心。", "Sān dài rén chuán xiàlái de, zhēn hǎo. Tā yīdìng hěn kāixīn.", "Three generations passing it down — that's wonderful. She must be so happy.", 1.0, "Moved — recognizes the beauty of the tradition."),
            opt("买一个比较方便。", "Mǎi yī ge bǐjiào fāngbiàn.", "Buying one is more convenient.", 0.0, "Off-topic — misses the point about handmade family tradition."),
            opt("我该回去了。", "Wǒ gāi huíqù le.", "I should head back.", 0.0, "Off-topic — leaves during a touching story.")
        ])
    ],
    "Kite flying is an ancient Chinese tradition dating back over 2,000 years. Hand-making kites and teaching the craft to grandchildren represents the passage of knowledge and love between generations. Windy hills are gathering places for this timeless activity."
))

write_dlg("j2_dlg_022.json", dlg(
    "The Laundry Line", "晾衣绳",
    2, 0.4,
    "You're hanging laundry on the shared balcony. Your neighbor comes out with her basket too.",
    "你在共用阳台上晾衣服。你的邻居也端着一盆衣服出来了。",
    [
        npc("今天阳光真好，正好晾衣服。你来中国以后习惯了吗？", "Jīntiān yángguāng zhēn hǎo, zhènghǎo liàng yīfu. Nǐ lái Zhōngguó yǐhòu xíguàn le ma?", "Great sunshine today — perfect for drying clothes. Have you gotten used to life in China?"),
        player("Share how you've adjusted.", [
            opt("越来越习惯了。以前在家我都用烘干机，现在觉得晾衣服也很好。", "Yuè lái yuè xíguàn le. Yǐqián zài jiā wǒ dōu yòng hōnggān jī, xiànzài juéde liàng yīfu yě hěn hǎo.", "More and more used to it. Back home I always used a dryer, but now I think air-drying is nice too.", 1.0, "Open and reflective — shows genuine adaptation."),
            opt("我不喜欢晾衣服。", "Wǒ bù xǐhuan liàng yīfu.", "I don't like hanging laundry.", 0.0, "Off-topic — she asked a broader question about adjusting."),
            opt("你的衣服很多。", "Nǐ de yīfu hěn duō.", "You have a lot of clothes.", 0.0, "Off-topic — an odd observation that ignores her question.")
        ]),
        npc("是吧？阳光晒过的衣服有一种味道，很好闻。我觉得这是最简单的幸福。", "Shì ba? Yángguāng shài guò de yīfu yǒu yī zhǒng wèidào, hěn hǎo wén. Wǒ juéde zhè shì zuì jiǎndān de xìngfú.", "Right? Sun-dried clothes have a certain smell — very pleasant. I think it's the simplest kind of happiness."),
        player("Respond to her observation about simple happiness.", [
            opt("你说得真好。我也开始喜欢这些小事了。", "Nǐ shuō de zhēn hǎo. Wǒ yě kāishǐ xǐhuan zhèxiē xiǎo shì le.", "Beautifully said. I'm starting to love these little things too.", 1.0, "Genuine — embraces the small joys of daily life."),
            opt("烘干机更快。", "Hōnggān jī gèng kuài.", "A dryer is faster.", 0.0, "Off-topic — misses her point about simple pleasures."),
            opt("我要去买菜了。", "Wǒ yào qù mǎi cài le.", "I need to go buy vegetables.", 0.0, "Off-topic — leaves during a meaningful moment.")
        ])
    ],
    "Air-drying laundry in the sun is a universal practice in China. Shared balcony time creates natural neighbor interactions. The smell of sun-dried clothes (阳光的味道) is often described as one of life's simplest and purest pleasures."
))

print("HSK 2 Part 1 complete: 22 files written")
