#!/usr/bin/env python3
"""Rewrite weak passages to fill tonal gaps in the reading corpus."""
import json
import copy

with open("data/reading_passages.json") as f:
    data = json.load(f)

# Build index
idx = {p["id"]: i for i, p in enumerate(data["passages"])}

def replace_passage(pid, new_data):
    """Replace a passage's text fields and questions, keeping id and hsk_level."""
    i = idx[pid]
    old = data["passages"][i]
    old["title"] = new_data["title"]
    old["title_zh"] = new_data["title_zh"]
    old["text_zh"] = new_data["text_zh"]
    old["text_pinyin"] = new_data["text_pinyin"]
    old["text_en"] = new_data["text_en"]
    old["questions"] = new_data["questions"]

# ============================================================
# HSK 3 REWRITES (12 passages)
# ============================================================

# 1. j3_comedy_011 - Was: generic "wrong floor" slapstick with realize ending
# NEW: SEINFELD MOVE - the last snack in the office fridge
replace_passage("j3_comedy_011", {
    "title": "The Last Yogurt",
    "title_zh": "最后一杯酸奶",
    "text_zh": "办公室的冰箱里有一杯酸奶，是公司买的。大家都看到了，但是没有人拿。因为只有一杯，谁拿了谁就不好意思。我也想喝，但是我不想做那个人。下午三点，小王走过去打开冰箱，拿了那杯酸奶。整个办公室安静了两秒钟。没有人说话，但是每个人都看了他一眼。小王喝完以后，把空杯子放在桌上。李姐走过来说：「小王，你喝了最后一杯？」小王说：「对啊，没有人要嘛。」李姐笑了笑，没有再说什么。但是从那天起，大家再也没有买过酸奶。",
    "text_pinyin": "Bàngōngshì de bīngxiāng lǐ yǒu yì bēi suānnǎi, shì gōngsī mǎi de. Dàjiā dōu kàn dào le, dànshì méiyǒu rén ná. Yīnwèi zhǐ yǒu yì bēi, shéi ná le shéi jiù bù hǎoyìsi. Wǒ yě xiǎng hē, dànshì wǒ bù xiǎng zuò nàge rén. Xiàwǔ sān diǎn, Xiǎo Wáng zǒu guòqù dǎkāi bīngxiāng, ná le nà bēi suānnǎi. Zhěnggè bàngōngshì ānjìng le liǎng miǎozhōng. Méiyǒu rén shuō huà, dànshì měi gè rén dōu kàn le tā yì yǎn. Xiǎo Wáng hē wán yǐhòu, bǎ kōng bēizi fàng zài zhuō shàng. Lǐ jiě zǒu guòlái shuō:「Xiǎo Wáng, nǐ hē le zuìhòu yì bēi?」Xiǎo Wáng shuō:「Duì a, méiyǒu rén yào ma.」Lǐ jiě xiào le xiào, méiyǒu zài shuō shénme. Dànshì cóng nà tiān qǐ, dàjiā zài yě méiyǒu mǎi guò suānnǎi.",
    "text_en": "There was one yogurt in the office fridge, bought by the company. Everyone saw it, but nobody took it. There was only one, and whoever took it would look bad. I wanted it too, but I didn't want to be that person. At three in the afternoon, Xiao Wang walked over, opened the fridge, and took the yogurt. The entire office went quiet for two seconds. Nobody said anything, but everyone glanced at him. After Xiao Wang finished, he left the empty cup on his desk. Sister Li came over: 'Xiao Wang, you drank the last one?' Xiao Wang said: 'Yeah, nobody wanted it.' Sister Li smiled and said nothing more. But from that day on, nobody ever bought yogurt again.",
    "questions": [
        {"type": "mc", "q_zh": "为什么没有人拿酸奶？", "q_en": "Why didn't anyone take the yogurt?",
         "options": [
             {"text": "因为只有一杯，拿了不好意思", "pinyin": "yīnwèi zhǐ yǒu yì bēi, ná le bù hǎoyìsi", "text_en": "only one, taking it would be embarrassing", "correct": True},
             {"text": "因为酸奶过期了", "pinyin": "yīnwèi suānnǎi guòqī le", "text_en": "the yogurt expired", "correct": False},
             {"text": "因为大家不喜欢酸奶", "pinyin": "yīnwèi dàjiā bù xǐhuan suānnǎi", "text_en": "nobody likes yogurt", "correct": False},
             {"text": "因为是别人的", "pinyin": "yīnwèi shì biéren de", "text_en": "it belonged to someone", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "小王拿酸奶以后，大家怎么反应？", "q_en": "How did everyone react when Xiao Wang took the yogurt?",
         "options": [
             {"text": "大家鼓掌了", "pinyin": "dàjiā gǔzhǎng le", "text_en": "everyone applauded", "correct": False},
             {"text": "安静了两秒钟，每个人都看了他一眼", "pinyin": "ānjìng le liǎng miǎozhōng, měi gè rén dōu kàn le tā yì yǎn", "text_en": "silence for two seconds, everyone glanced at him", "correct": True},
             {"text": "有人生气了", "pinyin": "yǒu rén shēngqì le", "text_en": "someone got angry", "correct": False},
             {"text": "没有人注意到", "pinyin": "méiyǒu rén zhùyì dào", "text_en": "nobody noticed", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "最后的结果是什么？", "q_en": "What was the final result?",
         "options": [
             {"text": "公司买了更多酸奶", "pinyin": "gōngsī mǎi le gèng duō suānnǎi", "text_en": "company bought more yogurt", "correct": False},
             {"text": "小王道歉了", "pinyin": "Xiǎo Wáng dàoqiàn le", "text_en": "Xiao Wang apologized", "correct": False},
             {"text": "大家再也没有买过酸奶", "pinyin": "dàjiā zài yě méiyǒu mǎi guò suānnǎi", "text_en": "nobody ever bought yogurt again", "correct": True},
             {"text": "他们定了新的规则", "pinyin": "tāmen dìng le xīn de guīzé", "text_en": "they made a new rule", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 2. j3_identity_009 - Was: generic name reflection with 突然觉得 ending
# NEW: ELAINE MAY MOVE - two people having different conversations
replace_passage("j3_identity_009", {
    "title": "Two Different Conversations",
    "title_zh": "两个不同的话题",
    "text_zh": "我和小李在咖啡店聊天。我说：「最近工作太忙了，每天都加班。」小李点点头说：「对，我也觉得要换一个。」我以为她在说换工作，就说：「是啊，你找到新的了吗？」小李说：「还没有，但是我想要一个大一点的。」我很惊讶：「大一点的公司？」小李说：「不是公司，是房子。我在找新房子。」我们看着对方，都笑了。小李说：「你刚才一直在说工作？」我说：「你一直在说房子？」我们喝了一口咖啡，决定从头开始聊。",
    "text_pinyin": "Wǒ hé Xiǎo Lǐ zài kāfēi diàn liáo tiān. Wǒ shuō:「Zuìjìn gōngzuò tài máng le, měi tiān dōu jiābān.」Xiǎo Lǐ diǎn diǎn tóu shuō:「Duì, wǒ yě juéde yào huàn yí gè.」Wǒ yǐwéi tā zài shuō huàn gōngzuò, jiù shuō:「Shì a, nǐ zhǎo dào xīn de le ma?」Xiǎo Lǐ shuō:「Hái méiyǒu, dànshì wǒ xiǎng yào yí gè dà yìdiǎn de.」Wǒ hěn jīngyà:「Dà yìdiǎn de gōngsī?」Xiǎo Lǐ shuō:「Bú shì gōngsī, shì fángzi. Wǒ zài zhǎo xīn fángzi.」Wǒmen kànzhe duìfāng, dōu xiào le. Xiǎo Lǐ shuō:「Nǐ gāngcái yìzhí zài shuō gōngzuò?」Wǒ shuō:「Nǐ yìzhí zài shuō fángzi?」Wǒmen hē le yì kǒu kāfēi, juédìng cóng tóu kāishǐ liáo.",
    "text_en": "Xiao Li and I were chatting at a coffee shop. I said: 'Work has been so busy lately, overtime every day.' Xiao Li nodded: 'Yeah, I think I need to switch too.' I thought she meant switching jobs: 'Right, have you found a new one?' Xiao Li said: 'Not yet, but I want a bigger one.' I was surprised: 'A bigger company?' Xiao Li said: 'Not a company — an apartment. I'm looking for a new place.' We looked at each other and laughed. Xiao Li said: 'You were talking about work the whole time?' I said: 'You were talking about apartments?' We took a sip of coffee and decided to start the conversation over.",
    "questions": [
        {"type": "mc", "q_zh": "「我」以为小李在说什么？", "q_en": "What did 'I' think Xiao Li was talking about?",
         "options": [
             {"text": "换工作", "pinyin": "huàn gōngzuò", "text_en": "switching jobs", "correct": True},
             {"text": "换手机", "pinyin": "huàn shǒujī", "text_en": "switching phones", "correct": False},
             {"text": "换房子", "pinyin": "huàn fángzi", "text_en": "switching apartments", "correct": False},
             {"text": "换咖啡店", "pinyin": "huàn kāfēi diàn", "text_en": "switching coffee shops", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "小李其实在说什么？", "q_en": "What was Xiao Li actually talking about?",
         "options": [
             {"text": "找新工作", "pinyin": "zhǎo xīn gōngzuò", "text_en": "finding a new job", "correct": False},
             {"text": "找新房子", "pinyin": "zhǎo xīn fángzi", "text_en": "finding a new apartment", "correct": True},
             {"text": "找新朋友", "pinyin": "zhǎo xīn péngyou", "text_en": "finding new friends", "correct": False},
             {"text": "找新咖啡店", "pinyin": "zhǎo xīn kāfēi diàn", "text_en": "finding a new coffee shop", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "最后他们怎么做了？", "q_en": "What did they do in the end?",
         "options": [
             {"text": "生气走了", "pinyin": "shēngqì zǒu le", "text_en": "left angrily", "correct": False},
             {"text": "决定从头开始聊", "pinyin": "juédìng cóng tóu kāishǐ liáo", "text_en": "decided to start the conversation over", "correct": True},
             {"text": "不说话了", "pinyin": "bù shuō huà le", "text_en": "stopped talking", "correct": False},
             {"text": "换了一家咖啡店", "pinyin": "huàn le yì jiā kāfēi diàn", "text_en": "switched coffee shops", "correct": False}
         ], "difficulty": 0.2}
    ]
})

# 3. j3_travel_001 - Was: restorative guesthouse guestbook
# NEW: GOLDEN GIRLS MOVE - fast banter between friends who know each other
replace_passage("j3_travel_001", {
    "title": "Packing for the Trip",
    "title_zh": "出发前的行李",
    "text_zh": "我和老朋友小美一起去旅行。出发前一天，小美发了一张照片给我——她的行李箱已经满了。我说：「我们只去三天。」小美说：「对啊，所以我只带了三双鞋。」我说：「三双鞋？」小美说：「一双走路的，一双好看的，一双万一下雨的。」我说：「我只带了一双。」小美说：「你每次旅行都只带一双鞋，然后每次都跟我借。」我想了想，她说得对。我又说：「你带了几件外套？」小美说：「四件。你呢？」我说：「一件。」小美叹了一口气说：「你把箱子带大一点吧，我的东西也放不下了。」",
    "text_pinyin": "Wǒ hé lǎo péngyou Xiǎo Měi yìqǐ qù lǚxíng. Chūfā qián yì tiān, Xiǎo Měi fā le yì zhāng zhàopiàn gěi wǒ——tā de xíngli xiāng yǐjīng mǎn le. Wǒ shuō:「Wǒmen zhǐ qù sān tiān.」Xiǎo Měi shuō:「Duì a, suǒyǐ wǒ zhǐ dài le sān shuāng xié.」Wǒ shuō:「Sān shuāng xié?」Xiǎo Měi shuō:「Yì shuāng zǒu lù de, yì shuāng hǎokàn de, yì shuāng wànyī xià yǔ de.」Wǒ shuō:「Wǒ zhǐ dài le yì shuāng.」Xiǎo Měi shuō:「Nǐ měi cì lǚxíng dōu zhǐ dài yì shuāng xié, ránhòu měi cì dōu gēn wǒ jiè.」Wǒ xiǎng le xiǎng, tā shuō de duì. Wǒ yòu shuō:「Nǐ dài le jǐ jiàn wàitào?」Xiǎo Měi shuō:「Sì jiàn. Nǐ ne?」Wǒ shuō:「Yí jiàn.」Xiǎo Měi tàn le yì kǒu qì shuō:「Nǐ bǎ xiāngzi dài dà yìdiǎn ba, wǒ de dōngxi yě fàng bú xià le.」",
    "text_en": "My old friend Xiao Mei and I were going on a trip together. The day before departure, Xiao Mei sent me a photo — her suitcase was already full. I said: 'We're only going for three days.' Xiao Mei said: 'Right, that's why I only packed three pairs of shoes.' I said: 'Three pairs of shoes?' Xiao Mei: 'One for walking, one for looking nice, one in case it rains.' I said: 'I only packed one pair.' Xiao Mei: 'You always bring one pair on trips, and then you always borrow mine.' I thought about it — she was right. I asked: 'How many jackets did you bring?' Xiao Mei: 'Four. You?' I said: 'One.' Xiao Mei sighed: 'Bring a bigger suitcase — my stuff won't fit either.'",
    "questions": [
        {"type": "mc", "q_zh": "他们的旅行是几天？", "q_en": "How many days is their trip?",
         "options": [
             {"text": "两天", "pinyin": "liǎng tiān", "text_en": "two days", "correct": False},
             {"text": "三天", "pinyin": "sān tiān", "text_en": "three days", "correct": True},
             {"text": "五天", "pinyin": "wǔ tiān", "text_en": "five days", "correct": False},
             {"text": "一个星期", "pinyin": "yí gè xīngqī", "text_en": "one week", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "小美为什么带三双鞋？", "q_en": "Why did Xiao Mei bring three pairs of shoes?",
         "options": [
             {"text": "走路的、好看的、下雨的", "pinyin": "zǒu lù de, hǎokàn de, xià yǔ de", "text_en": "walking, looking nice, rain", "correct": True},
             {"text": "因为她喜欢买鞋", "pinyin": "yīnwèi tā xǐhuan mǎi xié", "text_en": "she likes buying shoes", "correct": False},
             {"text": "因为每双穿一天", "pinyin": "yīnwèi měi shuāng chuān yì tiān", "text_en": "one pair per day", "correct": False},
             {"text": "因为朋友让她带的", "pinyin": "yīnwèi péngyou ràng tā dài de", "text_en": "her friend told her to", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "小美最后让「我」怎么做？", "q_en": "What did Xiao Mei ask 'me' to do?",
         "options": [
             {"text": "少带一点东西", "pinyin": "shǎo dài yìdiǎn dōngxi", "text_en": "bring less stuff", "correct": False},
             {"text": "带大一点的箱子", "pinyin": "dài dà yìdiǎn de xiāngzi", "text_en": "bring a bigger suitcase", "correct": True},
             {"text": "自己买鞋", "pinyin": "zìjǐ mǎi xié", "text_en": "buy own shoes", "correct": False},
             {"text": "不要去旅行了", "pinyin": "búyào qù lǚxíng le", "text_en": "cancel the trip", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 4. j3_travel_002 - Was: train station piano with 突然 ending
# NEW: SONDHEIM MOVE - emotional contradiction, saying one thing feeling another
replace_passage("j3_travel_002", {
    "title": "The New Apartment",
    "title_zh": "新公寓",
    "text_zh": "搬家那天，妈妈帮我整理东西。新公寓离公司很近，走路只要十分钟。妈妈说：「这个地方真不错，比旧的好多了。」她打开窗户看了看，说：「光线也好，你不用开灯也很亮。」我说：「是啊。」妈妈又说：「厨房也够大，你可以做饭了。」我说：「嗯。」东西都整理好以后，妈妈说要走了。她说：「新地方方便多了，我放心了。」然后她站在窗户旁边，看着外面的街，看了很久，什么也没说。最后她拿起包，在门口回头看了一眼这个房间，轻轻关上了门。",
    "text_pinyin": "Bān jiā nà tiān, māma bāng wǒ zhěnglǐ dōngxi. Xīn gōngyù lí gōngsī hěn jìn, zǒu lù zhǐ yào shí fēnzhōng. Māma shuō:「Zhège dìfāng zhēn búcuò, bǐ jiù de hǎo duō le.」Tā dǎkāi chuānghù kàn le kàn, shuō:「Guāngxiàn yě hǎo, nǐ bú yòng kāi dēng yě hěn liàng.」Wǒ shuō:「Shì a.」Māma yòu shuō:「Chúfáng yě gòu dà, nǐ kěyǐ zuò fàn le.」Wǒ shuō:「Ǹg.」Dōngxi dōu zhěnglǐ hǎo yǐhòu, māma shuō yào zǒu le. Tā shuō:「Xīn dìfāng fāngbiàn duō le, wǒ fàngxīn le.」Ránhòu tā zhàn zài chuānghù pángbiān, kànzhe wàimiàn de jiē, kàn le hěn jiǔ, shénme yě méi shuō. Zuìhòu tā ná qǐ bāo, zài ménkǒu huí tóu kàn le yì yǎn zhège fángjiān, qīngqīng guān shàng le mén.",
    "text_en": "On moving day, Mom helped me organize things. The new apartment was close to work, only a ten-minute walk. Mom said: 'This place is really nice, much better than the old one.' She opened the window and looked out: 'Good light too, you won't even need to turn on the lamp.' I said: 'Yeah.' Mom said: 'The kitchen is big enough, you can cook now.' I said: 'Mm.' After everything was in place, Mom said she should go. She said: 'The new place is much more convenient. I feel better now.' Then she stood by the window, looking at the street below for a long time, saying nothing. Finally she picked up her bag, glanced back at the room from the doorway, and closed the door softly.",
    "questions": [
        {"type": "mc", "q_zh": "新公寓离公司多远？", "q_en": "How far is the new apartment from work?",
         "options": [
             {"text": "走路十分钟", "pinyin": "zǒu lù shí fēnzhōng", "text_en": "ten-minute walk", "correct": True},
             {"text": "坐车半小时", "pinyin": "zuò chē bàn xiǎoshí", "text_en": "half-hour drive", "correct": False},
             {"text": "走路五分钟", "pinyin": "zǒu lù wǔ fēnzhōng", "text_en": "five-minute walk", "correct": False},
             {"text": "坐地铁二十分钟", "pinyin": "zuò dìtiě èrshí fēnzhōng", "text_en": "twenty-minute subway ride", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "妈妈嘴上说什么？", "q_en": "What did Mom say out loud?",
         "options": [
             {"text": "她很担心", "pinyin": "tā hěn dānxīn", "text_en": "she was worried", "correct": False},
             {"text": "她不想走", "pinyin": "tā bù xiǎng zǒu", "text_en": "she didn't want to leave", "correct": False},
             {"text": "新地方方便多了，她放心了", "pinyin": "xīn dìfāng fāngbiàn duō le, tā fàngxīn le", "text_en": "the new place is convenient, she's relieved", "correct": True},
             {"text": "她会常来看你", "pinyin": "tā huì cháng lái kàn nǐ", "text_en": "she'll visit often", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "妈妈走之前做了什么？", "q_en": "What did Mom do before leaving?",
         "options": [
             {"text": "做了一顿饭", "pinyin": "zuò le yí dùn fàn", "text_en": "cooked a meal", "correct": False},
             {"text": "站在窗户旁边看了很久", "pinyin": "zhàn zài chuānghù pángbiān kàn le hěn jiǔ", "text_en": "stood by the window looking out for a long time", "correct": True},
             {"text": "哭了", "pinyin": "kū le", "text_en": "cried", "correct": False},
             {"text": "打了一个电话", "pinyin": "dǎ le yí gè diànhuà", "text_en": "made a phone call", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 5. j3_food_006 - Was: soup grandmother taught me, "realize" ending about missing grandma
# NEW: BOURDAIN RAW FOOD LOVE - messy pleasure, not reverent
replace_passage("j3_food_006", {
    "title": "The Soup That Burns Your Tongue",
    "title_zh": "烫嘴的汤",
    "text_zh": "冬天最冷的那几天，我最喜欢去楼下的小店喝汤。那家店的汤特别烫。老板每次都说：「小心，很烫！」但是我每次都等不了。第一口一定会烫到嘴，舌头疼一下，但是热的汤从嘴到肚子，整个身体都暖了。我朋友觉得我很奇怪：「你为什么不等一等再喝？」我说不出来为什么。也许是因为冬天太冷了，也许是因为我喜欢那种又疼又舒服的感觉。老板的汤没有什么特别的——白菜、豆腐、一点肉。但是冬天的晚上，冷风吹着你的脸，你走进那家热热的小店，端起一碗太烫的汤——这个比什么都好。",
    "text_pinyin": "Dōngtiān zuì lěng de nà jǐ tiān, wǒ zuì xǐhuan qù lóu xià de xiǎo diàn hē tāng. Nà jiā diàn de tāng tèbié tàng. Lǎobǎn měi cì dōu shuō:「Xiǎoxīn, hěn tàng!」Dànshì wǒ měi cì dōu děng bù liǎo. Dì yī kǒu yídìng huì tàng dào zuǐ, shétou téng yíxià, dànshì rè de tāng cóng zuǐ dào dùzi, zhěnggè shēntǐ dōu nuǎn le. Wǒ péngyou juéde wǒ hěn qíguài:「Nǐ wèi shénme bù děng yì děng zài hē?」Wǒ shuō bù chūlái wèi shénme. Yěxǔ shì yīnwèi dōngtiān tài lěng le, yěxǔ shì yīnwèi wǒ xǐhuan nà zhǒng yòu téng yòu shūfu de gǎnjué. Lǎobǎn de tāng méiyǒu shénme tèbié de——báicài, dòufu, yìdiǎn ròu. Dànshì dōngtiān de wǎnshàng, lěng fēng chuīzhe nǐ de liǎn, nǐ zǒu jìn nà jiā rè rè de xiǎo diàn, duān qǐ yì wǎn tài tàng de tāng——zhège bǐ shénme dōu hǎo.",
    "text_en": "On the coldest days of winter, my favorite thing is going to the little shop downstairs for soup. Their soup is scalding hot. The owner always says: 'Careful, it's very hot!' But I can never wait. The first sip always burns — a flash of pain on the tongue — but the hot soup goes from mouth to stomach and your whole body warms up. My friend thinks I'm strange: 'Why don't you just wait a bit?' I can't explain why. Maybe it's because winter is too cold. Maybe it's because I like that feeling of pain and comfort at the same time. The owner's soup is nothing special — cabbage, tofu, a little meat. But on a winter night, cold wind on your face, walking into that warm little shop and picking up a bowl of too-hot soup — nothing beats it.",
    "questions": [
        {"type": "mc", "q_zh": "汤里面有什么？", "q_en": "What's in the soup?",
         "options": [
             {"text": "白菜、豆腐、一点肉", "pinyin": "báicài, dòufu, yìdiǎn ròu", "text_en": "cabbage, tofu, a little meat", "correct": True},
             {"text": "鸡肉和面条", "pinyin": "jīròu hé miàntiáo", "text_en": "chicken and noodles", "correct": False},
             {"text": "牛肉和土豆", "pinyin": "niúròu hé tǔdòu", "text_en": "beef and potatoes", "correct": False},
             {"text": "鱼和蔬菜", "pinyin": "yú hé shūcài", "text_en": "fish and vegetables", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "朋友问了什么问题？", "q_en": "What did the friend ask?",
         "options": [
             {"text": "为什么不等一等再喝", "pinyin": "wèi shénme bù děng yì děng zài hē", "text_en": "why not wait before drinking", "correct": True},
             {"text": "为什么每天都去", "pinyin": "wèi shénme měi tiān dōu qù", "text_en": "why go every day", "correct": False},
             {"text": "为什么不去别的店", "pinyin": "wèi shénme bú qù bié de diàn", "text_en": "why not go to another shop", "correct": False},
             {"text": "汤好不好喝", "pinyin": "tāng hǎo bù hǎo hē", "text_en": "is the soup good", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "「我」为什么喜欢第一口？", "q_en": "Why does 'I' like the first sip?",
         "options": [
             {"text": "因为味道最好", "pinyin": "yīnwèi wèidào zuì hǎo", "text_en": "best flavor", "correct": False},
             {"text": "因为又疼又舒服，整个身体都暖了", "pinyin": "yīnwèi yòu téng yòu shūfu, zhěnggè shēntǐ dōu nuǎn le", "text_en": "painful yet comfortable, whole body warms up", "correct": True},
             {"text": "因为老板说要小心", "pinyin": "yīnwèi lǎobǎn shuō yào xiǎoxīn", "text_en": "because the owner says be careful", "correct": False},
             {"text": "因为朋友不理解", "pinyin": "yīnwèi péngyou bù lǐjiě", "text_en": "because friends don't understand", "correct": False}
         ], "difficulty": 0.4}
    ]
})

# 6. j3_cozy_108 - Was: generic "neighborhood sounds" restorative
# NEW: ARRESTED DEVELOPMENT MOVE - character blind spot everyone works around
replace_passage("j3_cozy_108", {
    "title": "The Meeting King",
    "title_zh": "开会大王",
    "text_zh": "我们经理最喜欢开会。星期一开会，星期三开会，星期五也开会。每次开会都要一个小时。他说：「开会是为了更好地工作。」但是每次开完会，大家都要加班，因为开会用了太多时间。小张想了一个办法。他每次开会都带很多问题问经理，让经理讲个不停。这样经理就觉得会开得很好，很高兴。其实大家都知道，小张问的问题和工作没有关系——他问的是天气、是午饭、是周末的计划。但是经理从来没有发现。每次开完会，经理都说：「今天的会很有效率。」大家互相看一眼，不说话。",
    "text_pinyin": "Wǒmen jīnglǐ zuì xǐhuan kāi huì. Xīngqī yī kāi huì, xīngqī sān kāi huì, xīngqī wǔ yě kāi huì. Měi cì kāi huì dōu yào yí gè xiǎoshí. Tā shuō:「Kāi huì shì wèile gèng hǎo de gōngzuò.」Dànshì měi cì kāi wán huì, dàjiā dōu yào jiābān, yīnwèi kāi huì yòng le tài duō shíjiān. Xiǎo Zhāng xiǎng le yí gè bànfǎ. Tā měi cì kāi huì dōu dài hěn duō wèntí wèn jīnglǐ, ràng jīnglǐ jiǎng gè bù tíng. Zhèyàng jīnglǐ jiù juéde huì kāi de hěn hǎo, hěn gāoxìng. Qíshí dàjiā dōu zhīdào, Xiǎo Zhāng wèn de wèntí hé gōngzuò méiyǒu guānxi——tā wèn de shì tiānqì, shì wǔfàn, shì zhōumò de jìhuà. Dànshì jīnglǐ cónglái méiyǒu fāxiàn. Měi cì kāi wán huì, jīnglǐ dōu shuō:「Jīntiān de huì hěn yǒu xiàolǜ.」Dàjiā hùxiāng kàn yì yǎn, bù shuō huà.",
    "text_pinyin": "Wǒmen jīnglǐ zuì xǐhuan kāi huì. Xīngqī yī kāi huì, xīngqī sān kāi huì, xīngqī wǔ yě kāi huì. Měi cì kāi huì dōu yào yí gè xiǎoshí. Tā shuō:「Kāi huì shì wèile gèng hǎo de gōngzuò.」Dànshì měi cì kāi wán huì, dàjiā dōu yào jiābān, yīnwèi kāi huì yòng le tài duō shíjiān. Xiǎo Zhāng xiǎng le yí gè bànfǎ. Tā měi cì kāi huì dōu dài hěn duō wèntí wèn jīnglǐ, ràng jīnglǐ jiǎng gè bù tíng. Zhèyàng jīnglǐ jiù juéde huì kāi de hěn hǎo, hěn gāoxìng. Qíshí dàjiā dōu zhīdào, Xiǎo Zhāng wèn de wèntí hé gōngzuò méiyǒu guānxi——tā wèn de shì tiānqì, shì wǔfàn, shì zhōumò de jìhuà. Dànshì jīnglǐ cónglái méiyǒu fāxiàn. Měi cì kāi wán huì, jīnglǐ dōu shuō:「Jīntiān de huì hěn yǒu xiàolǜ.」Dàjiā hùxiāng kàn yì yǎn, bù shuō huà.",
    "text_en": "Our manager loves meetings. Monday meeting, Wednesday meeting, Friday meeting. Each one takes an hour. He says: 'Meetings help us work better.' But after every meeting, everyone has to work overtime, because the meetings took too much time. Xiao Zhang came up with a plan. At every meeting, he brings lots of questions for the manager, keeping him talking nonstop. That way the manager feels the meeting went great and leaves happy. The truth is, everyone knows Xiao Zhang's questions have nothing to do with work — he asks about the weather, about lunch, about weekend plans. But the manager has never noticed. After every meeting, the manager says: 'Today's meeting was very productive.' Everyone exchanges a glance and says nothing.",
    "questions": [
        {"type": "mc", "q_zh": "经理每个星期开几次会？", "q_en": "How many meetings does the manager hold per week?",
         "options": [
             {"text": "一次", "pinyin": "yí cì", "text_en": "once", "correct": False},
             {"text": "两次", "pinyin": "liǎng cì", "text_en": "twice", "correct": False},
             {"text": "三次", "pinyin": "sān cì", "text_en": "three times", "correct": True},
             {"text": "五次", "pinyin": "wǔ cì", "text_en": "five times", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "小张问的问题是关于什么的？", "q_en": "What are Xiao Zhang's questions about?",
         "options": [
             {"text": "工作计划", "pinyin": "gōngzuò jìhuà", "text_en": "work plans", "correct": False},
             {"text": "天气、午饭、周末计划", "pinyin": "tiānqì, wǔfàn, zhōumò jìhuà", "text_en": "weather, lunch, weekend plans", "correct": True},
             {"text": "公司的问题", "pinyin": "gōngsī de wèntí", "text_en": "company issues", "correct": False},
             {"text": "客户的事情", "pinyin": "kèhù de shìqing", "text_en": "client matters", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "经理知不知道真相？", "q_en": "Does the manager know the truth?",
         "options": [
             {"text": "知道，但是不在意", "pinyin": "zhīdào, dànshì bú zàiyì", "text_en": "knows but doesn't care", "correct": False},
             {"text": "从来没有发现", "pinyin": "cónglái méiyǒu fāxiàn", "text_en": "has never noticed", "correct": True},
             {"text": "最后发现了", "pinyin": "zuìhòu fāxiàn le", "text_en": "eventually found out", "correct": False},
             {"text": "别人告诉他了", "pinyin": "biéren gàosu tā le", "text_en": "someone told him", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 7. j3_cozy_109 - Was: generic "Weekend Morning" restorative
# NEW: HODGMAN/SEDARIS MOVE - deadpan authority about trivial obsessions
replace_passage("j3_cozy_109", {
    "title": "The Pen Shop Rule",
    "title_zh": "文具店的规矩",
    "text_zh": "我家附近有一家文具店，老板姓周。周老板卖笔卖了三十年。他的店有一个奇怪的规矩：买笔之前，你必须先试写。如果你拿笔的方式不对，他不会卖给你。上个星期，一个年轻人来买钢笔。他拿起笔试了试，周老板摇摇头说：「你的手指太紧了，这支笔不适合你。」年轻人说：「我就是想买这支。」周老板说：「你可以去别的店买。」年轻人很生气地走了。旁边的客人问周老板：「你为什么不卖给他？」周老板说：「一支好笔被拿错了，写出来的字也不会好看。我不能让我的笔受这种委屈。」",
    "text_pinyin": "Wǒ jiā fùjìn yǒu yì jiā wénjù diàn, lǎobǎn xìng Zhōu. Zhōu lǎobǎn mài bǐ mài le sānshí nián. Tā de diàn yǒu yí gè qíguài de guījǔ: mǎi bǐ zhīqián, nǐ bìxū xiān shì xiě. Rúguǒ nǐ ná bǐ de fāngshì bú duì, tā bú huì mài gěi nǐ. Shàng gè xīngqī, yí gè niánqīng rén lái mǎi gāngbǐ. Tā ná qǐ bǐ shì le shì, Zhōu lǎobǎn yáo yao tóu shuō:「Nǐ de shǒuzhǐ tài jǐn le, zhè zhī bǐ bù shìhé nǐ.」Niánqīng rén shuō:「Wǒ jiù shì xiǎng mǎi zhè zhī.」Zhōu lǎobǎn shuō:「Nǐ kěyǐ qù bié de diàn mǎi.」Niánqīng rén hěn shēngqì de zǒu le. Pángbiān de kèrén wèn Zhōu lǎobǎn:「Nǐ wèi shénme bú mài gěi tā?」Zhōu lǎobǎn shuō:「Yì zhī hǎo bǐ bèi ná cuò le, xiě chūlái de zì yě bú huì hǎokàn. Wǒ bù néng ràng wǒ de bǐ shòu zhè zhǒng wěiqu.」",
    "text_en": "Near my home there's a stationery shop. The owner, Mr. Zhou, has been selling pens for thirty years. His shop has a strange rule: before buying a pen, you have to test-write with it. If you hold the pen wrong, he won't sell it to you. Last week, a young man came to buy a fountain pen. He picked it up and tried it. Mr. Zhou shook his head: 'Your fingers are too tight. This pen isn't right for you.' The young man said: 'But I want this one.' Mr. Zhou: 'You can buy it at another shop.' The young man left angry. A customer nearby asked Mr. Zhou: 'Why wouldn't you sell it to him?' Mr. Zhou said: 'A good pen held the wrong way — the writing won't be good either. I can't let my pens suffer that kind of indignity.'",
    "questions": [
        {"type": "mc", "q_zh": "周老板卖笔卖了多久？", "q_en": "How long has Mr. Zhou been selling pens?",
         "options": [
             {"text": "十年", "pinyin": "shí nián", "text_en": "ten years", "correct": False},
             {"text": "二十年", "pinyin": "èrshí nián", "text_en": "twenty years", "correct": False},
             {"text": "三十年", "pinyin": "sānshí nián", "text_en": "thirty years", "correct": True},
             {"text": "四十年", "pinyin": "sìshí nián", "text_en": "forty years", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "年轻人为什么买不到笔？", "q_en": "Why couldn't the young man buy the pen?",
         "options": [
             {"text": "因为太贵了", "pinyin": "yīnwèi tài guì le", "text_en": "too expensive", "correct": False},
             {"text": "因为他拿笔的方式不对", "pinyin": "yīnwèi tā ná bǐ de fāngshì bú duì", "text_en": "he held the pen wrong", "correct": True},
             {"text": "因为笔卖完了", "pinyin": "yīnwèi bǐ mài wán le", "text_en": "the pen was sold out", "correct": False},
             {"text": "因为店要关门了", "pinyin": "yīnwèi diàn yào guān mén le", "text_en": "the shop was closing", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "周老板为什么不卖？", "q_en": "Why did Mr. Zhou refuse to sell?",
         "options": [
             {"text": "他不喜欢年轻人", "pinyin": "tā bù xǐhuan niánqīng rén", "text_en": "he doesn't like young people", "correct": False},
             {"text": "他觉得笔不够好", "pinyin": "tā juéde bǐ bú gòu hǎo", "text_en": "the pen wasn't good enough", "correct": False},
             {"text": "他不想让笔被拿错", "pinyin": "tā bù xiǎng ràng bǐ bèi ná cuò", "text_en": "he didn't want the pen held wrong", "correct": True},
             {"text": "那支笔是他自己的", "pinyin": "nà zhī bǐ shì tā zìjǐ de", "text_en": "the pen was his own", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 8. j3_cozy_110 - Was: generic "The Tea Shop" restorative
# NEW: FRASIER MOVE - smart people absurd because of vanity
replace_passage("j3_cozy_110", {
    "title": "The Napkin Argument",
    "title_zh": "叠餐巾的争论",
    "text_zh": "公司聚餐，小陈和小吴为了怎么叠餐巾吵了起来。小陈说餐巾要叠成三角形，因为这样比较正式。小吴说不对，应该叠成长方形，因为三角形太随便了。两个人都觉得自己是对的。小陈说他在大学学过，小吴说他在网上查过。旁边的同事都看着他们，没有人说话。最后经理来了，看了看他们两个的餐巾，说：「你们叠得都不对。」然后他把餐巾放在腿上，没有叠。小陈和小吴互相看了一眼。经理已经开始吃了。其实大家早就饿了，但是没有人好意思先说。",
    "text_pinyin": "Gōngsī jùcān, Xiǎo Chén hé Xiǎo Wú wèile zěnme dié cānjīn chǎo le qǐlái. Xiǎo Chén shuō cānjīn yào dié chéng sānjiǎoxíng, yīnwèi zhèyàng bǐjiào zhèngshì. Xiǎo Wú shuō bú duì, yīnggāi dié chéng chángfāngxíng, yīnwèi sānjiǎoxíng tài suíbiàn le. Liǎng gè rén dōu juéde zìjǐ shì duì de. Xiǎo Chén shuō tā zài dàxué xué guò, Xiǎo Wú shuō tā zài wǎng shàng chá guò. Pángbiān de tóngshì dōu kànzhe tāmen, méiyǒu rén shuō huà. Zuìhòu jīnglǐ lái le, kàn le kàn tāmen liǎng gè de cānjīn, shuō:「Nǐmen dié de dōu bú duì.」Ránhòu tā bǎ cānjīn fàng zài tuǐ shàng, méiyǒu dié. Xiǎo Chén hé Xiǎo Wú hùxiāng kàn le yì yǎn. Jīnglǐ yǐjīng kāishǐ chī le. Qíshí dàjiā zǎo jiù è le, dànshì méiyǒu rén hǎoyìsi xiān shuō.",
    "text_en": "At the company dinner, Xiao Chen and Xiao Wu got into an argument about how to fold a napkin. Xiao Chen said it should be folded into a triangle because that's more formal. Xiao Wu said no, it should be a rectangle, because triangles are too casual. Both were sure they were right. Xiao Chen said he learned it in college. Xiao Wu said he looked it up online. The other colleagues watched them, nobody saying a word. Finally the manager arrived, looked at both their napkins, and said: 'You're both wrong.' Then he put the napkin on his lap, unfolded. Xiao Chen and Xiao Wu glanced at each other. The manager was already eating. The truth was, everyone had been hungry for a while, but nobody had wanted to be the first to say so.",
    "questions": [
        {"type": "mc", "q_zh": "小陈觉得餐巾要叠成什么形状？", "q_en": "What shape did Xiao Chen think the napkin should be?",
         "options": [
             {"text": "三角形", "pinyin": "sānjiǎoxíng", "text_en": "triangle", "correct": True},
             {"text": "长方形", "pinyin": "chángfāngxíng", "text_en": "rectangle", "correct": False},
             {"text": "正方形", "pinyin": "zhèngfāngxíng", "text_en": "square", "correct": False},
             {"text": "圆形", "pinyin": "yuánxíng", "text_en": "circle", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "经理怎么做的？", "q_en": "What did the manager do?",
         "options": [
             {"text": "叠成三角形", "pinyin": "dié chéng sānjiǎoxíng", "text_en": "folded it into a triangle", "correct": False},
             {"text": "叠成长方形", "pinyin": "dié chéng chángfāngxíng", "text_en": "folded it into a rectangle", "correct": False},
             {"text": "把餐巾放在腿上，没有叠", "pinyin": "bǎ cānjīn fàng zài tuǐ shàng, méiyǒu dié", "text_en": "put it on his lap, unfolded", "correct": True},
             {"text": "没有用餐巾", "pinyin": "méiyǒu yòng cānjīn", "text_en": "didn't use a napkin", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "其实大家怎么了？", "q_en": "What was actually going on with everyone?",
         "options": [
             {"text": "大家都不饿", "pinyin": "dàjiā dōu bú è", "text_en": "nobody was hungry", "correct": False},
             {"text": "大家早就饿了", "pinyin": "dàjiā zǎo jiù è le", "text_en": "everyone had been hungry", "correct": True},
             {"text": "大家都想走了", "pinyin": "dàjiā dōu xiǎng zǒu le", "text_en": "everyone wanted to leave", "correct": False},
             {"text": "大家都在玩手机", "pinyin": "dàjiā dōu zài wán shǒujī", "text_en": "everyone was on their phones", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 9. j3_cozy_111 - Was: generic "A Handwritten Letter" restorative
# NEW: MIYAZAKI GROWING-UP ACHE - returning to find things smaller
replace_passage("j3_cozy_111", {
    "title": "The Playground",
    "title_zh": "游乐场",
    "text_zh": "上个周末我回了老家。走过小学旁边的时候，我看到了小时候玩过的游乐场。滑梯还在，但是比我记得的小很多。以前我觉得那个滑梯很高很高，要爬很久才能到上面。现在看，只有一米多。旁边的秋千也在。小时候我总是要爸爸推我，因为我的脚够不到地上。现在我坐上去，腿太长了，膝盖都弯不下来。一个小女孩跑过来问我：「叔叔，你也要玩吗？」我笑了笑说：「不了，我只是来看看。」她跑走了。我又站了一会儿。风跟小时候的一样，但是所有的东西都变小了。",
    "text_pinyin": "Shàng gè zhōumò wǒ huí le lǎojiā. Zǒu guò xiǎoxué pángbiān de shíhou, wǒ kàn dào le xiǎo shíhou wán guò de yóulèchǎng. Huátī hái zài, dànshì bǐ wǒ jì de de xiǎo hěn duō. Yǐqián wǒ juéde nàge huátī hěn gāo hěn gāo, yào pá hěn jiǔ cái néng dào shàngmiàn. Xiànzài kàn, zhǐ yǒu yì mǐ duō. Pángbiān de qiūqiān yě zài. Xiǎo shíhou wǒ zǒngshì yào bàba tuī wǒ, yīnwèi wǒ de jiǎo gòu bú dào dì shàng. Xiànzài wǒ zuò shàngqù, tuǐ tài cháng le, xīgài dōu wān bù xiàlái. Yí gè xiǎo nǚhái pǎo guòlái wèn wǒ:「Shūshu, nǐ yě yào wán ma?」Wǒ xiào le xiào shuō:「Bù le, wǒ zhǐ shì lái kàn kàn.」Tā pǎo zǒu le. Wǒ yòu zhàn le yíhuìr. Fēng gēn xiǎo shíhou de yíyàng, dànshì suǒyǒu de dōngxi dōu biàn xiǎo le.",
    "text_en": "Last weekend I went back to my hometown. Walking past the elementary school, I saw the playground where I used to play. The slide was still there, but much smaller than I remembered. I used to think it was so tall, a long climb to the top. Now I could see it was barely over a meter. The swing next to it was still there too. When I was little, I always needed Dad to push me because my feet couldn't reach the ground. Now when I sat on it, my legs were too long, knees wouldn't even bend right. A little girl ran over: 'Mister, do you want to play too?' I smiled: 'No, I'm just here to look.' She ran off. I stood there a little longer. The wind was the same as when I was small, but everything else had shrunk.",
    "questions": [
        {"type": "mc", "q_zh": "滑梯现在有多高？", "q_en": "How tall is the slide now?",
         "options": [
             {"text": "一米多", "pinyin": "yì mǐ duō", "text_en": "a little over one meter", "correct": True},
             {"text": "三米多", "pinyin": "sān mǐ duō", "text_en": "over three meters", "correct": False},
             {"text": "两米", "pinyin": "liǎng mǐ", "text_en": "two meters", "correct": False},
             {"text": "不知道", "pinyin": "bù zhīdào", "text_en": "unknown", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "为什么「我」坐不了秋千？", "q_en": "Why couldn't 'I' sit on the swing properly?",
         "options": [
             {"text": "秋千坏了", "pinyin": "qiūqiān huài le", "text_en": "the swing was broken", "correct": False},
             {"text": "腿太长了", "pinyin": "tuǐ tài cháng le", "text_en": "legs were too long", "correct": True},
             {"text": "太重了", "pinyin": "tài zhòng le", "text_en": "too heavy", "correct": False},
             {"text": "有小孩在玩", "pinyin": "yǒu xiǎohái zài wán", "text_en": "children were using it", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "什么没有变？", "q_en": "What hadn't changed?",
         "options": [
             {"text": "滑梯的高度", "pinyin": "huátī de gāodù", "text_en": "the height of the slide", "correct": False},
             {"text": "风", "pinyin": "fēng", "text_en": "the wind", "correct": True},
             {"text": "游乐场的大小", "pinyin": "yóulèchǎng de dàxiǎo", "text_en": "the size of the playground", "correct": False},
             {"text": "附近的人", "pinyin": "fùjìn de rén", "text_en": "the people nearby", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 10. j3_inst_007 - Was: bus driver farewell with 突然 realize pattern
# NEW: NORM VIOLATION / social comedy - the person who talks on speaker phone
replace_passage("j3_inst_007", {
    "title": "The Speaker Phone Person",
    "title_zh": "外放手机的人",
    "text_zh": "地铁上有一个人在外放手机看视频，声音很大。旁边的人都看他，但是他没有注意到。一个老太太走过去说：「年轻人，你能不能戴耳机？」他说：「没带耳机。」老太太说：「那你可以把声音关小一点吗？」他说：「关小了我听不到。」老太太点点头，从包里拿出自己的手机，打开了一首老歌，也外放。声音比他的还大。年轻人看了她一眼。老太太笑着说：「你听你的，我听我的。大家都方便。」车上有几个人笑了。年轻人低头想了几秒钟，把手机声音关了，开始看窗外。",
    "text_pinyin": "Dìtiě shàng yǒu yí gè rén zài wài fàng shǒujī kàn shìpín, shēngyīn hěn dà. Pángbiān de rén dōu kàn tā, dànshì tā méiyǒu zhùyì dào. Yí gè lǎo tàitai zǒu guòqù shuō:「Niánqīng rén, nǐ néng bu néng dài ěrjī?」Tā shuō:「Méi dài ěrjī.」Lǎo tàitai shuō:「Nà nǐ kěyǐ bǎ shēngyīn guān xiǎo yìdiǎn ma?」Tā shuō:「Guān xiǎo le wǒ tīng bú dào.」Lǎo tàitai diǎn diǎn tóu, cóng bāo lǐ ná chū zìjǐ de shǒujī, dǎkāi le yì shǒu lǎo gē, yě wài fàng. Shēngyīn bǐ tā de hái dà. Niánqīng rén kàn le tā yì yǎn. Lǎo tàitai xiàozhe shuō:「Nǐ tīng nǐ de, wǒ tīng wǒ de. Dàjiā dōu fāngbiàn.」Chē shàng yǒu jǐ gè rén xiào le. Niánqīng rén dī tóu xiǎng le jǐ miǎozhōng, bǎ shǒujī shēngyīn guān le, kāishǐ kàn chuāng wài.",
    "text_en": "On the subway, someone was watching videos on speakerphone, volume up. Everyone nearby was staring, but he didn't notice. An old lady walked over: 'Young man, could you use earphones?' He said: 'Didn't bring any.' The old lady: 'Then could you turn the volume down?' He said: 'If I turn it down I can't hear it.' The old lady nodded. She took out her own phone, put on an old song, also on speaker. Louder than his. The young man glanced at her. The old lady smiled: 'You listen to yours, I'll listen to mine. Convenient for everyone.' A few people on the train laughed. The young man thought for a few seconds, turned his phone off, and started looking out the window.",
    "questions": [
        {"type": "mc", "q_zh": "年轻人为什么不戴耳机？", "q_en": "Why wasn't the young man using earphones?",
         "options": [
             {"text": "他不喜欢耳机", "pinyin": "tā bù xǐhuan ěrjī", "text_en": "he doesn't like earphones", "correct": False},
             {"text": "没带耳机", "pinyin": "méi dài ěrjī", "text_en": "didn't bring any", "correct": True},
             {"text": "耳机坏了", "pinyin": "ěrjī huài le", "text_en": "earphones were broken", "correct": False},
             {"text": "他觉得声音不大", "pinyin": "tā juéde shēngyīn bú dà", "text_en": "he thought it wasn't loud", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "老太太做了什么？", "q_en": "What did the old lady do?",
         "options": [
             {"text": "跟他吵了一架", "pinyin": "gēn tā chǎo le yí jià", "text_en": "argued with him", "correct": False},
             {"text": "也外放自己的手机，放老歌", "pinyin": "yě wài fàng zìjǐ de shǒujī, fàng lǎo gē", "text_en": "played her own music on speaker too", "correct": True},
             {"text": "叫了地铁工作人员", "pinyin": "jiào le dìtiě gōngzuò rényuán", "text_en": "called subway staff", "correct": False},
             {"text": "换了一个座位", "pinyin": "huàn le yí gè zuòwèi", "text_en": "changed seats", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "年轻人最后怎么做了？", "q_en": "What did the young man do in the end?",
         "options": [
             {"text": "也听老太太的歌", "pinyin": "yě tīng lǎo tàitai de gē", "text_en": "listened to the old lady's song too", "correct": False},
             {"text": "生气地下车了", "pinyin": "shēngqì de xià chē le", "text_en": "got off angrily", "correct": False},
             {"text": "把手机声音关了，看窗外", "pinyin": "bǎ shǒujī shēngyīn guān le, kàn chuāng wài", "text_en": "turned off the sound and looked out the window", "correct": True},
             {"text": "跟老太太道歉了", "pinyin": "gēn lǎo tàitai dàoqiàn le", "text_en": "apologized to the old lady", "correct": False}
         ], "difficulty": 0.2}
    ]
})

# 11. j3_urban_017 - Was: generic skyline from roof with realize ending
# NEW: CROSS-PURPOSE DIALOGUE - two people pursuing different goals
replace_passage("j3_urban_017", {
    "title": "The Restaurant Recommendation",
    "title_zh": "推荐餐厅",
    "text_zh": "朋友问我：「你知道附近有什么好吃的吗？」我说：「楼下那家面馆不错。」朋友说：「我不想吃面。」我说：「那旁边有一家饺子馆。」朋友说：「也不想吃饺子。」我说：「那你想吃什么？」朋友说：「我不知道，所以才问你啊。」我又说了三家，她都说不想去。我有点生气：「那你自己选吧。」朋友说：「我就是选不出来才问你的。你再推荐一个。」我说：「韩国菜？」朋友说：「昨天刚吃过。」我说：「火锅？」朋友的眼睛亮了：「火锅！走！」我说：「你从一开始就想吃火锅吧？」朋友笑了一下，没有回答。",
    "text_pinyin": "Péngyou wèn wǒ:「Nǐ zhīdào fùjìn yǒu shénme hǎochī de ma?」Wǒ shuō:「Lóu xià nà jiā miànguǎn búcuò.」Péngyou shuō:「Wǒ bù xiǎng chī miàn.」Wǒ shuō:「Nà pángbiān yǒu yì jiā jiǎozi guǎn.」Péngyou shuō:「Yě bù xiǎng chī jiǎozi.」Wǒ shuō:「Nà nǐ xiǎng chī shénme?」Péngyou shuō:「Wǒ bù zhīdào, suǒyǐ cái wèn nǐ a.」Wǒ yòu shuō le sān jiā, tā dōu shuō bù xiǎng qù. Wǒ yǒudiǎn shēngqì:「Nà nǐ zìjǐ xuǎn ba.」Péngyou shuō:「Wǒ jiù shì xuǎn bù chūlái cái wèn nǐ de. Nǐ zài tuījiàn yí gè.」Wǒ shuō:「Hánguó cài?」Péngyou shuō:「Zuótiān gāng chī guò.」Wǒ shuō:「Huǒguō?」Péngyou de yǎnjīng liàng le:「Huǒguō! Zǒu!」Wǒ shuō:「Nǐ cóng yì kāishǐ jiù xiǎng chī huǒguō ba?」Péngyou xiào le yíxià, méiyǒu huídá.",
    "text_en": "My friend asked: 'Know any good food nearby?' I said: 'The noodle place downstairs is good.' She said: 'Don't feel like noodles.' I said: 'There's a dumpling place next door.' She said: 'Don't feel like dumplings either.' I said: 'Then what do you want?' She said: 'I don't know, that's why I'm asking you.' I suggested three more places. She turned down all of them. I got a little annoyed: 'Then you pick.' She said: 'I can't pick, that's why I asked you. Suggest one more.' I said: 'Korean?' She said: 'Had it yesterday.' I said: 'Hot pot?' Her eyes lit up: 'Hot pot! Let's go!' I said: 'You wanted hot pot from the start, didn't you?' She smiled and didn't answer.",
    "questions": [
        {"type": "mc", "q_zh": "朋友一开始说想吃什么？", "q_en": "What did the friend say she wanted at first?",
         "options": [
             {"text": "面条", "pinyin": "miàntiáo", "text_en": "noodles", "correct": False},
             {"text": "火锅", "pinyin": "huǒguō", "text_en": "hot pot", "correct": False},
             {"text": "她不知道", "pinyin": "tā bù zhīdào", "text_en": "she didn't know", "correct": True},
             {"text": "饺子", "pinyin": "jiǎozi", "text_en": "dumplings", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "「我」推荐了几个地方？", "q_en": "How many places did 'I' suggest?",
         "options": [
             {"text": "三个", "pinyin": "sān gè", "text_en": "three", "correct": False},
             {"text": "四个", "pinyin": "sì gè", "text_en": "four", "correct": False},
             {"text": "五个", "pinyin": "wǔ gè", "text_en": "five", "correct": False},
             {"text": "至少七个", "pinyin": "zhìshǎo qī gè", "text_en": "at least seven", "correct": True}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "朋友最后选了什么？", "q_en": "What did the friend finally choose?",
         "options": [
             {"text": "面条", "pinyin": "miàntiáo", "text_en": "noodles", "correct": False},
             {"text": "韩国菜", "pinyin": "Hánguó cài", "text_en": "Korean food", "correct": False},
             {"text": "火锅", "pinyin": "huǒguō", "text_en": "hot pot", "correct": True},
             {"text": "饺子", "pinyin": "jiǎozi", "text_en": "dumplings", "correct": False}
         ], "difficulty": 0.2}
    ]
})

# 12. j3_cozy_112 - Was: generic "The Old Bookstore" restorative
# NEW: ENSEMBLE BANTER - the group chat that won't stop
replace_passage("j3_cozy_112", {
    "title": "The Group Chat",
    "title_zh": "群聊",
    "text_zh": "我们大学同学有一个微信群，里面有二十个人。每天消息最多的时候是中午十二点，因为大家都在吃午饭。今天小刘先发了一张照片：他的午饭。小王说：「又是外卖？你不能自己做饭吗？」小刘说：「你做了吗？」小王发了一张照片——也是外卖。大家都发了笑脸。然后小美说：「我自己做的！」她发了一张照片，是一碗煮得太烂的面条。小张说：「这个看起来像糊了。」小美说：「不是糊了，是日式软面。」小张说：「日式软面不是这个颜色。」小美发了一个生气的表情，然后说：「好吧，是糊了。但是我吃完了。」群里发了二十个大拇指。",
    "text_pinyin": "Wǒmen dàxué tóngxué yǒu yí gè Wēixìn qún, lǐmiàn yǒu èrshí gè rén. Měi tiān xiāoxi zuì duō de shíhou shì zhōngwǔ shí'èr diǎn, yīnwèi dàjiā dōu zài chī wǔfàn. Jīntiān Xiǎo Liú xiān fā le yì zhāng zhàopiàn: tā de wǔfàn. Xiǎo Wáng shuō:「Yòu shì wàimài? Nǐ bù néng zìjǐ zuò fàn ma?」Xiǎo Liú shuō:「Nǐ zuò le ma?」Xiǎo Wáng fā le yì zhāng zhàopiàn——yě shì wàimài. Dàjiā dōu fā le xiàoliǎn. Ránhòu Xiǎo Měi shuō:「Wǒ zìjǐ zuò de!」Tā fā le yì zhāng zhàopiàn, shì yì wǎn zhǔ de tài làn de miàntiáo. Xiǎo Zhāng shuō:「Zhège kàn qǐlái xiàng hú le.」Xiǎo Měi shuō:「Bú shì hú le, shì Rìshì ruǎn miàn.」Xiǎo Zhāng shuō:「Rìshì ruǎn miàn bú shì zhège yánsè.」Xiǎo Měi fā le yí gè shēngqì de biǎoqíng, ránhòu shuō:「Hǎo ba, shì hú le. Dànshì wǒ chī wán le.」Qún lǐ fā le èrshí gè dà muzhǐ.",
    "text_en": "Our college classmates have a WeChat group with twenty people. The busiest time every day is noon, because everyone's eating lunch. Today Xiao Liu sent a photo first: his lunch. Xiao Wang said: 'Takeout again? Can't you cook?' Xiao Liu said: 'Did you?' Xiao Wang posted a photo — also takeout. Everyone sent smiley faces. Then Xiao Mei said: 'I cooked mine!' She posted a photo of overcooked noodles. Xiao Zhang said: 'That looks burned.' Xiao Mei said: 'It's not burned, it's Japanese-style soft noodles.' Xiao Zhang: 'Japanese soft noodles aren't that color.' Xiao Mei sent an angry emoji, then said: 'Fine, it burned. But I ate it all.' The group sent twenty thumbs-ups.",
    "questions": [
        {"type": "mc", "q_zh": "群里有多少人？", "q_en": "How many people are in the group?",
         "options": [
             {"text": "十个", "pinyin": "shí gè", "text_en": "ten", "correct": False},
             {"text": "十五个", "pinyin": "shíwǔ gè", "text_en": "fifteen", "correct": False},
             {"text": "二十个", "pinyin": "èrshí gè", "text_en": "twenty", "correct": True},
             {"text": "三十个", "pinyin": "sānshí gè", "text_en": "thirty", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "小美说她的面是什么？", "q_en": "What did Xiao Mei say her noodles were?",
         "options": [
             {"text": "中国面", "pinyin": "Zhōngguó miàn", "text_en": "Chinese noodles", "correct": False},
             {"text": "日式软面", "pinyin": "Rìshì ruǎn miàn", "text_en": "Japanese-style soft noodles", "correct": True},
             {"text": "意大利面", "pinyin": "Yìdàlì miàn", "text_en": "Italian pasta", "correct": False},
             {"text": "方便面", "pinyin": "fāngbiàn miàn", "text_en": "instant noodles", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "小美最后承认了什么？", "q_en": "What did Xiao Mei admit in the end?",
         "options": [
             {"text": "面是外卖", "pinyin": "miàn shì wàimài", "text_en": "the noodles were takeout", "correct": False},
             {"text": "面糊了", "pinyin": "miàn hú le", "text_en": "the noodles burned", "correct": True},
             {"text": "她不会做饭", "pinyin": "tā bú huì zuò fàn", "text_en": "she can't cook", "correct": False},
             {"text": "她没有吃完", "pinyin": "tā méiyǒu chī wán", "text_en": "she didn't finish", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# Save after HSK 3 batch
with open("data/reading_passages.json", "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("HSK 3 batch done: 12 passages rewritten")
print("Rewrote: j3_comedy_011, j3_identity_009, j3_travel_001, j3_travel_002, j3_food_006, j3_cozy_108, j3_cozy_109, j3_cozy_110, j3_cozy_111, j3_inst_007, j3_urban_017, j3_cozy_112")
