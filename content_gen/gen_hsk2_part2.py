#!/usr/bin/env python3
"""Generate HSK 2 dialogue scenarios, part 2 (023-044)."""
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

print("=== HSK 2 Part 2 (023-044) ===")

write_dlg("j2_dlg_023.json", dlg(
    "The Map in the Lobby", "大厅里的地图",
    2, 0.4,
    "You're in a hotel lobby studying a map of the city. The receptionist comes over to help.",
    "你在酒店大厅看城市地图。前台过来帮你。",
    [
        npc("你想去什么地方？我可以帮你推荐。", "Nǐ xiǎng qù shénme dìfang? Wǒ kěyǐ bāng nǐ tuījiàn.", "Where would you like to go? I can recommend some places."),
        player("Tell her what you're looking for.", [
            opt("我想找一个安静的地方走走。不想去太多游客的地方。", "Wǒ xiǎng zhǎo yī ge ānjìng de dìfang zǒu zou. Bù xiǎng qù tài duō yóukè de dìfang.", "I'd like a quiet place to walk around. Don't want to go somewhere too touristy.", 1.0, "Specific and thoughtful — shows preference for authentic experiences."),
            opt("我不知道。", "Wǒ bù zhīdào.", "I don't know.", 0.0, "Off-topic — she can't help without any direction."),
            opt("酒店早餐几点？", "Jiǔdiàn zǎocān jǐ diǎn?", "What time is hotel breakfast?", 0.0, "Off-topic — she's offering sightseeing recommendations.")
        ]),
        npc("那你可以去老城区。那里有很多老房子和小巷子，很有味道。而且人不多。", "Nà nǐ kěyǐ qù lǎo chéngqū. Nàlǐ yǒu hěn duō lǎo fángzi hé xiǎo xiàngzi, hěn yǒu wèidào. Érqiě rén bù duō.", "Then you could go to the old town. There are lots of old houses and small alleys — very charming. And not crowded."),
        player("Respond to her suggestion.", [
            opt("听起来很好！怎么去呢？走路可以吗？", "Tīng qǐlái hěn hǎo! Zěnme qù ne? Zǒu lù kěyǐ ma?", "Sounds great! How do I get there? Can I walk?", 1.0, "Enthusiastic and practical — ready to explore."),
            opt("我不喜欢老房子。", "Wǒ bù xǐhuan lǎo fángzi.", "I don't like old houses.", 0.0, "Off-topic — dismisses her thoughtful recommendation."),
            opt("你去过吗？", "Nǐ qù guò ma?", "Have you been there?", 0.0, "Off-topic — she clearly knows the area, and this delays the useful info.")
        ])
    ],
    "China's old town districts (老城区) are often the most authentic parts of a city. Away from tourist crowds, they preserve the rhythms of daily life — street vendors, elderly neighbors, hidden tea shops. Hotel staff who recommend these areas are sharing something real."
))

write_dlg("j2_dlg_024.json", dlg(
    "The Grandma and the Chess Board", "奶奶和棋盘",
    2, 0.4,
    "In the park, you see an elderly woman sitting alone at a stone chess table. She notices you watching.",
    "在公园里，你看到一位老奶奶独自坐在石头棋桌旁。她注意到你在看。",
    [
        npc("年轻人，你会下棋吗？我等了半天了，没人来。", "Niánqīng rén, nǐ huì xià qí ma? Wǒ děng le bàntiān le, méi rén lái.", "Young person, do you know how to play chess? I've been waiting a long time — no one's come."),
        player("Tell her about your chess ability.", [
            opt("我会一点点，但是下得不好。您不介意的话，我可以试试。", "Wǒ huì yīdiǎndiǎn, dànshì xià de bù hǎo. Nín bú jièyì de huà, wǒ kěyǐ shìshi.", "I know a tiny bit, but I'm not good. If you don't mind, I can try.", 1.0, "Humble and willing — respects her while accepting."),
            opt("我要去跑步。", "Wǒ yào qù pǎobù.", "I'm going jogging.", 0.0, "Off-topic — declines an elderly person's request without warmth."),
            opt("这个公园很大。", "Zhège gōngyuán hěn dà.", "This park is very big.", 0.0, "Off-topic — she asked if you play chess.")
        ]),
        npc("不怕！我教你。下棋这个东西，越下越有意思。来坐吧。", "Bú pà! Wǒ jiāo nǐ. Xià qí zhège dōngxi, yuè xià yuè yǒu yìsi. Lái zuò ba.", "Don't worry! I'll teach you. Chess is one of those things — the more you play, the more interesting it gets. Come sit."),
        player("Sit down and respond.", [
            opt("好的，谢谢您！您下棋下了多少年了？", "Hǎo de, xièxie nín! Nín xià qí xià le duōshao nián le?", "Okay, thank you! How many years have you been playing chess?", 1.0, "Respectful and curious — shows genuine interest in her."),
            opt("我怕输。", "Wǒ pà shū.", "I'm afraid of losing.", 0.0, "Off-topic — she's being generous, not competitive."),
            opt("你每天都来吗？", "Nǐ měi tiān dōu lái ma?", "Do you come every day?", 0.0, "Off-topic — she just invited you to sit, and your first question should engage with chess.")
        ])
    ],
    "Stone chess tables (棋桌) in Chinese parks are gathering spots for elderly players. Chinese chess (象棋) is a beloved pastime. The generosity of an older player teaching a stranger reflects the park's role as a community living room."
))

write_dlg("j2_dlg_025.json", dlg(
    "The Scent of Osmanthus", "桂花的香味",
    2, 0.4,
    "Walking home in autumn, you pass a row of osmanthus trees in bloom. Your neighbor is standing under one, inhaling deeply.",
    "秋天，你走路回家，经过一排开着花的桂花树。邻居站在树下深呼吸。",
    [
        npc("你闻到了吗？桂花开了！每年这个时候我最喜欢。", "Nǐ wén dào le ma? Guìhuā kāi le! Měi nián zhège shíhou wǒ zuì xǐhuan.", "Can you smell it? The osmanthus is blooming! This is my favorite time every year."),
        player("Share your reaction to the scent.", [
            opt("闻到了，好香啊。我第一次闻到桂花。", "Wén dào le, hǎo xiāng a. Wǒ dì yī cì wén dào guìhuā.", "I can smell it — so fragrant. This is my first time smelling osmanthus.", 1.0, "Present and open — experiencing something new."),
            opt("我对花过敏。", "Wǒ duì huā guòmǐn.", "I'm allergic to flowers.", 0.0, "Off-topic — kills the joyful mood."),
            opt("今天很冷。", "Jīntiān hěn lěng.", "It's cold today.", 0.0, "Off-topic — she's talking about the beautiful scent.")
        ]),
        npc("真的？那你运气好。桂花只开十几天。有些人会摘下来泡茶喝。", "Zhēn de? Nà nǐ yùnqi hǎo. Guìhuā zhǐ kāi shí jǐ tiān. Yǒuxiē rén huì zhāi xiàlái pào chá hē.", "Really? You're lucky then. Osmanthus only blooms for about two weeks. Some people pick the flowers to make tea."),
        player("Respond with curiosity.", [
            opt("桂花茶！听起来一定很好喝。你会做吗？", "Guìhuā chá! Tīng qǐlái yīdìng hěn hǎo hē. Nǐ huì zuò ma?", "Osmanthus tea! That must taste wonderful. Do you know how to make it?", 1.0, "Curious and engaged — wants to learn more."),
            opt("我不喝茶。", "Wǒ bù hē chá.", "I don't drink tea.", 0.0, "Off-topic — shuts down the conversation."),
            opt("我要赶快回家。", "Wǒ yào gǎnkuài huí jiā.", "I need to hurry home.", 0.0, "Off-topic — rushes past a beautiful moment.")
        ])
    ],
    "Osmanthus (桂花) blooming in autumn is one of China's most anticipated seasonal events. The sweet, intense fragrance fills entire neighborhoods. Making osmanthus tea, wine, and rice cakes is a tradition that marks the season. The brief bloom is a reminder to savor fleeting beauty."
))

