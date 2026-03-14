#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rebuild 10 comedy passages that scored below 15 on the comedy rubric.
Replaces text fields (title, title_zh, text_zh, text_pinyin, text_en)
while preserving id, hsk_level, and questions arrays.
"""

import json
import os

CONTENT_DIR = "/Users/jasongerson/mandarin/content_gen"

# ── NEW PASSAGE DATA ──────────────────────────────────────────────

REPLACEMENTS = {

# ═══════════════════════════════════════════════════════════════════
# HSK 1 PASSAGES
# ═══════════════════════════════════════════════════════════════════

"j1_comedy_006": {
    # Comic truth: We pretend we know where we're going long past the point
    # where we obviously don't.
    # Behavior: Misplaced confidence / refusal to ask for help
    # Mechanism: Understatement — narrator's calm tone vs. escalating lostness
    # Ends on image, not moral.
    "title": "The Confident Passenger",
    "title_zh": "自信的乘客",
    "text_zh": "我上了车。窗外的路我不认识，但是我没有问。又过了十分钟，外面的楼越来越少，树越来越多。天也暗了。我心里说：没问题，快到了。又过了二十分钟，车停了。司机说「到了，终点站」。我下了车。四面都是山。没有灯，没有人。我站在那里，不知道我在哪里。风很大，很冷。和我心里的感觉一样。",
    "text_pinyin": "Wǒ shàng le chē. Chuāngwài de lù wǒ bú rènshi, dànshì wǒ méiyǒu wèn. Yòu guò le shí fēnzhōng, wàimian de lóu yuè lái yuè shǎo, shù yuè lái yuè duō. Tiān yě àn le. Wǒ xīnli shuō: méi wèntí, kuài dào le. Yòu guò le èrshí fēnzhōng, chē tíng le. Sījī shuō 'dào le, zhōngdiǎnzhàn'. Wǒ xià le chē. Sìmiàn dōu shì shān. Méiyǒu dēng, méiyǒu rén. Wǒ zhàn zài nàlǐ, bù zhīdào wǒ zài nǎlǐ. Fēng hěn dà, hěn lěng. Hé wǒ xīnli de gǎnjué yíyàng.",
    "text_en": "I got on the bus. I didn't recognize the road outside, but I didn't ask. Ten more minutes — fewer buildings, more trees. The sky went dark. I told myself: no problem, almost there. Twenty more minutes, the bus stopped. The driver said 'Last stop.' I got off. Mountains on all sides. No lights, no people. I stood there, not knowing where I was. The wind was strong and cold. Same as the feeling inside me.",
},

"j1_comedy_011": {
    # Comic truth: We bark at threats that turn out to be ourselves.
    # Behavior: Excessive earnestness in the face of nothing
    # Mechanism: Literal-mindedness — dog takes reflection at face value
    # Ends on image (dog walking away, still suspicious), not moral.
    "title": "The Dog's Enemy",
    "title_zh": "狗的敌人",
    "text_zh": "我家的狗看到了镜子里的另一只狗。它叫了很久。镜子里的狗也叫了很久——其实没有声音，但是嘴在动。我家的狗更生气了：你叫什么叫？它跑到镜子后面。后面什么都没有。它又跑回来——那只狗还在！它看了看我，好像在说「你怎么不帮我？」。最后它不高兴地走了。走了三步，又回头看了一眼。",
    "text_pinyin": "Wǒ jiā de gǒu kàn dào le jìngzi lǐ de lìng yì zhī gǒu. Tā jiào le hěn jiǔ. Jìngzi lǐ de gǒu yě jiào le hěn jiǔ — qíshí méiyǒu shēngyīn, dànshì zuǐ zài dòng. Wǒ jiā de gǒu gèng shēngqì le: nǐ jiào shénme jiào? Tā pǎo dào jìngzi hòumiàn. Hòumiàn shénme dōu méiyǒu. Tā yòu pǎo huílái — nà zhī gǒu hái zài! Tā kàn le kàn wǒ, hǎoxiàng zài shuō 'nǐ zěnme bù bāng wǒ?'. Zuìhòu tā bù gāoxìng de zǒu le. Zǒu le sān bù, yòu huítóu kàn le yì yǎn.",
    "text_en": "My dog spotted another dog in the mirror. It barked for a long time. The mirror dog barked back — no sound, actually, but its mouth was moving. My dog got angrier: what are you barking at? It ran behind the mirror. Nothing back there. It ran back around — that dog was still there! It looked at me like: why aren't you helping? Finally it walked away, unhappy. Three steps later, it looked back one more time.",
},

"j1_comedy_012": {
    # Comic truth: We'd rather pretend we understand than admit we don't.
    # Behavior: Self-protective face-saving
    # Mechanism: Misplaced confidence → status drop when caught
    # Ends on the beat of the laugh + the save attempt, not a lesson.
    "title": "The Serious Reader",
    "title_zh": "认真的读者",
    "text_zh": "咖啡店里，一个男人在看书。他看了很久，表情很认真。旁边的人看了看他的书，说「你的书拿反了」。那个男人低头看了看。真的反了。他笑了，说「啊，我在练习」。旁边的人没有说话。",
    "text_pinyin": "Kāfēi diàn lǐ, yí gè nánrén zài kàn shū. Tā kàn le hěn jiǔ, biǎoqíng hěn rènzhēn. Pángbiān de rén kàn le kàn tā de shū, shuō 'nǐ de shū ná fǎn le'. Nà ge nánrén dītóu kàn le kàn. Zhēn de fǎn le. Tā xiào le, shuō 'a, wǒ zài liànxí'. Pángbiān de rén méiyǒu shuō huà.",
    "text_en": "In a coffee shop, a man was reading. He'd been at it a while, expression very serious. The person next to him glanced at his book and said 'Your book is upside down.' The man looked down. It really was. He laughed and said 'Oh, I'm practicing.' The person next to him said nothing.",
},

"j1_comedy_015": {
    # Comic truth: First attempts at cooking are an exercise in discovering
    # how many things can go wrong simultaneously.
    # Behavior: Excessive earnestness / over-preparation that backfires
    # Mechanism: Reversal — each "fix" makes things worse, but result is OK
    # Ends on the understated "not bad" verdict, not a lesson.
    "title": "The First Egg Fried Rice",
    "title_zh": "第一次炒饭",
    "text_zh": "我想做鸡蛋炒饭。我看了手机上的视频三次。视频说「一点点油」。我放了很多。视频说「一个鸡蛋」。我的鸡蛋太大了，锅太小了，油到处都是。我很紧张。饭放进去的时候，锅里发出了很大的声音。我用了二十分钟。做完以后，我看了看——颜色不太对，形状也不太好看。但是我吃了一口。还可以。",
    "text_pinyin": "Wǒ xiǎng zuò jīdàn chǎofàn. Wǒ kàn le shǒujī shàng de shìpín sān cì. Shìpín shuō 'yìdiǎndiǎn yóu'. Wǒ fàng le hěn duō. Shìpín shuō 'yí gè jīdàn'. Wǒ de jīdàn tài dà le, guō tài xiǎo le, yóu dàochù dōu shì. Wǒ hěn jǐnzhāng. Fàn fàng jìnqù de shíhou, guō lǐ fāchū le hěn dà de shēngyīn. Wǒ yòng le èrshí fēnzhōng. Zuò wán yǐhòu, wǒ kàn le kàn — yánsè bú tài duì, xíngzhuàng yě bú tài hǎokàn. Dànshì wǒ chī le yì kǒu. Hái kěyǐ.",
    "text_en": "I wanted to make egg fried rice. I watched the phone video three times. The video said 'a little oil.' I put in a lot. The video said 'one egg.' My egg was too big, the pan too small, oil everywhere. I was nervous. When the rice went in, the pan made a loud noise. It took me twenty minutes. When I finished, I looked at it — wrong color, wrong shape. But I took a bite. Not bad.",
},

# ═══════════════════════════════════════════════════════════════════
# HSK 4 PASSAGES
# ═══════════════════════════════════════════════════════════════════

"j4_comedy_001": {
    # Comic truth: Delivery mix-ups create small parallel universes where
    # strangers briefly live each other's emotional moments.
    # Behavior: Going along with a situation rather than correcting it
    # Mechanism: Reversal — the wrong order becomes someone else's romantic story
    # Ends on wondering, not explaining.
    "title": "Someone Else's Birthday",
    "title_zh": "别人的生日",
    "text_zh": "昨天晚上我点了一份炒饭。外卖员来了，递给我一个很大的袋子。我打开一看——是一个生日蛋糕，上面写着「亲爱的，生日快乐」。我吓了一跳。我跟外卖员解释，他看了看手机说：「糟糕，两份单搞混了。」然后他满头大汗地去找我的炒饭。半个小时以后他回来了，端着我的炒饭，不好意思地说：「那个人收到了你的炒饭，还以为是男朋友送的惊喜。」我一边吃炒饭一边想：当那个蛋糕变成炒饭的时候，她是什么表情？",
    "text_pinyin": "Zuótiān wǎnshang wǒ diǎn le yí fèn chǎofàn. Wàimài yuán lái le, dì gěi wǒ yí gè hěn dà de dàizi. Wǒ dǎkāi yí kàn — shì yí gè shēngrì dàngāo, shàngmiàn xiě zhe 'qīn'ài de, shēngrì kuàilè'. Wǒ xià le yí tiào. Wǒ gēn wàimài yuán jiěshì, tā kàn le kàn shǒujī shuō: 'zāogāo, liǎng fèn dān gǎo hùn le.' Ránhòu tā mǎntóu dàhàn de qù zhǎo wǒ de chǎofàn. Bàn ge xiǎoshí yǐhòu tā huílái le, duān zhe wǒ de chǎofàn, bù hǎoyìsi de shuō: 'nà ge rén shōu dào le nǐ de chǎofàn, hái yǐwéi shì nán péngyou sòng de jīngxǐ.' Wǒ yìbiān chī chǎofàn yìbiān xiǎng: dāng nà ge dàngāo biànchéng chǎofàn de shíhou, tā shì shénme biǎoqíng?",
    "text_en": "Last night I ordered fried rice. The delivery guy handed me a huge bag. I opened it — a birthday cake, iced with 'Happy Birthday, darling.' I nearly jumped. I explained the mix-up; he checked his phone: 'Oh no, I swapped the two orders.' Then he ran off, sweating, to track down my fried rice. Half an hour later he came back with it, embarrassed: 'The other person got your fried rice and thought it was a surprise from her boyfriend.' I ate my fried rice and wondered: what was her face when the birthday cake turned into fried rice?",
},

"j4_comedy_002": {
    # Comic truth: The terror of sending the wrong message to the wrong person
    # is universal, but the social fallout reveals who people really are.
    # Behavior: Panic → overcorrection → the other person being gracious
    # Mechanism: Status drop — narrator tries to recover dignity, colleague
    # one-ups with effortless grace
    # Ends on the coffee gesture, not a lesson.
    "title": "The Wrong Chat Window",
    "title_zh": "发错了人",
    "text_zh": "我想给好朋友发一条语音消息，吐槽新来的同事。我说了一大堆：他说话太慢了，开会的时候总是跑题，而且喝咖啡的声音特别大。说完很爽。然后我看了一眼屏幕——我发到了新同事的对话框里。我的手开始抖。我马上点撤回，系统提示：已超过两分钟，无法撤回。那天下午我一直没敢看手机。第二天早上，新同事走到我桌子前，递了一杯咖啡，笑着说：「以后有什么想法可以直接跟我说，不用发语音。」他喝了一口自己的咖啡，声音确实挺大的。",
    "text_pinyin": "Wǒ xiǎng gěi hǎo péngyou fā yì tiáo yǔyīn xiāoxi, tùcáo xīn lái de tóngshì. Wǒ shuō le yí dà duī: tā shuōhuà tài màn le, kāihuì de shíhou zǒngshì pǎo tí, érqiě hē kāfēi de shēngyīn tèbié dà. Shuō wán hěn shuǎng. Ránhòu wǒ kàn le yì yǎn píngmù — wǒ fā dào le xīn tóngshì de duìhuà kuāng lǐ. Wǒ de shǒu kāishǐ dǒu. Wǒ mǎshàng diǎn chèhuí, xìtǒng tíshì: yǐ chāoguò liǎng fēnzhōng, wúfǎ chèhuí. Nà tiān xiàwǔ wǒ yìzhí méi gǎn kàn shǒujī. Dì'èr tiān zǎoshang, xīn tóngshì zǒu dào wǒ zhuōzi qián, dì le yì bēi kāfēi, xiào zhe shuō: 'yǐhòu yǒu shénme xiǎngfǎ kěyǐ zhíjiē gēn wǒ shuō, bú yòng fā yǔyīn.' Tā hē le yì kǒu zìjǐ de kāfēi, shēngyīn quèshí tǐng dà de.",
    "text_en": "I wanted to send my good friend a voice message complaining about the new colleague. I went off: he talks too slowly, goes off-topic in every meeting, and drinks coffee absurdly loud. Felt great to say it. Then I looked at the screen — I'd sent it to the new colleague's chat window. My hands started shaking. I hit recall. System: 'More than two minutes have passed. Cannot recall.' I didn't touch my phone all afternoon. Next morning, the new colleague walked to my desk, handed me a coffee, and said with a smile: 'If you have thoughts, just tell me directly — no need for voice messages.' He took a sip of his own coffee. It really was pretty loud.",
},

"j4_comedy_003": {
    # Comic truth: The parent who asks you to fix their tech is the same
    # parent who created the problem by "fixing" it themselves.
    # Behavior: Mom's cycle of tech frustration → asking for help → creating
    # new problems
    # Mechanism: Reversal — turning off autocorrect makes things worse
    # Ends on mom's decision (delegate to kid), not a lesson.
    "title": "Mom vs. Autocorrect",
    "title_zh": "妈妈和自动纠正",
    "text_zh": "我妈给家人群发消息：「今天去买彩，晚上做红烧鱼。」我姐问：「妈，你什么时候开始买彩票了？」我妈说她打的是「买菜」，手机自己改的。这种事每天都会发生。上周她想说「我到家了」，手机改成了「我倒下了」，我爸吓得打了三个电话。我帮她关掉了自动纠正。结果更惨——没有自动纠正以后，她打错字反而更多了，而且这次没人帮她改。她试了一个星期，最后对我说：「算了，你以后帮我检查消息再发。」从此我每天收到十条待审核的消息。",
    "text_pinyin": "Wǒ mā gěi jiārén qún fā xiāoxi: 'jīntiān qù mǎi cǎi, wǎnshang zuò hóngshāo yú.' Wǒ jiě wèn: 'mā, nǐ shénme shíhou kāishǐ mǎi cǎipiào le?' Wǒ mā shuō tā dǎ de shì 'mǎi cài', shǒujī zìjǐ gǎi de. Zhè zhǒng shì měitiān dōu huì fāshēng. Shàng zhōu tā xiǎng shuō 'wǒ dào jiā le', shǒujī gǎi chéng le 'wǒ dǎo xià le', wǒ bà xià de dǎ le sān ge diànhuà. Wǒ bāng tā guān diào le zìdòng jiūzhèng. Jiéguǒ gèng cǎn — méiyǒu zìdòng jiūzhèng yǐhòu, tā dǎ cuò zì fǎn'ér gèng duō le, érqiě zhè cì méi rén bāng tā gǎi. Tā shì le yí gè xīngqī, zuìhòu duì wǒ shuō: 'suàn le, nǐ yǐhòu bāng wǒ jiǎnchá xiāoxi zài fā.' Cóngcǐ wǒ měitiān shōu dào shí tiáo dài shěnhé de xiāoxi.",
    "text_en": "Mom texted the family group: 'Going to buy lottery today, making braised fish tonight.' My sister asked: 'Mom, since when do you buy lottery tickets?' Mom said she typed 'buy groceries' — the phone changed it. This happens every day. Last week she typed 'I'm home' and the phone changed it to 'I've collapsed.' Dad called three times in a panic. I turned off her autocorrect. That was worse — without autocorrect she made even more typos, and now nothing was fixing them. She lasted one week, then told me: 'Forget it, you check my messages before I send them from now on.' Since then I get ten messages a day awaiting review.",
},

"j4_comedy_005": {
    # Comic truth: The worst photos from a trip are the ones you actually
    # remember, because perfect photos feel like they happened to someone else.
    # Behavior: The gap between how we think photos will turn out and reality
    # Mechanism: Reversal — "failed" photos become more valued than good ones
    # Ends on the feeling, compressed, not explained.
    "title": "The Best Bad Photos",
    "title_zh": "最好的坏照片",
    "text_zh": "去年我和朋友去旅行。她帮我拍了二十多张照片，回来一看——全部拍模糊了。每一张都在抖，像是在地震中拍的。她说她以为按一下就好了，不知道要拿稳。然后我帮她拍。我很认真，找了最好的角度。结果出来以后，她的脸只剩下一半——另一半被一个路过的游客挡住了。那个游客还在对着镜头微笑。我们在手机上翻这些照片的时候，比看任何一张完美的照片都开心。",
    "text_pinyin": "Qùnián wǒ hé péngyou qù lǚxíng. Tā bāng wǒ pāi le èrshí duō zhāng zhàopiàn, huílái yí kàn — quánbù pāi móhu le. Měi yì zhāng dōu zài dǒu, xiàng shì zài dìzhèn zhōng pāi de. Tā shuō tā yǐwéi àn yíxià jiù hǎo le, bù zhīdào yào ná wěn. Ránhòu wǒ bāng tā pāi. Wǒ hěn rènzhēn, zhǎo le zuì hǎo de jiǎodù. Jiéguǒ chūlái yǐhòu, tā de liǎn zhǐ shèng xià yíbàn — lìng yíbàn bèi yí gè lùguò de yóukè dǎng zhù le. Nà ge yóukè hái zài duì zhe jìngtóu wēixiào. Wǒmen zài shǒujī shang fān zhèxiē zhàopiàn de shíhou, bǐ kàn rènhé yì zhāng wánměi de zhàopiàn dōu kāixīn.",
    "text_en": "Last year my friend and I went traveling. She took twenty-something photos of me — every single one blurry. Each one shaking, like photographed during an earthquake. She said she thought you just press once, didn't know you had to hold still. Then I took her photos. I was careful, found the perfect angle. Result: half her face — the other half blocked by a passing tourist. That tourist was smiling at the camera. Scrolling through these photos on our phones later, we were happier than looking at any perfect photo.",
},

# ═══════════════════════════════════════════════════════════════════
# HSK 8 PASSAGES
# ═══════════════════════════════════════════════════════════════════

"j8_comedy_003": {
    # Comic truth: Queue-jumping is a performance art, and the real comedy
    # is that everyone sees through it but almost no one says anything.
    # Behavior: The elaborate social theater of pretending not to notice
    # Mechanism: Bureaucratic laundering — treating queue-jumping like an
    # academic discipline elevates the absurdity
    # NOW A SCENE with a specific incident, but preserving the four schools
    # and the 80/15/5 ratio the questions require.
    "title": "The Art of Merging",
    "title_zh": "插队的艺术",
    "text_zh": "上周六在奶茶店排队，我亲眼见证了四种流派的现场演示。先是一个女生，站在队伍旁边假装看手机，等前面的人注意力一松懈，自然地「融入」了队伍——表情平静得让你怀疑自己的记忆。这是第一流派：无辜融入派。紧接着，一个中年男人认出了队伍中间的熟人，热情地打招呼，以「聊天」的名义站在他旁边，前面的人一走他就补上了空隙。第二流派：熟人寄生派。然后一位阿姨抱着孩子走到前面，用疲惫的眼神换取了全队默许的通行证。第三流派：弱势优先派。最高级的出现在最后——一个穿西装的男人发现排队拐角处有一个模糊的分叉点，声称那里是另一条队伍的起点，然后把自己安排在「新队伍」的第一位。第四流派：规则重新定义派。他们不是违反规则，而是重新定义了规则，从根本上改变了游戏。我观察了一下周围人的反应：百分之八十沉默忍受，百分之十五用眼神表达不满，只有百分之五的人真的开了口。那个开口的人说的是：「不好意思，请问这里是排队吗？」——用的还是疑问句。",
    "text_pinyin": "Shàng zhōuliù zài nǎichá diàn páiduì, wǒ qīnyǎn jiànzhèng le sì zhǒng liúpài de xiànchǎng yǎnshì. Xiān shì yí gè nǚshēng, zhàn zài duìwu pángbiān jiǎzhuāng kàn shǒujī, děng qiánmiàn de rén zhùyìlì yí sōngxiè, zìrán de 'róngrù' le duìwu — biǎoqíng píngjìng de ràng nǐ huáiyí zìjǐ de jìyì. Zhè shì dì-yī liúpài: wúgū róngrù pài. Jǐn jiē zhe, yí gè zhōngnián nánrén rèn chū le duìwu zhōngjiān de shúrén, rèqíng de dǎ zhāohu, yǐ 'liáotiān' de míngyì zhàn zài tā pángbiān, qiánmiàn de rén yí zǒu tā jiù bǔ shàng le kòngxì. Dì-èr liúpài: shúrén jìshēng pài. Ránhòu yí wèi āyí bào zhe háizi zǒu dào qiánmiàn, yòng píbèi de yǎnshén huànqǔ le quán duì mòxǔ de tōngxíngzhèng. Dì-sān liúpài: ruòshì yōuxiān pài. Zuì gāojí de chūxiàn zài zuìhòu — yí gè chuān xīzhuāng de nánrén fāxiàn páiduì guǎijiǎo chù yǒu yí gè móhu de fēnchā diǎn, shēngchēng nàlǐ shì lìng yì tiáo duìwu de qǐdiǎn, ránhòu bǎ zìjǐ ānpái zài 'xīn duìwu' de dì-yī wèi. Dì-sì liúpài: guīzé chóngxīn dìngyì pài. Tāmen bú shì wéifǎn guīzé, ér shì chóngxīn dìngyì le guīzé, cóng gēnběn shàng gǎibiàn le yóuxì. Wǒ guānchá le yíxià zhōuwéi rén de fǎnyìng: bǎi fēn zhī bāshí chénmò rěnshòu, bǎi fēn zhī shíwǔ yòng yǎnshén biǎodá bùmǎn, zhǐ yǒu bǎi fēn zhī wǔ de rén zhēn de kāi le kǒu. Nà ge kāikǒu de rén shuō de shì: 'bù hǎoyìsi, qǐngwèn zhèlǐ shì páiduì ma?' — yòng de háishi yíwènjù.",
    "text_en": "Last Saturday at a milk tea shop, I witnessed all four schools of queue-jumping perform live. First, a girl stood beside the line pretending to check her phone, and when the people ahead lost focus for a moment, she 'merged' in — expression so calm you doubted your own memory. School one: the Innocent Merger. Next, a middle-aged man recognized an acquaintance mid-queue, greeted him warmly, stood beside him under the pretense of 'chatting,' and filled the gap the moment the person ahead moved. School two: the Acquaintance Parasite. Then an auntie carrying a child walked to the front, trading a look of exhaustion for the entire queue's tacit permission. School three: Vulnerability Privilege. The most advanced came last — a man in a suit spotted an ambiguous fork at the queue's bend, declared it the start of a separate line, and installed himself first in the 'new queue.' School four: the Rule Redefiners. They don't break rules — they redefine them, changing the game entirely. I observed the crowd's reaction: eighty percent endured in silence, fifteen percent expressed displeasure through eye contact alone, and only five percent actually spoke up. The one who spoke said: 'Excuse me, is this the queue?' — still phrased as a question.",
},

"j8_comedy_004": {
    # Comic truth: Office napping is a covert operation where the real skill
    # isn't sleeping — it's disguising sleep as work.
    # Behavior: The performance of productivity while actually unconscious
    # Mechanism: Over-formality — treating napping like espionage tradecraft
    # NOW A SCENE: specific meeting napping incident, but preserving the five
    # postures, desk-drape sleeve marks, and open-eyed trance the questions need.
    "title": "The Meeting That Wasn't",
    "title_zh": "不存在的会议",
    "text_zh": "周三下午的季度报告会上，我终于见识了办公室午睡的五种经典姿势同台演出。小张用的是「趴桌式」——双臂交叉，脸埋在臂弯里。这是最常见也最容易暴露的姿势，致命缺点在于：醒来后脸上会留下衣袖褶皱的印记，大约四十分钟才能消退。财务部的老李用了更高级的「假装在读」——一只手撑着头，另一只手放在翻开的文件上，眼睛闭着，头微微下垂。远远看去，这个人好像在思考一个很复杂的问题。行政部的小王选择了最有风险的路线：「洗手间冥想式」——在隔间里坐五到十分钟，需要极好的平衡感，否则睡着了会从马桶上滑下来。市场部的陈经理走了舒适路线——「通勤式午睡」，午休时间躲到车里睡，最舒服但成本最高，因为停车费要十五块。然后我看到了传说中的最高境界。对面坐着的王总监——眼睛睁着，姿势端正，目视前方。乍一看完全清醒。但仔细看，瞳孔已经失焦了。「睁眼入定式」。他在看似清醒的状态下进入了浅度睡眠，完全不会被发现。会后有人问他对报告有什么看法，他说：「整体方向没问题，细节再讨论。」一句万能回答。",
    "text_pinyin": "Zhōusān xiàwǔ de jìdù bàogào huì shàng, wǒ zhōngyú jiànshi le bàngōngshì wǔshuì de wǔ zhǒng jīngdiǎn zīshì tóngtái yǎnchū. Xiǎo Zhāng yòng de shì 'pā zhuō shì' — shuāng bì jiāochā, liǎn mái zài bìwān lǐ. Zhè shì zuì chángjiàn yě zuì róngyì bàolù de zīshì, zhìmìng quēdiǎn zàiyú: xǐnglái hòu liǎn shàng huì liú xià yīxiù zhězhòu de yìnjì, dàyuē sìshí fēnzhōng cái néng xiāotuì. Cáiwù bù de Lǎo Lǐ yòng le gèng gāojí de 'jiǎzhuāng zài dú' — yì zhī shǒu chēng zhe tóu, lìng yì zhī shǒu fàng zài fānkāi de wénjiàn shàng, yǎnjing bì zhe, tóu wēiwēi xiàchuí. Yuǎnyuǎn kàn qù, zhè ge rén hǎoxiàng zài sīkǎo yí gè hěn fùzá de wèntí. Xíngzhèng bù de Xiǎo Wáng xuǎnzé le zuì yǒu fēngxiǎn de lùxiàn: 'xǐshǒujiān míngxiǎng shì' — zài géjiān lǐ zuò wǔ dào shí fēnzhōng, xūyào jí hǎo de pínghéng gǎn, fǒuzé shuìzháo le huì cóng mǎtǒng shàng huá xiàlái. Shìchǎng bù de Chén jīnglǐ zǒu le shūshì lùxiàn — 'tōngqín shì wǔshuì', wǔxiū shíjiān duǒ dào chē lǐ shuì, zuì shūfu dàn chéngběn zuì gāo, yīnwèi tíngchē fèi yào shíwǔ kuài. Ránhòu wǒ kàn dào le chuánshuō zhōng de zuìgāo jìngjiè. Duìmiàn zuò zhe de Wáng zǒngjiān — yǎnjing zhēng zhe, zīshì duānzhèng, mùshì qiánfāng. Zhà yí kàn wánquán qīngxǐng. Dàn zǐxì kàn, tóngkǒng yǐjīng shī jiāo le. 'Zhēng yǎn rùdìng shì'. Tā zài kànsì qīngxǐng de zhuàngtài xià jìnrù le qiǎndù shuìmián, wánquán bú huì bèi fāxiàn. Huì hòu yǒu rén wèn tā duì bàogào yǒu shénme kànfǎ, tā shuō: 'zhěngtǐ fāngxiàng méi wèntí, xìjié zài tǎolùn.' Yí jù wànnéng huídá.",
    "text_en": "Wednesday afternoon's quarterly report meeting: I finally witnessed all five classic office-napping postures perform on the same stage. Xiao Zhang went with the 'desk drape' — arms crossed, face buried in the crook. Most common, most exposed. Fatal flaw: waking with sleeve-crease imprints on the face, lasting about forty minutes. Old Li from Finance deployed the more advanced 'pretending to read' — one hand propping his head, the other on an open document, eyes closed, head drooping slightly. From a distance, this man appeared to be pondering something complex. Xiao Wang from Admin chose the riskiest route: 'restroom meditation' — sitting in a stall for five to ten minutes, requiring excellent balance to avoid sliding off the toilet. Manager Chen from Marketing took the comfort route — 'commute nap,' hiding in his car during lunch break. Most comfortable, highest cost: parking was fifteen yuan. Then I saw the legendary ultimate level. Director Wang, sitting across from me — eyes open, posture upright, gaze forward. At first glance, completely awake. But look closely: the pupils had lost focus. The 'open-eyed trance.' He'd entered light sleep while appearing fully conscious, completely undetectable. After the meeting someone asked his thoughts on the report. He said: 'Overall direction is fine, we can discuss the details.' One all-purpose answer.",
},

}

# ── REPLACEMENT LOGIC ─────────────────────────────────────────────

def replace_passages(filepath, replacements_for_file):
    """Read a JSON file, replace matching passages, write back."""
    with open(filepath, "r", encoding="utf-8") as f:
        passages = json.load(f)

    replaced = []
    for p in passages:
        if p["id"] in replacements_for_file:
            new = replacements_for_file[p["id"]]
            p["title"] = new["title"]
            p["title_zh"] = new["title_zh"]
            p["text_zh"] = new["text_zh"]
            p["text_pinyin"] = new["text_pinyin"]
            p["text_en"] = new["text_en"]
            # questions and other fields stay intact
            replaced.append(p["id"])

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(passages, f, ensure_ascii=False, indent=2)

    return replaced


def main():
    # Map passage IDs to their HSK-level files
    file_map = {
        "passages_hsk1.json": ["j1_comedy_006", "j1_comedy_011",
                                "j1_comedy_012", "j1_comedy_015"],
        "passages_hsk4.json": ["j4_comedy_001", "j4_comedy_002",
                                "j4_comedy_003", "j4_comedy_005"],
        "passages_hsk8.json": ["j8_comedy_003", "j8_comedy_004"],
    }

    total_replaced = 0
    for filename, ids in file_map.items():
        filepath = os.path.join(CONTENT_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  [SKIP] {filename} not found")
            continue

        subs = {pid: REPLACEMENTS[pid] for pid in ids if pid in REPLACEMENTS}
        replaced = replace_passages(filepath, subs)
        for pid in replaced:
            en_words = len(REPLACEMENTS[pid]["text_en"].split())
            print(f"  [OK] {pid} -> \"{REPLACEMENTS[pid]['title']}\" ({en_words} EN words)")
            total_replaced += 1

    print(f"\nDone: {total_replaced}/10 passages replaced.")
    if total_replaced < 10:
        missing = set(REPLACEMENTS.keys()) - set(
            pid for ids in file_map.values() for pid in ids
        )
        print(f"  Missing from file_map: {missing}")


if __name__ == "__main__":
    main()
