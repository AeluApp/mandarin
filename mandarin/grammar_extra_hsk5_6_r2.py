"""Extra HSK 5-6 grammar points, round 2 — fills remaining gaps."""

EXTRA_GRAMMAR_HSK5_6_R2 = [
    # ── HSK 5 (18 new) ──────────────────────────────────────────────

    {"name": "显然 obviously", "name_zh": "显然", "hsk_level": 5, "category": "particle",
     "description": "States something is clearly the case: 这显然不对", "difficulty": 0.6,
     "examples": [
         {"zh": "这显然不对。", "pinyin": "Zhè xiǎnrán bú duì.", "en": "This is obviously wrong."},
         {"zh": "他显然没有准备好。", "pinyin": "Tā xiǎnrán méiyǒu zhǔnbèi hǎo.", "en": "He obviously wasn't prepared."},
         {"zh": "显然，这个方案需要修改。", "pinyin": "Xiǎnrán, zhège fāng'àn xūyào xiūgǎi.", "en": "Obviously, this plan needs revision."},
     ]},

    {"name": "既...又 both...and (formal)", "name_zh": "既…又", "hsk_level": 5, "category": "connector",
     "description": "Formal parallel structure linking two qualities: 既便宜又好用", "difficulty": 0.6,
     "examples": [
         {"zh": "这个手机既便宜又好用。", "pinyin": "Zhège shǒujī jì piányi yòu hǎoyòng.", "en": "This phone is both cheap and useful."},
         {"zh": "她既聪明又勤奋。", "pinyin": "Tā jì cōngmíng yòu qínfèn.", "en": "She is both smart and hardworking."},
         {"zh": "这份工作既稳定又有发展前景。", "pinyin": "Zhè fèn gōngzuò jì wěndìng yòu yǒu fāzhǎn qiánjǐng.", "en": "This job is both stable and has growth prospects."},
     ]},

    {"name": "而 conjunction (but/and/yet)", "name_zh": "而", "hsk_level": 5, "category": "connector",
     "description": "Literary conjunction linking contrast or parallel: 他聪明而勤奋", "difficulty": 0.7,
     "examples": [
         {"zh": "他聪明而勤奋。", "pinyin": "Tā cōngmíng ér qínfèn.", "en": "He is smart and hardworking."},
         {"zh": "这个问题简单而重要。", "pinyin": "Zhège wèntí jiǎndān ér zhòngyào.", "en": "This question is simple yet important."},
         {"zh": "他没有放弃，而是继续努力。", "pinyin": "Tā méiyǒu fàngqì, ér shì jìxù nǔlì.", "en": "He didn't give up, but rather continued to work hard."},
     ]},

    {"name": "于是 thereupon", "name_zh": "于是", "hsk_level": 5, "category": "connector",
     "description": "Introduces a natural consequence or next action: 于是他决定离开", "difficulty": 0.6,
     "examples": [
         {"zh": "天黑了，于是他决定回家。", "pinyin": "Tiān hēi le, yúshì tā juédìng huíjiā.", "en": "It got dark, so he decided to go home."},
         {"zh": "她觉得无聊，于是出去散步了。", "pinyin": "Tā juéde wúliáo, yúshì chūqù sànbù le.", "en": "She felt bored, so she went out for a walk."},
         {"zh": "大家都同意了，于是会议就结束了。", "pinyin": "Dàjiā dōu tóngyì le, yúshì huìyì jiù jiéshù le.", "en": "Everyone agreed, so the meeting ended."},
     ]},

    {"name": "逐渐 gradually", "name_zh": "逐渐", "hsk_level": 5, "category": "particle",
     "description": "Indicates a gradual process of change: 天气逐渐变暖", "difficulty": 0.6,
     "examples": [
         {"zh": "天气逐渐变暖了。", "pinyin": "Tiānqì zhújiàn biàn nuǎn le.", "en": "The weather is gradually getting warmer."},
         {"zh": "他的中文水平逐渐提高了。", "pinyin": "Tā de Zhōngwén shuǐpíng zhújiàn tígāo le.", "en": "His Chinese level has gradually improved."},
         {"zh": "人们逐渐习惯了新的生活方式。", "pinyin": "Rénmen zhújiàn xíguàn le xīn de shēnghuó fāngshì.", "en": "People gradually got used to the new lifestyle."},
     ]},

    {"name": "一旦 once / if ever", "name_zh": "一旦", "hsk_level": 5, "category": "connector",
     "description": "Introduces a critical condition with significant consequences: 一旦开始就不能停", "difficulty": 0.7,
     "examples": [
         {"zh": "一旦开始，就不能停下来。", "pinyin": "Yídàn kāishǐ, jiù bù néng tíng xiàlái.", "en": "Once you start, you can't stop."},
         {"zh": "一旦错过了机会，就很难再有了。", "pinyin": "Yídàn cuòguò le jīhuì, jiù hěn nán zài yǒu le.", "en": "Once you miss the opportunity, it's hard to get another one."},
         {"zh": "一旦养成了坏习惯，就很难改掉。", "pinyin": "Yídàn yǎngchéng le huài xíguàn, jiù hěn nán gǎidiào.", "en": "Once you develop a bad habit, it's hard to break."},
     ]},

    {"name": "不得已 have no choice", "name_zh": "不得已", "hsk_level": 5, "category": "structure",
     "description": "Indicates acting out of necessity with no alternative: 他不得已才这样做", "difficulty": 0.7,
     "examples": [
         {"zh": "他不得已才这样做的。", "pinyin": "Tā bùdéyǐ cái zhèyàng zuò de.", "en": "He had no choice but to do it this way."},
         {"zh": "不得已的情况下，她只好放弃了。", "pinyin": "Bùdéyǐ de qíngkuàng xià, tā zhǐhǎo fàngqì le.", "en": "Having no other option, she had to give up."},
         {"zh": "我也是不得已才来找你帮忙的。", "pinyin": "Wǒ yě shì bùdéyǐ cái lái zhǎo nǐ bāngmáng de.", "en": "I had no choice but to come ask you for help."},
     ]},

    {"name": "不由得 can't help but", "name_zh": "不由得", "hsk_level": 5, "category": "particle",
     "description": "Indicates an involuntary reaction: 他不由得笑了", "difficulty": 0.7,
     "examples": [
         {"zh": "听到这个笑话，他不由得笑了。", "pinyin": "Tīngdào zhège xiàohua, tā bùyóude xiào le.", "en": "Hearing the joke, he couldn't help but laugh."},
         {"zh": "看到美丽的风景，她不由得停下了脚步。", "pinyin": "Kàndào měilì de fēngjǐng, tā bùyóude tíngxià le jiǎobù.", "en": "Seeing the beautiful scenery, she couldn't help but stop."},
         {"zh": "想起以前的事，他不由得叹了口气。", "pinyin": "Xiǎngqǐ yǐqián de shì, tā bùyóude tàn le kǒu qì.", "en": "Thinking of the past, he couldn't help but sigh."},
     ]},

    {"name": "恰好 happen to", "name_zh": "恰好", "hsk_level": 5, "category": "particle",
     "description": "Indicates a coincidence: 我恰好也在那儿", "difficulty": 0.6,
     "examples": [
         {"zh": "我恰好也在那儿。", "pinyin": "Wǒ qiàhǎo yě zài nàr.", "en": "I happened to be there too."},
         {"zh": "他来的时候，我恰好出去了。", "pinyin": "Tā lái de shíhou, wǒ qiàhǎo chūqù le.", "en": "When he came, I happened to be out."},
         {"zh": "这本书恰好是我想找的。", "pinyin": "Zhè běn shū qiàhǎo shì wǒ xiǎng zhǎo de.", "en": "This book happens to be the one I was looking for."},
     ]},

    {"name": "从而 thereby (HSK 5 intro)", "name_zh": "从而", "hsk_level": 5, "category": "connector",
     "description": "Introduces a logical result or consequence: 提高效率，从而节省时间", "difficulty": 0.7,
     "examples": [
         {"zh": "提高效率，从而节省时间。", "pinyin": "Tígāo xiàolǜ, cóng'ér jiéshěng shíjiān.", "en": "Improve efficiency, thereby saving time."},
         {"zh": "多读书，从而增长知识。", "pinyin": "Duō dúshū, cóng'ér zēngzhǎng zhīshi.", "en": "Read more, thereby increasing knowledge."},
         {"zh": "加强锻炼，从而提高身体素质。", "pinyin": "Jiāqiáng duànliàn, cóng'ér tígāo shēntǐ sùzhì.", "en": "Strengthen exercise, thereby improving physical fitness."},
     ]},

    {"name": "何况 let alone (HSK 5 intro)", "name_zh": "何况", "hsk_level": 5, "category": "connector",
     "description": "A fortiori argument — if X is true, how much more so Y: 大人都做不到，何况小孩", "difficulty": 0.7,
     "examples": [
         {"zh": "大人都做不到，何况小孩呢？", "pinyin": "Dàrén dōu zuò bu dào, hékuàng xiǎohái ne?", "en": "Even adults can't do it, let alone children."},
         {"zh": "专家都说难，何况我们呢？", "pinyin": "Zhuānjiā dōu shuō nán, hékuàng wǒmen ne?", "en": "Even experts say it's hard, let alone us."},
         {"zh": "白天都找不到，何况晚上？", "pinyin": "Báitiān dōu zhǎo bu dào, hékuàng wǎnshang?", "en": "Can't even find it in daylight, let alone at night."},
     ]},

    {"name": "以免 so as to avoid (HSK 5 intro)", "name_zh": "以免", "hsk_level": 5, "category": "connector",
     "description": "States a preventive purpose: 带伞以免淋雨", "difficulty": 0.7,
     "examples": [
         {"zh": "带把伞，以免淋雨。", "pinyin": "Dài bǎ sǎn, yǐmiǎn lín yǔ.", "en": "Bring an umbrella so as to avoid getting rained on."},
         {"zh": "提前出发，以免堵车。", "pinyin": "Tíqián chūfā, yǐmiǎn dǔchē.", "en": "Leave early to avoid traffic jams."},
         {"zh": "多检查几遍，以免出错。", "pinyin": "Duō jiǎnchá jǐ biàn, yǐmiǎn chūcuò.", "en": "Check a few more times to avoid mistakes."},
     ]},

    {"name": "尚且...何况 even X, let alone Y", "name_zh": "尚且…何况", "hsk_level": 5, "category": "connector",
     "description": "Emphatic a fortiori: even X can't manage, how much less Y: 专家尚且不懂，何况我们", "difficulty": 0.8,
     "examples": [
         {"zh": "专家尚且不懂，何况我们呢？", "pinyin": "Zhuānjiā shàngqiě bù dǒng, hékuàng wǒmen ne?", "en": "Even experts don't understand, let alone us."},
         {"zh": "年轻人尚且觉得累，何况老人？", "pinyin": "Niánqīngrén shàngqiě juéde lèi, hékuàng lǎorén?", "en": "Even young people find it tiring, let alone the elderly."},
         {"zh": "本地人尚且迷路，何况外地人？", "pinyin": "Běndìrén shàngqiě mílù, hékuàng wàidìrén?", "en": "Even locals get lost, let alone outsiders."},
     ]},

    {"name": "势必 is bound to", "name_zh": "势必", "hsk_level": 5, "category": "particle",
     "description": "Indicates an inevitable outcome: 这势必影响结果", "difficulty": 0.7,
     "examples": [
         {"zh": "这势必影响最终结果。", "pinyin": "Zhè shìbì yǐngxiǎng zuìzhōng jiéguǒ.", "en": "This is bound to affect the final result."},
         {"zh": "不改革势必落后。", "pinyin": "Bù gǎigé shìbì luòhòu.", "en": "Without reform, falling behind is inevitable."},
         {"zh": "这样做势必引起争议。", "pinyin": "Zhèyàng zuò shìbì yǐnqǐ zhēngyì.", "en": "Doing it this way is bound to cause controversy."},
     ]},

    {"name": "然而 however", "name_zh": "然而", "hsk_level": 5, "category": "connector",
     "description": "Formal adversative connector introducing contrast: 然而事实并非如此", "difficulty": 0.7,
     "examples": [
         {"zh": "然而，事实并非如此。", "pinyin": "Rán'ér, shìshí bìngfēi rúcǐ.", "en": "However, the truth is not so."},
         {"zh": "他很努力，然而结果并不理想。", "pinyin": "Tā hěn nǔlì, rán'ér jiéguǒ bìng bù lǐxiǎng.", "en": "He worked very hard; however, the results were not ideal."},
         {"zh": "计划看起来很完美，然而执行起来很难。", "pinyin": "Jìhuà kàn qǐlái hěn wánměi, rán'ér zhíxíng qǐlái hěn nán.", "en": "The plan looks perfect; however, it's hard to execute."},
     ]},

    {"name": "反倒 on the contrary", "name_zh": "反倒", "hsk_level": 5, "category": "particle",
     "description": "Indicates an outcome opposite to expectation: 他反倒更开心了", "difficulty": 0.7,
     "examples": [
         {"zh": "被批评后，他反倒更开心了。", "pinyin": "Bèi pīpíng hòu, tā fǎndào gèng kāixīn le.", "en": "After being criticized, he was actually happier."},
         {"zh": "吃了药，病反倒更严重了。", "pinyin": "Chī le yào, bìng fǎndào gèng yánzhòng le.", "en": "After taking medicine, the illness actually got worse."},
         {"zh": "帮了忙，他反倒不高兴了。", "pinyin": "Bāng le máng, tā fǎndào bù gāoxìng le.", "en": "After being helped, he was unhappy instead."},
     ]},

    {"name": "况且 moreover (HSK 5 intro)", "name_zh": "况且", "hsk_level": 5, "category": "connector",
     "description": "Adds a further supporting reason: 太晚了，况且也没准备好", "difficulty": 0.7,
     "examples": [
         {"zh": "太晚了，况且也没准备好。", "pinyin": "Tài wǎn le, kuàngqiě yě méi zhǔnbèi hǎo.", "en": "It's too late, and besides, we're not prepared."},
         {"zh": "价格太高了，况且质量也不好。", "pinyin": "Jiàgé tài gāo le, kuàngqiě zhìliàng yě bù hǎo.", "en": "The price is too high, and moreover the quality isn't good."},
         {"zh": "路太远了，况且天也快黑了。", "pinyin": "Lù tài yuǎn le, kuàngqiě tiān yě kuài hēi le.", "en": "The road is too far, and besides, it's getting dark."},
     ]},

    {"name": "以便 in order to", "name_zh": "以便", "hsk_level": 5, "category": "connector",
     "description": "States an enabling purpose: 提前到，以便占个好位置", "difficulty": 0.7,
     "examples": [
         {"zh": "请提前到，以便占个好位置。", "pinyin": "Qǐng tíqián dào, yǐbiàn zhàn gè hǎo wèizhi.", "en": "Please arrive early in order to get a good seat."},
         {"zh": "我把地址发给你，以便你能找到。", "pinyin": "Wǒ bǎ dìzhǐ fā gěi nǐ, yǐbiàn nǐ néng zhǎodào.", "en": "I'll send you the address so that you can find it."},
         {"zh": "多带些现金，以便随时使用。", "pinyin": "Duō dài xiē xiànjīn, yǐbiàn suíshí shǐyòng.", "en": "Bring more cash so you can use it anytime."},
     ]},

    # ── HSK 6 (18 new) ──────────────────────────────────────────────

    {"name": "不至于 not so bad as to", "name_zh": "不至于", "hsk_level": 6, "category": "structure",
     "description": "Indicates a situation is not as extreme as suggested: 不至于那么严重吧", "difficulty": 0.7,
     "examples": [
         {"zh": "不至于那么严重吧？", "pinyin": "Bú zhìyú nàme yánzhòng ba?", "en": "It's not that serious, is it?"},
         {"zh": "迟到几分钟，不至于被开除吧。", "pinyin": "Chídào jǐ fēnzhōng, bú zhìyú bèi kāichú ba.", "en": "Being a few minutes late shouldn't get you fired."},
         {"zh": "一次失败不至于影响整个计划。", "pinyin": "Yí cì shībài bú zhìyú yǐngxiǎng zhěnggè jìhuà.", "en": "One failure shouldn't be bad enough to affect the whole plan."},
     ]},

    {"name": "难以 hard to", "name_zh": "难以", "hsk_level": 6, "category": "structure",
     "description": "Formal expression for difficulty: 难以置信", "difficulty": 0.7,
     "examples": [
         {"zh": "这简直难以置信。", "pinyin": "Zhè jiǎnzhí nányǐ zhìxìn.", "en": "This is simply hard to believe."},
         {"zh": "他的行为难以理解。", "pinyin": "Tā de xíngwéi nányǐ lǐjiě.", "en": "His behavior is hard to understand."},
         {"zh": "这种损失难以弥补。", "pinyin": "Zhè zhǒng sǔnshī nányǐ míbǔ.", "en": "This kind of loss is hard to make up for."},
     ]},

    {"name": "无非 nothing but (HSK 6 intro)", "name_zh": "无非", "hsk_level": 6, "category": "particle",
     "description": "Reduces something to its essence: 他的目的无非是挣钱", "difficulty": 0.8,
     "examples": [
         {"zh": "他的目的无非是挣钱。", "pinyin": "Tā de mùdì wúfēi shì zhèngqián.", "en": "His purpose is nothing but making money."},
         {"zh": "办法无非两个：要么接受，要么放弃。", "pinyin": "Bànfǎ wúfēi liǎng gè: yàome jiēshòu, yàome fàngqì.", "en": "There are only two options: either accept or give up."},
         {"zh": "他不高兴，无非是因为没被邀请。", "pinyin": "Tā bù gāoxìng, wúfēi shì yīnwèi méi bèi yāoqǐng.", "en": "He's unhappy — it's nothing more than not being invited."},
     ]},

    {"name": "迫不得已 forced by circumstances", "name_zh": "迫不得已", "hsk_level": 6, "category": "structure",
     "description": "Indicates being compelled to act with no alternative: 他迫不得已才离开", "difficulty": 0.8,
     "examples": [
         {"zh": "他迫不得已才离开了家乡。", "pinyin": "Tā pòbùdéyǐ cái líkāi le jiāxiāng.", "en": "He was forced by circumstances to leave his hometown."},
         {"zh": "迫不得已之下，她只好向别人借钱。", "pinyin": "Pòbùdéyǐ zhī xià, tā zhǐhǎo xiàng biérén jiè qián.", "en": "Having no other choice, she had to borrow money from others."},
         {"zh": "不是我想这样做，实在是迫不得已。", "pinyin": "Bú shì wǒ xiǎng zhèyàng zuò, shízài shì pòbùdéyǐ.", "en": "It's not that I wanted to do this — I truly had no choice."},
     ]},

    {"name": "以至于 to the extent that (HSK 6 usage)", "name_zh": "以至于", "hsk_level": 6, "category": "connector",
     "description": "Indicates a result reaching an extreme degree: 忙得以至于忘了吃饭", "difficulty": 0.8,
     "examples": [
         {"zh": "他忙得以至于忘了吃饭。", "pinyin": "Tā máng de yǐzhìyú wàng le chīfàn.", "en": "He was so busy that he forgot to eat."},
         {"zh": "雨下得很大，以至于路上都是积水。", "pinyin": "Yǔ xià de hěn dà, yǐzhìyú lùshang dōu shì jīshuǐ.", "en": "It rained so heavily that the roads were all flooded."},
         {"zh": "他太紧张了，以至于说不出话来。", "pinyin": "Tā tài jǐnzhāng le, yǐzhìyú shuō bu chū huà lái.", "en": "He was so nervous that he couldn't speak."},
     ]},

    {"name": "尚 still/yet (formal)", "name_zh": "尚", "hsk_level": 6, "category": "particle",
     "description": "Formal marker meaning 'still' or 'yet': 此事尚未解决", "difficulty": 0.8,
     "examples": [
         {"zh": "此事尚未解决。", "pinyin": "Cǐ shì shàng wèi jiějué.", "en": "This matter has not yet been resolved."},
         {"zh": "原因尚不清楚。", "pinyin": "Yuányīn shàng bù qīngchǔ.", "en": "The cause is still unclear."},
         {"zh": "结果尚待进一步确认。", "pinyin": "Jiéguǒ shàng dài jìnyíbù quèrèn.", "en": "The results still await further confirmation."},
     ]},

    {"name": "乃至 and even", "name_zh": "乃至", "hsk_level": 6, "category": "connector",
     "description": "Extends scope to an even further degree: 全国乃至全世界", "difficulty": 0.8,
     "examples": [
         {"zh": "这个品牌在全国乃至全世界都很有名。", "pinyin": "Zhège pǐnpái zài quánguó nǎizhì quán shìjiè dōu hěn yǒumíng.", "en": "This brand is famous nationwide and even worldwide."},
         {"zh": "影响了整个行业，乃至整个社会。", "pinyin": "Yǐngxiǎng le zhěnggè hángyè, nǎizhì zhěnggè shèhuì.", "en": "It affected the entire industry, and even the whole of society."},
         {"zh": "他的家人、朋友，乃至同事都很担心他。", "pinyin": "Tā de jiārén, péngyou, nǎizhì tóngshì dōu hěn dānxīn tā.", "en": "His family, friends, and even colleagues are all worried about him."},
     ]},

    {"name": "并非 not at all / is not", "name_zh": "并非", "hsk_level": 6, "category": "structure",
     "description": "Emphatic formal negation: 事实并非如此", "difficulty": 0.8,
     "examples": [
         {"zh": "事实并非如此。", "pinyin": "Shìshí bìngfēi rúcǐ.", "en": "The facts are not so."},
         {"zh": "这并非偶然，而是必然的结果。", "pinyin": "Zhè bìngfēi ǒurán, ér shì bìrán de jiéguǒ.", "en": "This is by no means a coincidence, but rather an inevitable result."},
         {"zh": "成功并非一朝一夕的事。", "pinyin": "Chénggōng bìngfēi yìzhāo yíxī de shì.", "en": "Success is by no means achieved overnight."},
     ]},

    {"name": "一旦...就 once...then", "name_zh": "一旦…就", "hsk_level": 6, "category": "connector",
     "description": "Full pattern for critical conditional with consequence: 一旦决定就不能改", "difficulty": 0.8,
     "examples": [
         {"zh": "一旦决定了，就不能再改了。", "pinyin": "Yídàn juédìng le, jiù bù néng zài gǎi le.", "en": "Once decided, it can't be changed."},
         {"zh": "一旦失去了信任，就很难恢复。", "pinyin": "Yídàn shīqù le xìnrèn, jiù hěn nán huīfù.", "en": "Once trust is lost, it's hard to recover."},
         {"zh": "一旦出了问题，就必须立刻处理。", "pinyin": "Yídàn chū le wèntí, jiù bìxū lìkè chǔlǐ.", "en": "Once a problem arises, it must be dealt with immediately."},
     ]},

    {"name": "出于 out of / based on", "name_zh": "出于", "hsk_level": 6, "category": "structure",
     "description": "Indicates motivation or basis for an action: 出于安全考虑", "difficulty": 0.8,
     "examples": [
         {"zh": "出于安全考虑，这条路被封了。", "pinyin": "Chūyú ānquán kǎolǜ, zhè tiáo lù bèi fēng le.", "en": "Out of safety considerations, this road was closed."},
         {"zh": "他出于好意才提醒你的。", "pinyin": "Tā chūyú hǎoyì cái tíxǐng nǐ de.", "en": "He reminded you out of good intentions."},
         {"zh": "出于对环境的保护，我们减少了用纸。", "pinyin": "Chūyú duì huánjìng de bǎohù, wǒmen jiǎnshǎo le yòng zhǐ.", "en": "Out of environmental protection, we reduced paper usage."},
     ]},

    {"name": "不惜 not hesitate to", "name_zh": "不惜", "hsk_level": 6, "category": "structure",
     "description": "Indicates willingness to pay any price: 他不惜一切代价", "difficulty": 0.8,
     "examples": [
         {"zh": "他不惜一切代价也要完成任务。", "pinyin": "Tā bùxī yíqiè dàijià yě yào wánchéng rènwu.", "en": "He'll spare no effort to complete the task."},
         {"zh": "为了孩子的教育，她不惜花重金。", "pinyin": "Wèile háizi de jiàoyù, tā bùxī huā zhòngjīn.", "en": "For her child's education, she spares no expense."},
         {"zh": "他不惜牺牲休息时间来加班。", "pinyin": "Tā bùxī xīshēng xiūxi shíjiān lái jiābān.", "en": "He doesn't hesitate to sacrifice rest time to work overtime."},
     ]},

    {"name": "可谓 can be called", "name_zh": "可谓", "hsk_level": 6, "category": "structure",
     "description": "Formal evaluative: what can be described as: 他的成就可谓辉煌", "difficulty": 0.8,
     "examples": [
         {"zh": "他的成就可谓辉煌。", "pinyin": "Tā de chéngjiù kěwèi huīhuáng.", "en": "His achievements can be called brilliant."},
         {"zh": "这次旅行可谓收获颇丰。", "pinyin": "Zhè cì lǚxíng kěwèi shōuhuò pō fēng.", "en": "This trip can be called quite fruitful."},
         {"zh": "这道菜可谓色香味俱全。", "pinyin": "Zhè dào cài kěwèi sè xiāng wèi jù quán.", "en": "This dish can be said to have it all — color, aroma, and flavor."},
     ]},

    {"name": "以致 so that (negative result)", "name_zh": "以致", "hsk_level": 6, "category": "connector",
     "description": "Introduces an undesirable consequence: 他太粗心，以致犯了大错", "difficulty": 0.8,
     "examples": [
         {"zh": "他太粗心了，以致犯了大错。", "pinyin": "Tā tài cūxīn le, yǐzhì fàn le dà cuò.", "en": "He was too careless, so much so that he made a big mistake."},
         {"zh": "管理不善，以致公司亏损严重。", "pinyin": "Guǎnlǐ bú shàn, yǐzhì gōngsī kuīsǔn yánzhòng.", "en": "Poor management led to severe company losses."},
         {"zh": "长期熬夜，以致身体出了问题。", "pinyin": "Chángqī áoyè, yǐzhì shēntǐ chū le wèntí.", "en": "Staying up late for a long time resulted in health problems."},
     ]},

    {"name": "与其 rather than (standalone)", "name_zh": "与其", "hsk_level": 6, "category": "connector",
     "description": "Introduces a less preferred option in comparison: 与其等待不如行动", "difficulty": 0.8,
     "examples": [
         {"zh": "与其等待，不如立刻行动。", "pinyin": "Yǔqí děngdài, bùrú lìkè xíngdòng.", "en": "Rather than wait, it's better to act immediately."},
         {"zh": "与其担心失败，不如认真准备。", "pinyin": "Yǔqí dānxīn shībài, bùrú rènzhēn zhǔnbèi.", "en": "Rather than worry about failure, prepare carefully instead."},
         {"zh": "与其花时间抱怨，不如想办法解决。", "pinyin": "Yǔqí huā shíjiān bàoyuàn, bùrú xiǎng bànfǎ jiějué.", "en": "Rather than spend time complaining, find a solution instead."},
     ]},

    {"name": "非...不可 must / have to", "name_zh": "非…不可", "hsk_level": 6, "category": "structure",
     "description": "Double-negative emphasis meaning 'absolutely must': 这件事非做不可", "difficulty": 0.8,
     "examples": [
         {"zh": "这件事非做不可。", "pinyin": "Zhè jiàn shì fēi zuò bùkě.", "en": "This matter absolutely must be done."},
         {"zh": "这个问题非解决不可。", "pinyin": "Zhège wèntí fēi jiějué bùkě.", "en": "This problem must be solved no matter what."},
         {"zh": "他非要亲自去不可。", "pinyin": "Tā fēi yào qīnzì qù bùkě.", "en": "He insists on going in person."},
     ]},

    {"name": "莫过于 nothing more than / the greatest is", "name_zh": "莫过于", "hsk_level": 6, "category": "structure",
     "description": "Superlative structure meaning 'nothing surpasses': 最大的幸福莫过于健康", "difficulty": 0.9,
     "examples": [
         {"zh": "最大的幸福莫过于健康。", "pinyin": "Zuì dà de xìngfú mòguòyú jiànkāng.", "en": "The greatest happiness is nothing more than health."},
         {"zh": "最好的老师莫过于经验。", "pinyin": "Zuì hǎo de lǎoshī mòguòyú jīngyàn.", "en": "The best teacher is nothing other than experience."},
         {"zh": "人生最痛苦的事莫过于失去亲人。", "pinyin": "Rénshēng zuì tòngkǔ de shì mòguòyú shīqù qīnrén.", "en": "The most painful thing in life is nothing more than losing a loved one."},
     ]},

    {"name": "不得而知 unknown / cannot be known", "name_zh": "不得而知", "hsk_level": 6, "category": "structure",
     "description": "Formal expression meaning the truth is unknowable: 原因不得而知", "difficulty": 0.9,
     "examples": [
         {"zh": "原因不得而知。", "pinyin": "Yuányīn bùdé ér zhī.", "en": "The reason is unknown."},
         {"zh": "他为什么突然辞职，外人不得而知。", "pinyin": "Tā wèishéme tūrán cízhí, wàirén bùdé ér zhī.", "en": "Why he suddenly resigned, outsiders have no way of knowing."},
         {"zh": "事情的真相至今不得而知。", "pinyin": "Shìqing de zhēnxiàng zhìjīn bùdé ér zhī.", "en": "The truth of the matter remains unknown to this day."},
     ]},

    {"name": "有所 somewhat / to some extent", "name_zh": "有所", "hsk_level": 6, "category": "structure",
     "description": "Formal modifier indicating partial change: 情况有所改善", "difficulty": 0.8,
     "examples": [
         {"zh": "情况有所改善。", "pinyin": "Qíngkuàng yǒusuǒ gǎishàn.", "en": "The situation has somewhat improved."},
         {"zh": "他的态度有所转变。", "pinyin": "Tā de tàidù yǒusuǒ zhuǎnbiàn.", "en": "His attitude has changed somewhat."},
         {"zh": "经过治疗，病情有所好转。", "pinyin": "Jīngguò zhìliáo, bìngqíng yǒusuǒ hǎozhuǎn.", "en": "After treatment, the condition has improved to some extent."},
     ]},
]