write_dlg("j2_dlg_026.json", dlg(
    "The Overnight Train Bunk", "火车卧铺",
    2, 0.4,
    "You're settling into an overnight train sleeper compartment. Your bunkmate, a middle-aged woman, offers you snacks.",
    "你在火车卧铺车厢里安顿下来。同铺的一位中年女士给你递零食。",
    [
        npc("吃点东西吧，火车上的饭不太好吃。你要去哪里？", "Chī diǎn dōngxi ba, huǒchē shàng de fàn bú tài hǎochī. Nǐ yào qù nǎlǐ?", "Have something to eat — the train food isn't great. Where are you headed?"),
        player("Accept the snack and tell her your destination.", [
            opt("谢谢！我去成都，听说那里的火锅特别好吃。", "Xièxie! Wǒ qù Chéngdū, tīngshuō nàlǐ de huǒguō tèbié hǎochī.", "Thanks! I'm going to Chengdu — I hear the hotpot there is amazing.", 1.0, "Grateful and enthusiastic — a natural conversation starter."),
            opt("我不饿。", "Wǒ bú è.", "I'm not hungry.", 0.0, "Off-topic — refusing offered snacks from a friendly stranger is cold."),
            opt("火车票很贵。", "Huǒchē piào hěn guì.", "Train tickets are expensive.", 0.0, "Off-topic — she asked where you're going, not about prices.")
        ]),
        npc("成都好啊！我就是成都人。你一定要去宽窄巷子走走，还有人民公园的茶馆。", "Chéngdū hǎo a! Wǒ jiù shì Chéngdū rén. Nǐ yīdìng yào qù Kuānzhǎi Xiàngzi zǒu zou, hái yǒu Rénmín Gōngyuán de cháguǎn.", "Chengdu is great! I'm from Chengdu. You must visit Kuanzhai Alley and the teahouse in People's Park."),
        player("Respond to her local knowledge.", [
            opt("太好了，遇到本地人了！你能再多推荐一些吗？", "Tài hǎo le, yù dào běndì rén le! Nǐ néng zài duō tuījiàn yīxiē ma?", "How lucky — meeting a local! Can you recommend more?", 1.0, "Eager to learn — values her insider knowledge."),
            opt("我已经查好了。", "Wǒ yǐjīng chá hǎo le.", "I've already looked it up.", 0.0, "Off-topic — dismisses her generous offer to help."),
            opt("卧铺不太舒服。", "Wòpù bú tài shūfu.", "The sleeper bunk isn't very comfortable.", 0.0, "Off-topic — changes subject rudely.")
        ])
    ],
    "Overnight train (卧铺) conversations are legendary in China. Strangers sharing a sleeper compartment often become temporary friends, exchanging food, stories, and travel tips. The intimacy of the small space breaks down social barriers."
))

write_dlg("j2_dlg_027.json", dlg(
    "The Pharmacy Visit", "去药店",
    2, 0.4,
    "You have a sore throat and go to a neighborhood pharmacy. The pharmacist is a friendly older woman.",
    "你嗓子疼，去了小区的药店。药剂师是一位友善的阿姨。",
    [
        npc("你怎么了？脸色不太好。", "Nǐ zěnme le? Liǎnsè bú tài hǎo.", "What's wrong? You don't look well."),
        player("Describe your symptoms.", [
            opt("嗓子有点疼，可能是感冒了。有什么药推荐吗？", "Sǎngzi yǒudiǎn téng, kěnéng shì gǎnmào le. Yǒu shénme yào tuījiàn ma?", "My throat hurts a bit — probably a cold. Any medicine you'd recommend?", 1.0, "Clear and practical — gives her what she needs to help."),
            opt("我想买牙膏。", "Wǒ xiǎng mǎi yágāo.", "I want to buy toothpaste.", 0.0, "Off-topic — she asked what's wrong with you."),
            opt("今天天气不好。", "Jīntiān tiānqì bù hǎo.", "The weather is bad today.", 0.0, "Off-topic — she's concerned about your health.")
        ]),
        npc("这个润喉糖很好，含一颗就会舒服很多。回家多喝热水，少说话，好好休息。", "Zhège rùnhóu táng hěn hǎo, hán yī kē jiù huì shūfu hěn duō. Huí jiā duō hē rè shuǐ, shǎo shuōhuà, hǎohāo xiūxi.", "These throat lozenges are good — just one and you'll feel much better. Go home, drink more hot water, talk less, and rest well."),
        player("Thank her for the advice.", [
            opt("好的，我听您的。谢谢阿姨，多少钱？", "Hǎo de, wǒ tīng nín de. Xièxie āyí, duōshao qián?", "Okay, I'll follow your advice. Thank you, auntie — how much?", 1.0, "Respectful and trusting — addresses her warmly."),
            opt("我不喜欢吃药。", "Wǒ bù xǐhuan chī yào.", "I don't like taking medicine.", 0.0, "Off-topic — she recommended throat lozenges, not pills."),
            opt("有没有西药？", "Yǒu méiyǒu xīyào?", "Do you have Western medicine?", 0.0, "Off-topic — dismisses her recommendation without trying it.")
        ])
    ],
    "Neighborhood pharmacists in China often dispense both medicine and motherly advice. Being told to drink hot water and rest well is a form of care. Calling a pharmacist 阿姨 (auntie) shows warmth and respect."
))

write_dlg("j2_dlg_028.json", dlg(
    "The Sunset Fisherman", "夕阳下的钓鱼人",
    2, 0.4,
    "You walk along a lake at sunset and see a man fishing alone. He seems very peaceful.",
    "你在夕阳下沿着湖边走，看到一个人在独自钓鱼。他看起来很平静。",
    [
        npc("你也喜欢来湖边吗？我每个周末都来钓鱼。不为钓鱼，就是喜欢安静。", "Nǐ yě xǐhuan lái húbiān ma? Wǒ měi ge zhōumò dōu lái diàoyú. Bú wèi diàoyú, jiù shì xǐhuan ānjìng.", "You like coming to the lake too? I come fishing every weekend. Not for the fish — just for the quiet."),
        player("Share why you came to the lake.", [
            opt("我也是。走一走，看看水，心情就会好很多。", "Wǒ yě shì. Zǒu yī zǒu, kànkan shuǐ, xīnqíng jiù huì hǎo hěn duō.", "Same here. A walk, looking at the water — it really lifts my mood.", 1.0, "Kindred spirit — connects over shared need for quiet."),
            opt("你钓到了什么鱼？", "Nǐ diào dào le shénme yú?", "What fish did you catch?", 0.0, "Off-topic — he just said he's not here for the fish."),
            opt("这个湖干净吗？", "Zhège hú gānjìng ma?", "Is this lake clean?", 0.0, "Off-topic — misses the contemplative tone.")
        ]),
        npc("现在的生活太快了。在这里坐一坐，什么都不想，是最好的休息。", "Xiànzài de shēnghuó tài kuài le. Zài zhèlǐ zuò yī zuò, shénme dōu bù xiǎng, shì zuì hǎo de xiūxi.", "Life is too fast now. Sitting here, thinking about nothing — that's the best rest."),
        player("Respond to his philosophy.", [
            opt("我也越来越觉得这样。有时候什么都不做，反而是最重要的。", "Wǒ yě yuè lái yuè juéde zhèyàng. Yǒu shíhou shénme dōu bú zuò, fǎn'ér shì zuì zhòngyào de.", "I'm starting to feel the same way. Sometimes doing nothing is actually the most important thing.", 1.0, "Reflective — embraces the wisdom of stillness."),
            opt("我没有时间钓鱼。", "Wǒ méiyǒu shíjiān diàoyú.", "I don't have time for fishing.", 0.0, "Off-topic — that's exactly what he's talking about being a problem."),
            opt("夕阳要下去了。", "Xīyáng yào xià qù le.", "The sunset is going down.", 0.0, "Off-topic — states the obvious instead of engaging.")
        ])
    ],
    "Fishing as meditation is deeply rooted in Chinese philosophy. The image of a solitary fisherman at sunset appears throughout Chinese poetry and painting. The practice of 'sitting and forgetting' (坐忘) — emptying the mind — is considered a form of healing."
))

