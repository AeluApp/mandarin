#!/usr/bin/env python3
"""HSK 4 passage rewrites."""
import json

with open("data/reading_passages.json") as f:
    data = json.load(f)

idx = {p["id"]: i for i, p in enumerate(data["passages"])}

def replace_passage(pid, new_data):
    i = idx[pid]
    old = data["passages"][i]
    old["title"] = new_data["title"]
    old["title_zh"] = new_data["title_zh"]
    old["text_zh"] = new_data["text_zh"]
    old["text_pinyin"] = new_data["text_pinyin"]
    old["text_en"] = new_data["text_en"]
    old["questions"] = new_data["questions"]

# ============================================================
# HSK 4 REWRITES (13 passages)
# ============================================================

# 1. j4_observe_003 - Was: rain through café window with realize pattern
# NEW: SEINFELD MOVE - the office thermostat war
replace_passage("j4_observe_003", {
    "title": "The Thermostat War",
    "title_zh": "空调大战",
    "text_zh": "我们办公室有一台空调，但是二十个人对温度的要求不一样。李经理觉得二十六度太热了，每天早上来都把温度调到二十二度。坐在空调下面的小周受不了，等李经理去开会的时候偷偷调到二十六度。下午的时候，财务部的张姐觉得太热了，又调到二十四度。这场战争已经持续了三个月。后来有人在空调遥控器上贴了一张纸条，写着：「本遥控器仅限行政部使用。」但是没有人知道是谁贴的，行政部也说不是他们贴的。现在遥控器被锁在了一个抽屉里。钥匙在谁手上呢？没有人承认。空调停在了二十四度。没有人满意，但是也没有人再吵了。",
    "text_pinyin": "Wǒmen bàngōngshì yǒu yì tái kōngtiáo, dànshì èrshí gè rén duì wēndù de yāoqiú bù yíyàng. Lǐ jīnglǐ juéde èrshíliù dù tài rè le, měi tiān zǎoshang lái dōu bǎ wēndù tiáo dào èrshí'èr dù. Zuò zài kōngtiáo xiàmiàn de Xiǎo Zhōu shòu bù liǎo, děng Lǐ jīnglǐ qù kāi huì de shíhou tōutōu tiáo dào èrshíliù dù. Xiàwǔ de shíhou, cáiwùbù de Zhāng jiě juéde tài rè le, yòu tiáo dào èrshísì dù. Zhè chǎng zhànzhēng yǐjīng chíxù le sān gè yuè. Hòulái yǒu rén zài kōngtiáo yáokòngqì shàng tiē le yì zhāng zhǐtiáo, xiězhe:「Běn yáokòngqì jǐn xiàn xíngzhèngbù shǐyòng.」Dànshì méiyǒu rén zhīdào shì shéi tiē de, xíngzhèngbù yě shuō bú shì tāmen tiē de. Xiànzài yáokòngqì bèi suǒ zài le yí gè chōuti lǐ. Yàoshi zài shéi shǒu shàng ne? Méiyǒu rén chéngrèn. Kōngtiáo tíng zài le èrshísì dù. Méiyǒu rén mǎnyì, dànshì yě méiyǒu rén zài chǎo le.",
    "text_en": "Our office has one air conditioner, but twenty people have different temperature preferences. Manager Li thinks 26 degrees is too hot, and every morning turns it down to 22. Xiao Zhou, who sits right under the AC, can't take it, and sneaks it back to 26 when Manager Li goes to meetings. In the afternoon, Sister Zhang from finance finds it too hot and adjusts it to 24. This war has been going on for three months. Eventually someone stuck a note on the remote: 'This remote is for the administrative department only.' But nobody knows who put it there, and the admin department says it wasn't them. Now the remote is locked in a drawer. Who has the key? Nobody will admit it. The AC sits at 24 degrees. Nobody is satisfied, but nobody argues anymore either.",
    "questions": [
        {"type": "mc", "q_zh": "李经理喜欢把温度调到多少度？", "q_en": "What temperature does Manager Li set?",
         "options": [
             {"text": "二十二度", "pinyin": "èrshí'èr dù", "text_en": "22 degrees", "correct": True},
             {"text": "二十四度", "pinyin": "èrshísì dù", "text_en": "24 degrees", "correct": False},
             {"text": "二十六度", "pinyin": "èrshíliù dù", "text_en": "26 degrees", "correct": False},
             {"text": "二十度", "pinyin": "èrshí dù", "text_en": "20 degrees", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "小周为什么要调温度？", "q_en": "Why does Xiao Zhou adjust the temperature?",
         "options": [
             {"text": "他觉得太热了", "pinyin": "tā juéde tài rè le", "text_en": "he thinks it's too hot", "correct": False},
             {"text": "他坐在空调下面，太冷了", "pinyin": "tā zuò zài kōngtiáo xiàmiàn, tài lěng le", "text_en": "he sits under the AC, too cold", "correct": True},
             {"text": "他喜欢按按钮", "pinyin": "tā xǐhuan àn ànniǔ", "text_en": "he likes pressing buttons", "correct": False},
             {"text": "经理让他调的", "pinyin": "jīnglǐ ràng tā tiáo de", "text_en": "the manager asked him to", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "最后空调停在了多少度？", "q_en": "What temperature is the AC stuck at?",
         "options": [
             {"text": "二十二度", "pinyin": "èrshí'èr dù", "text_en": "22 degrees", "correct": False},
             {"text": "二十四度", "pinyin": "èrshísì dù", "text_en": "24 degrees", "correct": True},
             {"text": "二十六度", "pinyin": "èrshíliù dù", "text_en": "26 degrees", "correct": False},
             {"text": "关了", "pinyin": "guān le", "text_en": "turned off", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 2. j4_identity_001 - Was: "Two Names" with 也许 realize ending
# NEW: SONDHEIM MOVE - says one thing, feels another - farewell dinner
replace_passage("j4_identity_001", {
    "title": "The Farewell Dinner",
    "title_zh": "送别晚饭",
    "text_zh": "小林要搬到另一个城市工作了。走之前，老朋友们在常去的那家小饭馆给他办了一顿送别晚饭。吃饭的时候大家一直在开玩笑，说以后终于不用听小林唱歌了，说他走了以后谁来迟到呢，说新城市的人还不知道自己多倒霉。小林也笑着说：「终于可以离开你们这些人了。」但是点菜的时候，他点的全是大家以前最常点的菜。吃到一半的时候，小林说去洗手间。他走了五分钟才回来，眼睛红红的。大家都假装没有看到。结账的时候谁也不让谁付钱，吵了十分钟。最后还是老板娘说：「算了，这顿我请，你们安静点。」走出饭馆的时候，每个人都说「常联系」，说得很轻松。然后各自往不同的方向走了。",
    "text_pinyin": "Xiǎo Lín yào bān dào lìng yí gè chéngshì gōngzuò le. Zǒu zhīqián, lǎo péngyoumen zài cháng qù de nà jiā xiǎo fànguǎn gěi tā bàn le yí dùn sòngbié wǎnfàn. Chī fàn de shíhou dàjiā yìzhí zài kāi wánxiào, shuō yǐhòu zhōngyú búyòng tīng Xiǎo Lín chàng gē le, shuō tā zǒu le yǐhòu shéi lái chídào ne, shuō xīn chéngshì de rén hái bù zhīdào zìjǐ duō dǎoméi. Xiǎo Lín yě xiàozhe shuō:「Zhōngyú kěyǐ líkāi nǐmen zhèxiē rén le.」Dànshì diǎn cài de shíhou, tā diǎn de quán shì dàjiā yǐqián zuì cháng diǎn de cài. Chī dào yíbàn de shíhou, Xiǎo Lín shuō qù xǐshǒujiān. Tā zǒu le wǔ fēnzhōng cái huílái, yǎnjīng hóng hóng de. Dàjiā dōu jiǎzhuāng méiyǒu kàn dào. Jiézhàng de shíhou shéi yě bú ràng shéi fù qián, chǎo le shí fēnzhōng. Zuìhòu háishi lǎobǎnniáng shuō:「Suàn le, zhè dùn wǒ qǐng, nǐmen ānjìng diǎn.」Zǒu chū fànguǎn de shíhou, měi gè rén dōu shuō「cháng liánxì」, shuō de hěn qīngsōng. Ránhòu gèzì wǎng bù tóng de fāngxiàng zǒu le.",
    "text_en": "Xiao Lin was moving to another city for work. Before he left, his old friends threw him a farewell dinner at the little restaurant they always went to. During dinner everyone kept joking — they said finally they wouldn't have to hear Xiao Lin sing, said who'd be late to everything after he left, said the people in the new city didn't know how unlucky they were. Xiao Lin laughed too: 'Finally I can get away from you people.' But when he ordered, he chose all the dishes the group used to order together. Halfway through the meal, Xiao Lin said he was going to the restroom. He was gone five minutes and came back with red eyes. Everyone pretended not to notice. When the bill came, nobody would let anyone else pay, and they argued for ten minutes. Finally the restaurant owner said: 'Forget it, this one's on me. Quiet down.' Walking out, everyone said 'keep in touch,' casually. Then they walked off in different directions.",
    "questions": [
        {"type": "mc", "q_zh": "大家在饭桌上做什么？", "q_en": "What did everyone do at dinner?",
         "options": [
             {"text": "一直开玩笑", "pinyin": "yìzhí kāi wánxiào", "text_en": "kept joking around", "correct": True},
             {"text": "很安静地吃饭", "pinyin": "hěn ānjìng de chī fàn", "text_en": "ate quietly", "correct": False},
             {"text": "说了很多感人的话", "pinyin": "shuō le hěn duō gǎnrén de huà", "text_en": "said many touching words", "correct": False},
             {"text": "看手机", "pinyin": "kàn shǒujī", "text_en": "looked at phones", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "小林点了什么菜？", "q_en": "What dishes did Xiao Lin order?",
         "options": [
             {"text": "最贵的菜", "pinyin": "zuì guì de cài", "text_en": "the most expensive dishes", "correct": False},
             {"text": "新城市的菜", "pinyin": "xīn chéngshì de cài", "text_en": "dishes from the new city", "correct": False},
             {"text": "大家以前最常点的菜", "pinyin": "dàjiā yǐqián zuì cháng diǎn de cài", "text_en": "the dishes the group always used to order", "correct": True},
             {"text": "他自己最喜欢的菜", "pinyin": "tā zìjǐ zuì xǐhuan de cài", "text_en": "his own favorite dishes", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "最后谁付的钱？", "q_en": "Who paid the bill?",
         "options": [
             {"text": "小林", "pinyin": "Xiǎo Lín", "text_en": "Xiao Lin", "correct": False},
             {"text": "大家一起付的", "pinyin": "dàjiā yìqǐ fù de", "text_en": "everyone split it", "correct": False},
             {"text": "老板娘请客", "pinyin": "lǎobǎnniáng qǐngkè", "text_en": "the restaurant owner treated them", "correct": True},
             {"text": "没有人付", "pinyin": "méiyǒu rén fù", "text_en": "nobody paid", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 3. j4_observe_010 - Was: old man's radio with 才明白 ending
# NEW: ARRESTED DEVELOPMENT MOVE - the 4pm Friday meeting boss
replace_passage("j4_observe_010", {
    "title": "The Friday 4 PM Meeting",
    "title_zh": "周五下午四点的会",
    "text_zh": "我们部门的主管有一个习惯：每个星期五下午四点开会。他觉得这是总结一周工作的最好时间。问题是：下午五点就下班了，开完会周末就开始了。但是他的会从来没有准时结束过。最短的一次也开了一个半小时。所以每个星期五下午三点四十五分，你就能看到一个有趣的现象——每个人都变得特别忙。有人突然接到很重要的电话，有人发现一个必须马上处理的紧急问题，有人去了洗手间就再也没有回来。主管从来不觉得奇怪。他经常在会上说：「我注意到大家周五工作特别努力，三点以后每个人都在忙。」大家低头看着自己的笔记本，谁也不敢笑。",
    "text_pinyin": "Wǒmen bùmén de zhǔguǎn yǒu yí gè xíguàn: měi gè xīngqī wǔ xiàwǔ sì diǎn kāi huì. Tā juéde zhè shì zǒngjié yì zhōu gōngzuò de zuì hǎo shíjiān. Wèntí shì: xiàwǔ wǔ diǎn jiù xiàbān le, kāi wán huì zhōumò jiù kāishǐ le. Dànshì tā de huì cónglái méiyǒu zhǔnshí jiéshù guò. Zuì duǎn de yí cì yě kāi le yí gè bàn xiǎoshí. Suǒyǐ měi gè xīngqī wǔ xiàwǔ sān diǎn sìshíwǔ fēn, nǐ jiù néng kàn dào yí gè yǒuqù de xiànxiàng——měi gè rén dōu biàn de tèbié máng. Yǒu rén tūrán jiē dào hěn zhòngyào de diànhuà, yǒu rén fāxiàn yí gè bìxū mǎshàng chǔlǐ de jǐnjí wèntí, yǒu rén qù le xǐshǒujiān jiù zài yě méiyǒu huílái. Zhǔguǎn cónglái bù juéde qíguài. Tā jīngcháng zài huì shàng shuō:「Wǒ zhùyì dào dàjiā zhōuwǔ gōngzuò tèbié nǔlì, sān diǎn yǐhòu měi gè rén dōu zài máng.」Dàjiā dī tóu kànzhe zìjǐ de bǐjìběn, shéi yě bù gǎn xiào.",
    "text_en": "Our department head has a habit: meetings every Friday at 4 PM. He thinks it's the perfect time to wrap up the week. The problem: work ends at five, and after the meeting the weekend begins. But his meetings have never ended on time. The shortest one still ran an hour and a half. So every Friday at 3:45, you can observe an interesting phenomenon — everyone suddenly gets very busy. Someone receives an urgent phone call. Someone discovers a critical issue that needs immediate attention. Someone goes to the restroom and never comes back. The boss never finds this strange. He often says in meetings: 'I've noticed everyone works especially hard on Fridays — after three o'clock, everyone is busy.' Everyone looks down at their notebooks. Nobody dares laugh.",
    "questions": [
        {"type": "mc", "q_zh": "主管的会最短开了多久？", "q_en": "How long was the boss's shortest meeting?",
         "options": [
             {"text": "半小时", "pinyin": "bàn xiǎoshí", "text_en": "half an hour", "correct": False},
             {"text": "一个小时", "pinyin": "yí gè xiǎoshí", "text_en": "one hour", "correct": False},
             {"text": "一个半小时", "pinyin": "yí gè bàn xiǎoshí", "text_en": "an hour and a half", "correct": True},
             {"text": "两个小时", "pinyin": "liǎng gè xiǎoshí", "text_en": "two hours", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "三点四十五分大家在做什么？", "q_en": "What is everyone doing at 3:45?",
         "options": [
             {"text": "准备开会", "pinyin": "zhǔnbèi kāi huì", "text_en": "preparing for the meeting", "correct": False},
             {"text": "假装特别忙来避开会议", "pinyin": "jiǎzhuāng tèbié máng lái bìkāi huìyì", "text_en": "pretending to be busy to avoid the meeting", "correct": True},
             {"text": "收拾东西准备下班", "pinyin": "shōushi dōngxi zhǔnbèi xiàbān", "text_en": "packing up to leave", "correct": False},
             {"text": "在会议室等着", "pinyin": "zài huìyìshì děngzhe", "text_en": "waiting in the meeting room", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "主管觉得大家周五下午怎么样？", "q_en": "What does the boss think about Fridays?",
         "options": [
             {"text": "大家想早下班", "pinyin": "dàjiā xiǎng zǎo xiàbān", "text_en": "everyone wants to leave early", "correct": False},
             {"text": "大家不喜欢开会", "pinyin": "dàjiā bù xǐhuan kāi huì", "text_en": "nobody likes meetings", "correct": False},
             {"text": "大家工作特别努力", "pinyin": "dàjiā gōngzuò tèbié nǔlì", "text_en": "everyone works especially hard", "correct": True},
             {"text": "大家都不在", "pinyin": "dàjiā dōu bú zài", "text_en": "everyone is absent", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 4. j4_mystery_003 - Was: piano at midnight with 突然 pattern
# NEW: EZRA KLEIN MOVE - patient layered inquiry about a small mystery
replace_passage("j4_mystery_003", {
    "title": "The Disappearing Bananas",
    "title_zh": "消失的香蕉",
    "text_zh": "办公室的水果篮里每天都有水果。苹果、橘子、香蕉。但是每天下午两点以前，香蕉一定会全部消失，苹果和橘子还在。我开始注意这件事。星期一，我数了一下，早上有六根香蕉。到了下午一点，只剩两根了。我两点再去看——全没了。我问隔壁的同事：「你拿了香蕉吗？」他说没有。我又问了三个人，都说没有。但是有人告诉我一个细节：行政部的王姐每天下午两点会经过我们这层楼去开会。我第二天特别注意了一下。下午一点五十分，王姐走过来，看了看水果篮，很自然地拿了两根香蕉放进包里，然后继续走。她走的动作非常自然，就像在自己家厨房拿东西一样。我很想问她，但是不知道为什么，我觉得如果问了，就会破坏某种平衡。所以我没问。香蕉继续每天消失。",
    "text_pinyin": "Bàngōngshì de shuǐguǒ lán lǐ měi tiān dōu yǒu shuǐguǒ. Píngguǒ, júzi, xiāngjiāo. Dànshì měi tiān xiàwǔ liǎng diǎn yǐqián, xiāngjiāo yídìng huì quánbù xiāoshī, píngguǒ hé júzi hái zài. Wǒ kāishǐ zhùyì zhè jiàn shì. Xīngqī yī, wǒ shǔ le yíxià, zǎoshang yǒu liù gēn xiāngjiāo. Dào le xiàwǔ yì diǎn, zhǐ shèng liǎng gēn le. Wǒ liǎng diǎn zài qù kàn——quán méi le. Wǒ wèn gébì de tóngshì:「Nǐ ná le xiāngjiāo ma?」Tā shuō méiyǒu. Wǒ yòu wèn le sān gè rén, dōu shuō méiyǒu. Dànshì yǒu rén gàosu wǒ yí gè xìjié: xíngzhèngbù de Wáng jiě měi tiān xiàwǔ liǎng diǎn huì jīngguò wǒmen zhè céng lóu qù kāi huì. Wǒ dì èr tiān tèbié zhùyì le yíxià. Xiàwǔ yì diǎn wǔshí fēn, Wáng jiě zǒu guòlái, kàn le kàn shuǐguǒ lán, hěn zìrán de ná le liǎng gēn xiāngjiāo fàng jìn bāo lǐ, ránhòu jìxù zǒu. Tā zǒu de dòngzuò fēicháng zìrán, jiù xiàng zài zìjǐ jiā chúfáng ná dōngxi yíyàng. Wǒ hěn xiǎng wèn tā, dànshì bù zhīdào wèi shénme, wǒ juéde rúguǒ wèn le, jiù huì pòhuài mǒu zhǒng pínghéng. Suǒyǐ wǒ méi wèn. Xiāngjiāo jìxù měi tiān xiāoshī.",
    "text_en": "The office fruit basket gets refilled every day. Apples, oranges, bananas. But every day before 2 PM, the bananas are always gone, while the apples and oranges remain. I started paying attention. Monday I counted: six bananas in the morning. By 1 PM, only two left. At 2 PM — all gone. I asked the colleague next to me: 'Did you take a banana?' No. I asked three more people. All said no. But someone mentioned a detail: Sister Wang from admin passes through our floor every day at 2 PM on her way to a meeting. The next day I watched carefully. At 1:50, Sister Wang walked by, glanced at the fruit basket, took two bananas and put them in her bag with a perfectly natural motion, then kept walking. Her movement was completely natural, like grabbing something from her own kitchen. I wanted to ask her about it, but for some reason I felt that asking would disrupt some kind of balance. So I didn't. The bananas keep disappearing every day.",
    "questions": [
        {"type": "mc", "q_zh": "每天消失的水果是什么？", "q_en": "Which fruit disappears every day?",
         "options": [
             {"text": "苹果", "pinyin": "píngguǒ", "text_en": "apples", "correct": False},
             {"text": "橘子", "pinyin": "júzi", "text_en": "oranges", "correct": False},
             {"text": "香蕉", "pinyin": "xiāngjiāo", "text_en": "bananas", "correct": True},
             {"text": "所有水果", "pinyin": "suǒyǒu shuǐguǒ", "text_en": "all fruit", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "王姐拿香蕉的动作怎么样？", "q_en": "How does Sister Wang take the bananas?",
         "options": [
             {"text": "很紧张", "pinyin": "hěn jǐnzhāng", "text_en": "nervously", "correct": False},
             {"text": "非常自然", "pinyin": "fēicháng zìrán", "text_en": "very naturally", "correct": True},
             {"text": "偷偷地", "pinyin": "tōutōu de", "text_en": "secretly", "correct": False},
             {"text": "很快地", "pinyin": "hěn kuài de", "text_en": "very quickly", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "「我」为什么没有问王姐？", "q_en": "Why didn't 'I' ask Sister Wang?",
         "options": [
             {"text": "怕她生气", "pinyin": "pà tā shēngqì", "text_en": "afraid she'd be angry", "correct": False},
             {"text": "觉得问了会破坏某种平衡", "pinyin": "juéde wèn le huì pòhuài mǒu zhǒng pínghéng", "text_en": "felt asking would disrupt some balance", "correct": True},
             {"text": "没有时间", "pinyin": "méiyǒu shíjiān", "text_en": "didn't have time", "correct": False},
             {"text": "不在意", "pinyin": "bú zàiyì", "text_en": "didn't care", "correct": False}
         ], "difficulty": 0.4}
    ]
})

# 5. j4_observe_015 - Was: sound of chopping with 突然 pattern
# NEW: COMPETENT AND A MESS character study
replace_passage("j4_observe_015", {
    "title": "The Brilliant Coworker",
    "title_zh": "天才同事",
    "text_zh": "我的同事老张是公司里技术最好的人。老板有什么难题都找他，他每次都能解决。但是老张的桌子是整个办公室最乱的。文件堆得像小山，咖啡杯从来没有少于三个，他的键盘上有去年感恩节的面包屑。他的日程表永远是乱的，经常忘记开会时间。上个月他把重要的报告发错了三次——两次发给了错误的人，一次发给了自己。但是每次遇到真正困难的技术问题，大家都安静下来等他说话。他会看着屏幕想三分钟，然后说出一个没有人想到的解决方案。老板曾经派人帮他整理桌子，第二天他找不到任何东西了，那一周是他效率最低的一周。从那以后，没有人再动过他的桌子。",
    "text_pinyin": "Wǒ de tóngshì Lǎo Zhāng shì gōngsī lǐ jìshù zuì hǎo de rén. Lǎobǎn yǒu shénme nántí dōu zhǎo tā, tā měi cì dōu néng jiějué. Dànshì Lǎo Zhāng de zhuōzi shì zhěnggè bàngōngshì zuì luàn de. Wénjiàn duī de xiàng xiǎo shān, kāfēi bēi cónglái méiyǒu shǎo yú sān gè, tā de jiànpán shàng yǒu qùnián Gǎn'ēnjié de miànbāo xiè. Tā de rìchéng biǎo yǒngyuǎn shì luàn de, jīngcháng wàng jì kāi huì shíjiān. Shàng gè yuè tā bǎ zhòngyào de bàogào fā cuò le sān cì——liǎng cì fā gěi le cuòwù de rén, yí cì fā gěi le zìjǐ. Dànshì měi cì yù dào zhēnzhèng kùnnan de jìshù wèntí, dàjiā dōu ānjìng xiàlái děng tā shuō huà. Tā huì kànzhe píngmù xiǎng sān fēnzhōng, ránhòu shuō chū yí gè méiyǒu rén xiǎng dào de jiějué fāng'àn. Lǎobǎn céngjīng pài rén bāng tā zhěnglǐ zhuōzi, dì èr tiān tā zhǎo bú dào rènhé dōngxi le, nà yì zhōu shì tā xiàolǜ zuì dī de yì zhōu. Cóng nà yǐhòu, méiyǒu rén zài dòng guò tā de zhuōzi.",
    "text_en": "My colleague Lao Zhang is the best engineer at the company. The boss brings every hard problem to him, and he always solves it. But Lao Zhang's desk is the messiest in the entire office. Papers stacked like mountains, never fewer than three coffee cups, crumbs from last Thanksgiving still on his keyboard. His calendar is always a mess, and he constantly forgets meeting times. Last month he sent an important report to the wrong person three times — twice to the wrong colleagues, once to himself. But whenever there's a truly difficult technical problem, everyone goes quiet and waits for him to speak. He'll stare at the screen for three minutes, then propose a solution nobody thought of. The boss once sent someone to organize his desk. The next day he couldn't find anything, and it was his least productive week. After that, nobody touched his desk again.",
    "questions": [
        {"type": "mc", "q_zh": "老张最擅长什么？", "q_en": "What is Lao Zhang best at?",
         "options": [
             {"text": "整理文件", "pinyin": "zhěnglǐ wénjiàn", "text_en": "organizing files", "correct": False},
             {"text": "技术", "pinyin": "jìshù", "text_en": "technology/engineering", "correct": True},
             {"text": "开会", "pinyin": "kāi huì", "text_en": "meetings", "correct": False},
             {"text": "写报告", "pinyin": "xiě bàogào", "text_en": "writing reports", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "帮他整理桌子以后怎么了？", "q_en": "What happened after his desk was organized?",
         "options": [
             {"text": "他工作效率更高了", "pinyin": "tā gōngzuò xiàolǜ gèng gāo le", "text_en": "he became more productive", "correct": False},
             {"text": "那一周是他效率最低的一周", "pinyin": "nà yì zhōu shì tā xiàolǜ zuì dī de yì zhōu", "text_en": "it was his least productive week", "correct": True},
             {"text": "他很高兴", "pinyin": "tā hěn gāoxìng", "text_en": "he was happy", "correct": False},
             {"text": "他把桌子弄得更乱了", "pinyin": "tā bǎ zhuōzi nòng de gèng luàn le", "text_en": "he made it even messier", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "上个月报告发错了几次？", "q_en": "How many times was the report sent to the wrong person last month?",
         "options": [
             {"text": "一次", "pinyin": "yí cì", "text_en": "once", "correct": False},
             {"text": "两次", "pinyin": "liǎng cì", "text_en": "twice", "correct": False},
             {"text": "三次", "pinyin": "sān cì", "text_en": "three times", "correct": True},
             {"text": "四次", "pinyin": "sì cì", "text_en": "four times", "correct": False}
         ], "difficulty": 0.2}
    ]
})

# 6. j4_observe_026 - Was: fog in park with realize pattern
# NEW: GOLDEN GIRLS banter - elderly neighbors
replace_passage("j4_observe_026", {
    "title": "The Elevator Neighbors",
    "title_zh": "电梯里的邻居",
    "text_zh": "我楼里有两个老太太，一个住三楼，一个住五楼。她们每天早上八点在电梯里碰面，已经碰了十五年了。她们的对话永远是一个样子。三楼的说：「今天冷不冷？」五楼的说：「冷。你穿少了。」三楼的说：「我不冷。」五楼的说：「你每次都说不冷，然后每次都感冒。」三楼的说：「我上次感冒是三年前的事了。」五楼的说：「是去年十一月。你忘了？你还借了我的围巾。」三楼的不说话了。电梯到了一楼，她们一起走出去。三楼的走了两步，回头说：「你那条围巾不好看。」五楼的说：「你借的时候没有嫌难看。」两个人一起笑了，然后各走各的路。",
    "text_pinyin": "Wǒ lóu lǐ yǒu liǎng gè lǎo tàitai, yí gè zhù sān lóu, yí gè zhù wǔ lóu. Tāmen měi tiān zǎoshang bā diǎn zài diàntī lǐ pèng miàn, yǐjīng pèng le shíwǔ nián le. Tāmen de duìhuà yǒngyuǎn shì yí gè yàngzi. Sān lóu de shuō:「Jīntiān lěng bu lěng?」Wǔ lóu de shuō:「Lěng. Nǐ chuān shǎo le.」Sān lóu de shuō:「Wǒ bù lěng.」Wǔ lóu de shuō:「Nǐ měi cì dōu shuō bù lěng, ránhòu měi cì dōu gǎnmào.」Sān lóu de shuō:「Wǒ shàng cì gǎnmào shì sān nián qián de shì le.」Wǔ lóu de shuō:「Shì qùnián shíyī yuè. Nǐ wàng le? Nǐ hái jiè le wǒ de wéijīn.」Sān lóu de bù shuō huà le. Diàntī dào le yī lóu, tāmen yìqǐ zǒu chūqù. Sān lóu de zǒu le liǎng bù, huí tóu shuō:「Nǐ nà tiáo wéijīn bù hǎokàn.」Wǔ lóu de shuō:「Nǐ jiè de shíhou méiyǒu xián nánkàn.」Liǎng gè rén yìqǐ xiào le, ránhòu gè zǒu gè de lù.",
    "text_en": "In my building there are two old ladies, one on the third floor and one on the fifth. Every morning at eight they meet in the elevator. This has been going on for fifteen years. Their conversation is always the same. Third floor: 'Cold today?' Fifth floor: 'Cold. You're not dressed warm enough.' Third floor: 'I'm not cold.' Fifth floor: 'You always say you're not cold, then you always catch a cold.' Third floor: 'My last cold was three years ago.' Fifth floor: 'It was last November. Forgot? You borrowed my scarf.' Third floor goes quiet. The elevator reaches the ground floor and they walk out together. Third floor takes two steps, turns around: 'That scarf was ugly.' Fifth floor: 'You didn't complain when you borrowed it.' They both laugh, then go their separate ways.",
    "questions": [
        {"type": "mc", "q_zh": "两个老太太认识多久了？", "q_en": "How long have the two ladies known each other?",
         "options": [
             {"text": "五年", "pinyin": "wǔ nián", "text_en": "five years", "correct": False},
             {"text": "十年", "pinyin": "shí nián", "text_en": "ten years", "correct": False},
             {"text": "十五年", "pinyin": "shíwǔ nián", "text_en": "fifteen years", "correct": True},
             {"text": "二十年", "pinyin": "èrshí nián", "text_en": "twenty years", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "三楼的老太太上次什么时候感冒的？", "q_en": "When did the third-floor lady last have a cold?",
         "options": [
             {"text": "三年前", "pinyin": "sān nián qián", "text_en": "three years ago", "correct": False},
             {"text": "去年十一月", "pinyin": "qùnián shíyī yuè", "text_en": "last November", "correct": True},
             {"text": "上个月", "pinyin": "shàng gè yuè", "text_en": "last month", "correct": False},
             {"text": "她从来没感冒过", "pinyin": "tā cónglái méi gǎnmào guò", "text_en": "she's never had a cold", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "三楼的老太太怎么评价那条围巾？", "q_en": "How did the third-floor lady describe the scarf?",
         "options": [
             {"text": "很好看", "pinyin": "hěn hǎokàn", "text_en": "pretty", "correct": False},
             {"text": "不好看", "pinyin": "bù hǎokàn", "text_en": "ugly", "correct": True},
             {"text": "很暖和", "pinyin": "hěn nuǎnhuo", "text_en": "warm", "correct": False},
             {"text": "太旧了", "pinyin": "tài jiù le", "text_en": "too old", "correct": False}
         ], "difficulty": 0.2}
    ]
})

# 7. j4_observe_030 - Was: grandfather clock with 突然 realize
# NEW: POMPOSITY PUNCTURE - coffee snob
replace_passage("j4_observe_030", {
    "title": "The Coffee Expert",
    "title_zh": "咖啡专家",
    "text_zh": "公司新来了一个同事，他对咖啡非常讲究。他自己带咖啡豆来办公室，用自己的磨豆机磨，用自己的法压壶泡。他经常跟我们说：「速溶咖啡不是真正的咖啡。你们喝的那些东西，连咖啡都算不上。」有一天，他给每个人倒了一小杯他做的咖啡，让大家品尝。他说这是来自埃塞俄比亚的特级豆子，有花果的香味。大家都说好喝，虽然大部分人觉得味道跟公司咖啡机出来的差不多。后来有一次部门聚餐，他迟到了半小时。到的时候大家已经在喝饮料了。他很渴，坐下来拿起桌上唯一剩下的一杯咖啡就喝了。「这个还行，」他说，「哪家的豆子？」旁边的人说：「那是速溶的。」整张桌子安静了三秒钟，然后所有人同时笑了出来。他也笑了，虽然脸有点红。",
    "text_pinyin": "Gōngsī xīn lái le yí gè tóngshì, tā duì kāfēi fēicháng jiǎngjiu. Tā zìjǐ dài kāfēi dòu lái bàngōngshì, yòng zìjǐ de mó dòu jī mó, yòng zìjǐ de fǎ yā hú pào. Tā jīngcháng gēn wǒmen shuō:「Sùróng kāfēi bú shì zhēnzhèng de kāfēi. Nǐmen hē de nàxiē dōngxi, lián kāfēi dōu suàn bú shàng.」Yǒu yì tiān, tā gěi měi gè rén dào le yì xiǎo bēi tā zuò de kāfēi, ràng dàjiā pǐncháng. Tā shuō zhè shì lái zì Āisài'ébǐyà de tèjí dòuzi, yǒu huā guǒ de xiāngwèi. Dàjiā dōu shuō hǎo hē, suīrán dà bùfen rén juéde wèidào gēn gōngsī kāfēi jī chūlái de chàbuduō. Hòulái yǒu yí cì bùmén jùcān, tā chídào le bàn xiǎoshí. Dào de shíhou dàjiā yǐjīng zài hē yǐnliào le. Tā hěn kě, zuò xiàlái ná qǐ zhuō shàng wéiyī shèng xià de yì bēi kāfēi jiù hē le.「Zhège hái xíng,」tā shuō,「nǎ jiā de dòuzi?」Pángbiān de rén shuō:「Nà shì sùróng de.」Zhěng zhāng zhuōzi ānjìng le sān miǎozhōng, ránhòu suǒyǒu rén tóngshí xiào le chūlái. Tā yě xiào le, suīrán liǎn yǒudiǎn hóng.",
    "text_en": "A new colleague arrived who was very particular about coffee. He brought his own beans to the office, ground them with his own grinder, brewed them in his own French press. He'd often tell us: 'Instant coffee isn't real coffee. What you people drink doesn't even count as coffee.' One day he poured everyone a small cup of his brew to taste. He said it was premium Ethiopian beans with floral and fruity notes. Everyone said it was good, though most thought it tasted about the same as the office machine. Later, at a department dinner, he arrived half an hour late. Everyone was already drinking. He was thirsty, sat down, and grabbed the only cup of coffee left on the table. 'This is decent,' he said. 'Whose beans?' The person beside him said: 'That's instant.' The entire table went quiet for three seconds. Then everyone burst out laughing at once. He laughed too, though his face was a little red.",
    "questions": [
        {"type": "mc", "q_zh": "新同事用什么泡咖啡？", "q_en": "What does the new colleague use to brew coffee?",
         "options": [
             {"text": "咖啡机", "pinyin": "kāfēi jī", "text_en": "coffee machine", "correct": False},
             {"text": "法压壶", "pinyin": "fǎ yā hú", "text_en": "French press", "correct": True},
             {"text": "速溶咖啡", "pinyin": "sùróng kāfēi", "text_en": "instant coffee", "correct": False},
             {"text": "茶壶", "pinyin": "cháhú", "text_en": "teapot", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "他品尝的时候说什么？", "q_en": "What did he say when tasting it?",
         "options": [
             {"text": "不好喝", "pinyin": "bù hǎo hē", "text_en": "not good", "correct": False},
             {"text": "是速溶的", "pinyin": "shì sùróng de", "text_en": "it's instant", "correct": False},
             {"text": "这个还行，哪家的豆子", "pinyin": "zhège hái xíng, nǎ jiā de dòuzi", "text_en": "decent, whose beans", "correct": True},
             {"text": "跟他的一样好", "pinyin": "gēn tā de yíyàng hǎo", "text_en": "as good as his", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "大家为什么笑了？", "q_en": "Why did everyone laugh?",
         "options": [
             {"text": "因为咖啡很好喝", "pinyin": "yīnwèi kāfēi hěn hǎo hē", "text_en": "the coffee was good", "correct": False},
             {"text": "因为他说速溶不是咖啡，但是他自己喝了速溶还说不错", "pinyin": "yīnwèi tā shuō sùróng bú shì kāfēi, dànshì tā zìjǐ hē le sùróng hái shuō búcuò", "text_en": "he said instant isn't coffee but drank it and said it was decent", "correct": True},
             {"text": "因为他迟到了", "pinyin": "yīnwèi tā chídào le", "text_en": "he was late", "correct": False},
             {"text": "因为有人讲了笑话", "pinyin": "yīnwèi yǒu rén jiǎng le xiàohua", "text_en": "someone told a joke", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 8. j4_observe_031 - Was: paper airplane with 突然 realize
# NEW: ELAINE MAY MOVE - two people at cross purposes in a shop
replace_passage("j4_observe_031", {
    "title": "The Flower Shop Misunderstanding",
    "title_zh": "花店的误会",
    "text_zh": "一个男人走进花店，说：「我需要一束花，要表达歉意的。」老板娘问：「是什么事？」男人说：「忘了我们的纪念日。」老板娘点点头，开始帮他选花。她挑了一束百合和一些粉色的玫瑰，说：「这个组合很合适，百合代表纯洁，玫瑰代表爱。」男人看了看，说：「颜色能不能再深一点？事情比较严重。」老板娘换了深红的玫瑰。男人想了想，又说：「能不能再加一些？我忘了已经是第三年了。」老板娘停下来，认真地看着他说：「先生，花可以帮你表达歉意，但是花再多也代替不了一句真心的道歉。」男人愣了一下，然后说：「你说得对。那就这束吧。但是你能在卡片上帮我写几个字吗？我自己的字太丑了。」老板娘笑着摇摇头，还是帮他写了。",
    "text_pinyin": "Yí gè nánrén zǒu jìn huā diàn, shuō:「Wǒ xūyào yí shù huā, yào biǎodá qiànyì de.」Lǎobǎnniáng wèn:「Shì shénme shì?」Nánrén shuō:「Wàng le wǒmen de jìniànrì.」Lǎobǎnniáng diǎn diǎn tóu, kāishǐ bāng tā xuǎn huā. Tā tiāo le yí shù bǎihé hé yìxiē fěnsè de méiguī, shuō:「Zhège zǔhé hěn héshì, bǎihé dàibiǎo chúnjié, méiguī dàibiǎo ài.」Nánrén kàn le kàn, shuō:「Yánsè néng bu néng zài shēn yìdiǎn? Shìqíng bǐjiào yánzhòng.」Lǎobǎnniáng huàn le shēn hóng de méiguī. Nánrén xiǎng le xiǎng, yòu shuō:「Néng bu néng zài jiā yìxiē? Wǒ wàng le yǐjīng shì dì sān nián le.」Lǎobǎnniáng tíng xiàlái, rènzhēn de kànzhe tā shuō:「Xiānshēng, huā kěyǐ bāng nǐ biǎodá qiànyì, dànshì huā zài duō yě dàitì bù liǎo yí jù zhēnxīn de dàoqiàn.」Nánrén lèng le yíxià, ránhòu shuō:「Nǐ shuō de duì. Nà jiù zhè shù ba. Dànshì nǐ néng zài kǎpiàn shàng bāng wǒ xiě jǐ gè zì ma? Wǒ zìjǐ de zì tài chǒu le.」Lǎobǎnniáng xiàozhe yáo yao tóu, háishi bāng tā xiě le.",
    "text_en": "A man walked into a flower shop: 'I need a bouquet — to express an apology.' The owner asked: 'What happened?' The man: 'Forgot our anniversary.' She nodded and started selecting flowers. She chose lilies and some pink roses: 'This combination works well — lilies for purity, roses for love.' The man looked: 'Could the color be deeper? It's fairly serious.' She switched to deep red roses. He thought about it: 'Could you add more? I've forgotten three years in a row.' The owner paused and looked at him seriously: 'Sir, flowers can express an apology, but no amount of flowers can replace a sincere one in words.' He paused, then said: 'You're right. I'll take this bunch then. But could you write a few words on the card for me? My handwriting is too ugly.' The owner shook her head with a smile, but wrote it for him anyway.",
    "questions": [
        {"type": "mc", "q_zh": "男人为什么要买花？", "q_en": "Why did the man want to buy flowers?",
         "options": [
             {"text": "过生日", "pinyin": "guò shēngrì", "text_en": "for a birthday", "correct": False},
             {"text": "忘了纪念日", "pinyin": "wàng le jìniànrì", "text_en": "forgot their anniversary", "correct": True},
             {"text": "送朋友", "pinyin": "sòng péngyou", "text_en": "for a friend", "correct": False},
             {"text": "装饰房间", "pinyin": "zhuāngshì fángjiān", "text_en": "to decorate a room", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "他忘了几年了？", "q_en": "How many years has he forgotten?",
         "options": [
             {"text": "一年", "pinyin": "yì nián", "text_en": "one year", "correct": False},
             {"text": "两年", "pinyin": "liǎng nián", "text_en": "two years", "correct": False},
             {"text": "三年", "pinyin": "sān nián", "text_en": "three years", "correct": True},
             {"text": "五年", "pinyin": "wǔ nián", "text_en": "five years", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "老板娘说了什么重要的话？", "q_en": "What important thing did the shop owner say?",
         "options": [
             {"text": "花越多越好", "pinyin": "huā yuè duō yuè hǎo", "text_en": "the more flowers the better", "correct": False},
             {"text": "花代替不了真心的道歉", "pinyin": "huā dàitì bù liǎo zhēnxīn de dàoqiàn", "text_en": "flowers can't replace a sincere apology", "correct": True},
             {"text": "百合比玫瑰好", "pinyin": "bǎihé bǐ méiguī hǎo", "text_en": "lilies are better than roses", "correct": False},
             {"text": "他应该买巧克力", "pinyin": "tā yīnggāi mǎi qiǎokèlì", "text_en": "he should buy chocolate", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 9. j4_inst_008 - Was: night shift nurse with 突然 realize pattern
# NEW: INSTITUTIONAL COMPETENCE - the canteen auntie's system
replace_passage("j4_inst_008", {
    "title": "The Canteen Auntie's Memory",
    "title_zh": "食堂阿姨的记忆",
    "text_zh": "我们公司食堂有一个阿姨，在这里工作了二十年。她记得每个人吃什么。你刚走到窗口，她就说：「一荤两素，不要葱，多一点辣椒，对吧？」刚来的同事觉得很神奇，问她：「你怎么记得这么多人的口味？」她说：「打了二十年的饭，跟你们每个人见面次数比你们同事之间还多呢。」有一次，一个从来只吃素的同事突然点了一份红烧肉。阿姨看了他一眼，什么也没说，但是多给了他一个鸡腿。第二天那个同事来的时候，阿姨问：「昨天怎么了？」同事说：「分手了。」阿姨点点头，给他盛了一碗汤，说：「汤不要钱。慢慢来。」那碗汤确实是那天菜单上没有的。",
    "text_pinyin": "Wǒmen gōngsī shítáng yǒu yí gè āyí, zài zhèlǐ gōngzuò le èrshí nián. Tā jì de měi gè rén chī shénme. Nǐ gāng zǒu dào chuāngkǒu, tā jiù shuō:「Yì hūn liǎng sù, búyào cōng, duō yìdiǎn làjiāo, duì ba?」Gāng lái de tóngshì juéde hěn shénqí, wèn tā:「Nǐ zěnme jì de zhème duō rén de kǒuwèi?」Tā shuō:「Dǎ le èrshí nián de fàn, gēn nǐmen měi gè rén jiàn miàn cìshù bǐ nǐmen tóngshì zhījiān hái duō ne.」Yǒu yí cì, yí gè cónglái zhǐ chī sù de tóngshì tūrán diǎn le yí fèn hóngshāo ròu. Āyí kàn le tā yì yǎn, shénme yě méi shuō, dànshì duō gěi le tā yí gè jītuǐ. Dì èr tiān nàge tóngshì lái de shíhou, āyí wèn:「Zuótiān zěnme le?」Tóngshì shuō:「Fēnshǒu le.」Āyí diǎn diǎn tóu, gěi tā chéng le yì wǎn tāng, shuō:「Tāng búyào qián. Mànmàn lái.」Nà wǎn tāng quèshí shì nà tiān càidān shàng méiyǒu de.",
    "text_en": "Our company cafeteria has an auntie who's worked there for twenty years. She remembers what everyone eats. The moment you reach the window, she says: 'One meat two vegetables, no scallions, extra chili, right?' Newer colleagues find it amazing and ask: 'How do you remember so many people's preferences?' She says: 'Twenty years of serving food — I've seen each of you more times than you've seen your own coworkers.' Once, a colleague who only ever ordered vegetarian suddenly asked for braised pork. The auntie glanced at him, said nothing, but gave him an extra chicken leg. The next day when he came back, she asked: 'What happened yesterday?' He said: 'Broke up.' She nodded, ladled him a bowl of soup, and said: 'The soup is free. Take your time.' That soup was definitely not on the day's menu.",
    "questions": [
        {"type": "mc", "q_zh": "阿姨在食堂工作了多久？", "q_en": "How long has the auntie worked in the cafeteria?",
         "options": [
             {"text": "十年", "pinyin": "shí nián", "text_en": "ten years", "correct": False},
             {"text": "十五年", "pinyin": "shíwǔ nián", "text_en": "fifteen years", "correct": False},
             {"text": "二十年", "pinyin": "èrshí nián", "text_en": "twenty years", "correct": True},
             {"text": "三十年", "pinyin": "sānshí nián", "text_en": "thirty years", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "那个同事为什么突然点了红烧肉？", "q_en": "Why did the colleague suddenly order braised pork?",
         "options": [
             {"text": "他想试试新菜", "pinyin": "tā xiǎng shìshi xīn cài", "text_en": "wanted to try something new", "correct": False},
             {"text": "分手了", "pinyin": "fēnshǒu le", "text_en": "had a breakup", "correct": True},
             {"text": "素菜卖完了", "pinyin": "sù cài mài wán le", "text_en": "vegetables sold out", "correct": False},
             {"text": "阿姨推荐的", "pinyin": "āyí tuījiàn de", "text_en": "the auntie recommended it", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "那碗汤有什么特别的？", "q_en": "What was special about the soup?",
         "options": [
             {"text": "特别好喝", "pinyin": "tèbié hǎo hē", "text_en": "especially delicious", "correct": False},
             {"text": "不要钱，而且不在菜单上", "pinyin": "búyào qián, érqiě bú zài càidān shàng", "text_en": "free, and not on the menu", "correct": True},
             {"text": "是他最喜欢的", "pinyin": "shì tā zuì xǐhuan de", "text_en": "his favorite", "correct": False},
             {"text": "阿姨自己做的", "pinyin": "āyí zìjǐ zuò de", "text_en": "made by the auntie herself", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 10. j4_urban_092 - Was: elevator gets stuck with realize ending
# NEW: NORM VIOLATION comedy - reply-all disaster
replace_passage("j4_urban_092", {
    "title": "The Reply-All Disaster",
    "title_zh": "回复全部的灾难",
    "text_zh": "昨天下午，人事部的小赵给全公司发了一封邮件，通知大家下周三团建。两分钟以后，财务部的老陈回复了一句：「又团建，上次的钱还没报销呢。」问题是，他按了回复全部。一百五十个人都看到了。整个公司群安静了十秒钟，然后销售部的小李回复全部说：「对啊，而且上次的活动真的很无聊。」行政部的人马上回复全部说：「请大家注意，不要用回复全部。」但是这封提醒本身就是回复全部。接下来的二十分钟，至少有十个人回复全部说：「请不要回复全部。」每一封都是回复全部发的。最后老板发了一封邮件，只有四个字：「都别回了。」当然，他也用了回复全部。",
    "text_pinyin": "Zuótiān xiàwǔ, rénshìbù de Xiǎo Zhào gěi quán gōngsī fā le yì fēng yóujiàn, tōngzhī dàjiā xià zhōu sān tuánjiàn. Liǎng fēnzhōng yǐhòu, cáiwùbù de Lǎo Chén huífù le yí jù:「Yòu tuánjiàn, shàng cì de qián hái méi bàoxiāo ne.」Wèntí shì, tā àn le huífù quánbù. Yì bǎi wǔshí gè rén dōu kàn dào le. Zhěnggè gōngsī qún ānjìng le shí miǎozhōng, ránhòu xiāoshòubù de Xiǎo Lǐ huífù quánbù shuō:「Duì a, érqiě shàng cì de huódòng zhēnde hěn wúliáo.」Xíngzhèngbù de rén mǎshàng huífù quánbù shuō:「Qǐng dàjiā zhùyì, búyào yòng huífù quánbù.」Dànshì zhè fēng tíxǐng běnshēn jiù shì huífù quánbù. Jiēxiàlái de èrshí fēnzhōng, zhìshǎo yǒu shí gè rén huífù quánbù shuō:「Qǐng búyào huífù quánbù.」Měi yì fēng dōu shì huífù quánbù fā de. Zuìhòu lǎobǎn fā le yì fēng yóujiàn, zhǐ yǒu sì gè zì:「Dōu bié huí le.」Dāngrán, tā yě yòng le huífù quánbù.",
    "text_en": "Yesterday afternoon, Xiao Zhao from HR emailed the entire company about next Wednesday's team building event. Two minutes later, Lao Chen from finance replied: 'Team building again — last time's expenses still haven't been reimbursed.' The problem: he hit reply-all. All one hundred fifty people saw it. The company went silent for ten seconds. Then Xiao Li from sales replied-all: 'Yeah, and last time's activity was really boring.' Admin immediately replied-all: 'Please be careful not to use reply-all.' But that reminder itself was a reply-all. Over the next twenty minutes, at least ten people replied-all saying: 'Please don't reply-all.' Every single one was sent via reply-all. Finally the boss sent an email with just four characters: 'Stop replying.' Of course, he also used reply-all.",
    "questions": [
        {"type": "mc", "q_zh": "老陈说了什么？", "q_en": "What did Lao Chen say?",
         "options": [
             {"text": "团建很好", "pinyin": "tuánjiàn hěn hǎo", "text_en": "team building is great", "correct": False},
             {"text": "上次的钱还没报销", "pinyin": "shàng cì de qián hái méi bàoxiāo", "text_en": "last time's expenses haven't been reimbursed", "correct": True},
             {"text": "他不能参加", "pinyin": "tā bù néng cānjiā", "text_en": "he can't attend", "correct": False},
             {"text": "应该换个时间", "pinyin": "yīnggāi huàn gè shíjiān", "text_en": "should change the time", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "为什么这件事变得很搞笑？", "q_en": "Why did this become funny?",
         "options": [
             {"text": "邮件内容很好笑", "pinyin": "yóujiàn nèiróng hěn hǎoxiào", "text_en": "the email content was funny", "correct": False},
             {"text": "每个说别用回复全部的人都用了回复全部", "pinyin": "měi gè shuō bié yòng huífù quánbù de rén dōu yòng le huífù quánbù", "text_en": "everyone telling others not to reply-all used reply-all", "correct": True},
             {"text": "老板生气了", "pinyin": "lǎobǎn shēngqì le", "text_en": "the boss got angry", "correct": False},
             {"text": "团建取消了", "pinyin": "tuánjiàn qǔxiāo le", "text_en": "team building was cancelled", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "公司有多少人看到了邮件？", "q_en": "How many people saw the emails?",
         "options": [
             {"text": "五十人", "pinyin": "wǔshí rén", "text_en": "fifty", "correct": False},
             {"text": "一百人", "pinyin": "yì bǎi rén", "text_en": "one hundred", "correct": False},
             {"text": "一百五十人", "pinyin": "yì bǎi wǔshí rén", "text_en": "one hundred fifty", "correct": True},
             {"text": "两百人", "pinyin": "liǎng bǎi rén", "text_en": "two hundred", "correct": False}
         ], "difficulty": 0.2}
    ]
})

# 11. j4_urban_112 - Was: laundry room at midnight, generic restorative
# NEW: BOURDAIN food love - street food at 2am
replace_passage("j4_urban_112", {
    "title": "The 2 AM Barbecue Stand",
    "title_zh": "凌晨两点的烧烤摊",
    "text_zh": "加完班出来已经凌晨两点了。街上只有一家烧烤摊还开着，老板是一对夫妻。丈夫烤串，妻子收钱。你坐在塑料椅子上，桌子歪歪的，但是你不在乎。羊肉串上来了，外面焦的，里面嫩的，孜然和辣椒粉多得要掉下来。你咬第一口的时候，油顺着手指往下流，烫得你甩了一下手。旁边另一张桌子坐着三个穿西装的男人，领带松了，也在吃串。谁也不说话。大家都累了，但是吃烧烤的时候，累好像不算什么了。老板娘问：「要不要啤酒？冰的。」你本来不想喝，但是听到「冰的」两个字就改主意了。第一口啤酒配上最后一口羊肉串——凌晨两点的街上，没有比这更好的事情了。",
    "text_pinyin": "Jiā wán bān chūlái yǐjīng língchén liǎng diǎn le. Jiē shàng zhǐ yǒu yì jiā shāokǎo tān hái kāizhe, lǎobǎn shì yí duì fūqī. Zhàngfu kǎo chuàn, qīzi shōu qián. Nǐ zuò zài sùliào yǐzi shàng, zhuōzi wāi wāi de, dànshì nǐ bú zàihu. Yángròu chuàn shàng lái le, wàimiàn jiāo de, lǐmiàn nèn de, zīrán hé làjiāo fěn duō de yào diào xiàlái. Nǐ yǎo dì yī kǒu de shíhou, yóu shùnzhe shǒuzhǐ wǎng xià liú, tàng de nǐ shuǎi le yíxià shǒu. Pángbiān lìng yì zhāng zhuōzi zuòzhe sān gè chuān xīzhuāng de nánrén, lǐngdài sōng le, yě zài chī chuàn. Shéi yě bù shuō huà. Dàjiā dōu lèi le, dànshì chī shāokǎo de shíhou, lèi hǎoxiàng bú suàn shénme le. Lǎobǎnniáng wèn:「Yào búyào píjiǔ? Bīng de.」Nǐ běnlái bù xiǎng hē, dànshì tīng dào「bīng de」liǎng gè zì jiù gǎi zhǔyì le. Dì yī kǒu píjiǔ pèi shàng zuìhòu yì kǒu yángròu chuàn——língchén liǎng diǎn de jiē shàng, méiyǒu bǐ zhè gèng hǎo de shìqíng le.",
    "text_en": "You leave after overtime and it's already 2 AM. Only one barbecue stand is still open, run by a husband and wife. He grills the skewers, she collects the money. You sit on a plastic chair, the table wobbles, but you don't care. The lamb skewers arrive — charred outside, tender inside, cumin and chili powder piled so thick it's about to fall off. When you take the first bite, oil runs down your fingers, so hot you shake your hand. At the next table, three men in suits with loosened ties are eating skewers too. Nobody talks. Everyone's tired, but while eating barbecue, tired doesn't seem to count for much. The wife asks: 'Beer? Ice cold.' You weren't planning to drink, but the words 'ice cold' change your mind. That first sip of beer with the last bite of lamb skewer — at 2 AM on an empty street, there's nothing better than this.",
    "questions": [
        {"type": "mc", "q_zh": "烧烤摊的老板是什么人？", "q_en": "Who runs the barbecue stand?",
         "options": [
             {"text": "一个老人", "pinyin": "yí gè lǎo rén", "text_en": "an old man", "correct": False},
             {"text": "一对夫妻", "pinyin": "yí duì fūqī", "text_en": "a husband and wife", "correct": True},
             {"text": "两个年轻人", "pinyin": "liǎng gè niánqīng rén", "text_en": "two young people", "correct": False},
             {"text": "一个女人", "pinyin": "yí gè nǚrén", "text_en": "a woman", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "旁边桌子的人穿什么？", "q_en": "What are the people at the next table wearing?",
         "options": [
             {"text": "T恤", "pinyin": "T xù", "text_en": "T-shirts", "correct": False},
             {"text": "西装", "pinyin": "xīzhuāng", "text_en": "suits", "correct": True},
             {"text": "工作服", "pinyin": "gōngzuò fú", "text_en": "work uniforms", "correct": False},
             {"text": "运动服", "pinyin": "yùndòng fú", "text_en": "sportswear", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "「你」为什么改主意要啤酒了？", "q_en": "Why did 'you' change your mind about the beer?",
         "options": [
             {"text": "啤酒很便宜", "pinyin": "píjiǔ hěn piányi", "text_en": "beer was cheap", "correct": False},
             {"text": "朋友让他喝的", "pinyin": "péngyou ràng tā hē de", "text_en": "friend told him to drink", "correct": False},
             {"text": "听到「冰的」就改主意了", "pinyin": "tīng dào 'bīng de' jiù gǎi zhǔyì le", "text_en": "hearing 'ice cold' changed his mind", "correct": True},
             {"text": "太渴了", "pinyin": "tài kě le", "text_en": "too thirsty", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 12. j4_urban_115 - Was: bicycle doctor with 突然 realize
# NEW: NORM VIOLATION - the person who microwaves fish
replace_passage("j4_urban_115", {
    "title": "The Office Microwave Incident",
    "title_zh": "办公室微波炉事件",
    "text_zh": "办公室有一条不成文的规矩：不要用微波炉热鱼。所有人都知道，除了新来的实习生小刘。星期一中午，小刘打开微波炉，放进了一盒带鱼。三分钟以后，整个楼层都是鱼的味道。坐在最近的小王首先闻到了，他皱了一下眉毛但是没说话。然后气味传到了第二排，第三排，最后传到了角落里经理的办公室。经理开门出来的时候，表情很复杂。他看了看微波炉旁边的小刘，小刘正开开心心地在吃带鱼。经理看了看其他人的脸色，决定发一封全员邮件。邮件标题是：「关于公共区域使用微波炉的温馨提示。」内容很客气，但是大家都知道是为什么。第二天微波炉旁边多了一张手写的清单，列出了「不推荐加热的食品」。排在第一位的，用红笔写着：鱼。",
    "text_pinyin": "Bàngōngshì yǒu yì tiáo bù chéng wén de guījǔ: búyào yòng wēibōlú rè yú. Suǒyǒu rén dōu zhīdào, chúle xīn lái de shíxí shēng Xiǎo Liú. Xīngqī yī zhōngwǔ, Xiǎo Liú dǎkāi wēibōlú, fàng jìn le yì hé dàiyú. Sān fēnzhōng yǐhòu, zhěnggè lóucéng dōu shì yú de wèidào. Zuò zài zuì jìn de Xiǎo Wáng shǒuxiān wén dào le, tā zhòu le yíxià méimao dànshì méi shuō huà. Ránhòu qìwèi chuán dào le dì èr pái, dì sān pái, zuìhòu chuán dào le jiǎoluò lǐ jīnglǐ de bàngōngshì. Jīnglǐ kāi mén chūlái de shíhou, biǎoqíng hěn fùzá. Tā kàn le kàn wēibōlú pángbiān de Xiǎo Liú, Xiǎo Liú zhèng kāi kāi xīn xīn de zài chī dàiyú. Jīnglǐ kàn le kàn qítā rén de liǎnsè, juédìng fā yì fēng quányuán yóujiàn. Yóujiàn biāotí shì:「Guānyú gōnggòng qūyù shǐyòng wēibōlú de wēnxīn tíshì.」Nèiróng hěn kèqi, dànshì dàjiā dōu zhīdào shì wèi shénme. Dì èr tiān wēibōlú pángbiān duō le yì zhāng shǒuxiě de qīngdān, liè chū le「bù tuījiàn jiārè de shípǐn」. Pái zài dì yī wèi de, yòng hóng bǐ xiězhe: yú.",
    "text_en": "The office has an unwritten rule: don't microwave fish. Everyone knows this, except the new intern Xiao Liu. Monday at noon, Xiao Liu opened the microwave and put in a box of hairtail fish. Three minutes later, the entire floor smelled like fish. Xiao Wang, sitting closest, smelled it first — he frowned but said nothing. Then the smell reached the second row, the third row, and finally the manager's office in the corner. When the manager opened his door, his expression was complicated. He looked at Xiao Liu by the microwave, happily eating hairtail. He looked at everyone else's faces. He decided to send a company-wide email. Subject line: 'A Friendly Reminder About Microwave Use in Common Areas.' Very polite, but everyone knew why. The next day a handwritten list appeared next to the microwave: 'Foods Not Recommended for Heating.' First on the list, written in red pen: fish.",
    "questions": [
        {"type": "mc", "q_zh": "小刘为什么不知道这个规矩？", "q_en": "Why didn't Xiao Liu know the rule?",
         "options": [
             {"text": "他是新来的实习生", "pinyin": "tā shì xīn lái de shíxí shēng", "text_en": "he was a new intern", "correct": True},
             {"text": "他不在乎", "pinyin": "tā bú zàihu", "text_en": "he didn't care", "correct": False},
             {"text": "没有人告诉他", "pinyin": "méiyǒu rén gàosu tā", "text_en": "nobody told him", "correct": False},
             {"text": "规矩是新定的", "pinyin": "guījǔ shì xīn dìng de", "text_en": "the rule was new", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "经理怎么处理这件事？", "q_en": "How did the manager handle it?",
         "options": [
             {"text": "直接跟小刘说了", "pinyin": "zhíjiē gēn Xiǎo Liú shuō le", "text_en": "told Xiao Liu directly", "correct": False},
             {"text": "发了一封全员邮件", "pinyin": "fā le yì fēng quányuán yóujiàn", "text_en": "sent a company-wide email", "correct": True},
             {"text": "把微波炉搬走了", "pinyin": "bǎ wēibōlú bān zǒu le", "text_en": "moved the microwave", "correct": False},
             {"text": "没有做任何事", "pinyin": "méiyǒu zuò rènhé shì", "text_en": "did nothing", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "清单上排在第一位的是什么？", "q_en": "What was first on the list?",
         "options": [
             {"text": "咖喱", "pinyin": "gālí", "text_en": "curry", "correct": False},
             {"text": "鱼", "pinyin": "yú", "text_en": "fish", "correct": True},
             {"text": "大蒜", "pinyin": "dàsuàn", "text_en": "garlic", "correct": False},
             {"text": "鸡蛋", "pinyin": "jīdàn", "text_en": "eggs", "correct": False}
         ], "difficulty": 0.2}
    ]
})

# 13. j4_inst_009 - Was: library quiet rule with realize ending
# NEW: MIYAZAKI GROWING-UP ACHE - old neighborhood changing
replace_passage("j4_inst_009", {
    "title": "The Noodle Shop That Closed",
    "title_zh": "关了的面馆",
    "text_zh": "我上大学的时候，学校门口有一家面馆，老板姓黄。黄叔的牛肉面是方圆三公里最好吃的。面条有嚼劲，汤头浓但是不咸，牛肉切得厚厚的。大碗十二块，小碗八块，学生再便宜两块。我在那里吃了四年的面，吃到最后黄叔看到我进门就开始下面了，不用点菜。毕业以后我搬到了另一个城市，过了六年才回去。走到学校门口的时候，面馆的位置变成了一家奶茶店。我站在门口看了一会儿。里面装修得很新，墙上有霓虹灯，菜单是电子屏幕。几个大学生坐在里面看手机。我走进去买了一杯奶茶，坐在角落里。奶茶很甜。窗户的位置没有变，还是对着那条种着梧桐树的路。树比以前高了很多。",
    "text_pinyin": "Wǒ shàng dàxué de shíhou, xuéxiào ménkǒu yǒu yì jiā miànguǎn, lǎobǎn xìng Huáng. Huáng shū de niúròu miàn shì fāngyuán sān gōnglǐ zuì hǎochī de. Miàntiáo yǒu jiáojìn, tāngtóu nóng dànshì bú xián, niúròu qiē de hòu hòu de. Dà wǎn shí'èr kuài, xiǎo wǎn bā kuài, xuéshēng zài piányi liǎng kuài. Wǒ zài nàlǐ chī le sì nián de miàn, chī dào zuìhòu Huáng shū kàn dào wǒ jìn mén jiù kāishǐ xià miàn le, búyòng diǎn cài. Bìyè yǐhòu wǒ bān dào le lìng yí gè chéngshì, guò le liù nián cái huíqù. Zǒu dào xuéxiào ménkǒu de shíhou, miànguǎn de wèizhi biàn chéng le yì jiā nǎichá diàn. Wǒ zhàn zài ménkǒu kàn le yíhuìr. Lǐmiàn zhuāngxiū de hěn xīn, qiáng shàng yǒu ní hóng dēng, càidān shì diànzǐ píngmù. Jǐ gè dàxuéshēng zuò zài lǐmiàn kàn shǒujī. Wǒ zǒu jìnqù mǎi le yì bēi nǎichá, zuò zài jiǎoluò lǐ. Nǎichá hěn tián. Chuānghù de wèizhi méiyǒu biàn, háishi duìzhe nà tiáo zhòngzhe wútóng shù de lù. Shù bǐ yǐqián gāo le hěn duō.",
    "text_en": "When I was in college, there was a noodle shop at the school gate, run by Uncle Huang. His beef noodles were the best within three kilometers. The noodles were chewy, the broth rich but not salty, the beef cut thick. Large bowl twelve yuan, small bowl eight, two yuan off for students. I ate there for four years — by the end, Uncle Huang would start cooking my noodles the moment he saw me walk in, no need to order. After graduation I moved to another city and didn't go back for six years. Walking up to the school gate, I found the noodle shop had become a milk tea store. I stood outside for a while. Inside was all new renovation — neon lights on the walls, electronic menu screens. A few college students sat inside looking at their phones. I went in and bought a milk tea, sat in the corner. The tea was sweet. The window was in the same spot, still facing the road lined with sycamore trees. The trees were much taller now.",
    "questions": [
        {"type": "mc", "q_zh": "大碗牛肉面多少钱？", "q_en": "How much was a large bowl of beef noodles?",
         "options": [
             {"text": "八块", "pinyin": "bā kuài", "text_en": "eight yuan", "correct": False},
             {"text": "十块", "pinyin": "shí kuài", "text_en": "ten yuan", "correct": False},
             {"text": "十二块", "pinyin": "shí'èr kuài", "text_en": "twelve yuan", "correct": True},
             {"text": "十五块", "pinyin": "shíwǔ kuài", "text_en": "fifteen yuan", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "面馆变成了什么？", "q_en": "What did the noodle shop become?",
         "options": [
             {"text": "另一家面馆", "pinyin": "lìng yì jiā miànguǎn", "text_en": "another noodle shop", "correct": False},
             {"text": "奶茶店", "pinyin": "nǎichá diàn", "text_en": "a milk tea store", "correct": True},
             {"text": "咖啡店", "pinyin": "kāfēi diàn", "text_en": "a coffee shop", "correct": False},
             {"text": "书店", "pinyin": "shūdiàn", "text_en": "a bookstore", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "什么东西没有变？", "q_en": "What hadn't changed?",
         "options": [
             {"text": "老板", "pinyin": "lǎobǎn", "text_en": "the owner", "correct": False},
             {"text": "菜单", "pinyin": "càidān", "text_en": "the menu", "correct": False},
             {"text": "窗户的位置和对面的路", "pinyin": "chuānghù de wèizhi hé duìmiàn de lù", "text_en": "the window position and the road across", "correct": True},
             {"text": "桌子和椅子", "pinyin": "zhuōzi hé yǐzi", "text_en": "tables and chairs", "correct": False}
         ], "difficulty": 0.3}
    ]
})

with open("data/reading_passages.json", "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("HSK 4 batch done: 13 passages rewritten")
