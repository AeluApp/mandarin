#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HSK 5 passage rewrites."""
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
# HSK 5 REWRITES (13 passages)
# ============================================================

# 1. j5_observe_001 - Was: last bench in the park, generic observe
# NEW: SEINFELD MOVE - the person who stands too close in the elevator
replace_passage("j5_observe_001", {
    "title": "The Elevator Space Invader",
    "title_zh": "电梯里站太近的人",
    "text_zh": "我注意到一个现象：电梯里有一套精密的空间分配规则，所有人都自动遵守，但没有人明确制定过。第一个人进去站中间，第二个人进来以后两个人各站一边，第三个人会站在中间偏后的位置。就像粒子在容器里自动均匀分布一样。但是我们楼有一个人破坏了这个系统。他总是站在离你非常近的地方，近到你能闻到他用的洗发水。不是故意的，他只是没有那种距离感。你退后一步，他会无意识地跟着前进一步。你靠墙站，他会转过身面对你说话。没有任何恶意，就是那个出厂设置的社交距离比一般人短了大约四十厘米。全楼的人都学会了一件事：看到他进电梯，就假装忘了东西回去等下一趟。没有人跟他说过这件事。也许永远不会有人说。",
    "text_pinyin": "Wǒ zhùyì dào yí gè xiànxiàng: diàntī lǐ yǒu yí tào jīngmì de kōngjiān fēnpèi guīzé, suǒyǒu rén dōu zìdòng zūnshǒu, dàn méiyǒu rén míngquè zhìdìng guò. Dì yī gè rén jìnqù zhàn zhōngjiān, dì èr gè rén jìnlái yǐhòu liǎng gè rén gè zhàn yì biān, dì sān gè rén huì zhàn zài zhōngjiān piān hòu de wèizhi. Jiù xiàng lìzǐ zài róngqì lǐ zìdòng jūnyún fēnbù yíyàng. Dànshì wǒmen lóu yǒu yí gè rén pòhuài le zhège xìtǒng. Tā zǒngshì zhàn zài lí nǐ fēicháng jìn de dìfāng, jìn dào nǐ néng wén dào tā yòng de xǐfà shuǐ. Bú shì gùyì de, tā zhǐ shì méiyǒu nà zhǒng jùlí gǎn. Nǐ tuì hòu yí bù, tā huì wú yìshí de gēnzhe qiánjìn yí bù. Nǐ kào qiáng zhàn, tā huì zhuǎn guò shēn miàn duì nǐ shuō huà. Méiyǒu rènhé èyì, jiù shì nàge chūchǎng shèzhì de shèjiāo jùlí bǐ yìbān rén duǎn le dàyuē sìshí límǐ. Quán lóu de rén dōu xué huì le yí jiàn shì: kàn dào tā jìn diàntī, jiù jiǎzhuāng wàng le dōngxi huíqù děng xià yí tàng. Méiyǒu rén gēn tā shuō guò zhè jiàn shì. Yěxǔ yǒngyuǎn bú huì yǒu rén shuō.",
    "text_en": "I've noticed something: elevators have a precise system of spatial allocation that everyone follows automatically, though nobody ever wrote it down. The first person stands in the center. When a second enters, they each take a side. The third stands center-back. Like particles distributing evenly in a container. But someone in our building breaks this system. He always stands extremely close to you — close enough to smell his shampoo. It's not deliberate; he simply lacks that sense of distance. You step back, he unconsciously steps forward. You lean against the wall, he turns to face you and starts talking. No malice at all — his factory-default social distance is just about forty centimeters shorter than average. Everyone in the building has learned one thing: when they see him enter the elevator, pretend you forgot something and wait for the next one. Nobody has ever told him about this. Maybe nobody ever will.",
    "questions": [
        {"type": "mc", "q_zh": "电梯里第三个人通常站在哪里？", "q_en": "Where does the third person in an elevator usually stand?",
         "options": [
             {"text": "门口", "pinyin": "ménkǒu", "text_en": "at the door", "correct": False},
             {"text": "中间偏后", "pinyin": "zhōngjiān piān hòu", "text_en": "center-back", "correct": True},
             {"text": "角落里", "pinyin": "jiǎoluò lǐ", "text_en": "in the corner", "correct": False},
             {"text": "左边", "pinyin": "zuǒbiān", "text_en": "on the left", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "那个人的社交距离有什么特点？", "q_en": "What's special about that person's social distance?",
         "options": [
             {"text": "比一般人远", "pinyin": "bǐ yìbān rén yuǎn", "text_en": "farther than average", "correct": False},
             {"text": "比一般人短大约四十厘米", "pinyin": "bǐ yìbān rén duǎn dàyuē sìshí límǐ", "text_en": "about 40cm shorter than average", "correct": True},
             {"text": "跟一般人一样", "pinyin": "gēn yìbān rén yíyàng", "text_en": "same as average", "correct": False},
             {"text": "取决于心情", "pinyin": "qǔjué yú xīnqíng", "text_en": "depends on mood", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "大家怎么应对这个人？", "q_en": "How does everyone deal with this person?",
         "options": [
             {"text": "直接告诉他", "pinyin": "zhíjiē gàosu tā", "text_en": "tell him directly", "correct": False},
             {"text": "假装忘了东西，等下一趟电梯", "pinyin": "jiǎzhuāng wàng le dōngxi, děng xià yí tàng diàntī", "text_en": "pretend to forget something, wait for next elevator", "correct": True},
             {"text": "走楼梯", "pinyin": "zǒu lóutī", "text_en": "take the stairs", "correct": False},
             {"text": "站得更近", "pinyin": "zhàn de gèng jìn", "text_en": "stand even closer", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 2. j5_observe_002 - Was: sound of elevator with 原来 realize
# NEW: FRASIER MOVE - two experts arguing about the trivial
replace_passage("j5_observe_002", {
    "title": "The Tea Temperature Debate",
    "title_zh": "泡茶温度之争",
    "text_zh": "办公室里有两个泡茶爱好者，一个是市场部的老赵，一个是技术部的老孙。他们对水温的看法完全不同。老赵坚持说龙井茶必须用八十度的水泡，因为温度太高会把茶叶烫伤，破坏里面的氨基酸。老孙则认为八十五度才是最佳温度，因为八十度不够充分释放茶叶的香气。他们为了这五度的差距争论了整整一年。双方都能引用各种文章、视频和茶艺大师的讲座来支持自己的观点。有一次他们甚至带了温度计来做实验——结果因为温度计不够精确而吵了起来。最讽刺的是，公司茶水间的饮水机只有两个选项：常温和开水，根本没有八十度也没有八十五度。他们每天用的其实都是同一个温度。但是这件事，两个人似乎都心照不宣地选择了不提。",
    "text_pinyin": "Bàngōngshì lǐ yǒu liǎng gè pào chá àihào zhě, yí gè shì shìchǎngbù de Lǎo Zhào, yí gè shì jìshùbù de Lǎo Sūn. Tāmen duì shuǐ wēn de kànfǎ wánquán bù tóng. Lǎo Zhào jiānchí shuō Lóngjǐng chá bìxū yòng bāshí dù de shuǐ pào, yīnwèi wēndù tài gāo huì bǎ cháyè tàng shāng, pòhuài lǐmiàn de ānjīsuān. Lǎo Sūn zé rènwéi bāshíwǔ dù cái shì zuì jiā wēndù, yīnwèi bāshí dù bú gòu chōngfèn shìfàng cháyè de xiāngqì. Tāmen wèile zhè wǔ dù de chājù zhēnglùn le zhěngzhěng yì nián. Shuāngfāng dōu néng yǐnyòng gè zhǒng wénzhāng, shìpín hé cháyì dàshī de jiǎngzuò lái zhīchí zìjǐ de guāndiǎn. Yǒu yí cì tāmen shènzhì dài le wēndùjì lái zuò shíyàn——jiéguǒ yīnwèi wēndùjì bú gòu jīngquè ér chǎo le qǐlái. Zuì fěngcì de shì, gōngsī chá shuǐ jiān de yǐnshuǐ jī zhǐ yǒu liǎng gè xuǎnxiàng: chángwēn hé kāishuǐ, gēnběn méiyǒu bāshí dù yě méiyǒu bāshíwǔ dù. Tāmen měi tiān yòng de qíshí dōu shì tóng yí gè wēndù. Dànshì zhè jiàn shì, liǎng gè rén sìhū dōu xīnzhào bù xuān de xuǎnzé le bù tí.",
    "text_en": "Two tea enthusiasts work in our office: Lao Zhao from marketing and Lao Sun from engineering. They have completely opposite views on water temperature. Lao Zhao insists Longjing tea must be brewed at 80 degrees, because higher temperatures scald the leaves and destroy the amino acids. Lao Sun believes 85 degrees is optimal, because 80 doesn't release the tea's aroma fully. They've been arguing over these five degrees for an entire year. Both can cite articles, videos, and tea master lectures to support their positions. Once they even brought a thermometer to do an experiment — then argued because the thermometer wasn't precise enough. The most ironic part: the office water dispenser only has two settings — room temperature and boiling. There is no 80 degrees. There is no 85 degrees. They've been using the exact same temperature every day. But this fact, both of them seem to have tacitly agreed never to mention.",
    "questions": [
        {"type": "mc", "q_zh": "老赵觉得泡龙井茶应该用多少度的水？", "q_en": "What temperature does Lao Zhao think Longjing should be brewed at?",
         "options": [
             {"text": "七十五度", "pinyin": "qīshíwǔ dù", "text_en": "75 degrees", "correct": False},
             {"text": "八十度", "pinyin": "bāshí dù", "text_en": "80 degrees", "correct": True},
             {"text": "八十五度", "pinyin": "bāshíwǔ dù", "text_en": "85 degrees", "correct": False},
             {"text": "九十度", "pinyin": "jiǔshí dù", "text_en": "90 degrees", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "饮水机有哪些选项？", "q_en": "What settings does the water dispenser have?",
         "options": [
             {"text": "八十度和八十五度", "pinyin": "bāshí dù hé bāshíwǔ dù", "text_en": "80 and 85 degrees", "correct": False},
             {"text": "常温和开水", "pinyin": "chángwēn hé kāishuǐ", "text_en": "room temperature and boiling", "correct": True},
             {"text": "三种温度", "pinyin": "sān zhǒng wēndù", "text_en": "three temperatures", "correct": False},
             {"text": "可以调节温度", "pinyin": "kěyǐ tiáojié wēndù", "text_en": "adjustable temperature", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "这件事最讽刺的地方是什么？", "q_en": "What's the most ironic part?",
         "options": [
             {"text": "茶不好喝", "pinyin": "chá bù hǎo hē", "text_en": "the tea doesn't taste good", "correct": False},
             {"text": "他们用的是同一个温度", "pinyin": "tāmen yòng de shì tóng yí gè wēndù", "text_en": "they use the same temperature", "correct": True},
             {"text": "老板不让他们喝茶", "pinyin": "lǎobǎn bú ràng tāmen hē chá", "text_en": "boss won't let them drink tea", "correct": False},
             {"text": "温度计是准确的", "pinyin": "wēndùjì shì zhǔnquè de", "text_en": "the thermometer was accurate", "correct": False}
         ], "difficulty": 0.4}
    ]
})

# 3. j5_observe_003 - Was: closing ritual with 才明白 ending
# NEW: SONDHEIM MOVE - emotional contradiction at retirement party
replace_passage("j5_observe_003", {
    "title": "The Retirement Speech",
    "title_zh": "退休演讲",
    "text_zh": "老王退休那天，公司开了一个小型欢送会。HR准备了蛋糕，同事们凑了一笔钱买了一块手表。老王上台说了几句话。他说：「终于可以每天睡到自然醒了。」大家笑了。他说：「不用再开那些开不完的会了。」大家又笑了。他说：「不用再看经理的脸色了。」经理也笑了，虽然笑得有点勉强。然后老王停了一下，看着自己用了十八年的那张桌子。他清了清嗓子，说：「不过我会想念那台总是卡纸的打印机。」没有人笑。因为每个人都看出来了——他想说的不是打印机。他在桌子上放了三十年的全家福照片还在那里，他没有拿走。过了一会儿他说：「我明天再来拿吧。」HR小声说：「好的，不急。」但是大家都知道，他已经没有明天再来的理由了。",
    "text_pinyin": "Lǎo Wáng tuìxiū nà tiān, gōngsī kāi le yí gè xiǎoxíng huānsòng huì. HR zhǔnbèi le dàngāo, tóngshìmen còu le yì bǐ qián mǎi le yí kuài shǒubiǎo. Lǎo Wáng shàng tái shuō le jǐ jù huà. Tā shuō:「Zhōngyú kěyǐ měi tiān shuì dào zìrán xǐng le.」Dàjiā xiào le. Tā shuō:「Búyòng zài kāi nàxiē kāi bù wán de huì le.」Dàjiā yòu xiào le. Tā shuō:「Búyòng zài kàn jīnglǐ de liǎnsè le.」Jīnglǐ yě xiào le, suīrán xiào de yǒudiǎn miǎnqiǎng. Ránhòu Lǎo Wáng tíng le yíxià, kànzhe zìjǐ yòng le shíbā nián de nà zhāng zhuōzi. Tā qīng le qīng sǎngzi, shuō:「Búguò wǒ huì xiǎngniàn nà tái zǒngshì kǎ zhǐ de dǎyìnjī.」Méiyǒu rén xiào. Yīnwèi měi gè rén dōu kàn chūlái le——tā xiǎng shuō de bú shì dǎyìnjī. Tā zài zhuōzi shàng fàng le sānshí nián de quánjiā fú zhàopiàn hái zài nàlǐ, tā méiyǒu ná zǒu. Guò le yíhuìr tā shuō:「Wǒ míngtiān zài lái ná ba.」HR xiǎo shēng shuō:「Hǎo de, bù jí.」Dànshì dàjiā dōu zhīdào, tā yǐjīng méiyǒu míngtiān zài lái de lǐyóu le.",
    "text_en": "On Lao Wang's retirement day, the company held a small farewell party. HR prepared a cake, and colleagues pooled money for a watch. Lao Wang got up and said a few words. He said: 'Finally I can sleep in every day.' Everyone laughed. 'No more endless meetings.' More laughter. 'No more reading the manager's mood.' Even the manager laughed, though it looked a bit forced. Then Lao Wang paused and looked at the desk he'd used for eighteen years. He cleared his throat: 'But I'll miss that printer that always jams.' Nobody laughed. Because everyone could see — he wasn't talking about the printer. The family photo he'd kept on his desk for thirty years was still there. He hadn't taken it. After a moment he said: 'I'll come pick it up tomorrow.' HR said softly: 'Sure, no rush.' But everyone knew he no longer had a reason to come back tomorrow.",
    "questions": [
        {"type": "mc", "q_zh": "同事们送了老王什么？", "q_en": "What did the colleagues give Lao Wang?",
         "options": [
             {"text": "一束花", "pinyin": "yí shù huā", "text_en": "a bouquet", "correct": False},
             {"text": "一块手表", "pinyin": "yí kuài shǒubiǎo", "text_en": "a watch", "correct": True},
             {"text": "一本书", "pinyin": "yì běn shū", "text_en": "a book", "correct": False},
             {"text": "一个红包", "pinyin": "yí gè hóngbāo", "text_en": "a red envelope", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "老王说会想念什么？", "q_en": "What did Lao Wang say he'd miss?",
         "options": [
             {"text": "同事们", "pinyin": "tóngshìmen", "text_en": "colleagues", "correct": False},
             {"text": "总是卡纸的打印机", "pinyin": "zǒngshì kǎ zhǐ de dǎyìnjī", "text_en": "the printer that always jams", "correct": True},
             {"text": "经理", "pinyin": "jīnglǐ", "text_en": "the manager", "correct": False},
             {"text": "会议", "pinyin": "huìyì", "text_en": "meetings", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "老王为什么没有拿走全家福照片？", "q_en": "Why didn't Lao Wang take the family photo?",
         "options": [
             {"text": "他忘了", "pinyin": "tā wàng le", "text_en": "he forgot", "correct": False},
             {"text": "照片太旧了", "pinyin": "zhàopiàn tài jiù le", "text_en": "the photo was too old", "correct": False},
             {"text": "他可能不想接受离开的事实", "pinyin": "tā kěnéng bù xiǎng jiēshòu líkāi de shìshí", "text_en": "he might not want to accept the reality of leaving", "correct": True},
             {"text": "他不喜欢那张照片", "pinyin": "tā bù xǐhuan nà zhāng zhàopiàn", "text_en": "he doesn't like the photo", "correct": False}
         ], "difficulty": 0.5}
    ]
})

# 4. j5_observe_005 - Was: smell of autumn with realize pattern
# NEW: HODGMAN/SEDARIS MOVE - obsessive taxonomy of trivial thing
replace_passage("j5_observe_005", {
    "title": "The Nod Taxonomy",
    "title_zh": "点头学",
    "text_zh": "在电梯里遇到同一栋楼的人，你们会互相点头。我花了一些时间研究这些点头，发现至少有七种不同的类型。第一种是「认识但不熟」的点头——幅度很小，嘴角微微上扬，目光接触不超过零点五秒。第二种是「上次见面你帮了我一个忙」的点头——幅度稍大，配合一个完整的微笑。第三种是「我知道你昨天装修噪音很大但我选择不提」的点头——嘴唇紧闭，点头速度偏快，目光迅速转向电梯按钮。第四种是「你的快递又被我误收了」的点头——点头的同时一只手已经在掏钥匙准备开门。最微妙的是第七种：完全不点头。这意味着某种关系已经彻底恶化，连一个最低限度的社交礼仪都不愿意给。我住在这栋楼五年了，目前和大部分人保持在第一种到第二种之间。只有一个邻居和我到了第七种。我们上一次为谁堵了谁的车位争论以后，就再也没有在电梯里交换过目光。",
    "text_pinyin": "Zài diàntī lǐ yù dào tóng yí dòng lóu de rén, nǐmen huì hùxiāng diǎn tóu. Wǒ huā le yìxiē shíjiān yánjiū zhèxiē diǎn tóu, fāxiàn zhìshǎo yǒu qī zhǒng bù tóng de lèixíng. Dì yī zhǒng shì「rènshi dàn bù shú」de diǎn tóu——fúdù hěn xiǎo, zuǐjiǎo wēiwēi shàng yáng, mùguāng jiēchù bù chāoguò líng diǎn wǔ miǎo. Dì èr zhǒng shì「shàng cì jiàn miàn nǐ bāng le wǒ yí gè máng」de diǎn tóu——fúdù shāo dà, pèihé yí gè wánzhěng de wēixiào. Dì sān zhǒng shì「wǒ zhīdào nǐ zuótiān zhuāngxiū zàoyīn hěn dà dàn wǒ xuǎnzé bù tí」de diǎn tóu——zuǐchún jǐn bì, diǎn tóu sùdù piān kuài, mùguāng xùnsù zhuǎn xiàng diàntī ànniǔ. Dì sì zhǒng shì「nǐ de kuàidì yòu bèi wǒ wù shōu le」de diǎn tóu——diǎn tóu de tóngshí yì zhī shǒu yǐjīng zài tāo yàoshi zhǔnbèi kāi mén. Zuì wēimiào de shì dì qī zhǒng: wánquán bù diǎn tóu. Zhè yìwèizhe mǒu zhǒng guānxi yǐjīng chèdǐ èhuà, lián yí gè zuì dī xiàndù de shèjiāo lǐyí dōu bú yuànyì gěi. Wǒ zhù zài zhè dòng lóu wǔ nián le, mùqián hé dà bùfen rén bǎochí zài dì yī zhǒng dào dì èr zhǒng zhījiān. Zhǐ yǒu yí gè línjū hé wǒ dào le dì qī zhǒng. Wǒmen shàng yí cì wèi shéi dǔ le shéi de chē wèi zhēnglùn yǐhòu, jiù zài yě méiyǒu zài diàntī lǐ jiāohuàn guò mùguāng.",
    "text_en": "When you meet someone from the same building in the elevator, you nod at each other. I've spent some time studying these nods and identified at least seven types. Type one: the 'I know you but we're not close' nod — small amplitude, slight upturn of mouth corners, eye contact under 0.5 seconds. Type two: the 'you helped me last time' nod — slightly bigger, paired with a full smile. Type three: the 'I know your renovation yesterday was noisy but I'm choosing not to mention it' nod — lips pressed tight, nod speed slightly fast, eyes darting quickly to the elevator buttons. Type four: the 'I accidentally took your package again' nod — nodding while one hand is already digging for keys. The most subtle is type seven: the complete non-nod. This means a relationship has deteriorated to the point where even the minimum social courtesy is withheld. I've lived in this building five years and maintain type one to two with most people. Only one neighbor and I have reached type seven. Since our last argument about who blocked whose parking spot, we've never exchanged a glance in the elevator again.",
    "questions": [
        {"type": "mc", "q_zh": "作者发现了几种点头方式？", "q_en": "How many types of nods did the author identify?",
         "options": [
             {"text": "三种", "pinyin": "sān zhǒng", "text_en": "three", "correct": False},
             {"text": "五种", "pinyin": "wǔ zhǒng", "text_en": "five", "correct": False},
             {"text": "至少七种", "pinyin": "zhìshǎo qī zhǒng", "text_en": "at least seven", "correct": True},
             {"text": "十种", "pinyin": "shí zhǒng", "text_en": "ten", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "第七种「点头」是什么？", "q_en": "What is the type seven 'nod'?",
         "options": [
             {"text": "最热情的点头", "pinyin": "zuì rèqíng de diǎn tóu", "text_en": "the most enthusiastic nod", "correct": False},
             {"text": "完全不点头", "pinyin": "wánquán bù diǎn tóu", "text_en": "no nod at all", "correct": True},
             {"text": "低头看手机", "pinyin": "dī tóu kàn shǒujī", "text_en": "looking down at phone", "correct": False},
             {"text": "微笑点头", "pinyin": "wēixiào diǎn tóu", "text_en": "smiling nod", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "作者为什么跟一个邻居到了第七种？", "q_en": "Why did the author reach type seven with one neighbor?",
         "options": [
             {"text": "邻居太吵了", "pinyin": "línjū tài chǎo le", "text_en": "neighbor was too noisy", "correct": False},
             {"text": "为车位争论过", "pinyin": "wèi chē wèi zhēnglùn guò", "text_en": "argued over a parking spot", "correct": True},
             {"text": "快递被拿错了", "pinyin": "kuàidì bèi ná cuò le", "text_en": "packages were mixed up", "correct": False},
             {"text": "因为装修", "pinyin": "yīnwèi zhuāngxiū", "text_en": "because of renovation", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 5. j5_food_001 - Was: grandmother's dumplings with 突然明白了 ending
# NEW: BOURDAIN RAW FOOD LOVE - imperfect street food glory
replace_passage("j5_food_001", {
    "title": "The Worst-Looking Best Noodles",
    "title_zh": "最难看的最好吃的面",
    "text_zh": "城西有一家面馆，环境极其糟糕。桌面是油腻的，椅子是塑料的，墙上的菜单已经发黄了至少五年。灯光暗得让人怀疑是不是故意省电。第一次去的人通常会站在门口犹豫三秒钟，然后在看到里面坐满了人之后决定试一试。老板是一个从来不笑的中年女人。你点完菜她不会重复确认，也不会说「请稍等」——她只是转过身开始做。面上来的时候也不说话，直接往你面前一放。碗是那种旧旧的白瓷碗，边缘有一个小缺口。但是你吃第一口的时候就知道了：汤底是骨头熬了至少六个小时的，面条是手擀的——粗细不均匀，有些地方厚一些有些地方薄一些——但正是这种不完美让每一口都有不同的口感。辣椒油是她自己炸的，花椒的麻和辣椒的辣混在一起，在嘴里待了很久才散去。你会吃到最后连汤都喝完，然后放下碗的时候发出一声满足的叹息。这是那种让你在下雨天专门走二十分钟去吃的面。",
    "text_pinyin": "Chéng xī yǒu yì jiā miànguǎn, huánjìng jíqí zāogāo. Zhuōmiàn shì yóunì de, yǐzi shì sùliào de, qiáng shàng de càidān yǐjīng fāhuáng le zhìshǎo wǔ nián. Dēngguāng àn de ràng rén huáiyí shì bu shì gùyì shěng diàn. Dì yī cì qù de rén tōngcháng huì zhàn zài ménkǒu yóuyù sān miǎozhōng, ránhòu zài kàn dào lǐmiàn zuò mǎn le rén zhīhòu juédìng shì yí shì. Lǎobǎn shì yí gè cónglái bú xiào de zhōngnián nǚrén. Nǐ diǎn wán cài tā bú huì chóngfù quèrèn, yě bú huì shuō「qǐng shāo děng」——tā zhǐ shì zhuǎn guò shēn kāishǐ zuò. Miàn shàng lái de shíhou yě bù shuō huà, zhíjiē wǎng nǐ miànqián yí fàng. Wǎn shì nà zhǒng jiù jiù de bái cí wǎn, biānyuán yǒu yí gè xiǎo quēkǒu. Dànshì nǐ chī dì yī kǒu de shíhou jiù zhīdào le: tāngtǐ shì gǔtou áo le zhìshǎo liù gè xiǎoshí de, miàntiáo shì shǒu gǎn de——cūxì bù jūnyún, yǒuxiē dìfāng hòu yìxiē yǒuxiē dìfāng báo yìxiē——dàn zhèng shì zhè zhǒng bù wánměi ràng měi yì kǒu dōu yǒu bù tóng de kǒugǎn. Làjiāo yóu shì tā zìjǐ zhà de, huājiāo de má hé làjiāo de là hùn zài yìqǐ, zài zuǐ lǐ dāi le hěn jiǔ cái sàn qù. Nǐ huì chī dào zuìhòu lián tāng dōu hē wán, ránhòu fàng xià wǎn de shíhou fāchū yì shēng mǎnzú de tànxī. Zhè shì nà zhǒng ràng nǐ zài xià yǔ tiān zhuānmén zǒu èrshí fēnzhōng qù chī de miàn.",
    "text_en": "On the west side of town there's a noodle shop with terrible decor. Greasy tables, plastic chairs, a menu on the wall that's been yellowing for at least five years. The lighting is so dim you suspect they're saving on electricity. First-timers usually hesitate in the doorway for three seconds, then decide to try it when they see the place is packed. The owner is a middle-aged woman who never smiles. When you order, she doesn't repeat it back or say 'please wait' — she just turns around and starts cooking. When the noodles come, she says nothing, just sets the bowl in front of you. Old white porcelain, a small chip on the rim. But the first bite tells you everything: the broth is bones simmered at least six hours. The noodles are hand-rolled — uneven in thickness, some spots thicker, some thinner — but that imperfection gives every bite a different texture. The chili oil is fried herself, the numbing of the Sichuan peppercorn and the heat of the chili tangled together, lingering in your mouth long after. You eat until you've drunk every drop of broth, then set the bowl down with a satisfied sigh. This is the kind of noodles you walk twenty minutes in the rain specifically to eat.",
    "questions": [
        {"type": "mc", "q_zh": "面馆的环境怎么样？", "q_en": "What's the noodle shop's environment like?",
         "options": [
             {"text": "很干净", "pinyin": "hěn gānjìng", "text_en": "very clean", "correct": False},
             {"text": "极其糟糕", "pinyin": "jíqí zāogāo", "text_en": "extremely bad", "correct": True},
             {"text": "一般般", "pinyin": "yìbānbān", "text_en": "average", "correct": False},
             {"text": "很漂亮", "pinyin": "hěn piàoliang", "text_en": "very pretty", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "面条为什么粗细不均匀？", "q_en": "Why are the noodles uneven in thickness?",
         "options": [
             {"text": "机器坏了", "pinyin": "jīqì huài le", "text_en": "machine was broken", "correct": False},
             {"text": "是手擀的", "pinyin": "shì shǒu gǎn de", "text_en": "hand-rolled", "correct": True},
             {"text": "老板不认真", "pinyin": "lǎobǎn bú rènzhēn", "text_en": "owner wasn't careful", "correct": False},
             {"text": "面粉不好", "pinyin": "miànfěn bù hǎo", "text_en": "bad flour", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "辣椒油是怎么做的？", "q_en": "How is the chili oil made?",
         "options": [
             {"text": "买的", "pinyin": "mǎi de", "text_en": "store-bought", "correct": False},
             {"text": "老板自己炸的", "pinyin": "lǎobǎn zìjǐ zhà de", "text_en": "fried by the owner herself", "correct": True},
             {"text": "别人送的", "pinyin": "biéren sòng de", "text_en": "a gift from someone", "correct": False},
             {"text": "机器做的", "pinyin": "jīqì zuò de", "text_en": "machine-made", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 6. j5_mystery_001 - Was: light in apartment 1402 with realize
# NEW: EZRA KLEIN MOVE - patient inquiry about why someone quits
replace_passage("j5_mystery_001", {
    "title": "Why She Quit",
    "title_zh": "她为什么辞职",
    "text_zh": "小杨是我们团队里最优秀的人之一，上个月她辞职了。大家都很惊讶。HR说她的离职面谈很正常——「个人发展」「新的机会」，都是标准答案。但我不太相信。午饭的时候我问了几个同事。小李说：「可能是工资太低了。」我说：「她去年刚涨过。」小李想了想：「那可能是跟经理关系不好？」我说：「她跟经理关系一直不错。」设计部的小陈说了一个细节：三个月前有一次会议，小杨提了一个方案，讲了二十分钟，经理听完说「回去再想想」。两周以后经理自己提了一个几乎一样的方案。小杨什么都没说。我又问了产品部的老刘。老刘说了另一个细节：小杨的名字在上一次晋升名单里被划掉了，换成了一个跟领导关系更近的人。小杨也什么都没说。也许让一个人离开的，不是某一件大事，而是一连串她选择沉默的小时刻。沉默到最后就变成了决定。",
    "text_pinyin": "Xiǎo Yáng shì wǒmen tuánduì lǐ zuì yōuxiù de rén zhī yī, shàng gè yuè tā cízhí le. Dàjiā dōu hěn jīngyà. HR shuō tā de lízhí miàntán hěn zhèngcháng——「gèrén fāzhǎn」「xīn de jīhuì」, dōu shì biāozhǔn dá'àn. Dàn wǒ bú tài xiāngxìn. Wǔfàn de shíhou wǒ wèn le jǐ gè tóngshì. Xiǎo Lǐ shuō:「Kěnéng shì gōngzī tài dī le.」Wǒ shuō:「Tā qùnián gāng zhǎng guò.」Xiǎo Lǐ xiǎng le xiǎng:「Nà kěnéng shì gēn jīnglǐ guānxi bù hǎo?」Wǒ shuō:「Tā gēn jīnglǐ guānxi yìzhí búcuò.」Shèjìbù de Xiǎo Chén shuō le yí gè xìjié: sān gè yuè qián yǒu yí cì huìyì, Xiǎo Yáng tí le yí gè fāng'àn, jiǎng le èrshí fēnzhōng, jīnglǐ tīng wán shuō「huíqù zài xiǎng xiǎng」. Liǎng zhōu yǐhòu jīnglǐ zìjǐ tí le yí gè jīhū yíyàng de fāng'àn. Xiǎo Yáng shénme dōu méi shuō. Wǒ yòu wèn le chǎnpǐnbù de Lǎo Liú. Lǎo Liú shuō le lìng yí gè xìjié: Xiǎo Yáng de míngzi zài shàng yí cì jìnshēng míngdān lǐ bèi huá diào le, huàn chéng le yí gè gēn lǐngdǎo guānxi gèng jìn de rén. Xiǎo Yáng yě shénme dōu méi shuō. Yěxǔ ràng yí gè rén líkāi de, bú shì mǒu yí jiàn dà shì, ér shì yì lián chuàn tā xuǎnzé chénmò de xiǎo shíkè. Chénmò dào zuìhòu jiù biàn chéng le juédìng.",
    "text_en": "Xiao Yang was one of the best people on our team. Last month she resigned. Everyone was shocked. HR said her exit interview was standard — 'personal development,' 'new opportunities,' all the usual answers. But I wasn't convinced. At lunch I asked around. Xiao Li said: 'Maybe the salary was too low.' I said: 'She just got a raise last year.' Xiao Li thought: 'Then maybe she doesn't get along with the manager?' I said: 'They've always gotten along fine.' Xiao Chen from design mentioned a detail: three months ago at a meeting, Xiao Yang presented a proposal, spoke for twenty minutes. The manager listened and said 'go back and think it over.' Two weeks later the manager proposed something nearly identical. Xiao Yang said nothing. I asked Lao Liu from product. He mentioned another detail: Xiao Yang's name had been crossed off the last promotion list, replaced by someone closer to leadership. Xiao Yang said nothing then too. Maybe what makes a person leave isn't one big thing, but a series of small moments where she chose silence. Enough silence eventually becomes a decision.",
    "questions": [
        {"type": "mc", "q_zh": "小杨在离职面谈中怎么说的？", "q_en": "What did Xiao Yang say in her exit interview?",
         "options": [
             {"text": "她说了真正的原因", "pinyin": "tā shuō le zhēnzhèng de yuányīn", "text_en": "she gave the real reason", "correct": False},
             {"text": "标准答案：个人发展、新的机会", "pinyin": "biāozhǔn dá'àn: gèrén fāzhǎn, xīn de jīhuì", "text_en": "standard answers: personal development, new opportunities", "correct": True},
             {"text": "她哭了", "pinyin": "tā kū le", "text_en": "she cried", "correct": False},
             {"text": "她批评了经理", "pinyin": "tā pīpíng le jīnglǐ", "text_en": "she criticized the manager", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "经理对小杨的方案做了什么？", "q_en": "What did the manager do with Xiao Yang's proposal?",
         "options": [
             {"text": "同意了", "pinyin": "tóngyì le", "text_en": "agreed to it", "correct": False},
             {"text": "直接拒绝了", "pinyin": "zhíjiē jùjué le", "text_en": "rejected it directly", "correct": False},
             {"text": "说回去再想想，后来自己提了几乎一样的", "pinyin": "shuō huíqù zài xiǎng xiǎng, hòulái zìjǐ tí le jīhū yíyàng de", "text_en": "said think it over, then proposed nearly the same thing himself", "correct": True},
             {"text": "让别人来做", "pinyin": "ràng biéren lái zuò", "text_en": "had someone else do it", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "作者认为小杨离开的真正原因是什么？", "q_en": "What does the author think is the real reason Xiao Yang left?",
         "options": [
             {"text": "工资太低", "pinyin": "gōngzī tài dī", "text_en": "salary too low", "correct": False},
             {"text": "跟经理吵架了", "pinyin": "gēn jīnglǐ chǎo jià le", "text_en": "argued with manager", "correct": False},
             {"text": "一连串她选择沉默的小时刻", "pinyin": "yì lián chuàn tā xuǎnzé chénmò de xiǎo shíkè", "text_en": "a series of small moments where she chose silence", "correct": True},
             {"text": "找到了更好的工作", "pinyin": "zhǎo dào le gèng hǎo de gōngzuò", "text_en": "found a better job", "correct": False}
         ], "difficulty": 0.5}
    ]
})

# 7. j5_observe_006 - Was: way people hold umbrellas with 也许 realize
# NEW: CROSS-PURPOSE comedy - the gift exchange disaster
replace_passage("j5_observe_006", {
    "title": "The Gift Exchange",
    "title_zh": "交换礼物",
    "text_zh": "公司年终聚会有一个交换礼物的环节，规则是每人准备一份一百块以内的礼物，随机交换。我花了很多心思选了一本精装版的村上春树小说，因为我觉得这是一份有品位的礼物。结果我抽到的是一个巨大的毛绒玩具——一只粉色的猪。我三十五岁了，我不知道怎么把一只粉色的猪带回家。但是真正精彩的是后面发生的事。买那本村上春树的礼物的那个人抽到了一包五双的袜子。买袜子的人抽到了一瓶高级橄榄油。买橄榄油的人抽到了我那本村上春树。但是她是那种从来不看书的人，她拿到以后翻了两页就放下了，说：「这个可以换吗？我比较想要那只猪。」我看着那只粉色的猪，犹豫了整整五秒钟。然后我发现自己说了一句完全没想到的话：「不换。」也许我已经开始喜欢它了。",
    "text_pinyin": "Gōngsī niánzhōng jùhuì yǒu yí gè jiāohuàn lǐwù de huánjié, guīzé shì měi rén zhǔnbèi yí fèn yì bǎi kuài yǐnèi de lǐwù, suíjī jiāohuàn. Wǒ huā le hěn duō xīnsi xuǎn le yì běn jīngzhuāng bǎn de Cūnshàng Chūnshù xiǎoshuō, yīnwèi wǒ juéde zhè shì yí fèn yǒu pǐnwèi de lǐwù. Jiéguǒ wǒ chōu dào de shì yí gè jùdà de máoróng wánjù——yì zhī fěnsè de zhū. Wǒ sānshíwǔ suì le, wǒ bù zhīdào zěnme bǎ yì zhī fěnsè de zhū dài huí jiā. Dànshì zhēnzhèng jīngcǎi de shì hòumiàn fāshēng de shì. Mǎi nà běn Cūnshàng Chūnshù de lǐwù de nàge rén chōu dào le yì bāo wǔ shuāng de wàzi. Mǎi wàzi de rén chōu dào le yì píng gāojí gǎnlǎn yóu. Mǎi gǎnlǎn yóu de rén chōu dào le wǒ nà běn Cūnshàng Chūnshù. Dànshì tā shì nà zhǒng cónglái bú kàn shū de rén, tā ná dào yǐhòu fān le liǎng yè jiù fàng xià le, shuō:「Zhège kěyǐ huàn ma? Wǒ bǐjiào xiǎng yào nà zhī zhū.」Wǒ kànzhe nà zhī fěnsè de zhū, yóuyù le zhěngzhěng wǔ miǎozhōng. Ránhòu wǒ fāxiàn zìjǐ shuō le yí jù wánquán méi xiǎng dào de huà:「Bú huàn.」Yěxǔ wǒ yǐjīng kāishǐ xǐhuan tā le.",
    "text_en": "Our company's year-end party had a gift exchange — everyone prepares a gift under 100 yuan, then they're randomly swapped. I put a lot of thought into choosing a hardcover Murakami novel, because I thought it was a tasteful gift. What I drew: a giant stuffed animal — a pink pig. I'm thirty-five. I had no idea how to bring a pink pig home. But the real show was what happened next. The person who bought my Murakami drew a pack of five pairs of socks. The person who bought the socks drew a bottle of premium olive oil. The person who bought the olive oil drew my Murakami. But she's the type who never reads. She flipped two pages, put it down, and said: 'Can I trade? I'd rather have that pig.' I looked at the pink pig. I hesitated for a full five seconds. Then I heard myself say something I didn't expect: 'No trade.' Maybe I was already starting to like it.",
    "questions": [
        {"type": "mc", "q_zh": "礼物的价格限制是多少？", "q_en": "What was the gift price limit?",
         "options": [
             {"text": "五十块", "pinyin": "wǔshí kuài", "text_en": "50 yuan", "correct": False},
             {"text": "一百块", "pinyin": "yì bǎi kuài", "text_en": "100 yuan", "correct": True},
             {"text": "两百块", "pinyin": "liǎng bǎi kuài", "text_en": "200 yuan", "correct": False},
             {"text": "没有限制", "pinyin": "méiyǒu xiànzhì", "text_en": "no limit", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "「我」抽到了什么礼物？", "q_en": "What gift did 'I' draw?",
         "options": [
             {"text": "一本书", "pinyin": "yì běn shū", "text_en": "a book", "correct": False},
             {"text": "一只粉色的毛绒猪", "pinyin": "yì zhī fěnsè de máoróng zhū", "text_en": "a pink stuffed pig", "correct": True},
             {"text": "袜子", "pinyin": "wàzi", "text_en": "socks", "correct": False},
             {"text": "橄榄油", "pinyin": "gǎnlǎn yóu", "text_en": "olive oil", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "最后「我」愿不愿意换？", "q_en": "Did 'I' agree to trade in the end?",
         "options": [
             {"text": "换了", "pinyin": "huàn le", "text_en": "traded", "correct": False},
             {"text": "没换", "pinyin": "méi huàn", "text_en": "didn't trade", "correct": True},
             {"text": "换了一半", "pinyin": "huàn le yíbàn", "text_en": "half-traded", "correct": False},
             {"text": "还在犹豫", "pinyin": "hái zài yóuyù", "text_en": "still hesitating", "correct": False}
         ], "difficulty": 0.2}
    ]
})

# 8. j5_system_093 - Was: company meeting with realize ending
# NEW: ARRESTED DEVELOPMENT - the email that nobody reads
replace_passage("j5_system_093", {
    "title": "The Announcement Nobody Read",
    "title_zh": "没有人看的通知",
    "text_zh": "行政部的小周每个月都发一封全员通知，内容包括新的办公室规定、活动安排和注意事项。她写得很认真，排版也很好看，每次都附上重点标注和彩色图表。但是她已经怀疑了很久：没有人在读这些通知。为了验证这个猜测，上个月她在通知的第三页、第四段、第七行，插入了这样一句话：「如果你看到了这句话，请到行政部找小周领取一杯免费咖啡。」一个月过去了，一百八十个人里，来领咖啡的一共有三个人。其中一个是她自己——她在校对的时候看到的。另一个是实习生——他太害怕做错事所以把每一封邮件都从头到尾读完。第三个是清洁阿姨——她说她用通知来练习认字。小周把这个结果写进了下个月的通知里。当然，也没有人看到。",
    "text_pinyin": "Xíngzhèngbù de Xiǎo Zhōu měi gè yuè dōu fā yì fēng quányuán tōngzhī, nèiróng bāokuò xīn de bàngōngshì guīdìng, huódòng ānpái hé zhùyì shìxiàng. Tā xiě de hěn rènzhēn, páibǎn yě hěn hǎokàn, měi cì dōu fùshàng zhòngdiǎn biāozhù hé cǎisè túbiǎo. Dànshì tā yǐjīng huáiyí le hěn jiǔ: méiyǒu rén zài dú zhèxiē tōngzhī. Wèile yànzhèng zhège cāicè, shàng gè yuè tā zài tōngzhī de dì sān yè, dì sì duàn, dì qī háng, chārù le zhèyàng yí jù huà:「Rúguǒ nǐ kàn dào le zhè jù huà, qǐng dào xíngzhèngbù zhǎo Xiǎo Zhōu lǐngqǔ yì bēi miǎnfèi kāfēi.」Yí gè yuè guòqù le, yì bǎi bāshí gè rén lǐ, lái lǐng kāfēi de yígòng yǒu sān gè rén. Qízhōng yí gè shì tā zìjǐ——tā zài jiàoduì de shíhou kàn dào de. Lìng yí gè shì shíxí shēng——tā tài hàipà zuò cuò shì suǒyǐ bǎ měi yì fēng yóujiàn dōu cóng tóu dào wěi dú wán. Dì sān gè shì qīngjié āyí——tā shuō tā yòng tōngzhī lái liànxí rèn zì. Xiǎo Zhōu bǎ zhège jiéguǒ xiě jìn le xià gè yuè de tōngzhī lǐ. Dāngrán, yě méiyǒu rén kàn dào.",
    "text_en": "Xiao Zhou from admin sends a company-wide notice every month — new office rules, event schedules, reminders. She writes carefully, formats beautifully, always includes highlighted key points and color charts. But she's suspected for a long time: nobody reads these notices. To test her theory, last month she inserted a sentence on page three, paragraph four, line seven: 'If you see this sentence, come to admin and find Xiao Zhou for a free cup of coffee.' One month passed. Out of one hundred eighty people, a total of three came for coffee. One was herself — she spotted it while proofreading. One was the intern — he's so afraid of making mistakes that he reads every email start to finish. The third was the cleaning auntie — she said she uses the notices to practice reading. Xiao Zhou included this result in the next month's notice. Of course, nobody saw that either.",
    "questions": [
        {"type": "mc", "q_zh": "小周在通知里加了什么？", "q_en": "What did Xiao Zhou add to the notice?",
         "options": [
             {"text": "一张图片", "pinyin": "yì zhāng túpiàn", "text_en": "a picture", "correct": False},
             {"text": "免费咖啡的信息", "pinyin": "miǎnfèi kāfēi de xìnxī", "text_en": "free coffee information", "correct": True},
             {"text": "一个笑话", "pinyin": "yí gè xiàohua", "text_en": "a joke", "correct": False},
             {"text": "辞职信", "pinyin": "cízhí xìn", "text_en": "resignation letter", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "一共有几个人来领咖啡？", "q_en": "How many people came for coffee?",
         "options": [
             {"text": "没有人", "pinyin": "méiyǒu rén", "text_en": "nobody", "correct": False},
             {"text": "三个", "pinyin": "sān gè", "text_en": "three", "correct": True},
             {"text": "十个", "pinyin": "shí gè", "text_en": "ten", "correct": False},
             {"text": "一个", "pinyin": "yí gè", "text_en": "one", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "清洁阿姨为什么看通知？", "q_en": "Why does the cleaning auntie read the notices?",
         "options": [
             {"text": "她的工作需要", "pinyin": "tā de gōngzuò xūyào", "text_en": "her job requires it", "correct": False},
             {"text": "练习认字", "pinyin": "liànxí rèn zì", "text_en": "to practice reading characters", "correct": True},
             {"text": "想要咖啡", "pinyin": "xiǎng yào kāfēi", "text_en": "wanted coffee", "correct": False},
             {"text": "小周让她看的", "pinyin": "Xiǎo Zhōu ràng tā kàn de", "text_en": "Xiao Zhou asked her to", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 9. j5_system_094 - Was: parking lot attendant with realize ending
# NEW: NORM VIOLATION - the person who eats other people's labeled food
replace_passage("j5_system_094", {
    "title": "The Fridge Thief",
    "title_zh": "冰箱小偷",
    "text_zh": "办公室冰箱里的食物经常神秘消失。不是那种模糊的「好像少了一点」——是明确的、无可争辩的消失。小张星期一放进去的酸奶，上面用马克笔写着「张」，星期二就不见了。市场部的老李准备了三天的沙拉，只吃了两天，第三天打开冰箱发现连盒子都没了。最过分的一次是有人喝了别人一半的牛奶，然后又放了回去。这意味着小偷不仅贪婪，而且精确——他知道全部喝完会被发现，所以只喝一半。行政部在冰箱上贴了一张纸：「请不要拿别人的食物。」食物继续消失。有人提议装摄像头，但HR说这涉及隐私。最后有个人在自己的午餐盒上贴了一张纸条：「本食物含有我的口水，请随意享用。」从那天起，他的午餐再也没有被动过。但其他人的食物仍然在消失。这个公司的冰箱，是整栋楼里唯一一个让你对人性产生怀疑的地方。",
    "text_pinyin": "Bàngōngshì bīngxiāng lǐ de shíwù jīngcháng shénmì xiāoshī. Bú shì nà zhǒng móhu de「hǎoxiàng shǎo le yìdiǎn」——shì míngquè de, wú kě zhēngyì de xiāoshī. Xiǎo Zhāng xīngqī yī fàng jìnqù de suānnǎi, shàngmiàn yòng mǎkè bǐ xiězhe「Zhāng」, xīngqī èr jiù bújiàn le. Shìchǎngbù de Lǎo Lǐ zhǔnbèi le sān tiān de shālā, zhǐ chī le liǎng tiān, dì sān tiān dǎkāi bīngxiāng fāxiàn lián hézi dōu méi le. Zuì guòfèn de yí cì shì yǒu rén hē le biéren yíbàn de niúnǎi, ránhòu yòu fàng le huíqù. Zhè yìwèizhe xiǎotōu bùjǐn tānlán, érqiě jīngquè——tā zhīdào quánbù hē wán huì bèi fāxiàn, suǒyǐ zhǐ hē yíbàn. Xíngzhèngbù zài bīngxiāng shàng tiē le yì zhāng zhǐ:「Qǐng búyào ná biéren de shíwù.」Shíwù jìxù xiāoshī. Yǒu rén tíyì zhuāng shèxiàngtóu, dàn HR shuō zhè shèjí yǐnsī. Zuìhòu yǒu gè rén zài zìjǐ de wǔcān hé shàng tiē le yì zhāng zhǐtiáo:「Běn shíwù hányǒu wǒ de kǒushuǐ, qǐng suíyì xiǎngyòng.」Cóng nà tiān qǐ, tā de wǔcān zài yě méiyǒu bèi dòng guò. Dàn qítā rén de shíwù réngran zài xiāoshī. Zhège gōngsī de bīngxiāng, shì zhěng dòng lóu lǐ wéiyī yí gè ràng nǐ duì rénxìng chǎnshēng huáiyí de dìfāng.",
    "text_en": "Food in the office fridge keeps mysteriously disappearing. Not the vague 'seems like there's less' kind — clear, indisputable disappearance. Xiao Zhang's yogurt, placed in on Monday with 'Zhang' written on it in marker, was gone by Tuesday. Lao Li from marketing prepared salad for three days, ate it for two, and on day three opened the fridge to find even the container gone. The most outrageous incident: someone drank half of another person's milk, then put it back. This means the thief is not only greedy but precise — they know drinking it all would be noticed, so they take only half. Admin posted a note on the fridge: 'Please don't take others' food.' The food kept disappearing. Someone suggested installing a camera, but HR said it was a privacy issue. Finally, one person stuck a note on their lunch box: 'This food contains my saliva. Enjoy.' From that day on, their lunch was never touched. But everyone else's food continued to vanish. This company's fridge is the only place in the entire building that makes you doubt human nature.",
    "questions": [
        {"type": "mc", "q_zh": "小偷喝牛奶为什么只喝一半？", "q_en": "Why did the thief only drink half the milk?",
         "options": [
             {"text": "不喜欢牛奶", "pinyin": "bù xǐhuan niúnǎi", "text_en": "doesn't like milk", "correct": False},
             {"text": "喝饱了", "pinyin": "hē bǎo le", "text_en": "was full", "correct": False},
             {"text": "全部喝完会被发现", "pinyin": "quánbù hē wán huì bèi fāxiàn", "text_en": "drinking it all would be noticed", "correct": True},
             {"text": "想分享", "pinyin": "xiǎng fēnxiǎng", "text_en": "wanted to share", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "为什么不装摄像头？", "q_en": "Why didn't they install a camera?",
         "options": [
             {"text": "太贵了", "pinyin": "tài guì le", "text_en": "too expensive", "correct": False},
             {"text": "涉及隐私", "pinyin": "shèjí yǐnsī", "text_en": "privacy concerns", "correct": True},
             {"text": "老板不同意", "pinyin": "lǎobǎn bù tóngyì", "text_en": "boss disagreed", "correct": False},
             {"text": "没有地方装", "pinyin": "méiyǒu dìfāng zhuāng", "text_en": "no place to install", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "谁的午餐再也没有被偷过？", "q_en": "Whose lunch was never stolen again?",
         "options": [
             {"text": "小张的", "pinyin": "Xiǎo Zhāng de", "text_en": "Xiao Zhang's", "correct": False},
             {"text": "贴了「含有口水」纸条的人", "pinyin": "tiē le 'hányǒu kǒushuǐ' zhǐtiáo de rén", "text_en": "the person who put the 'contains saliva' note", "correct": True},
             {"text": "老李的", "pinyin": "Lǎo Lǐ de", "text_en": "Lao Li's", "correct": False},
             {"text": "每个人的", "pinyin": "měi gè rén de", "text_en": "everyone's", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 10. j5_urban_010 - Was: last bus home with realize ending
# NEW: ELAINE MAY MOVE - two people at total cross purposes
replace_passage("j5_urban_010", {
    "title": "The Wrong Advice",
    "title_zh": "问错了人",
    "text_zh": "我在超市犹豫了十分钟，不知道选哪种酱油。旁边一个中年男人看起来很有经验的样子——他的购物车里有各种各样的调料和食材，而且他穿着一件围裙，显然是从厨房里直接出来的。我决定向他请教。「请问，做红烧肉的话，用哪种酱油比较好？」他认真地看了看货架上的七种酱油，然后指着一瓶说：「这个。酿造的，颜色深，味道浓，而且钠含量相对低一些。你看配料表，第一个是水，第二个是大豆——这说明大豆含量高。便宜那些的第二个是盐，说明基本上就是咸水加色素。」我很感激，按照他的建议买了一瓶。然后我看到他去了日用品区，开始认真地挑选洗洁精。他的妻子走过来说：「你怎么买酱油买了这么久？」他说：「我没买酱油，你让我买的不是洗洁精吗？」我低头看了看手里的酱油。也许他说的都是对的。也许一个字都不对。但那瓶酱油我已经打开了，红烧肉确实做得不错。",
    "text_pinyin": "Wǒ zài chāoshì yóuyù le shí fēnzhōng, bù zhīdào xuǎn nǎ zhǒng jiàngyóu. Pángbiān yí gè zhōngnián nánrén kàn qǐlái hěn yǒu jīngyàn de yàngzi——tā de gòuwù chē lǐ yǒu gè zhǒng gè yàng de tiáoliào hé shícái, érqiě tā chuānzhe yí jiàn wéiqún, xiǎnrán shì cóng chúfáng lǐ zhíjiē chūlái de. Wǒ juédìng xiàng tā qǐngjiào.「Qǐngwèn, zuò hóngshāo ròu de huà, yòng nǎ zhǒng jiàngyóu bǐjiào hǎo?」Tā rènzhēn de kàn le kàn huòjià shàng de qī zhǒng jiàngyóu, ránhòu zhǐzhe yì píng shuō:「Zhège. Niàngzào de, yánsè shēn, wèidào nóng, érqiě nà hánliàng xiāngduì dī yìxiē. Nǐ kàn pèiliào biǎo, dì yī gè shì shuǐ, dì èr gè shì dàdòu——zhè shuōmíng dàdòu hánliàng gāo. Piányi nàxiē de dì èr gè shì yán, shuōmíng jīběnshàng jiù shì xián shuǐ jiā sèsù.」Wǒ hěn gǎnjī, ànzhào tā de jiànyì mǎi le yì píng. Ránhòu wǒ kàn dào tā qù le rìyòng pǐn qū, kāishǐ rènzhēn de tiāoxuǎn xǐjiéjīng. Tā de qīzi zǒu guòlái shuō:「Nǐ zěnme mǎi jiàngyóu mǎi le zhème jiǔ?」Tā shuō:「Wǒ méi mǎi jiàngyóu, nǐ ràng wǒ mǎi de bú shì xǐjiéjīng ma?」Wǒ dī tóu kàn le kàn shǒu lǐ de jiàngyóu. Yěxǔ tā shuō de dōu shì duì de. Yěxǔ yí gè zì dōu bú duì. Dàn nà píng jiàngyóu wǒ yǐjīng dǎkāi le, hóngshāo ròu quèshí zuò de búcuò.",
    "text_en": "I stood in the supermarket for ten minutes, unsure which soy sauce to pick. A middle-aged man next to me looked experienced — his cart was full of various seasonings and ingredients, and he was wearing an apron, clearly having come straight from the kitchen. I decided to ask him. 'Excuse me, which soy sauce is better for braised pork?' He studied the seven kinds on the shelf carefully, then pointed to one: 'This one. Naturally brewed, deep color, rich flavor, and relatively low sodium. Look at the ingredients — first is water, second is soybeans, meaning high soy content. The cheap ones have salt listed second, meaning it's basically salt water plus coloring.' I was grateful and bought a bottle following his advice. Then I saw him walk to the household supplies aisle and start carefully selecting dish soap. His wife walked over: 'How did buying soy sauce take you so long?' He said: 'I didn't buy soy sauce. You asked me to get dish soap?' I looked down at the soy sauce in my hand. Maybe everything he said was right. Maybe none of it was. But I'd already opened the bottle, and the braised pork turned out pretty good.",
    "questions": [
        {"type": "mc", "q_zh": "那个男人为什么看起来很有经验？", "q_en": "Why did the man seem experienced?",
         "options": [
             {"text": "他穿着厨师帽", "pinyin": "tā chuānzhe chúshī mào", "text_en": "wearing a chef's hat", "correct": False},
             {"text": "购物车里有很多调料，穿着围裙", "pinyin": "gòuwù chē lǐ yǒu hěn duō tiáoliào, chuānzhe wéiqún", "text_en": "cart full of seasonings, wearing an apron", "correct": True},
             {"text": "他自我介绍是厨师", "pinyin": "tā zìwǒ jièshào shì chúshī", "text_en": "introduced himself as a chef", "correct": False},
             {"text": "他在看食谱", "pinyin": "tā zài kàn shípǔ", "text_en": "reading a recipe", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "那个男人其实来超市买什么？", "q_en": "What was the man actually there to buy?",
         "options": [
             {"text": "酱油", "pinyin": "jiàngyóu", "text_en": "soy sauce", "correct": False},
             {"text": "洗洁精", "pinyin": "xǐjiéjīng", "text_en": "dish soap", "correct": True},
             {"text": "调料", "pinyin": "tiáoliào", "text_en": "seasonings", "correct": False},
             {"text": "牛肉", "pinyin": "niúròu", "text_en": "beef", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "红烧肉做得怎么样？", "q_en": "How did the braised pork turn out?",
         "options": [
             {"text": "很难吃", "pinyin": "hěn nánchī", "text_en": "terrible", "correct": False},
             {"text": "不错", "pinyin": "búcuò", "text_en": "pretty good", "correct": True},
             {"text": "没做", "pinyin": "méi zuò", "text_en": "didn't make it", "correct": False},
             {"text": "太咸了", "pinyin": "tài xián le", "text_en": "too salty", "correct": False}
         ], "difficulty": 0.2}
    ]
})

# 11. j5_reflect_067 - Was: learning to say no with 突然 realize
# NEW: SONDHEIM emotional contradiction - the friend who's always fine
replace_passage("j5_reflect_067", {
    "title": "The Friend Who's Always Fine",
    "title_zh": "永远没事的朋友",
    "text_zh": "小美是那种永远说「没事」的人。你问她今天怎么样，她说很好。你问她最近是不是很累，她笑着说不会。工作出了问题她说没关系，跟男朋友吵架了她说很快就好。上个星期我们一起吃饭，她接了一个电话出去了。回来的时候眼睛有一点红，但她坐下来的第一句话是：「没事，接了个工作电话。」我没有追问。因为我认识她十年了，我知道追问只会让她把墙建得更高。但我做了另一件事：我把菜单递给她，说：「今天你来点，想吃什么就点什么。」她看着菜单看了很久，比平时久很多。然后她点了很多菜——比两个人吃得完的要多得多。我什么都没说。有时候一个人需要的不是被问「你怎么了」，而是被允许在一件安全的、不重要的事情上失控一下。我们没有谈论那个电话。我们吃了很多菜。回家的路上她说：「今天谢谢你。」我说：「谢什么？」她说：「就是谢谢。」",
    "text_pinyin": "Xiǎo Měi shì nà zhǒng yǒngyuǎn shuō「méi shì」de rén. Nǐ wèn tā jīntiān zěnmeyàng, tā shuō hěn hǎo. Nǐ wèn tā zuìjìn shì bu shì hěn lèi, tā xiàozhe shuō bú huì. Gōngzuò chū le wèntí tā shuō méi guānxi, gēn nán péngyou chǎo jià le tā shuō hěn kuài jiù hǎo. Shàng gè xīngqī wǒmen yìqǐ chī fàn, tā jiē le yí gè diànhuà chūqù le. Huílái de shíhou yǎnjīng yǒu yìdiǎn hóng, dàn tā zuò xiàlái de dì yī jù huà shì:「Méi shì, jiē le gè gōngzuò diànhuà.」Wǒ méiyǒu zhuī wèn. Yīnwèi wǒ rènshi tā shí nián le, wǒ zhīdào zhuī wèn zhǐ huì ràng tā bǎ qiáng jiàn de gèng gāo. Dàn wǒ zuò le lìng yí jiàn shì: wǒ bǎ càidān dì gěi tā, shuō:「Jīntiān nǐ lái diǎn, xiǎng chī shénme jiù diǎn shénme.」Tā kànzhe càidān kàn le hěn jiǔ, bǐ píngshí jiǔ hěn duō. Ránhòu tā diǎn le hěn duō cài——bǐ liǎng gè rén chī de wán de yào duō de duō. Wǒ shénme dōu méi shuō. Yǒu shíhou yí gè rén xūyào de bú shì bèi wèn「nǐ zěnme le」, ér shì bèi yǔnxǔ zài yí jiàn ānquán de, bú zhòngyào de shìqing shàng shīkòng yíxià. Wǒmen méiyǒu tánlùn nàge diànhuà. Wǒmen chī le hěn duō cài. Huí jiā de lù shàng tā shuō:「Jīntiān xièxie nǐ.」Wǒ shuō:「Xiè shénme?」Tā shuō:「Jiù shì xièxie.」",
    "text_en": "Xiao Mei is the type of person who always says 'I'm fine.' You ask how her day is, she says great. You ask if she's been tired lately, she laughs and says no. Work problems — it's fine. Argument with her boyfriend — it'll pass. Last week we were having dinner together and she took a phone call outside. When she came back her eyes were slightly red, but the first thing she said sitting down was: 'It's nothing, just a work call.' I didn't press. I've known her ten years — I know pushing only makes her build the walls higher. But I did something else: I handed her the menu and said: 'You order today. Get whatever you want.' She looked at the menu for a long time, much longer than usual. Then she ordered a lot — much more than two people could finish. I said nothing. Sometimes what a person needs isn't being asked 'what's wrong,' but being allowed to lose control over something safe and unimportant. We didn't discuss the phone call. We ate a lot of food. On the way home she said: 'Thank you for today.' I said: 'For what?' She said: 'Just thank you.'",
    "questions": [
        {"type": "mc", "q_zh": "小美接电话回来以后怎么样？", "q_en": "How was Xiao Mei when she came back from the phone call?",
         "options": [
             {"text": "哭了", "pinyin": "kū le", "text_en": "cried", "correct": False},
             {"text": "眼睛有点红，但说没事", "pinyin": "yǎnjīng yǒudiǎn hóng, dàn shuō méi shì", "text_en": "eyes slightly red, but said it's fine", "correct": True},
             {"text": "很生气", "pinyin": "hěn shēngqì", "text_en": "very angry", "correct": False},
             {"text": "开心了", "pinyin": "kāixīn le", "text_en": "became happy", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "「我」为什么没有追问？", "q_en": "Why didn't 'I' press for details?",
         "options": [
             {"text": "不关心", "pinyin": "bù guānxīn", "text_en": "didn't care", "correct": False},
             {"text": "知道追问会让她把墙建得更高", "pinyin": "zhīdào zhuī wèn huì ràng tā bǎ qiáng jiàn de gèng gāo", "text_en": "knew pressing would make her build walls higher", "correct": True},
             {"text": "在吃饭不方便问", "pinyin": "zài chī fàn bù fāngbiàn wèn", "text_en": "inconvenient to ask while eating", "correct": False},
             {"text": "不知道发生了什么", "pinyin": "bù zhīdào fāshēng le shénme", "text_en": "didn't know what happened", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "「我」觉得小美需要什么？", "q_en": "What does 'I' think Xiao Mei needs?",
         "options": [
             {"text": "有人问她怎么了", "pinyin": "yǒu rén wèn tā zěnme le", "text_en": "someone to ask what's wrong", "correct": False},
             {"text": "一个人待着", "pinyin": "yí gè rén dāizhe", "text_en": "to be alone", "correct": False},
             {"text": "被允许在安全的事情上失控一下", "pinyin": "bèi yǔnxǔ zài ānquán de shìqing shàng shīkòng yíxià", "text_en": "permission to lose control over something safe", "correct": True},
             {"text": "去看医生", "pinyin": "qù kàn yīshēng", "text_en": "see a doctor", "correct": False}
         ], "difficulty": 0.5}
    ]
})

# 12. j5_system_084 - Was: subway ecosystem with realize
# NEW: INSTITUTIONAL COMPETENCE - the security guard who knows everything
replace_passage("j5_system_084", {
    "title": "The Guard's Intelligence Network",
    "title_zh": "保安的情报网",
    "text_zh": "我们小区的保安老周掌握的信息量比任何人都大。他知道三号楼的王太太每天早上六点半出门遛狗，七号楼的小夫妻每个周末都吵架但周一就会和好，五号楼的退休教授每天收两份报纸但从来不扔旧的。他知道哪家在装修（因为他批准了施工车辆进出），哪家刚搬来（因为他登记了新的门禁卡），哪家可能要搬走（因为他看到了房产中介带人来看房）。有一次我丢了快递，他不需要查记录就告诉我：「应该在八号楼的李先生那里。你今天不在的时候，快递员按了你的门铃没人应，然后按了隔壁的，李先生帮你签收了。我看到他拿了两个箱子回去。」我问他怎么记得这么清楚。他说：「在门口站了十三年了。这个小区的事情，闭着眼睛我都知道。」他停了一下，补充道：「但是有些事情我假装不知道。这也是我的工作。」",
    "text_pinyin": "Wǒmen xiǎoqū de bǎo'ān Lǎo Zhōu zhǎngwò de xìnxī liàng bǐ rènhé rén dōu dà. Tā zhīdào sān hào lóu de Wáng tàitai měi tiān zǎoshang liù diǎn bàn chū mén liú gǒu, qī hào lóu de xiǎo fūqī měi gè zhōumò dōu chǎo jià dàn zhōuyī jiù huì hé hǎo, wǔ hào lóu de tuìxiū jiàoshòu měi tiān shōu liǎng fèn bàozhǐ dàn cónglái bù rēng jiù de. Tā zhīdào nǎ jiā zài zhuāngxiū (yīnwèi tā pīzhǔn le shīgōng chēliàng jìn chū), nǎ jiā gāng bān lái (yīnwèi tā dēngjì le xīn de ménjìn kǎ), nǎ jiā kěnéng yào bān zǒu (yīnwèi tā kàn dào le fángchǎn zhōngjiè dài rén lái kàn fáng). Yǒu yí cì wǒ diū le kuàidì, tā bù xūyào chá jìlù jiù gàosu wǒ:「Yīnggāi zài bā hào lóu de Lǐ xiānshēng nàlǐ. Nǐ jīntiān bú zài de shíhou, kuàidì yuán àn le nǐ de ménlíng méi rén yìng, ránhòu àn le gébì de, Lǐ xiānshēng bāng nǐ qiānshōu le. Wǒ kàn dào tā ná le liǎng gè xiāngzi huíqù.」Wǒ wèn tā zěnme jì de zhème qīngchu. Tā shuō:「Zài ménkǒu zhàn le shísān nián le. Zhège xiǎoqū de shìqing, bìzhe yǎnjīng wǒ dōu zhīdào.」Tā tíng le yíxià, bǔchōng dào:「Dànshì yǒuxiē shìqing wǒ jiǎzhuāng bù zhīdào. Zhè yě shì wǒ de gōngzuò.」",
    "text_en": "Our neighborhood's security guard, Lao Zhou, has more intelligence than anyone. He knows Mrs. Wang in Building 3 walks her dog at 6:30 every morning. The young couple in Building 7 argues every weekend but makes up by Monday. The retired professor in Building 5 receives two newspapers daily but never throws the old ones away. He knows who's renovating (he approved the construction vehicles), who just moved in (he registered new access cards), who might be moving out (he saw the real estate agent bring people for viewings). Once I lost a package. Without checking any records, he told me: 'Should be with Mr. Li in Building 8. You weren't home today, the delivery person rang your bell with no answer, then rang next door. Mr. Li signed for it. I saw him carry two boxes back.' I asked how he remembered so clearly. He said: 'Thirteen years at this gate. Everything that happens in this compound — I know it with my eyes closed.' He paused, then added: 'But some things I pretend not to know. That's part of my job too.'",
    "questions": [
        {"type": "mc", "q_zh": "老周在这个小区工作了多久？", "q_en": "How long has Lao Zhou worked at this compound?",
         "options": [
             {"text": "五年", "pinyin": "wǔ nián", "text_en": "five years", "correct": False},
             {"text": "十年", "pinyin": "shí nián", "text_en": "ten years", "correct": False},
             {"text": "十三年", "pinyin": "shísān nián", "text_en": "thirteen years", "correct": True},
             {"text": "二十年", "pinyin": "èrshí nián", "text_en": "twenty years", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "老周怎么知道谁可能要搬走？", "q_en": "How does Lao Zhou know who might be moving out?",
         "options": [
             {"text": "别人告诉他的", "pinyin": "biéren gàosu tā de", "text_en": "someone told him", "correct": False},
             {"text": "看到房产中介带人来看房", "pinyin": "kàn dào fángchǎn zhōngjiè dài rén lái kàn fáng", "text_en": "saw real estate agent bring people for viewings", "correct": True},
             {"text": "看到搬家公司的车", "pinyin": "kàn dào bān jiā gōngsī de chē", "text_en": "saw moving company trucks", "correct": False},
             {"text": "查了物业记录", "pinyin": "chá le wùyè jìlù", "text_en": "checked property records", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "老周说有些事情他会怎么做？", "q_en": "What does Lao Zhou do with some things?",
         "options": [
             {"text": "告诉物业", "pinyin": "gàosu wùyè", "text_en": "tell property management", "correct": False},
             {"text": "假装不知道", "pinyin": "jiǎzhuāng bù zhīdào", "text_en": "pretend not to know", "correct": True},
             {"text": "写在本子里", "pinyin": "xiě zài běnzi lǐ", "text_en": "write in a notebook", "correct": False},
             {"text": "跟邻居说", "pinyin": "gēn línjū shuō", "text_en": "tell the neighbors", "correct": False}
         ], "difficulty": 0.3}
    ]
})

# 13. j5_observe_012 - Was: rain on window with realize
# NEW: COMPETENT AND A MESS - the doctor who can't take care of herself
replace_passage("j5_observe_012", {
    "title": "The Doctor's Lunch",
    "title_zh": "医生的午饭",
    "text_zh": "我姐姐是一名急诊科医生，她对病人极其负责。她能在三十秒内判断一个胸痛患者需不需要立即手术，能同时处理四个不同程度的急救案例，能在值了二十四小时夜班之后还保持冷静和精确。但是她照顾不了自己。她的冰箱里经常只有过期的牛奶和三天前的外卖。她买的水果从来没有在变软之前吃完过。她的衣柜里有十二件白色T恤——因为她觉得不用搭配就可以省时间。她的鞋带经常是松的，她的包永远处于半拉开的状态，她的车里有一个月前的停车罚单还没交。有一次我问她：「你每天帮别人解决生死问题，怎么自己连午饭都不能按时吃？」她想了一下说：「也许是因为我的午饭不会在我忘了它的时候死掉。」我不知道该笑还是该担心。所以我现在每周给她送两次饭。她每次都说不用，但是每次都吃完了。",
    "text_pinyin": "Wǒ jiějie shì yì míng jízhěnkē yīshēng, tā duì bìngrén jíqí fùzé. Tā néng zài sānshí miǎo nèi pànduàn yí gè xiōng tòng huànzhě xū bù xūyào lìjí shǒushù, néng tóngshí chǔlǐ sì gè bù tóng chéngdù de jíjiù ànlì, néng zài zhí le èrshísì xiǎoshí yèbān zhīhòu hái bǎochí lěngjìng hé jīngquè. Dànshì tā zhàogù bù liǎo zìjǐ. Tā de bīngxiāng lǐ jīngcháng zhǐ yǒu guòqī de niúnǎi hé sān tiān qián de wàimài. Tā mǎi de shuǐguǒ cónglái méiyǒu zài biàn ruǎn zhīqián chī wán guò. Tā de yīguì lǐ yǒu shí'èr jiàn báisè T xù——yīnwèi tā juéde búyòng dāpèi jiù kěyǐ shěng shíjiān. Tā de xiédài jīngcháng shì sōng de, tā de bāo yǒngyuǎn chǔyú bàn lā kāi de zhuàngtài, tā de chē lǐ yǒu yí gè yuè qián de tíngchē fádān hái méi jiāo. Yǒu yí cì wǒ wèn tā:「Nǐ měi tiān bāng biéren jiějué shēngsǐ wèntí, zěnme zìjǐ lián wǔfàn dōu bù néng ànshí chī?」Tā xiǎng le yíxià shuō:「Yěxǔ shì yīnwèi wǒ de wǔfàn bú huì zài wǒ wàng le tā de shíhou sǐ diào.」Wǒ bù zhīdào gāi xiào háishi gāi dānxīn. Suǒyǐ wǒ xiànzài měi zhōu gěi tā sòng liǎng cì fàn. Tā měi cì dōu shuō búyòng, dànshì měi cì dōu chī wán le.",
    "text_en": "My sister is an ER doctor, extraordinarily dedicated to her patients. She can assess in thirty seconds whether a chest-pain patient needs immediate surgery. She can handle four emergency cases of varying severity at once. She can stay calm and precise after a twenty-four-hour night shift. But she cannot take care of herself. Her fridge usually contains only expired milk and three-day-old takeout. Fruit she buys has never been finished before going soft. Her closet has twelve white T-shirts — because she thinks not having to coordinate outfits saves time. Her shoelaces are often loose, her bag is permanently half-open, and there's a parking ticket from a month ago still unpaid in her car. I once asked her: 'You solve life-and-death problems for other people every day — how can you not even eat lunch on time?' She thought for a moment: 'Maybe because my lunch won't die if I forget about it.' I didn't know whether to laugh or worry. So now I bring her food twice a week. She always says I don't need to. She always finishes it.",
    "questions": [
        {"type": "mc", "q_zh": "姐姐的衣柜里有什么特点？", "q_en": "What's distinctive about the sister's closet?",
         "options": [
             {"text": "有很多漂亮的衣服", "pinyin": "yǒu hěn duō piàoliang de yīfu", "text_en": "lots of pretty clothes", "correct": False},
             {"text": "十二件白色T恤", "pinyin": "shí'èr jiàn báisè T xù", "text_en": "twelve white T-shirts", "correct": True},
             {"text": "什么都没有", "pinyin": "shénme dōu méiyǒu", "text_en": "nothing at all", "correct": False},
             {"text": "都是工作服", "pinyin": "dōu shì gōngzuò fú", "text_en": "all work uniforms", "correct": False}
         ], "difficulty": 0.2},
        {"type": "mc", "q_zh": "姐姐怎么回答关于午饭的问题？", "q_en": "How did the sister answer about lunch?",
         "options": [
             {"text": "她说太忙了", "pinyin": "tā shuō tài máng le", "text_en": "she said she's too busy", "correct": False},
             {"text": "午饭不会在她忘了的时候死掉", "pinyin": "wǔfàn bú huì zài tā wàng le de shíhou sǐ diào", "text_en": "her lunch won't die if she forgets it", "correct": True},
             {"text": "她不饿", "pinyin": "tā bú è", "text_en": "she's not hungry", "correct": False},
             {"text": "医院有食堂", "pinyin": "yīyuàn yǒu shítáng", "text_en": "the hospital has a cafeteria", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "「我」现在怎么做？", "q_en": "What does 'I' do now?",
         "options": [
             {"text": "不管她", "pinyin": "bù guǎn tā", "text_en": "doesn't bother", "correct": False},
             {"text": "每周送两次饭", "pinyin": "měi zhōu sòng liǎng cì fàn", "text_en": "brings food twice a week", "correct": True},
             {"text": "教她做饭", "pinyin": "jiāo tā zuò fàn", "text_en": "teaches her to cook", "correct": False},
             {"text": "帮她订外卖", "pinyin": "bāng tā dìng wàimài", "text_en": "orders takeout for her", "correct": False}
         ], "difficulty": 0.2}
    ]
})

with open("data/reading_passages.json", "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("HSK 5 batch done: 13 passages rewritten")