write_dlg("j2_dlg_029.json", dlg(
    "The Shoe Repair Stall", "修鞋摊",
    2, 0.45,
    "Your favorite shoes broke. You find a tiny shoe repair stall on a street corner.",
    "你最喜欢的鞋坏了。你在街角找到一个很小的修鞋摊。",
    [
        npc("这双鞋还能修。你穿了多长时间了？看得出来你很喜欢。", "Zhè shuāng xié hái néng xiū. Nǐ chuān le duō cháng shíjiān le? Kàn de chūlái nǐ hěn xǐhuan.", "These shoes can still be fixed. How long have you had them? I can tell you really like them."),
        player("Tell him about the shoes.", [
            opt("穿了快三年了。很舒服，所以不想换新的。", "Chuān le kuài sān nián le. Hěn shūfu, suǒyǐ bù xiǎng huàn xīn de.", "Almost three years. They're so comfortable — I don't want to get new ones.", 1.0, "Honest and sentimental — values comfort over fashion."),
            opt("新鞋多少钱？", "Xīn xié duōshao qián?", "How much are new shoes?", 0.0, "Off-topic — he's a repair man, not a shoe store."),
            opt("你能快一点吗？", "Nǐ néng kuài yīdiǎn ma?", "Can you be faster?", 0.0, "Off-topic — rude and impatient.")
        ]),
        npc("好东西值得修。现在的人什么都扔，不好。十分钟就好，你等等。", "Hǎo dōngxi zhíde xiū. Xiànzài de rén shénme dōu rēng, bù hǎo. Shí fēnzhōng jiù hǎo, nǐ děng děng.", "Good things are worth repairing. People throw everything away now — that's not good. Ten minutes, just wait."),
        player("Agree with his perspective.", [
            opt("您说得对。好东西修一修可以用很久。谢谢您。", "Nín shuō de duì. Hǎo dōngxi xiū yī xiū kěyǐ yòng hěn jiǔ. Xièxie nín.", "You're right. Good things can last a long time if you repair them. Thank you.", 1.0, "Appreciative — resonates with his values."),
            opt("修好以后会不会再坏？", "Xiū hǎo yǐhòu huì bú huì zài huài?", "Will they break again after you fix them?", 0.0, "Off-topic — doubts his skill instead of appreciating his philosophy."),
            opt("十分钟太久了。", "Shí fēnzhōng tài jiǔ le.", "Ten minutes is too long.", 0.0, "Off-topic — unreasonably impatient.")
        ])
    ],
    "Street-corner cobblers (修鞋匠) represent a philosophy of repair over replacement. Their craft is disappearing but still valued. The idea that 好东西值得修 (good things are worth fixing) extends beyond shoes to relationships and traditions."
))

write_dlg("j2_dlg_030.json", dlg(
    "The Birthday Noodles", "生日面",
    2, 0.45,
    "It's your birthday. Your Chinese friend insists on making you a special bowl of longevity noodles.",
    "今天是你的生日。你的中国朋友坚持要给你做一碗长寿面。",
    [
        npc("生日快乐！在中国，生日要吃面条。长长的面条代表长寿。我做给你吃！", "Shēngrì kuàilè! Zài Zhōngguó, shēngrì yào chī miàntiáo. Cháng cháng de miàntiáo dàibiǎo chángshòu. Wǒ zuò gěi nǐ chī!", "Happy birthday! In China, you eat noodles on your birthday. The long noodles represent long life. I'll make them for you!"),
        player("React to the tradition.", [
            opt("真的吗？我以前不知道！好期待。谢谢你！", "Zhēn de ma? Wǒ yǐqián bù zhīdào! Hǎo qīdài. Xièxie nǐ!", "Really? I didn't know! I'm so excited. Thank you!", 1.0, "Genuinely delighted — embraces the cultural experience."),
            opt("我不喜欢吃面。", "Wǒ bù xǐhuan chī miàn.", "I don't like noodles.", 0.0, "Off-topic — rejects a heartfelt birthday gesture."),
            opt("我更喜欢吃蛋糕。", "Wǒ gèng xǐhuan chī dàngāo.", "I prefer cake.", 0.0, "Off-topic — dismisses Chinese tradition in favor of your own.")
        ]),
        npc("好了！你吃的时候不要把面条咬断，要一口一口地吸进去。这样才长寿。", "Hǎo le! Nǐ chī de shíhou bú yào bǎ miàntiáo yǎo duàn, yào yī kǒu yī kǒu de xī jìnqù. Zhèyàng cái chángshòu.", "Done! When you eat, don't bite the noodles — slurp them in one go. That's how you get a long life."),
        player("Respond after eating.", [
            opt("好吃！这是我吃过的最特别的生日饭。明年也要吃长寿面。", "Hǎochī! Zhè shì wǒ chī guò de zuì tèbié de shēngrì fàn. Míngnián yě yào chī chángshòu miàn.", "Delicious! This is the most special birthday meal I've ever had. I want longevity noodles next year too.", 1.0, "Warm and committed — fully embraces the tradition."),
            opt("面条太长了。", "Miàntiáo tài cháng le.", "The noodles are too long.", 0.0, "Off-topic — misses the entire point of long noodles."),
            opt("你经常做饭吗？", "Nǐ jīngcháng zuòfàn ma?", "Do you cook often?", 0.0, "Off-topic — doesn't respond to the birthday moment.")
        ])
    ],
    "Birthday noodles (长寿面) are a cherished Chinese tradition. The unbroken length of the noodle symbolizes a long, unbroken life. Slurping without biting is both practical (keeps the noodle intact) and symbolic. Friends making this for you is a deep act of care."
))

write_dlg("j2_dlg_031.json", dlg(
    "The Quiet Barbershop", "安静的理发店",
    2, 0.45,
    "You get a haircut at a small neighborhood barbershop. The barber is a quiet man who works slowly and carefully.",
    "你在小区的理发店理发。理发师是一个安静的人，做事很慢很仔细。",
    [
        npc("你想剪什么样的？短一点还是只修一修？", "Nǐ xiǎng jiǎn shénme yàng de? Duǎn yīdiǎn háishi zhǐ xiū yī xiū?", "What kind of cut would you like? Shorter or just a trim?"),
        player("Tell him what you want.", [
            opt("短一点吧，但是不要太短。您看着办就好。", "Duǎn yīdiǎn ba, dànshì bú yào tài duǎn. Nín kànzhe bàn jiù hǎo.", "A bit shorter, but not too short. I'll leave it to you.", 1.0, "Trusting — gives creative freedom respectfully."),
            opt("我要跟明星一样的。", "Wǒ yào gēn míngxīng yīyàng de.", "I want it like a celebrity's.", 0.0, "Off-topic — unrealistic for a neighborhood barbershop."),
            opt("你这里有WiFi吗？", "Nǐ zhèlǐ yǒu WiFi ma?", "Do you have WiFi?", 0.0, "Off-topic — he asked about your haircut.")
        ]),
        npc("好的。你在这边住了多久了？以前没见过你。", "Hǎo de. Nǐ zài zhèbiān zhù le duō jiǔ le? Yǐqián méi jiàn guò nǐ.", "Okay. How long have you lived around here? I haven't seen you before."),
        player("Chat with the barber.", [
            opt("刚搬来两个月。这个小区很安静，我很喜欢。", "Gāng bān lái liǎng ge yuè. Zhège xiǎoqū hěn ānjìng, wǒ hěn xǐhuan.", "Just moved here two months ago. This neighborhood is very quiet — I really like it.", 1.0, "Open and positive — builds a local connection."),
            opt("快一点可以吗？", "Kuài yīdiǎn kěyǐ ma?", "Can you be faster?", 0.0, "Off-topic — rude when he's making conversation."),
            opt("剪完多少钱？", "Jiǎn wán duōshao qián?", "How much when you're done?", 0.0, "Off-topic — jumps to payment during friendly chat.")
        ])
    ],
    "Neighborhood barbershops (理发店) in China are intimate spaces where the barber knows everyone. The slow, careful work reflects an older standard of craftsmanship. 看着办 (I'll leave it to you) shows trust — one of the highest compliments you can give an artisan."
))

write_dlg("j2_dlg_032.json", dlg(
    "The Morning Market Tofu Seller", "早市的豆腐摊",
    2, 0.45,
    "At the morning market, you stop at a tofu stall. The woman selling tofu made it herself this morning.",
    "在早市上，你在一个豆腐摊前停下来。卖豆腐的阿姨今天早上自己做的。",
    [
        npc("新鲜豆腐！今天早上三点就起来做的。你吃豆腐吗？", "Xīnxiān dòufu! Jīntiān zǎoshang sān diǎn jiù qǐlái zuò de. Nǐ chī dòufu ma?", "Fresh tofu! I got up at three this morning to make it. Do you eat tofu?"),
        player("Tell her about your tofu experience.", [
            opt("吃！但是我不太会做。你有没有简单的做法？", "Chī! Dànshì wǒ bú tài huì zuò. Nǐ yǒu méiyǒu jiǎndān de zuòfǎ?", "Yes! But I don't really know how to cook it. Do you have a simple recipe?", 1.0, "Engaged and eager to learn — respects her expertise."),
            opt("三点太早了。", "Sān diǎn tài zǎo le.", "Three o'clock is too early.", 0.0, "Off-topic — sounds like a complaint about her schedule."),
            opt("超市的豆腐更便宜。", "Chāoshì de dòufu gèng piányi.", "Supermarket tofu is cheaper.", 0.0, "Off-topic — insulting to someone who hand-makes her product.")
        ]),
        npc("最简单的：切成块，放一点酱油和葱花，就很好吃了。新鲜的豆腐不需要太多调料。", "Zuì jiǎndān de: qiē chéng kuài, fàng yīdiǎn jiàngyóu hé cōnghuā, jiù hěn hǎochī le. Xīnxiān de dòufu bù xūyào tài duō tiáoliào.", "Simplest way: cut it into blocks, add a little soy sauce and scallions — delicious. Fresh tofu doesn't need much seasoning."),
        player("Decide to buy some.", [
            opt("听起来很好！我买一块。今晚回家就试试你说的做法。", "Tīng qǐlái hěn hǎo! Wǒ mǎi yī kuài. Jīn wǎn huí jiā jiù shìshi nǐ shuō de zuòfǎ.", "Sounds great! I'll buy one. I'll try your recipe tonight.", 1.0, "Enthusiastic and action-oriented — will actually use her advice."),
            opt("我再看看别的。", "Wǒ zài kànkan bié de.", "I'll look at other stalls.", 0.0, "Off-topic — dismissive after she shared her recipe."),
            opt("可以便宜一点吗？", "Kěyǐ piányi yīdiǎn ma?", "Can it be cheaper?", 0.0, "Off-topic — haggling feels wrong after she described her 3am effort.")
        ])
    ],
    "Hand-made tofu (手工豆腐) at morning markets represents a vanishing artisanal tradition. Vendors who wake before dawn take pride in their craft. Their simple cooking advice reflects a core Chinese food philosophy: the freshest ingredients need the least preparation."
))

write_dlg("j2_dlg_033.json", dlg(
    "The Neighbor's Moving Day", "邻居搬家",
    2, 0.45,
    "Your upstairs neighbor is moving out. You see her carrying boxes and looking a little sad.",
    "楼上的邻居要搬走了。你看到她搬箱子，看起来有点难过。",
    [
        npc("我下个星期就搬走了。在这里住了五年，真的舍不得。", "Wǒ xià ge xīngqī jiù bān zǒu le. Zài zhèlǐ zhù le wǔ nián, zhēn de shěbude.", "I'm moving next week. I've lived here five years — I'm really going to miss it."),
        player("Respond to her feelings about leaving.", [
            opt("五年了啊。我也会想你的。你搬到哪里去？", "Wǔ nián le a. Wǒ yě huì xiǎng nǐ de. Nǐ bān dào nǎlǐ qù?", "Five years... I'll miss you too. Where are you moving to?", 1.0, "Warm and empathetic — acknowledges the relationship."),
            opt("我可以用你的停车位吗？", "Wǒ kěyǐ yòng nǐ de tíngchē wèi ma?", "Can I use your parking spot?", 0.0, "Off-topic — shockingly insensitive to her sadness."),
            opt("搬家很累。", "Bānjiā hěn lèi.", "Moving is tiring.", 0.0, "Off-topic — misses the emotional weight of what she's saying.")
        ]),
        npc("搬到城的另一边去，因为工作。离这里比较远。希望以后还能常见面。", "Bān dào chéng de lìng yī biān qù, yīnwèi gōngzuò. Lí zhèlǐ bǐjiào yuǎn. Xīwàng yǐhòu hái néng cháng jiànmiàn.", "Moving to the other side of the city for work. It's quite far. I hope we can still see each other often."),
        player("Say something meaningful before she leaves.", [
            opt("一定的。你需要帮忙搬东西吗？我可以帮你。", "Yīdìng de. Nǐ xūyào bāngmáng bān dōngxi ma? Wǒ kěyǐ bāng nǐ.", "Definitely. Do you need help carrying things? I can help.", 1.0, "Kind and practical — offers real help."),
            opt("远也没关系。", "Yuǎn yě méi guānxi.", "Far doesn't matter.", 0.0, "Off-topic — dismissive of her genuine concern."),
            opt("你的房子会租给谁？", "Nǐ de fángzi huì zū gěi shéi?", "Who will rent your place?", 0.0, "Off-topic — focuses on the apartment, not the person.")
        ])
    ],
    "In Chinese apartment buildings, neighbors who share walls and hallways for years become like family. The word 舍不得 (shěbude) — reluctant to part with — captures a bittersweet attachment that has no direct English equivalent."
))

write_dlg("j2_dlg_034.json", dlg(
    "The Calligraphy Table", "书法桌",
    2, 0.45,
    "In the park, an old man has set up a table and is practicing calligraphy with a water brush on the ground. You watch.",
    "在公园里，一位老人摆了一张桌子，用水笔在地上写书法。你在旁边看。",
    [
        npc("看什么呢？想不想试试？", "Kàn shénme ne? Xiǎng bù xiǎng shìshi?", "What are you looking at? Want to try?"),
        player("Tell him you'd like to try.", [
            opt("我很想试！但是我写中文写得不好。", "Wǒ hěn xiǎng shì! Dànshì wǒ xiě Zhōngwén xiě de bù hǎo.", "I'd love to try! But my Chinese writing isn't very good.", 1.0, "Eager and humble — doesn't let imperfection stop you."),
            opt("水会干的。", "Shuǐ huì gān de.", "The water will dry.", 0.0, "Off-topic — that's the point, and it misses the beauty of it."),
            opt("我不喜欢书法。", "Wǒ bù xǐhuan shūfǎ.", "I don't like calligraphy.", 0.0, "Off-topic — you stopped to watch, so clearly you're interested.")
        ]),
        npc("没关系，写得好不好不重要。重要的是心静下来。你先写一个「水」字。", "Méi guānxi, xiě de hǎo bù hǎo bú zhòngyào. Zhòngyào de shì xīn jìng xiàlái. Nǐ xiān xiě yī ge「shuǐ」zì.", "It doesn't matter if it's good. What matters is calming your mind. First write the character for 'water.'"),
        player("Try writing and share how you feel.", [
            opt("写完以后觉得心真的安静了很多。书法原来是这样的。", "Xiě wán yǐhòu juéde xīn zhēn de ānjìng le hěn duō. Shūfǎ yuánlái shì zhèyàng de.", "After writing, I really do feel calmer. So this is what calligraphy is about.", 1.0, "Genuine realization — discovers the meditative quality."),
            opt("我写的不好看。", "Wǒ xiě de bù hǎokàn.", "Mine doesn't look good.", 0.0, "Off-topic — he just said that doesn't matter."),
            opt("你教别人吗？", "Nǐ jiāo biérén ma?", "Do you teach others?", 0.0, "Off-topic — he's already teaching you right now.")
        ])
    ],
    "Water calligraphy (地书) on park pavement is a common sight in Chinese parks. The characters evaporate, making the art truly ephemeral. Practitioners emphasize that the goal is inner calm (心静), not beautiful characters. The word 水 (water) is often the first taught — its flowing strokes embody the medium itself."
))

write_dlg("j2_dlg_035.json", dlg(
    "The Umbrella Borrower", "借伞的人",
    2, 0.45,
    "You're leaving a convenience store in the rain. A woman without an umbrella is standing at the door, hesitating.",
    "下雨了，你要离开便利店。一位没带伞的女士站在门口犹豫。",
    [
        npc("你有伞吗？我忘了带……我家就在前面不远。", "Nǐ yǒu sǎn ma? Wǒ wàng le dài…… wǒ jiā jiù zài qiánmiàn bù yuǎn.", "Do you have an umbrella? I forgot mine... My home is just ahead, not far."),
        player("Offer to help.", [
            opt("我有。你拿去用吧，反正我不着急。", "Wǒ yǒu. Nǐ ná qù yòng ba, fǎnzhèng wǒ bù zháojí.", "I do. Take it — I'm not in a rush anyway.", 1.0, "Generous and effortless — genuine kindness."),
            opt("你可以买一把。", "Nǐ kěyǐ mǎi yī bǎ.", "You can buy one.", 0.0, "Off-topic — unhelpful when she's in need right now."),
            opt("雨不大。", "Yǔ bú dà.", "The rain isn't heavy.", 0.0, "Off-topic — dismissive of her problem.")
        ]),
        npc("真的？太谢谢了！那我怎么还给你？你住在附近吗？", "Zhēn de? Tài xièxie le! Nà wǒ zěnme huán gěi nǐ? Nǐ zhù zài fùjìn ma?", "Really? Thank you so much! How do I return it? Do you live nearby?"),
        player("Arrange to get the umbrella back.", [
            opt("不用还了，送你了。下次记得带伞。", "Bú yòng huán le, sòng nǐ le. Xià cì jìde dài sǎn.", "No need to return it — it's yours. Remember to bring one next time.", 1.0, "Gracious — turns a small act into a gift."),
            opt("明天同一时间来这里。", "Míngtiān tóng yī shíjiān lái zhèlǐ.", "Come here at the same time tomorrow.", 0.0, "Off-topic — overly rigid for a casual act of kindness."),
            opt("你的微信号多少？", "Nǐ de Wēixìn hào duōshao?", "What's your WeChat?", 0.0, "Off-topic — sounds like you're using the umbrella to get her contact info.")
        ])
    ],
    "Lending or gifting an umbrella to a stranger is a quiet act of kindness seen throughout Chinese daily life. The phrase 不用还了 (no need to return it) transforms a loan into a gift — an expression of generosity that expects nothing in return."
))

write_dlg("j2_dlg_036.json", dlg(
    "The Locksmith", "开锁的师傅",
    2, 0.45,
    "You're locked out of your apartment. You call a locksmith who arrives on a scooter within minutes.",
    "你被锁在公寓外面了。你打电话叫了一个开锁师傅，他几分钟就骑电动车来了。",
    [
        npc("别着急，很快就能打开。你是忘了带钥匙了吧？", "Bié zháojí, hěn kuài jiù néng dǎkāi. Nǐ shì wàng le dài yàoshi le ba?", "Don't worry — I'll have it open in no time. You forgot your keys, right?"),
        player("Explain what happened.", [
            opt("是的，出门太急了。真不好意思这么晚叫你来。", "Shì de, chūmén tài jí le. Zhēn bù hǎo yìsi zhème wǎn jiào nǐ lái.", "Yes, I rushed out. Sorry for calling you so late.", 1.0, "Apologetic and honest — acknowledges the inconvenience."),
            opt("你来得很快。", "Nǐ lái de hěn kuài.", "You came very fast.", 0.0, "Off-topic — doesn't answer his question about what happened."),
            opt("开锁多少钱？", "Kāi suǒ duōshao qián?", "How much to unlock?", 0.0, "Off-topic — jumping to price before explaining the situation feels transactional.")
        ]),
        npc("没事没事，这就是我的工作。好了，开了！你下次出门检查一下钥匙。", "Méi shì méi shì, zhè jiù shì wǒ de gōngzuò. Hǎo le, kāi le! Nǐ xià cì chūmén jiǎnchá yīxià yàoshi.", "No worries, this is my job. There — open! Check your keys before leaving next time."),
        player("Thank him.", [
            opt("太感谢了！您真是帮了大忙。多少钱？", "Tài gǎnxiè le! Nín zhēn shì bāng le dà máng. Duōshao qián?", "Thank you so much! You really saved me. How much?", 1.0, "Genuinely grateful — acknowledges the help first, then pays."),
            opt("能不能便宜点？", "Néng bù néng piányi diǎn?", "Can it be cheaper?", 0.0, "Off-topic — haggling with someone who came to rescue you at night is poor form."),
            opt("你每天开很多锁吗？", "Nǐ měi tiān kāi hěn duō suǒ ma?", "Do you open many locks every day?", 0.0, "Off-topic — he just helped you and gave advice, respond to that.")
        ])
    ],
    "Locksmiths (开锁师傅) in China are remarkably responsive — they arrive quickly on scooters at any hour. The title 师傅 (master/skilled worker) conveys respect for their craft. Their gentle reminder to check your keys is care, not criticism."
))

write_dlg("j2_dlg_037.json", dlg(
    "The Community Bulletin Board", "小区公告栏",
    2, 0.45,
    "You're reading the community bulletin board when a neighbor stops to look too.",
    "你在看小区的公告栏，一位邻居也停下来看。",
    [
        npc("你看到了吗？这个周末小区有活动，一起包饺子。你要去吗？", "Nǐ kàn dào le ma? Zhège zhōumò xiǎoqū yǒu huódòng, yīqǐ bāo jiǎozi. Nǐ yào qù ma?", "Did you see? There's a community event this weekend — making dumplings together. Are you going?"),
        player("Respond to the invitation.", [
            opt("真的吗？我很想去！在哪里报名？", "Zhēn de ma? Wǒ hěn xiǎng qù! Zài nǎlǐ bàomíng?", "Really? I'd love to go! Where do I sign up?", 1.0, "Enthusiastic — eager to join community life."),
            opt("周末我很忙。", "Zhōumò wǒ hěn máng.", "I'm busy this weekend.", 0.0, "Off-topic — a flat refusal without engaging."),
            opt("公告栏上写了什么？", "Gōnggào lán shàng xiě le shénme?", "What does the bulletin board say?", 0.0, "Off-topic — she just told you what it says.")
        ]),
        npc("就在楼下活动室。每次都很热闹。你可以认识很多邻居。上次还有人带了自己做的饼干。", "Jiù zài lóu xià huódòng shì. Měi cì dōu hěn rènao. Nǐ kěyǐ rènshi hěn duō línjū. Shàng cì hái yǒu rén dài le zìjǐ zuò de bǐnggān.", "In the activity room downstairs. It's always lively. You can meet lots of neighbors. Last time someone even brought homemade cookies."),
        player("Show you're looking forward to it.", [
            opt("听起来真好！我也带一些东西去吧。请问几点开始？", "Tīng qǐlái zhēn hǎo! Wǒ yě dài yīxiē dōngxi qù ba. Qǐngwèn jǐ diǎn kāishǐ?", "Sounds wonderful! I'll bring something too. What time does it start?", 1.0, "Proactive and generous — wants to contribute."),
            opt("我不认识邻居。", "Wǒ bú rènshi línjū.", "I don't know the neighbors.", 0.0, "Off-topic — that's exactly why you should go."),
            opt("活动室在哪里？", "Huódòng shì zài nǎlǐ?", "Where is the activity room?", 0.0, "Off-topic — she already said it's downstairs.")
        ])
    ],
    "Community bulletin boards (公告栏) and activity rooms (活动室) are the social infrastructure of Chinese apartment complexes. Group dumpling-making events build neighborhood cohesion. Bringing food to share is the instinctive response of a good neighbor."
))

write_dlg("j2_dlg_038.json", dlg(
    "The Night Bus Home", "夜班公交车",
    2, 0.45,
    "It's late at night. You're the only passenger on the bus. The driver starts a conversation at a red light.",
    "很晚了。你是公交车上唯一的乘客。红灯的时候司机跟你聊天。",
    [
        npc("这么晚了还没回家？加班了吧？", "Zhème wǎn le hái méi huí jiā? Jiābān le ba?", "Still not home this late? Working overtime, right?"),
        player("Tell him why you're out late.", [
            opt("是啊，加了一会儿班。您也辛苦，这么晚还在开车。", "Shì a, jiā le yīhuǐr bān. Nín yě xīnkǔ, zhème wǎn hái zài kāichē.", "Yeah, worked some overtime. You're working hard too — driving this late.", 1.0, "Empathetic — reciprocates the concern."),
            opt("我没加班。", "Wǒ méi jiābān.", "I didn't work overtime.", 0.0, "Off-topic — a flat denial that kills the conversation."),
            opt("还有几站到？", "Hái yǒu jǐ zhàn dào?", "How many stops left?", 0.0, "Off-topic — ignores his friendly check-in.")
        ]),
        npc("习惯了。夜班的路很安静，我反而喜欢。白天太堵了。你在前面哪一站下？", "Xíguàn le. Yèbān de lù hěn ānjìng, wǒ fǎn'ér xǐhuan. Báitiān tài dǔ le. Nǐ zài qiánmiàn nǎ yī zhàn xià?", "I'm used to it. The roads are quiet on the night shift — I actually prefer it. Daytime is too congested. Which stop ahead are you getting off?"),
        player("Tell him your stop and continue the conversation.", [
            opt("下一站就到了。谢谢您，晚上有这趟车真好。回家注意安全。", "Xià yī zhàn jiù dào le. Xièxie nín, wǎnshang yǒu zhè tàng chē zhēn hǎo. Huí jiā zhùyì ānquán.", "Next stop. Thank you — it's nice to have this bus at night. Stay safe going home.", 1.0, "Genuine gratitude — acknowledges the essential service."),
            opt("开快一点吧。", "Kāi kuài yīdiǎn ba.", "Drive faster.", 0.0, "Off-topic — rude and unsafe."),
            opt("你一个月工资多少？", "Nǐ yī ge yuè gōngzī duōshao?", "How much is your monthly salary?", 0.0, "Off-topic — an intrusive question during a pleasant exchange.")
        ])
    ],
    "Night bus drivers in Chinese cities are quiet guardians of the late-night commute. The empty roads and single passengers create an unexpected intimacy. Saying 注意安全 (stay safe) to a driver is a common and caring parting phrase."
))

write_dlg("j2_dlg_039.json", dlg(
    "The Bakery at Closing Time", "面包店要关门了",
    2, 0.5,
    "You arrive at a small bakery just before closing. The baker is packing up the last few items.",
    "你在一家小面包店关门前赶到。面包师在收拾最后几样东西。",
    [
        npc("你来得正好！我们要关门了。剩下的这些半价卖。", "Nǐ lái de zhènghǎo! Wǒmen yào guānmén le. Shèng xià de zhèxiē bàn jià mài.", "Perfect timing! We're about to close. What's left is half price."),
        player("React to the deal.", [
            opt("太好了！那我都要了吧。你每天都这么早关门吗？", "Tài hǎo le! Nà wǒ dōu yào le ba. Nǐ měi tiān dōu zhème zǎo guānmén ma?", "Great! I'll take them all then. Do you close this early every day?", 1.0, "Practical and friendly — takes the offer and starts chatting."),
            opt("只剩这些了？", "Zhǐ shèng zhèxiē le?", "Is this all that's left?", 0.0, "Off-topic — sounds disappointed rather than grateful for the deal."),
            opt("你们明天几点开门？", "Nǐmen míngtiān jǐ diǎn kāimén?", "What time do you open tomorrow?", 0.0, "Off-topic — she's offering you a deal right now.")
        ]),
        npc("每天做多少就卖多少，卖完就关。不想浪费。你是住附近的吧？以后早点来，选择更多。", "Měi tiān zuò duōshao jiù mài duōshao, mài wán jiù guān. Bù xiǎng làngfèi. Nǐ shì zhù fùjìn de ba? Yǐhòu zǎodiǎn lái, xuǎnzé gèng duō.", "I make only as much as I sell, and close when it's gone. Don't want to waste. You live nearby? Come earlier next time — more choices."),
        player("Respond to her philosophy.", [
            opt("不浪费，这个想法真好。我以后一定早来。你做的面包闻起来特别香。", "Bú làngfèi, zhège xiǎngfǎ zhēn hǎo. Wǒ yǐhòu yīdìng zǎo lái. Nǐ zuò de miànbāo wén qǐlái tèbié xiāng.", "No waste — that's a great philosophy. I'll definitely come earlier. Your bread smells amazing.", 1.0, "Appreciative — values both her ethics and her craft."),
            opt("做少了不是赚得少吗？", "Zuò shǎo le bú shì zhuàn de shǎo ma?", "Don't you earn less if you make less?", 0.0, "Off-topic — reduces her values to profit."),
            opt("我可以提前预订吗？", "Wǒ kěyǐ tíqián yùdìng ma?", "Can I pre-order?", 0.0, "Off-topic — overly transactional after she shared her philosophy.")
        ])
    ],
    "Small bakeries in China that make only what they can sell embody an anti-waste philosophy (不浪费). This approach values quality and sustainability over profit maximization. The half-price end-of-day sale builds customer loyalty through trust."
))

write_dlg("j2_dlg_040.json", dlg(
    "The Old Bridge", "老桥",
    2, 0.5,
    "You're crossing an old stone bridge in a quiet part of town. A photographer is taking pictures of it.",
    "你在镇上安静的一角过一座老石桥。一位摄影师在拍照。",
    [
        npc("你知道这座桥有多少年了吗？据说有两百多年了。", "Nǐ zhīdào zhè zuò qiáo yǒu duōshao nián le ma? Jùshuō yǒu liǎng bǎi duō nián le.", "Do you know how old this bridge is? They say it's over two hundred years old."),
        player("React to the bridge's history.", [
            opt("两百多年？看起来还是很结实。它一定看过很多故事。", "Liǎng bǎi duō nián? Kàn qǐlái háishi hěn jiēshi. Tā yīdìng kàn guò hěn duō gùshi.", "Over two hundred years? It still looks solid. It must have seen many stories.", 1.0, "Poetic and observant — personifies the bridge."),
            opt("应该建一座新的。", "Yīnggāi jiàn yī zuò xīn de.", "They should build a new one.", 0.0, "Off-topic — misses the value of preservation."),
            opt("你的相机很贵吧？", "Nǐ de xiàngjī hěn guì ba?", "Your camera must be expensive.", 0.0, "Off-topic — he's talking about the bridge, not his equipment.")
        ]),
        npc("是啊。我在拍这个城市里快要消失的老地方。以后可能就看不到了。", "Shì a. Wǒ zài pāi zhège chéngshì lǐ kuài yào xiāoshī de lǎo dìfang. Yǐhòu kěnéng jiù kàn bú dào le.", "Yeah. I'm photographing the old places in this city that are about to disappear. We might not be able to see them in the future."),
        player("Respond to his project.", [
            opt("你做的事很有意义。这些照片以后会变成很珍贵的记录。", "Nǐ zuò de shì hěn yǒu yìyì. Zhèxiē zhàopiàn yǐhòu huì biàn chéng hěn zhēnguì de jìlù.", "What you're doing is really meaningful. These photos will become precious records.", 1.0, "Sincere — recognizes the importance of preservation."),
            opt("你拍了多少张了？", "Nǐ pāi le duōshao zhāng le?", "How many photos have you taken?", 0.0, "Off-topic — focuses on quantity instead of the meaning."),
            opt("我不太喜欢拍照。", "Wǒ bú tài xǐhuan pāi zhào.", "I don't really like taking photos.", 0.0, "Off-topic — makes the conversation about you.")
        ])
    ],
    "China's rapid modernization has made documentary photography of old architecture a race against time. Photographers who capture disappearing bridges, lanes, and buildings are preserving cultural memory. 快要消失的 (about to disappear) carries a sense of urgency and loss."
))

write_dlg("j2_dlg_041.json", dlg(
    "The Delivery Driver in the Rain", "雨中的快递员",
    2, 0.5,
    "A delivery driver arrives at your door soaking wet. He hands you your package with a smile.",
    "快递员浑身湿透地来到你家门口。他笑着把包裹递给你。",
    [
        npc("你的快递。下这么大的雨，不好意思让你等了。", "Nǐ de kuàidì. Xià zhème dà de yǔ, bù hǎo yìsi ràng nǐ děng le.", "Your delivery. Sorry for the wait — the rain is really heavy."),
        player("Respond with concern for him.", [
            opt("别说不好意思！下这么大的雨你还送，太辛苦了。要不要进来喝杯热水？", "Bié shuō bù hǎo yìsi! Xià zhème dà de yǔ nǐ hái sòng, tài xīnkǔ le. Yào bú yào jìnlái hē bēi rè shuǐ?", "Don't apologize! Delivering in this rain — that's so hard. Want to come in for some hot water?", 1.0, "Compassionate — prioritizes his comfort over the package."),
            opt("终于到了！", "Zhōngyú dào le!", "Finally here!", 0.0, "Off-topic — focuses on the package, not the person."),
            opt("包裹有没有湿？", "Bāoguǒ yǒu méiyǒu shī?", "Is the package wet?", 0.0, "Off-topic — the human standing in rain matters more.")
        ]),
        npc("谢谢，不用了。后面还有很多要送的。你给个好评就行了。", "Xièxie, bú yòng le. Hòumiàn hái yǒu hěn duō yào sòng de. Nǐ gěi ge hǎopíng jiù xíng le.", "Thanks, no need. I have many more to deliver. Just give me a good review."),
        player("Wish him well.", [
            opt("一定给好评！你注意安全，路上小心。", "Yīdìng gěi hǎopíng! Nǐ zhùyì ānquán, lùshang xiǎoxīn.", "Definitely giving a good review! Stay safe on the road.", 1.0, "Caring and supportive — treats service workers with dignity."),
            opt("你一天送多少个？", "Nǐ yī tiān sòng duōshao ge?", "How many do you deliver per day?", 0.0, "Off-topic — keeps him standing in the rain longer."),
            opt("好的，再见。", "Hǎo de, zàijiàn.", "Okay, bye.", 0.0, "Off-topic — too curt for someone who braved a storm for you.")
        ])
    ],
    "Delivery drivers (快递员) in China work through extreme weather. Their dedication is increasingly recognized and appreciated. Offering hot water and giving good reviews are small but meaningful ways to show respect for their labor."
))

write_dlg("j2_dlg_042.json", dlg(
    "The Midnight Snack Stall", "深夜小吃摊",
    2, 0.5,
    "Late at night, you find a small food stall still open on a quiet street. The owner is cooking alone under a light.",
    "深夜，你在一条安静的街上发现一个还开着的小吃摊。老板独自在灯下做吃的。",
    [
        npc("这么晚了还出来？来，坐下吃点东西暖暖身子。", "Zhème wǎn le hái chūlái? Lái, zuò xià chī diǎn dōngxi nuǎn nuǎn shēnzi.", "Out this late? Come, sit down and eat something to warm up."),
        player("Sit down and order.", [
            opt("好，来一碗馄饨吧。闻到味道就走不动了。", "Hǎo, lái yī wǎn húntun ba. Wén dào wèidào jiù zǒu bú dòng le.", "Okay, I'll have a bowl of wonton. The smell stopped me in my tracks.", 1.0, "Warm and genuine — the aroma drew you in."),
            opt("你怎么这么晚还开着？", "Nǐ zěnme zhème wǎn hái kāi zhe?", "Why are you still open this late?", 0.0, "Off-topic — she invited you to eat, respond to that first."),
            opt("有菜单吗？", "Yǒu càidān ma?", "Do you have a menu?", 0.0, "Off-topic — street stalls rarely have menus; just look at what's cooking.")
        ]),
        npc("馄饨好了！我每天都在这里到凌晨两点。很多加班的人会来吃一碗再回家。", "Húntun hǎo le! Wǒ měi tiān dōu zài zhèlǐ dào língchén liǎng diǎn. Hěn duō jiābān de rén huì lái chī yī wǎn zài huí jiā.", "Wonton's ready! I'm here every day until 2 AM. A lot of people working late come for a bowl before heading home."),
        player("Respond after tasting the wonton.", [
            opt("好暖和。深夜有这样的地方，真好。辛苦了。", "Hǎo nuǎnhuo. Shēnyè yǒu zhèyàng de dìfang, zhēn hǎo. Xīnkǔ le.", "So warm. Having a place like this late at night is wonderful. You work hard.", 1.0, "Heartfelt — acknowledges both the food and the person."),
            opt("你赚钱多吗？", "Nǐ zhuàn qián duō ma?", "Do you make a lot of money?", 0.0, "Off-topic — invasive question that reduces her work to profit."),
            opt("馄饨还可以。", "Húntun hái kěyǐ.", "The wonton is okay.", 0.0, "Off-topic — lukewarm praise for someone serving you at midnight.")
        ])
    ],
    "Late-night food stalls (深夜小吃摊) are lifelines for China's overworked population. A bowl of hot wonton at midnight carries emotional weight — it's comfort, warmth, and the feeling that someone is still awake caring for you. 辛苦了 means 'you've worked hard' and is a profound acknowledgment."
))

write_dlg("j2_dlg_043.json", dlg(
    "The Morning Dew", "早上的露水",
    2, 0.5,
    "You wake up early and step into the garden. Your landlord is already there, tending to his plants.",
    "你早起走进花园。房东已经在那里照料他的花了。",
    [
        npc("你看，叶子上的露水。每天早上只有这个时候能看到。", "Nǐ kàn, yèzi shàng de lùshuǐ. Měi tiān zǎoshang zhǐ yǒu zhège shíhou néng kàn dào.", "Look, the dew on the leaves. You can only see it at this time every morning."),
        player("Respond to his observation.", [
            opt("真的好美。太阳出来就没了吧？", "Zhēn de hǎo měi. Tàiyáng chūlái jiù méi le ba?", "It's really beautiful. It disappears once the sun comes out, right?", 1.0, "Observant and reflective — appreciates the fleeting beauty."),
            opt("我还很困。", "Wǒ hái hěn kùn.", "I'm still sleepy.", 0.0, "Off-topic — he's sharing something beautiful with you."),
            opt("花园需要浇水吗？", "Huāyuán xūyào jiāo shuǐ ma?", "Does the garden need watering?", 0.0, "Off-topic — misses the poetic moment about dew.")
        ]),
        npc("对。所以我每天都早起。很多美好的东西都是短暂的。习惯早起以后，你会发现世界完全不一样。", "Duì. Suǒyǐ wǒ měi tiān dōu zǎo qǐ. Hěn duō měihǎo de dōngxi dōu shì duǎnzàn de. Xíguàn zǎo qǐ yǐhòu, nǐ huì fāxiàn shìjiè wánquán bù yīyàng.", "Right. That's why I wake up early every day. Many beautiful things are fleeting. Once you get used to waking early, you'll see the world is completely different."),
        player("Respond to his wisdom.", [
            opt("我以后也想每天早起看看。谢谢您让我看到了这些。", "Wǒ yǐhòu yě xiǎng měi tiān zǎo qǐ kànkan. Xièxie nín ràng wǒ kàn dào le zhèxiē.", "I want to start waking early every day too. Thank you for showing me this.", 1.0, "Inspired — the moment genuinely moves you."),
            opt("我起不了这么早。", "Wǒ qǐ bù liǎo zhème zǎo.", "I can't get up this early.", 0.0, "Off-topic — defeatist response to something inspiring."),
            opt("您种了什么花？", "Nín zhǒng le shénme huā?", "What flowers did you plant?", 0.0, "Off-topic — changes the subject away from his deeper point.")
        ])
    ],
    "Morning dew as metaphor for fleeting beauty has deep roots in Chinese philosophy and poetry. The elderly gardener's wisdom — that waking early reveals a hidden world — echoes Daoist ideas about living in harmony with natural rhythms."
))

write_dlg("j2_dlg_044.json", dlg(
    "The Last Light in the Window", "窗口的最后一盏灯",
    2, 0.5,
    "Walking home late, you notice only one window still lit in the apartment building. Your neighbor sees you from her balcony.",
    "深夜走路回家，你发现整栋楼只有一个窗口还亮着灯。你的邻居在阳台上看到你。",
    [
        npc("你也这么晚回来？我在等我女儿。她今天加班。", "Nǐ yě zhème wǎn huílái? Wǒ zài děng wǒ nǚ'ér. Tā jīntiān jiābān.", "You're back this late too? I'm waiting for my daughter. She's working overtime today."),
        player("Respond to her vigil.", [
            opt("妈妈都是这样的。她看到灯亮着，一定很安心。", "Māma dōu shì zhèyàng de. Tā kàn dào dēng liàng zhe, yīdìng hěn ānxīn.", "That's what moms do. Seeing the light on will make her feel safe.", 1.0, "Tender — understands the universal gesture of a mother waiting."),
            opt("加班到这么晚不好。", "Jiābān dào zhème wǎn bù hǎo.", "Working overtime this late isn't good.", 0.0, "Off-topic — she knows, and this doesn't comfort her."),
            opt("我也要睡了。晚安。", "Wǒ yě yào shuì le. Wǎn'ān.", "I should sleep too. Goodnight.", 0.0, "Off-topic — too abrupt when she's sharing something emotional.")
        ]),
        npc("是啊。不管她多大了，我都会等。你也早点休息吧。路上注意安全。", "Shì a. Bùguǎn tā duō dà le, wǒ dōu huì děng. Nǐ yě zǎodiǎn xiūxi ba. Lùshang zhùyì ānquán.", "Yeah. No matter how old she is, I'll always wait. You get some rest too. Stay safe."),
        player("Say goodnight warmly.", [
            opt("谢谢阿姨。她很快就回来了。您也早点休息。晚安。", "Xièxie āyí. Tā hěn kuài jiù huílái le. Nín yě zǎodiǎn xiūxi. Wǎn'ān.", "Thank you, auntie. She'll be home soon. You rest early too. Goodnight.", 1.0, "Reassuring and caring — returns her warmth."),
            opt("晚安。", "Wǎn'ān.", "Goodnight.", 0.0, "Off-topic — too brief for such an intimate moment."),
            opt("你女儿在哪里上班？", "Nǐ nǚ'ér zài nǎlǐ shàngbān?", "Where does your daughter work?", 0.0, "Off-topic — keeps her up when she should rest.")
        ])
    ],
    "A mother leaving the light on for a child who's still out is one of the most universal gestures of love. In Chinese culture, 等门 (waiting at the door) carries deep emotional weight. The lit window says: someone is thinking of you, and you are safe."
))

print("HSK 2 Part 2 complete: 22 files written")
