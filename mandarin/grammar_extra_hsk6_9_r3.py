"""Extra HSK 6-9 grammar points, round 3 -- filling remaining gaps from official syllabus."""

EXTRA_GRAMMAR_HSK6_9_R3 = [
    # =========================================================================
    # HSK 6 -- additional grammar points (34)
    # =========================================================================

    {"name": "以致 with the result that (HSK6)", "name_zh": "以致(HSK6)", "hsk_level": 6, "category": "connector",
     "description": "Connects a cause to an undesirable result: 他粗心大意，以致犯了大错",
     "difficulty": 0.7,
     "examples": [
         {"zh": "他长期熬夜，以致身体越来越差。", "pinyin": "Tā chángqī áoyè, yǐzhì shēntǐ yuè lái yuè chà.", "en": "He stayed up late for a long time, with the result that his health got worse and worse."},
         {"zh": "管理不善，以致公司损失惨重。", "pinyin": "Guǎnlǐ bú shàn, yǐzhì gōngsī sǔnshī cǎnzhòng.", "en": "Poor management resulted in heavy losses for the company."},
         {"zh": "她太紧张了，以致说话都结巴了。", "pinyin": "Tā tài jǐnzhāng le, yǐzhì shuōhuà dōu jiēba le.", "en": "She was so nervous that she started to stutter."},
     ]},

    {"name": "有所+V have somewhat V-ed", "name_zh": "有所+V", "hsk_level": 6, "category": "structure",
     "description": "Formal expression meaning 'somewhat' or 'to some degree' before a verb: 有所改善",
     "difficulty": 0.7,
     "examples": [
         {"zh": "经过治疗，他的病情有所好转。", "pinyin": "Jīngguò zhìliáo, tā de bìngqíng yǒusuǒ hǎozhuǎn.", "en": "After treatment, his condition has somewhat improved."},
         {"zh": "最近物价有所上涨。", "pinyin": "Zuìjìn wùjià yǒusuǒ shàngzhǎng.", "en": "Prices have risen somewhat recently."},
         {"zh": "这个方案有所调整。", "pinyin": "Zhège fāng'àn yǒusuǒ tiáozhěng.", "en": "This plan has been somewhat adjusted."},
         {"zh": "他的态度有所改变。", "pinyin": "Tā de tàidu yǒusuǒ gǎibiàn.", "en": "His attitude has changed somewhat."},
     ]},

    {"name": "加以+V apply/carry out", "name_zh": "加以+V", "hsk_level": 6, "category": "structure",
     "description": "Formal construction meaning to apply an action to something: 加以改正",
     "difficulty": 0.7,
     "examples": [
         {"zh": "对于错误，我们应该加以改正。", "pinyin": "Duìyú cuòwù, wǒmen yīnggāi jiāyǐ gǎizhèng.", "en": "We should correct our mistakes."},
         {"zh": "这些问题需要加以解决。", "pinyin": "Zhèxiē wèntí xūyào jiāyǐ jiějué.", "en": "These problems need to be resolved."},
         {"zh": "请对此加以说明。", "pinyin": "Qǐng duì cǐ jiāyǐ shuōmíng.", "en": "Please provide an explanation for this."},
     ]},

    {"name": "予以+V give/grant (formal)", "name_zh": "予以+V", "hsk_level": 6, "category": "structure",
     "description": "Formal way to grant or bestow an action: 予以批准",
     "difficulty": 0.7,
     "examples": [
         {"zh": "对违规行为，应予以处罚。", "pinyin": "Duì wéiguī xíngwéi, yīng yǔyǐ chǔfá.", "en": "Violations should be punished."},
         {"zh": "我们对此予以高度重视。", "pinyin": "Wǒmen duì cǐ yǔyǐ gāodù zhòngshì.", "en": "We attach great importance to this."},
         {"zh": "他的申请已予以批准。", "pinyin": "Tā de shēnqǐng yǐ yǔyǐ pīzhǔn.", "en": "His application has been approved."},
     ]},

    {"name": "得以 manage to / able to", "name_zh": "得以", "hsk_level": 6, "category": "structure",
     "description": "Indicates that conditions enabled something to happen: 问题得以解决",
     "difficulty": 0.7,
     "examples": [
         {"zh": "在大家的帮助下，问题得以解决。", "pinyin": "Zài dàjiā de bāngzhù xià, wèntí déyǐ jiějué.", "en": "With everyone's help, the problem was able to be resolved."},
         {"zh": "这项技术使病人得以康复。", "pinyin": "Zhè xiàng jìshù shǐ bìngrén déyǐ kāngfù.", "en": "This technology enabled the patient to recover."},
         {"zh": "经过改革，经济得以快速发展。", "pinyin": "Jīngguò gǎigé, jīngjì déyǐ kuàisù fāzhǎn.", "en": "Through reform, the economy was able to develop rapidly."},
     ]},

    {"name": "给以/给予 give/grant (formal written)", "name_zh": "给予", "hsk_level": 6, "category": "structure",
     "description": "Formal written form of giving or bestowing: 给予支持",
     "difficulty": 0.7,
     "examples": [
         {"zh": "请给予我们更多的时间。", "pinyin": "Qǐng jǐyǔ wǒmen gèng duō de shíjiān.", "en": "Please give us more time."},
         {"zh": "政府给予灾区大量援助。", "pinyin": "Zhèngfǔ jǐyǔ zāiqū dàliàng yuánzhù.", "en": "The government gave a large amount of aid to the disaster area."},
         {"zh": "老师给予了学生很大的鼓励。", "pinyin": "Lǎoshī jǐyǔ le xuéshēng hěn dà de gǔlì.", "en": "The teacher gave the students great encouragement."},
     ]},

    {"name": "为...所 passive (literary)", "name_zh": "为…所(文言)", "hsk_level": 6, "category": "structure",
     "description": "Literary passive construction: 为人所知 (known by people)",
     "difficulty": 0.75,
     "examples": [
         {"zh": "他的事迹为人所知。", "pinyin": "Tā de shìjì wéi rén suǒ zhī.", "en": "His deeds are known by people."},
         {"zh": "不要为表面现象所迷惑。", "pinyin": "Bú yào wéi biǎomiàn xiànxiàng suǒ míhuo.", "en": "Don't be misled by surface appearances."},
         {"zh": "这部作品为世人所称赞。", "pinyin": "Zhè bù zuòpǐn wéi shìrén suǒ chēngzàn.", "en": "This work is praised by the world."},
     ]},

    {"name": "要不 otherwise/or else", "name_zh": "要不", "hsk_level": 6, "category": "connector",
     "description": "Colloquial way to say otherwise or suggest an alternative: 要不我们走吧",
     "difficulty": 0.6,
     "examples": [
         {"zh": "快点走，要不就来不及了。", "pinyin": "Kuài diǎn zǒu, yàobù jiù láibují le.", "en": "Hurry up, otherwise we won't make it."},
         {"zh": "要不我们换个地方吃饭？", "pinyin": "Yàobù wǒmen huàn gè dìfang chīfàn?", "en": "How about we eat somewhere else?"},
         {"zh": "你先休息，要不明天会很累。", "pinyin": "Nǐ xiān xiūxi, yàobù míngtiān huì hěn lèi.", "en": "Rest first, otherwise you'll be very tired tomorrow."},
     ]},

    {"name": "无所谓 doesn't matter", "name_zh": "无所谓", "hsk_level": 6, "category": "structure",
     "description": "Expresses indifference or that something is not important: 我无所谓",
     "difficulty": 0.65,
     "examples": [
         {"zh": "去哪儿吃饭我无所谓。", "pinyin": "Qù nǎr chīfàn wǒ wúsuǒwèi.", "en": "I don't care where we eat."},
         {"zh": "他对别人的看法无所谓。", "pinyin": "Tā duì biérén de kànfǎ wúsuǒwèi.", "en": "He doesn't care about other people's opinions."},
         {"zh": "成功或失败，她似乎无所谓。", "pinyin": "Chénggōng huò shībài, tā sìhū wúsuǒwèi.", "en": "Success or failure, she seems indifferent."},
     ]},

    {"name": "何以 how come (formal HSK6)", "name_zh": "何以(HSK6)", "hsk_level": 6, "category": "structure",
     "description": "Formal/literary way to ask 'how' or 'why': 何以见得",
     "difficulty": 0.75,
     "examples": [
         {"zh": "何以见得他说的是真的？", "pinyin": "Héyǐ jiàndé tā shuō de shì zhēn de?", "en": "How can you tell what he said is true?"},
         {"zh": "你何以如此肯定？", "pinyin": "Nǐ héyǐ rúcǐ kěndìng?", "en": "How can you be so certain?"},
         {"zh": "何以证明你的观点？", "pinyin": "Héyǐ zhèngmíng nǐ de guāndiǎn?", "en": "How can you prove your viewpoint?"},
     ]},

    {"name": "乃 is/indeed (HSK6 literary)", "name_zh": "乃(HSK6)", "hsk_level": 6, "category": "structure",
     "description": "Literary copula or emphasis marker: 此乃 means 'this is indeed'",
     "difficulty": 0.75,
     "examples": [
         {"zh": "此乃当务之急。", "pinyin": "Cǐ nǎi dāngwù zhī jí.", "en": "This is indeed a matter of utmost urgency."},
         {"zh": "这乃是多年努力的结果。", "pinyin": "Zhè nǎi shì duō nián nǔlì de jiéguǒ.", "en": "This is indeed the result of many years of effort."},
         {"zh": "诚信乃立身之本。", "pinyin": "Chéngxìn nǎi lìshēn zhī běn.", "en": "Integrity is the foundation of one's character."},
     ]},

    {"name": "以求 in order to seek", "name_zh": "以求", "hsk_level": 6, "category": "connector",
     "description": "Purpose clause meaning 'in order to seek/attain': 努力学习以求进步",
     "difficulty": 0.7,
     "examples": [
         {"zh": "他努力学习，以求取得好成绩。", "pinyin": "Tā nǔlì xuéxí, yǐqiú qǔdé hǎo chéngjì.", "en": "He studies hard in order to achieve good results."},
         {"zh": "公司不断创新，以求在竞争中胜出。", "pinyin": "Gōngsī búduàn chuàngxīn, yǐqiú zài jìngzhēng zhōng shèngchū.", "en": "The company constantly innovates in order to win in the competition."},
         {"zh": "她降低了价格，以求尽快卖出。", "pinyin": "Tā jiàngdī le jiàgé, yǐqiú jǐnkuài màichū.", "en": "She lowered the price in order to sell as quickly as possible."},
     ]},

    {"name": "有助于 helpful to/conducive to", "name_zh": "有助于", "hsk_level": 6, "category": "structure",
     "description": "Indicates something is beneficial or conducive to a goal: 有助于健康",
     "difficulty": 0.65,
     "examples": [
         {"zh": "适当运动有助于身体健康。", "pinyin": "Shìdàng yùndòng yǒuzhùyú shēntǐ jiànkāng.", "en": "Moderate exercise is conducive to physical health."},
         {"zh": "多阅读有助于提高写作水平。", "pinyin": "Duō yuèdú yǒuzhùyú tígāo xiězuò shuǐpíng.", "en": "Reading more helps improve writing skills."},
         {"zh": "这项政策有助于经济发展。", "pinyin": "Zhè xiàng zhèngcè yǒuzhùyú jīngjì fāzhǎn.", "en": "This policy is conducive to economic development."},
     ]},

    {"name": "有利于 beneficial to", "name_zh": "有利于", "hsk_level": 6, "category": "structure",
     "description": "Indicates something is favorable or advantageous: 有利于合作",
     "difficulty": 0.65,
     "examples": [
         {"zh": "良好的沟通有利于团队合作。", "pinyin": "Liánghǎo de gōutōng yǒulìyú tuánduì hézuò.", "en": "Good communication is beneficial to teamwork."},
         {"zh": "这个决定有利于公司的长远发展。", "pinyin": "Zhège juédìng yǒulìyú gōngsī de chángyuǎn fāzhǎn.", "en": "This decision is beneficial to the company's long-term development."},
         {"zh": "充足的睡眠有利于学习效率。", "pinyin": "Chōngzú de shuìmián yǒulìyú xuéxí xiàolǜ.", "en": "Sufficient sleep is beneficial to learning efficiency."},
     ]},

    {"name": "无益于 not beneficial to", "name_zh": "无益于", "hsk_level": 6, "category": "structure",
     "description": "Indicates something is unhelpful or detrimental: 无益于解决问题",
     "difficulty": 0.7,
     "examples": [
         {"zh": "抱怨无益于解决问题。", "pinyin": "Bàoyuàn wúyìyú jiějué wèntí.", "en": "Complaining is not beneficial to solving the problem."},
         {"zh": "过度焦虑无益于身心健康。", "pinyin": "Guòdù jiāolǜ wúyìyú shēnxīn jiànkāng.", "en": "Excessive anxiety is not beneficial to physical and mental health."},
         {"zh": "互相指责无益于团队合作。", "pinyin": "Hùxiāng zhǐzé wúyìyú tuánduì hézuò.", "en": "Blaming each other is not beneficial to teamwork."},
     ]},

    {"name": "至今 to this day/up to now", "name_zh": "至今", "hsk_level": 6, "category": "structure",
     "description": "Indicates something continues from the past to the present: 至今仍然",
     "difficulty": 0.65,
     "examples": [
         {"zh": "这个传统至今仍然保留着。", "pinyin": "Zhège chuántǒng zhìjīn réngrán bǎoliú zhe.", "en": "This tradition is still preserved to this day."},
         {"zh": "他离开至今已经三年了。", "pinyin": "Tā líkāi zhìjīn yǐjīng sān nián le.", "en": "It has been three years since he left."},
         {"zh": "那件事至今让我难以忘怀。", "pinyin": "Nà jiàn shì zhìjīn ràng wǒ nányǐ wànghuái.", "en": "That matter still makes it hard for me to forget to this day."},
     ]},

    {"name": "由此可见 from this it can be seen", "name_zh": "由此可见", "hsk_level": 6, "category": "connector",
     "description": "Discourse connector drawing a conclusion from evidence: 由此可见问题的严重性",
     "difficulty": 0.7,
     "examples": [
         {"zh": "由此可见，教育的重要性不可忽视。", "pinyin": "Yóucǐ kějiàn, jiàoyù de zhòngyàoxìng bùkě hūshì.", "en": "From this it can be seen that the importance of education cannot be ignored."},
         {"zh": "由此可见，他的判断是正确的。", "pinyin": "Yóucǐ kějiàn, tā de pànduàn shì zhèngquè de.", "en": "From this it can be seen that his judgment was correct."},
         {"zh": "由此可见，合作比竞争更有效。", "pinyin": "Yóucǐ kějiàn, hézuò bǐ jìngzhēng gèng yǒuxiào.", "en": "From this it can be seen that cooperation is more effective than competition."},
     ]},

    {"name": "综上所述 in summary (of above)", "name_zh": "综上所述", "hsk_level": 6, "category": "connector",
     "description": "Formal discourse marker summarizing preceding arguments: used in essays and reports",
     "difficulty": 0.7,
     "examples": [
         {"zh": "综上所述，我们应该采取积极的措施。", "pinyin": "Zōngshàng suǒshù, wǒmen yīnggāi cǎiqǔ jījí de cuòshī.", "en": "In summary, we should take proactive measures."},
         {"zh": "综上所述，这个方案是可行的。", "pinyin": "Zōngshàng suǒshù, zhège fāng'àn shì kěxíng de.", "en": "In summary, this plan is feasible."},
         {"zh": "综上所述，改革势在必行。", "pinyin": "Zōngshàng suǒshù, gǎigé shì zài bì xíng.", "en": "In summary, reform is imperative."},
     ]},

    {"name": "一言以蔽之 in a word/to sum up", "name_zh": "一言以蔽之", "hsk_level": 6, "category": "connector",
     "description": "Classical-style summarizing phrase meaning 'to put it in one word': literary but used in modern formal writing",
     "difficulty": 0.75,
     "examples": [
         {"zh": "一言以蔽之，就是要脚踏实地。", "pinyin": "Yì yán yǐ bì zhī, jiùshì yào jiǎotàshídì.", "en": "To sum it up in a word: be down-to-earth."},
         {"zh": "一言以蔽之，质量比数量更重要。", "pinyin": "Yì yán yǐ bì zhī, zhìliàng bǐ shùliàng gèng zhòngyào.", "en": "In a word, quality is more important than quantity."},
         {"zh": "一言以蔽之，成功需要坚持。", "pinyin": "Yì yán yǐ bì zhī, chénggōng xūyào jiānchí.", "en": "To put it in a word, success requires persistence."},
     ]},

    {"name": "可见 it is evident (HSK6 discourse)", "name_zh": "可见(HSK6)", "hsk_level": 6, "category": "connector",
     "description": "Discourse connector meaning 'it is evident that' or 'this shows that'",
     "difficulty": 0.65,
     "examples": [
         {"zh": "他连这么简单的题都不会，可见他根本没复习。", "pinyin": "Tā lián zhème jiǎndān de tí dōu bú huì, kějiàn tā gēnběn méi fùxí.", "en": "He can't even do such a simple problem; it's evident he didn't review at all."},
         {"zh": "可见，这个问题并不简单。", "pinyin": "Kějiàn, zhège wèntí bìng bù jiǎndān.", "en": "It can be seen that this problem is not simple."},
         {"zh": "大家都支持他，可见他很受欢迎。", "pinyin": "Dàjiā dōu zhīchí tā, kějiàn tā hěn shòu huānyíng.", "en": "Everyone supports him; it's evident he is very popular."},
     ]},

    {"name": "不至于 not go so far as to (HSK6)", "name_zh": "不至于(HSK6)", "hsk_level": 6, "category": "structure",
     "description": "Indicates something will not reach a certain extreme: 不至于那么严重",
     "difficulty": 0.65,
     "examples": [
         {"zh": "事情不至于那么严重吧。", "pinyin": "Shìqing bú zhìyú nàme yánzhòng ba.", "en": "Things can't be that serious, right?"},
         {"zh": "他虽然生气，但不至于不理你。", "pinyin": "Tā suīrán shēngqì, dàn bú zhìyú bù lǐ nǐ.", "en": "Although he's angry, it won't go so far as him ignoring you."},
         {"zh": "迟到几分钟不至于被开除吧？", "pinyin": "Chídào jǐ fēnzhōng bú zhìyú bèi kāichú ba?", "en": "Being a few minutes late wouldn't go so far as getting fired, would it?"},
     ]},

    {"name": "何处 where (literary)", "name_zh": "何处", "hsk_level": 6, "category": "structure",
     "description": "Literary interrogative for 'where': 何处是归途",
     "difficulty": 0.75,
     "examples": [
         {"zh": "人生何处不相逢。", "pinyin": "Rénshēng héchù bù xiāngféng.", "en": "Where in life will one not meet again?"},
         {"zh": "此情此景，何处可寻？", "pinyin": "Cǐ qíng cǐ jǐng, héchù kě xún?", "en": "Where can one find such feelings and scenery?"},
         {"zh": "故乡在何处？", "pinyin": "Gùxiāng zài héchù?", "en": "Where is my homeland?"},
     ]},

    {"name": "与其说...不如说 rather than say...better to say (HSK6)", "name_zh": "与其说…不如说(HSK6)", "hsk_level": 6, "category": "comparison",
     "description": "Corrective comparison reframing a description: 与其说聪明不如说勤奋",
     "difficulty": 0.7,
     "examples": [
         {"zh": "与其说他聪明，不如说他勤奋。", "pinyin": "Yǔqí shuō tā cōngmíng, bùrú shuō tā qínfèn.", "en": "Rather than say he is smart, better to say he is hardworking."},
         {"zh": "与其说是运气，不如说是实力。", "pinyin": "Yǔqí shuō shì yùnqi, bùrú shuō shì shílì.", "en": "Rather than call it luck, better to call it ability."},
         {"zh": "与其说她在休息，不如说她在思考。", "pinyin": "Yǔqí shuō tā zài xiūxi, bùrú shuō tā zài sīkǎo.", "en": "Rather than say she is resting, better to say she is thinking."},
     ]},

    {"name": "以免 in order to avoid (HSK6)", "name_zh": "以免(HSK6)", "hsk_level": 6, "category": "connector",
     "description": "Purpose clause expressing avoidance: 提前出发以免迟到",
     "difficulty": 0.65,
     "examples": [
         {"zh": "请提前出发，以免迟到。", "pinyin": "Qǐng tíqián chūfā, yǐmiǎn chídào.", "en": "Please leave early in order to avoid being late."},
         {"zh": "把窗户关上，以免着凉。", "pinyin": "Bǎ chuānghu guānshang, yǐmiǎn zháoliáng.", "en": "Close the window so as to avoid catching a cold."},
         {"zh": "多检查几遍，以免出错。", "pinyin": "Duō jiǎnchá jǐ biàn, yǐmiǎn chūcuò.", "en": "Check it a few more times to avoid making mistakes."},
     ]},

    {"name": "万一 in case/just in case (HSK6)", "name_zh": "万一(HSK6)", "hsk_level": 6, "category": "connector",
     "description": "Introduces a hypothetical worst-case scenario: 万一下雨怎么办",
     "difficulty": 0.6,
     "examples": [
         {"zh": "带把伞吧，万一下雨呢。", "pinyin": "Dài bǎ sǎn ba, wànyī xià yǔ ne.", "en": "Bring an umbrella, just in case it rains."},
         {"zh": "万一他不同意，我们怎么办？", "pinyin": "Wànyī tā bù tóngyì, wǒmen zěnme bàn?", "en": "What if he doesn't agree, what do we do?"},
         {"zh": "做好准备，万一出了问题也不慌。", "pinyin": "Zuòhǎo zhǔnbèi, wànyī chū le wèntí yě bù huāng.", "en": "Be well prepared so you won't panic if something goes wrong."},
     ]},

    {"name": "难免 hard to avoid (HSK6)", "name_zh": "难免(HSK6)", "hsk_level": 6, "category": "structure",
     "description": "Expresses that something is inevitable or hard to avoid: 难免犯错",
     "difficulty": 0.65,
     "examples": [
         {"zh": "刚开始学，难免会犯错。", "pinyin": "Gāng kāishǐ xué, nánmiǎn huì fàncuò.", "en": "When you're just starting to learn, it's hard to avoid making mistakes."},
         {"zh": "长时间工作，难免感到疲劳。", "pinyin": "Cháng shíjiān gōngzuò, nánmiǎn gǎndào píláo.", "en": "Working for a long time, it's inevitable to feel tired."},
         {"zh": "第一次做，难免有些紧张。", "pinyin": "Dì yī cì zuò, nánmiǎn yǒuxiē jǐnzhāng.", "en": "Doing it for the first time, it's natural to feel a bit nervous."},
     ]},

    {"name": "势必 bound to/certainly (HSK6)", "name_zh": "势必(HSK6)", "hsk_level": 6, "category": "structure",
     "description": "Indicates an inevitable outcome: 势必导致失败",
     "difficulty": 0.7,
     "examples": [
         {"zh": "这样做势必引起争议。", "pinyin": "Zhèyàng zuò shìbì yǐnqǐ zhēngyì.", "en": "Doing it this way will certainly cause controversy."},
         {"zh": "忽视环保势必付出代价。", "pinyin": "Hūshì huánbǎo shìbì fùchū dàijià.", "en": "Ignoring environmental protection will inevitably come at a cost."},
         {"zh": "缺乏沟通势必导致误解。", "pinyin": "Quēfá gōutōng shìbì dǎozhì wùjiě.", "en": "Lack of communication is bound to lead to misunderstandings."},
     ]},

    {"name": "未免 a bit too/rather (HSK6)", "name_zh": "未免(HSK6)", "hsk_level": 6, "category": "structure",
     "description": "Mild criticism that something goes a bit too far: 未免太过分了",
     "difficulty": 0.7,
     "examples": [
         {"zh": "你这样说未免太过分了。", "pinyin": "Nǐ zhèyàng shuō wèimiǎn tài guòfèn le.", "en": "What you said is a bit too much."},
         {"zh": "这个要求未免有些苛刻。", "pinyin": "Zhège yāoqiú wèimiǎn yǒuxiē kēkè.", "en": "This requirement is rather harsh."},
         {"zh": "现在就下结论未免为时过早。", "pinyin": "Xiànzài jiù xià jiélùn wèimiǎn wéishí guòzǎo.", "en": "Drawing a conclusion now is rather premature."},
     ]},

    {"name": "大不了 at worst/big deal", "name_zh": "大不了", "hsk_level": 6, "category": "structure",
     "description": "Colloquial expression meaning 'at worst' or dismissing consequences: 大不了重来",
     "difficulty": 0.6,
     "examples": [
         {"zh": "大不了重新来过。", "pinyin": "Dàbuliǎo chóngxīn láiguò.", "en": "At worst, we start over."},
         {"zh": "考不过大不了再考一次。", "pinyin": "Kǎo bú guò dàbuliǎo zài kǎo yí cì.", "en": "If I don't pass, at worst I'll take the exam again."},
         {"zh": "失败了大不了从头再来。", "pinyin": "Shībài le dàbuliǎo cóngtóu zài lái.", "en": "If we fail, the worst that can happen is starting from scratch."},
     ]},

    {"name": "罢了 that's all/merely", "name_zh": "罢了", "hsk_level": 6, "category": "particle",
     "description": "Sentence-final particle downplaying significance: 开玩笑罢了",
     "difficulty": 0.65,
     "examples": [
         {"zh": "我只是开个玩笑罢了。", "pinyin": "Wǒ zhǐshì kāi gè wánxiào bàle.", "en": "I was just joking, that's all."},
         {"zh": "这不过是个小问题罢了。", "pinyin": "Zhè búguò shì gè xiǎo wèntí bàle.", "en": "This is merely a small problem, that's all."},
         {"zh": "他随便说说罢了，你别当真。", "pinyin": "Tā suíbiàn shuōshuo bàle, nǐ bié dàngzhēn.", "en": "He was just saying it casually; don't take it seriously."},
     ]},

    {"name": "不妨 might as well (HSK6)", "name_zh": "不妨(HSK6)", "hsk_level": 6, "category": "structure",
     "description": "Gentle suggestion meaning 'might as well' or 'there is no harm in': 不妨考虑一下",
     "difficulty": 0.65,
     "examples": [
         {"zh": "你不妨考虑一下他的建议。", "pinyin": "Nǐ bùfáng kǎolǜ yíxià tā de jiànyì.", "en": "You might as well consider his suggestion."},
         {"zh": "不妨换个角度思考这个问题。", "pinyin": "Bùfáng huàn gè jiǎodù sīkǎo zhège wèntí.", "en": "You might as well think about this problem from a different angle."},
         {"zh": "有时间的话，不妨去看看。", "pinyin": "Yǒu shíjiān de huà, bùfáng qù kànkan.", "en": "If you have time, you might as well go take a look."},
     ]},

    {"name": "索性 simply/might as well (decisive)", "name_zh": "索性", "hsk_level": 6, "category": "structure",
     "description": "Indicates a decisive action, often after frustration: 索性不去了",
     "difficulty": 0.65,
     "examples": [
         {"zh": "既然等不到车，索性走路去吧。", "pinyin": "Jìrán děng bú dào chē, suǒxìng zǒulù qù ba.", "en": "Since we can't wait for the bus, let's just walk."},
         {"zh": "雨下个不停，她索性不出门了。", "pinyin": "Yǔ xià gè bù tíng, tā suǒxìng bù chūmén le.", "en": "The rain wouldn't stop, so she simply didn't go out."},
         {"zh": "想来想去，他索性辞职了。", "pinyin": "Xiǎng lái xiǎng qù, tā suǒxìng cízhí le.", "en": "After thinking it over, he simply resigned."},
     ]},

    {"name": "固然 admittedly/it is true that (HSK6 standalone)", "name_zh": "固然(单用)", "hsk_level": 6, "category": "connector",
     "description": "Concedes a point before introducing a counterargument: 固然重要，但...",
     "difficulty": 0.7,
     "examples": [
         {"zh": "钱固然重要，但健康更重要。", "pinyin": "Qián gùrán zhòngyào, dàn jiànkāng gèng zhòngyào.", "en": "Money is admittedly important, but health is more important."},
         {"zh": "他的方法固然有效，但成本太高。", "pinyin": "Tā de fāngfǎ gùrán yǒuxiào, dàn chéngběn tài gāo.", "en": "His method is admittedly effective, but the cost is too high."},
         {"zh": "经验固然宝贵，但不能固步自封。", "pinyin": "Jīngyàn gùrán bǎoguì, dàn bù néng gùbùzìfēng.", "en": "Experience is admittedly valuable, but one mustn't be complacent."},
     ]},

    {"name": "即便 even if (formal)", "name_zh": "即便", "hsk_level": 6, "category": "connector",
     "description": "Formal synonym of 即使, introducing a concessive condition: 即便如此",
     "difficulty": 0.7,
     "examples": [
         {"zh": "即便困难重重，我们也不会放弃。", "pinyin": "Jíbiàn kùnnán chóngchóng, wǒmen yě bú huì fàngqì.", "en": "Even if difficulties are many, we will not give up."},
         {"zh": "即便他不来，我们也照常开会。", "pinyin": "Jíbiàn tā bù lái, wǒmen yě zhàocháng kāihuì.", "en": "Even if he doesn't come, we will hold the meeting as usual."},
         {"zh": "即便如此，她依然坚持自己的立场。", "pinyin": "Jíbiàn rúcǐ, tā yīrán jiānchí zìjǐ de lìchǎng.", "en": "Even so, she still maintained her position."},
     ]},

    # =========================================================================
    # HSK 7 -- additional grammar points (18)
    # =========================================================================

    {"name": "极为 extremely (formal)", "name_zh": "极为", "hsk_level": 7, "category": "structure",
     "description": "Formal adverb meaning 'extremely': 极为重要",
     "difficulty": 0.75,
     "examples": [
         {"zh": "这项发现极为重要。", "pinyin": "Zhè xiàng fāxiàn jíwéi zhòngyào.", "en": "This discovery is extremely important."},
         {"zh": "他对此事极为不满。", "pinyin": "Tā duì cǐ shì jíwéi bùmǎn.", "en": "He is extremely dissatisfied with this matter."},
         {"zh": "该地区的生态环境极为脆弱。", "pinyin": "Gāi dìqū de shēngtài huánjìng jíwéi cuìruò.", "en": "The ecological environment of this region is extremely fragile."},
     ]},

    {"name": "颇 rather/quite (literary)", "name_zh": "颇", "hsk_level": 7, "category": "structure",
     "description": "Literary adverb meaning 'rather' or 'quite': 颇有道理",
     "difficulty": 0.75,
     "examples": [
         {"zh": "他的话颇有道理。", "pinyin": "Tā de huà pō yǒu dàolǐ.", "en": "What he said is quite reasonable."},
         {"zh": "这篇文章颇受好评。", "pinyin": "Zhè piān wénzhāng pō shòu hǎopíng.", "en": "This article received quite favorable reviews."},
         {"zh": "他在学术界颇有影响力。", "pinyin": "Tā zài xuéshùjiè pō yǒu yǐngxiǎnglì.", "en": "He is quite influential in academic circles."},
     ]},

    {"name": "何 what/where (literary interrogative)", "name_zh": "何(疑问)", "hsk_level": 7, "category": "particle",
     "description": "Literary interrogative pronoun meaning 'what' or 'where': 何必, 何时",
     "difficulty": 0.8,
     "examples": [
         {"zh": "你何时才能理解？", "pinyin": "Nǐ héshí cái néng lǐjiě?", "en": "When will you be able to understand?"},
         {"zh": "此举意义何在？", "pinyin": "Cǐ jǔ yìyì hé zài?", "en": "What is the significance of this move?"},
         {"zh": "何苦为难自己？", "pinyin": "Hékǔ wéinán zìjǐ?", "en": "Why make things difficult for yourself?"},
     ]},

    {"name": "岂 how could/rhetorical", "name_zh": "岂", "hsk_level": 7, "category": "particle",
     "description": "Rhetorical question marker meaning 'how could' or 'could it be': 岂能",
     "difficulty": 0.8,
     "examples": [
         {"zh": "岂能轻易放弃？", "pinyin": "Qǐ néng qīngyì fàngqì?", "en": "How could one give up so easily?"},
         {"zh": "岂有此理！", "pinyin": "Qǐ yǒu cǐ lǐ!", "en": "How can this be! / This is outrageous!"},
         {"zh": "他岂是那种人？", "pinyin": "Tā qǐ shì nà zhǒng rén?", "en": "How could he be that kind of person?"},
     ]},

    {"name": "之 literary possessive/pronoun", "name_zh": "之", "hsk_level": 7, "category": "particle",
     "description": "Literary possessive particle and pronoun equivalent to 的 or 'it/this': 成功之道",
     "difficulty": 0.8,
     "examples": [
         {"zh": "成功之道在于坚持。", "pinyin": "Chénggōng zhī dào zàiyú jiānchí.", "en": "The path to success lies in persistence."},
         {"zh": "取之不尽，用之不竭。", "pinyin": "Qǔ zhī bú jìn, yòng zhī bú jié.", "en": "Inexhaustible in taking, unlimited in use."},
         {"zh": "言之有理。", "pinyin": "Yán zhī yǒu lǐ.", "en": "What was said is reasonable."},
     ]},

    {"name": "其 his/her/its (literary pronoun)", "name_zh": "其(代词)", "hsk_level": 7, "category": "particle",
     "description": "Literary third-person possessive pronoun: 其结果, 其原因",
     "difficulty": 0.8,
     "examples": [
         {"zh": "其结果令人意想不到。", "pinyin": "Qí jiéguǒ lìng rén yìxiǎng bú dào.", "en": "The result was unexpected."},
         {"zh": "各国应尽其所能。", "pinyin": "Gè guó yīng jìn qí suǒ néng.", "en": "Every country should do its utmost."},
         {"zh": "其原因是多方面的。", "pinyin": "Qí yuányīn shì duō fāngmiàn de.", "en": "The reasons are multifaceted."},
     ]},

    {"name": "所 that which (literary nominalizer)", "name_zh": "所(名词化)", "hsk_level": 7, "category": "particle",
     "description": "Literary nominalizer turning a verb into 'that which is V-ed': 所见所闻",
     "difficulty": 0.8,
     "examples": [
         {"zh": "我把所见所闻告诉了他。", "pinyin": "Wǒ bǎ suǒ jiàn suǒ wén gàosu le tā.", "en": "I told him everything I saw and heard."},
         {"zh": "这正是我们所期望的。", "pinyin": "Zhè zhèng shì wǒmen suǒ qīwàng de.", "en": "This is exactly what we hoped for."},
         {"zh": "所学要用于实践。", "pinyin": "Suǒ xué yào yòngyú shíjiàn.", "en": "What is learned should be applied in practice."},
     ]},

    {"name": "则 then (literary conjunction)", "name_zh": "则", "hsk_level": 7, "category": "connector",
     "description": "Literary conjunction meaning 'then' or introducing a contrast: 学则不固",
     "difficulty": 0.8,
     "examples": [
         {"zh": "不进则退。", "pinyin": "Bú jìn zé tuì.", "en": "If you don't advance, you retreat."},
         {"zh": "学而不思则罔。", "pinyin": "Xué ér bù sī zé wǎng.", "en": "To study without thinking is futile."},
         {"zh": "有问题则解决，无问题则预防。", "pinyin": "Yǒu wèntí zé jiějué, wú wèntí zé yùfáng.", "en": "If there are problems, solve them; if there are none, prevent them."},
     ]},

    {"name": "且 moreover/and (literary)", "name_zh": "且(文言)", "hsk_level": 7, "category": "connector",
     "description": "Literary conjunction meaning 'moreover' or 'and': 简单且有效",
     "difficulty": 0.75,
     "examples": [
         {"zh": "这个方法简单且有效。", "pinyin": "Zhège fāngfǎ jiǎndān qiě yǒuxiào.", "en": "This method is simple and effective."},
         {"zh": "他聪明且努力。", "pinyin": "Tā cōngmíng qiě nǔlì.", "en": "He is smart and hardworking."},
         {"zh": "问题严重且紧急。", "pinyin": "Wèntí yánzhòng qiě jǐnjí.", "en": "The problem is serious and urgent."},
     ]},

    {"name": "而 and/but (literary full usage)", "name_zh": "而(完整用法)", "hsk_level": 7, "category": "connector",
     "description": "Full literary usage of 而 as a versatile conjunction covering contrast, sequence, and manner",
     "difficulty": 0.8,
     "examples": [
         {"zh": "满招损，谦受益，时乃天道。", "pinyin": "Mǎn zhāo sǔn, qiān shòu yì, shí nǎi tiāndào.", "en": "Arrogance invites loss, humility receives benefit -- such is the way of heaven."},
         {"zh": "敏而好学，不耻下问。", "pinyin": "Mǐn ér hàoxué, bù chǐ xiàwèn.", "en": "Quick-witted and fond of learning, not ashamed to ask those below."},
         {"zh": "知其不可而为之。", "pinyin": "Zhī qí bùkě ér wéi zhī.", "en": "Knowing it cannot be done, yet doing it anyway."},
         {"zh": "人而无信，不知其可。", "pinyin": "Rén ér wú xìn, bù zhī qí kě.", "en": "A person without trustworthiness -- I don't know what they're good for."},
     ]},

    {"name": "以 by means of (literary)", "name_zh": "以(文言)", "hsk_level": 7, "category": "particle",
     "description": "Literary preposition meaning 'by means of' or 'in order to': 以理服人",
     "difficulty": 0.8,
     "examples": [
         {"zh": "以理服人。", "pinyin": "Yǐ lǐ fú rén.", "en": "Convince people through reason."},
         {"zh": "以身作则。", "pinyin": "Yǐ shēn zuò zé.", "en": "Lead by example."},
         {"zh": "以德报怨。", "pinyin": "Yǐ dé bào yuàn.", "en": "Repay resentment with virtue."},
     ]},

    {"name": "者 one who (literary nominalizer)", "name_zh": "者", "hsk_level": 7, "category": "particle",
     "description": "Literary nominalizer meaning 'one who' or 'that which': 智者 (wise person)",
     "difficulty": 0.8,
     "examples": [
         {"zh": "智者千虑，必有一失。", "pinyin": "Zhìzhě qiān lǜ, bì yǒu yì shī.", "en": "Even the wise, after a thousand considerations, will make one mistake."},
         {"zh": "来者不拒。", "pinyin": "Lái zhě bú jù.", "en": "Those who come are not refused."},
         {"zh": "当局者迷，旁观者清。", "pinyin": "Dāngjúzhě mí, pángguānzhě qīng.", "en": "The one involved is confused; the bystander sees clearly."},
     ]},

    {"name": "固 originally/inherently (literary)", "name_zh": "固(文言)", "hsk_level": 7, "category": "particle",
     "description": "Literary adverb meaning 'originally' or 'inherently': 固有之义",
     "difficulty": 0.8,
     "examples": [
         {"zh": "人固有一死。", "pinyin": "Rén gù yǒu yì sǐ.", "en": "Everyone inherently must die."},
         {"zh": "此理固然。", "pinyin": "Cǐ lǐ gù rán.", "en": "This principle is inherently so."},
         {"zh": "其志固不可夺。", "pinyin": "Qí zhì gù bùkě duó.", "en": "His resolve inherently cannot be taken."},
     ]},

    {"name": "焉 here/how (literary particle)", "name_zh": "焉(文言)", "hsk_level": 7, "category": "particle",
     "description": "Literary particle used as a locative, interrogative, or sentence-final emphasis: 心不在焉",
     "difficulty": 0.85,
     "examples": [
         {"zh": "心不在焉。", "pinyin": "Xīn bú zài yān.", "en": "Absent-minded (the heart is not here)."},
         {"zh": "皮之不存，毛将焉附？", "pinyin": "Pí zhī bù cún, máo jiāng yān fù?", "en": "If the skin is gone, where will the hair attach?"},
         {"zh": "塞翁失马，焉知非福？", "pinyin": "Sài wēng shī mǎ, yān zhī fēi fú?", "en": "The old man lost his horse -- how do you know it's not a blessing?"},
     ]},

    {"name": "尽 as much as possible", "name_zh": "尽(尽量)", "hsk_level": 7, "category": "structure",
     "description": "Adverb meaning 'as much as possible' or 'to the fullest extent': 尽早, 尽快",
     "difficulty": 0.7,
     "examples": [
         {"zh": "请尽早提交报告。", "pinyin": "Qǐng jǐnzǎo tíjiāo bàogào.", "en": "Please submit the report as early as possible."},
         {"zh": "我会尽力帮助你。", "pinyin": "Wǒ huì jìnlì bāngzhù nǐ.", "en": "I will help you as much as I can."},
         {"zh": "尽可能减少浪费。", "pinyin": "Jǐn kěnéng jiǎnshǎo làngfèi.", "en": "Reduce waste as much as possible."},
     ]},

    {"name": "需 need (formal single-character)", "name_zh": "需(单字)", "hsk_level": 7, "category": "structure",
     "description": "Formal single-character form of 'need', used in written contexts: 需注意",
     "difficulty": 0.7,
     "examples": [
         {"zh": "使用前需仔细阅读说明书。", "pinyin": "Shǐyòng qián xū zǐxì yuèdú shuōmíngshū.", "en": "Before use, one needs to carefully read the instructions."},
         {"zh": "此事需进一步讨论。", "pinyin": "Cǐ shì xū jìnyíbù tǎolùn.", "en": "This matter needs further discussion."},
         {"zh": "需特别注意安全问题。", "pinyin": "Xū tèbié zhùyì ānquán wèntí.", "en": "One needs to pay special attention to safety issues."},
     ]},

    {"name": "蛮 quite/rather (colloquial)", "name_zh": "蛮(口语)", "hsk_level": 7, "category": "particle",
     "description": "Colloquial adverb meaning 'quite' or 'rather', common in southern dialects and informal speech",
     "difficulty": 0.65,
     "examples": [
         {"zh": "这家店的菜蛮好吃的。", "pinyin": "Zhè jiā diàn de cài mán hǎochī de.", "en": "The food at this restaurant is quite delicious."},
         {"zh": "他蛮聪明的，就是不够努力。", "pinyin": "Tā mán cōngmíng de, jiùshì bú gòu nǔlì.", "en": "He's rather smart, just not hardworking enough."},
         {"zh": "今天天气蛮冷的。", "pinyin": "Jīntiān tiānqì mán lěng de.", "en": "The weather today is quite cold."},
     ]},

    {"name": "也 literary sentence-final particle", "name_zh": "也(句末助词)", "hsk_level": 7, "category": "particle",
     "description": "Classical sentence-final particle for affirmation or explanation, distinct from modern 也 (also)",
     "difficulty": 0.85,
     "examples": [
         {"zh": "此天意也。", "pinyin": "Cǐ tiānyì yě.", "en": "This is the will of heaven."},
         {"zh": "非不能也，是不为也。", "pinyin": "Fēi bù néng yě, shì bù wéi yě.", "en": "It is not that one cannot, but that one will not."},
         {"zh": "学而时习之，不亦说乎？有朋自远方来，不亦乐乎？", "pinyin": "Xué ér shí xí zhī, bú yì yuè hū? Yǒu péng zì yuǎnfāng lái, bú yì lè hū?", "en": "To study and regularly practice it, is that not a pleasure? To have friends come from afar, is that not a joy?"},
     ]},

    # =========================================================================
    # HSK 8 -- chengyu and formal expressions (22)
    # =========================================================================

    {"name": "概莫能外 without exception", "name_zh": "概莫能外", "hsk_level": 8, "category": "structure",
     "description": "Literary expression meaning no one or nothing is an exception: used in formal arguments",
     "difficulty": 0.85,
     "examples": [
         {"zh": "自然界的规律，万物概莫能外。", "pinyin": "Zìránjiè de guīlǜ, wànwù gài mò néng wài.", "en": "The laws of nature apply to all things without exception."},
         {"zh": "法律面前人人平等，概莫能外。", "pinyin": "Fǎlǜ miànqián rénrén píngděng, gài mò néng wài.", "en": "Everyone is equal before the law, without exception."},
         {"zh": "历史的变迁，任何国家概莫能外。", "pinyin": "Lìshǐ de biànqiān, rènhé guójiā gài mò néng wài.", "en": "Historical changes spare no country without exception."},
     ]},

    {"name": "不可或缺 indispensable", "name_zh": "不可或缺", "hsk_level": 8, "category": "structure",
     "description": "Formal expression meaning something cannot be absent or missing: indispensable",
     "difficulty": 0.8,
     "examples": [
         {"zh": "水是生命中不可或缺的。", "pinyin": "Shuǐ shì shēngmìng zhōng bùkě huò quē de.", "en": "Water is indispensable to life."},
         {"zh": "团队合作是成功不可或缺的因素。", "pinyin": "Tuánduì hézuò shì chénggōng bùkě huò quē de yīnsù.", "en": "Teamwork is an indispensable factor for success."},
         {"zh": "创新是企业发展不可或缺的动力。", "pinyin": "Chuàngxīn shì qǐyè fāzhǎn bùkě huò quē de dònglì.", "en": "Innovation is an indispensable driving force for enterprise development."},
     ]},

    {"name": "行之有效 proven effective", "name_zh": "行之有效", "hsk_level": 8, "category": "structure",
     "description": "Describes a method or approach that has been proven effective through practice",
     "difficulty": 0.8,
     "examples": [
         {"zh": "这是一种行之有效的管理方法。", "pinyin": "Zhè shì yì zhǒng xíng zhī yǒuxiào de guǎnlǐ fāngfǎ.", "en": "This is a proven effective management method."},
         {"zh": "多年来，这个策略一直行之有效。", "pinyin": "Duō nián lái, zhège cèlüè yìzhí xíng zhī yǒuxiào.", "en": "For many years, this strategy has proven effective."},
         {"zh": "我们需要找到行之有效的解决方案。", "pinyin": "Wǒmen xūyào zhǎodào xíng zhī yǒuxiào de jiějué fāng'àn.", "en": "We need to find a proven effective solution."},
     ]},

    {"name": "相得益彰 complement each other", "name_zh": "相得益彰", "hsk_level": 8, "category": "structure",
     "description": "Two things bring out the best in each other; mutually enhancing",
     "difficulty": 0.85,
     "examples": [
         {"zh": "传统与现代在这里相得益彰。", "pinyin": "Chuántǒng yǔ xiàndài zài zhèlǐ xiāngdé yìzhāng.", "en": "Tradition and modernity complement each other here."},
         {"zh": "音乐和画面相得益彰，令人陶醉。", "pinyin": "Yīnyuè hé huàmiàn xiāngdé yìzhāng, lìng rén táozuì.", "en": "The music and visuals complement each other, enchanting the audience."},
         {"zh": "两位搭档配合默契，相得益彰。", "pinyin": "Liǎng wèi dādàng pèihé mòqì, xiāngdé yìzhāng.", "en": "The two partners cooperate tacitly, complementing each other."},
     ]},

    {"name": "相辅相成 mutually complementary", "name_zh": "相辅相成", "hsk_level": 8, "category": "structure",
     "description": "Two things support and complement each other in development",
     "difficulty": 0.8,
     "examples": [
         {"zh": "理论与实践相辅相成。", "pinyin": "Lǐlùn yǔ shíjiàn xiāngfǔ xiāngchéng.", "en": "Theory and practice are mutually complementary."},
         {"zh": "经济发展和环境保护相辅相成。", "pinyin": "Jīngjì fāzhǎn hé huánjìng bǎohù xiāngfǔ xiāngchéng.", "en": "Economic development and environmental protection complement each other."},
         {"zh": "教与学相辅相成，缺一不可。", "pinyin": "Jiāo yǔ xué xiāngfǔ xiāngchéng, quē yī bùkě.", "en": "Teaching and learning complement each other; neither is dispensable."},
     ]},

    {"name": "截然不同 completely different", "name_zh": "截然不同", "hsk_level": 8, "category": "structure",
     "description": "Describes two things that are sharply and completely different",
     "difficulty": 0.75,
     "examples": [
         {"zh": "他们俩的性格截然不同。", "pinyin": "Tāmen liǎ de xìnggé jiérán bùtóng.", "en": "The two of them have completely different personalities."},
         {"zh": "这两种方法的效果截然不同。", "pinyin": "Zhè liǎng zhǒng fāngfǎ de xiàoguǒ jiérán bùtóng.", "en": "The effects of these two methods are completely different."},
         {"zh": "现实与想象截然不同。", "pinyin": "Xiànshí yǔ xiǎngxiàng jiérán bùtóng.", "en": "Reality and imagination are completely different."},
     ]},

    {"name": "举足轻重 pivotal/of great importance", "name_zh": "举足轻重", "hsk_level": 8, "category": "structure",
     "description": "Describes a position or role of great importance where every move matters",
     "difficulty": 0.85,
     "examples": [
         {"zh": "他在公司里占据着举足轻重的地位。", "pinyin": "Tā zài gōngsī lǐ zhànjù zhe jǔzú qīngzhòng de dìwèi.", "en": "He holds a pivotal position in the company."},
         {"zh": "教育在国家发展中举足轻重。", "pinyin": "Jiàoyù zài guójiā fāzhǎn zhōng jǔzú qīngzhòng.", "en": "Education plays a pivotal role in national development."},
         {"zh": "这次谈判举足轻重，不容有失。", "pinyin": "Zhè cì tánpàn jǔzú qīngzhòng, bùróng yǒu shī.", "en": "This negotiation is of great importance; no mistakes are allowed."},
     ]},

    {"name": "不可思议 inconceivable", "name_zh": "不可思议", "hsk_level": 8, "category": "structure",
     "description": "Describes something beyond comprehension or imagination: inconceivable",
     "difficulty": 0.75,
     "examples": [
         {"zh": "他的进步速度简直不可思议。", "pinyin": "Tā de jìnbù sùdù jiǎnzhí bùkě sīyì.", "en": "His rate of progress is simply inconceivable."},
         {"zh": "宇宙之大，不可思议。", "pinyin": "Yǔzhòu zhī dà, bùkě sīyì.", "en": "The vastness of the universe is inconceivable."},
         {"zh": "这件事情的巧合不可思议。", "pinyin": "Zhè jiàn shìqing de qiǎohé bùkě sīyì.", "en": "The coincidence in this matter is inconceivable."},
     ]},

    {"name": "理所当然 as a matter of course", "name_zh": "理所当然", "hsk_level": 8, "category": "structure",
     "description": "Something taken as natural, obvious, or expected",
     "difficulty": 0.75,
     "examples": [
         {"zh": "他觉得别人帮他是理所当然的。", "pinyin": "Tā juéde biérén bāng tā shì lǐsuǒ dāngrán de.", "en": "He thinks it's only natural for others to help him."},
         {"zh": "努力之后获得回报是理所当然的。", "pinyin": "Nǔlì zhīhòu huòdé huíbào shì lǐsuǒ dāngrán de.", "en": "Getting rewarded after hard work is a matter of course."},
         {"zh": "不要把别人的帮助视为理所当然。", "pinyin": "Bú yào bǎ biérén de bāngzhù shìwéi lǐsuǒ dāngrán.", "en": "Don't take other people's help for granted."},
     ]},

    {"name": "不言自明 self-evident", "name_zh": "不言自明", "hsk_level": 8, "category": "structure",
     "description": "Something so obvious it needs no explanation: self-evident",
     "difficulty": 0.8,
     "examples": [
         {"zh": "这个道理不言自明。", "pinyin": "Zhège dàolǐ bùyán zìmíng.", "en": "This principle is self-evident."},
         {"zh": "他的能力不言自明，大家有目共睹。", "pinyin": "Tā de nénglì bùyán zìmíng, dàjiā yǒumù gòngdǔ.", "en": "His ability is self-evident; everyone can see it."},
         {"zh": "数据摆在面前，结论不言自明。", "pinyin": "Shùjù bǎi zài miànqián, jiélùn bùyán zìmíng.", "en": "With data laid out before us, the conclusion is self-evident."},
     ]},

    {"name": "显而易见 obviously/clearly", "name_zh": "显而易见", "hsk_level": 8, "category": "connector",
     "description": "Introduces something obviously apparent: a discourse marker for stating the obvious",
     "difficulty": 0.75,
     "examples": [
         {"zh": "显而易见，这个计划行不通。", "pinyin": "Xiǎn ér yì jiàn, zhège jìhuà xíng bù tōng.", "en": "Obviously, this plan won't work."},
         {"zh": "他的意图显而易见。", "pinyin": "Tā de yìtú xiǎn ér yì jiàn.", "en": "His intentions are clearly evident."},
         {"zh": "显而易见，教育改革势在必行。", "pinyin": "Xiǎn ér yì jiàn, jiàoyù gǎigé shì zài bì xíng.", "en": "It is obvious that educational reform is imperative."},
     ]},

    {"name": "无所适从 at a loss what to do", "name_zh": "无所适从", "hsk_level": 8, "category": "structure",
     "description": "Describes being at a loss, not knowing which way to turn or whom to follow",
     "difficulty": 0.85,
     "examples": [
         {"zh": "各种说法不一，让人无所适从。", "pinyin": "Gè zhǒng shuōfǎ bù yī, ràng rén wúsuǒ shìcóng.", "en": "Various accounts differ, leaving people at a loss what to do."},
         {"zh": "面对如此多的选择，他无所适从。", "pinyin": "Miànduì rúcǐ duō de xuǎnzé, tā wúsuǒ shìcóng.", "en": "Faced with so many choices, he was at a loss."},
         {"zh": "政策朝令夕改，企业无所适从。", "pinyin": "Zhèngcè zhāolìng xīgǎi, qǐyè wúsuǒ shìcóng.", "en": "Policies change day by day, leaving enterprises at a loss."},
     ]},

    {"name": "不可避免 unavoidable", "name_zh": "不可避免", "hsk_level": 8, "category": "structure",
     "description": "States that something cannot be avoided: unavoidable, inevitable",
     "difficulty": 0.75,
     "examples": [
         {"zh": "变化是不可避免的。", "pinyin": "Biànhuà shì bùkě bìmiǎn de.", "en": "Change is unavoidable."},
         {"zh": "冲突似乎不可避免。", "pinyin": "Chōngtū sìhū bùkě bìmiǎn.", "en": "Conflict seems unavoidable."},
         {"zh": "在全球化背景下，文化交流不可避免。", "pinyin": "Zài quánqiúhuà bèijǐng xià, wénhuà jiāoliú bùkě bìmiǎn.", "en": "In the context of globalization, cultural exchange is unavoidable."},
     ]},

    {"name": "首当其冲 bear the brunt", "name_zh": "首当其冲", "hsk_level": 8, "category": "structure",
     "description": "Be the first to be affected or suffer impact: bear the brunt",
     "difficulty": 0.85,
     "examples": [
         {"zh": "经济衰退时，中小企业首当其冲。", "pinyin": "Jīngjì shuāituì shí, zhōngxiǎo qǐyè shǒudāng qí chōng.", "en": "During economic recession, small and medium enterprises bear the brunt."},
         {"zh": "环境恶化，沿海城市首当其冲。", "pinyin": "Huánjìng èhuà, yánhǎi chéngshì shǒudāng qí chōng.", "en": "With environmental degradation, coastal cities bear the brunt."},
         {"zh": "技术革命中，传统行业首当其冲。", "pinyin": "Jìshù gémìng zhōng, chuántǒng hángyè shǒudāng qí chōng.", "en": "In the technological revolution, traditional industries bear the brunt."},
     ]},

    {"name": "众所周知 as everyone knows", "name_zh": "众所周知", "hsk_level": 8, "category": "connector",
     "description": "Discourse marker introducing commonly known information: as is well known",
     "difficulty": 0.75,
     "examples": [
         {"zh": "众所周知，中国是世界上人口最多的国家之一。", "pinyin": "Zhòngsuǒ zhōuzhī, Zhōngguó shì shìjiè shang rénkǒu zuì duō de guójiā zhī yī.", "en": "As everyone knows, China is one of the most populous countries in the world."},
         {"zh": "众所周知，吸烟有害健康。", "pinyin": "Zhòngsuǒ zhōuzhī, xīyān yǒuhài jiànkāng.", "en": "As everyone knows, smoking is harmful to health."},
         {"zh": "众所周知，教育是国家发展的基础。", "pinyin": "Zhòngsuǒ zhōuzhī, jiàoyù shì guójiā fāzhǎn de jīchǔ.", "en": "As everyone knows, education is the foundation of national development."},
     ]},

    {"name": "微乎其微 negligible/minuscule", "name_zh": "微乎其微", "hsk_level": 8, "category": "structure",
     "description": "Describes something extremely small or negligible in amount or probability",
     "difficulty": 0.8,
     "examples": [
         {"zh": "成功的概率微乎其微。", "pinyin": "Chénggōng de gàilǜ wēihū qí wēi.", "en": "The probability of success is negligible."},
         {"zh": "这点差距微乎其微，可以忽略不计。", "pinyin": "Zhè diǎn chājù wēihū qí wēi, kěyǐ hūlüè bú jì.", "en": "This tiny gap is minuscule and can be disregarded."},
         {"zh": "他对这个项目的贡献微乎其微。", "pinyin": "Tā duì zhège xiàngmù de gòngxiàn wēihū qí wēi.", "en": "His contribution to this project is negligible."},
     ]},

    {"name": "名副其实 live up to the name", "name_zh": "名副其实", "hsk_level": 8, "category": "structure",
     "description": "The reality matches the reputation: truly worthy of the name",
     "difficulty": 0.8,
     "examples": [
         {"zh": "他是名副其实的专家。", "pinyin": "Tā shì míngfù qíshí de zhuānjiā.", "en": "He is an expert in every sense of the word."},
         {"zh": "这家餐厅名副其实，菜品确实很好。", "pinyin": "Zhè jiā cāntīng míngfù qíshí, càipǐn quèshí hěn hǎo.", "en": "This restaurant lives up to its name; the dishes are truly excellent."},
         {"zh": "她是名副其实的学霸。", "pinyin": "Tā shì míngfù qíshí de xuébà.", "en": "She is a top student in every sense of the word."},
     ]},

    {"name": "见仁见智 different people different views", "name_zh": "见仁见智", "hsk_level": 8, "category": "structure",
     "description": "Different people have different perspectives on the same matter",
     "difficulty": 0.8,
     "examples": [
         {"zh": "这个问题见仁见智，没有标准答案。", "pinyin": "Zhège wèntí jiànrén jiànzhì, méiyǒu biāozhǔn dá'àn.", "en": "This question is a matter of perspective; there is no standard answer."},
         {"zh": "审美是见仁见智的事情。", "pinyin": "Shěnměi shì jiànrén jiànzhì de shìqing.", "en": "Aesthetics is a matter where different people have different views."},
         {"zh": "对于教育方法，家长们见仁见智。", "pinyin": "Duìyú jiàoyù fāngfǎ, jiāzhǎngmen jiànrén jiànzhì.", "en": "Parents have different views on educational methods."},
     ]},

    {"name": "不谋而合 happen to coincide", "name_zh": "不谋而合", "hsk_level": 8, "category": "structure",
     "description": "To reach the same conclusion independently without prior consultation",
     "difficulty": 0.8,
     "examples": [
         {"zh": "他们的想法不谋而合。", "pinyin": "Tāmen de xiǎngfǎ bùmóu ér hé.", "en": "Their ideas happened to coincide."},
         {"zh": "两位科学家的研究结论不谋而合。", "pinyin": "Liǎng wèi kēxuéjiā de yánjiū jiélùn bùmóu ér hé.", "en": "The research conclusions of the two scientists happened to coincide."},
         {"zh": "我们的计划和他们的不谋而合。", "pinyin": "Wǒmen de jìhuà hé tāmen de bùmóu ér hé.", "en": "Our plan happened to coincide with theirs."},
     ]},

    {"name": "与生俱来 innate/born with", "name_zh": "与生俱来", "hsk_level": 8, "category": "structure",
     "description": "Describes qualities or abilities one is born with: innate",
     "difficulty": 0.8,
     "examples": [
         {"zh": "他有一种与生俱来的领导才能。", "pinyin": "Tā yǒu yì zhǒng yǔshēng jùlái de lǐngdǎo cáinéng.", "en": "He has an innate talent for leadership."},
         {"zh": "好奇心是与生俱来的。", "pinyin": "Hàoqíxīn shì yǔshēng jùlái de.", "en": "Curiosity is innate."},
         {"zh": "她与生俱来的优雅气质令人印象深刻。", "pinyin": "Tā yǔshēng jùlái de yōuyǎ qìzhì lìng rén yìnxiàng shēnkè.", "en": "Her innate elegance is impressive."},
     ]},

    {"name": "恰如其分 apt/appropriate", "name_zh": "恰如其分", "hsk_level": 8, "category": "structure",
     "description": "Describes something perfectly appropriate or fitting: apt, just right",
     "difficulty": 0.8,
     "examples": [
         {"zh": "他的评价恰如其分。", "pinyin": "Tā de píngjià qiàrú qí fèn.", "en": "His evaluation was perfectly apt."},
         {"zh": "这个比喻恰如其分。", "pinyin": "Zhège bǐyù qiàrú qí fèn.", "en": "This metaphor is perfectly appropriate."},
         {"zh": "她总能恰如其分地表达自己的想法。", "pinyin": "Tā zǒng néng qiàrú qí fèn de biǎodá zìjǐ de xiǎngfǎ.", "en": "She can always express her ideas in a perfectly apt manner."},
     ]},

    {"name": "根深蒂固 deep-rooted", "name_zh": "根深蒂固", "hsk_level": 8, "category": "structure",
     "description": "Describes beliefs, habits, or traditions that are deeply ingrained and hard to change",
     "difficulty": 0.8,
     "examples": [
         {"zh": "这种偏见已经根深蒂固。", "pinyin": "Zhè zhǒng piānjiàn yǐjīng gēnshēn dìgù.", "en": "This prejudice is already deeply rooted."},
         {"zh": "传统观念在农村地区根深蒂固。", "pinyin": "Chuántǒng guānniàn zài nóngcūn dìqū gēnshēn dìgù.", "en": "Traditional concepts are deeply rooted in rural areas."},
         {"zh": "要改变根深蒂固的习惯并不容易。", "pinyin": "Yào gǎibiàn gēnshēn dìgù de xíguàn bìng bù róngyì.", "en": "Changing deeply rooted habits is not easy."},
     ]},

    # =========================================================================
    # HSK 9 -- classical Chinese particles and patterns (28)
    # =========================================================================

    {"name": "哉 classical exclamatory particle", "name_zh": "哉", "hsk_level": 9, "category": "particle",
     "description": "Classical sentence-final particle expressing exclamation or rhetorical emphasis",
     "difficulty": 0.9,
     "examples": [
         {"zh": "壮哉！我中华少年。", "pinyin": "Zhuàng zāi! Wǒ Zhōnghuá shàonián.", "en": "How magnificent! The youth of China."},
         {"zh": "善哉善哉！", "pinyin": "Shàn zāi shàn zāi!", "en": "How wonderful! How wonderful!"},
         {"zh": "悲哉，世人不知其过。", "pinyin": "Bēi zāi, shìrén bù zhī qí guò.", "en": "How sad that people of the world do not know their faults."},
     ]},

    {"name": "矣 classical completion particle", "name_zh": "矣", "hsk_level": 9, "category": "particle",
     "description": "Classical sentence-final particle indicating completion or change of state, equivalent to modern 了",
     "difficulty": 0.9,
     "examples": [
         {"zh": "吾知之矣。", "pinyin": "Wú zhī zhī yǐ.", "en": "I understand now."},
         {"zh": "天下定矣。", "pinyin": "Tiānxià dìng yǐ.", "en": "The realm is settled."},
         {"zh": "事已至此，悔之晚矣。", "pinyin": "Shì yǐ zhì cǐ, huǐ zhī wǎn yǐ.", "en": "Things have come to this; regret is too late."},
     ]},

    {"name": "乎 classical question particle", "name_zh": "乎", "hsk_level": 9, "category": "particle",
     "description": "Classical sentence-final particle for questions and rhetorical questions",
     "difficulty": 0.9,
     "examples": [
         {"zh": "不亦乐乎？", "pinyin": "Bú yì lè hū?", "en": "Is that not a joy?"},
         {"zh": "学而时习之，不亦说乎？", "pinyin": "Xué ér shí xí zhī, bú yì yuè hū?", "en": "To study and practice regularly, is that not a pleasure?"},
         {"zh": "人非圣贤，孰能无过乎？", "pinyin": "Rén fēi shèngxián, shú néng wú guò hū?", "en": "No one is a sage; who can be without faults?"},
     ]},

    {"name": "夫 classical topic marker", "name_zh": "夫(发语词)", "hsk_level": 9, "category": "particle",
     "description": "Classical sentence-initial particle introducing a topic or new subject for discussion",
     "difficulty": 0.9,
     "examples": [
         {"zh": "夫天地者，万物之逆旅也。", "pinyin": "Fú tiāndì zhě, wànwù zhī nìlǚ yě.", "en": "Now heaven and earth are a traveler's inn for all things."},
         {"zh": "夫战，勇气也。", "pinyin": "Fú zhàn, yǒngqì yě.", "en": "As for battle, it is a matter of courage."},
         {"zh": "夫学须静也。", "pinyin": "Fú xué xū jìng yě.", "en": "As for learning, one needs tranquility."},
     ]},

    {"name": "盖 classical 'it is because'", "name_zh": "盖(发语词)", "hsk_level": 9, "category": "particle",
     "description": "Classical sentence-initial particle meaning 'it is because' or 'presumably'",
     "difficulty": 0.9,
     "examples": [
         {"zh": "盖余之勤且艰若此。", "pinyin": "Gài yú zhī qín qiě jiān ruò cǐ.", "en": "It is because my diligence was as arduous as this."},
         {"zh": "盖天下之事，不可一概而论。", "pinyin": "Gài tiānxià zhī shì, bùkě yì gài ér lùn.", "en": "It is because the affairs of the world cannot be generalized."},
         {"zh": "盖闻古之善治者，以民为本。", "pinyin": "Gài wén gǔ zhī shàn zhì zhě, yǐ mín wéi běn.", "en": "It is said that the good rulers of old took the people as the foundation."},
     ]},

    {"name": "然 so/like this (classical)", "name_zh": "然(文言)", "hsk_level": 9, "category": "particle",
     "description": "Classical word meaning 'so', 'like this', or 'correct'; also used as a suffix meaning '-like'",
     "difficulty": 0.85,
     "examples": [
         {"zh": "虽然，犹有未树也。", "pinyin": "Suī rán, yóu yǒu wèi shù yě.", "en": "Even so, there is still something not established."},
         {"zh": "然则何以为治？", "pinyin": "Rán zé héyǐ wéi zhì?", "en": "If so, then how should one govern?"},
         {"zh": "其言然矣。", "pinyin": "Qí yán rán yǐ.", "en": "His words are indeed so."},
     ]},

    {"name": "故 therefore (classical)", "name_zh": "故(文言)", "hsk_level": 9, "category": "connector",
     "description": "Classical conjunction meaning 'therefore' or 'for this reason'",
     "difficulty": 0.85,
     "examples": [
         {"zh": "知己知彼，故百战不殆。", "pinyin": "Zhī jǐ zhī bǐ, gù bǎi zhàn bú dài.", "en": "Know yourself and your enemy, therefore a hundred battles bring no peril."},
         {"zh": "故天将降大任于斯人也。", "pinyin": "Gù tiān jiāng jiàng dà rèn yú sī rén yě.", "en": "Therefore when heaven is about to bestow a great task upon someone..."},
         {"zh": "学而不思则罔，故思而不学则殆。", "pinyin": "Xué ér bù sī zé wǎng, gù sī ér bù xué zé dài.", "en": "To study without thinking is futile; therefore to think without studying is dangerous."},
     ]},

    {"name": "若 if/like (classical)", "name_zh": "若(文言)", "hsk_level": 9, "category": "connector",
     "description": "Classical word meaning 'if' (conditional) or 'like/as' (comparison)",
     "difficulty": 0.85,
     "examples": [
         {"zh": "若无其事。", "pinyin": "Ruò wú qí shì.", "en": "As if nothing happened."},
         {"zh": "人生若只如初见。", "pinyin": "Rénshēng ruò zhǐ rú chū jiàn.", "en": "If life were only like the first meeting."},
         {"zh": "若欲速则不达。", "pinyin": "Ruò yù sù zé bù dá.", "en": "If you wish for speed, you will not arrive."},
     ]},

    {"name": "虽 although (classical standalone)", "name_zh": "虽(文言单用)", "hsk_level": 9, "category": "connector",
     "description": "Classical standalone form of 'although', without the modern 然 suffix",
     "difficulty": 0.85,
     "examples": [
         {"zh": "虽千万人，吾往矣。", "pinyin": "Suī qiān wàn rén, wú wǎng yǐ.", "en": "Even if there are tens of millions, I shall go forth."},
         {"zh": "虽不能至，心向往之。", "pinyin": "Suī bù néng zhì, xīn xiàngwǎng zhī.", "en": "Although I cannot reach it, my heart yearns for it."},
         {"zh": "虽有佳肴，弗食，不知其旨也。", "pinyin": "Suī yǒu jiāyáo, fú shí, bù zhī qí zhǐ yě.", "en": "Although there are fine dishes, if you don't eat them, you won't know their flavor."},
     ]},

    {"name": "犹 still/like (classical)", "name_zh": "犹(文言)", "hsk_level": 9, "category": "particle",
     "description": "Classical adverb meaning 'still', 'yet', or 'like/as if'",
     "difficulty": 0.85,
     "examples": [
         {"zh": "过犹不及。", "pinyin": "Guò yóu bù jí.", "en": "Going too far is as bad as not going far enough."},
         {"zh": "犹未可知。", "pinyin": "Yóu wèi kě zhī.", "en": "It is still not yet known."},
         {"zh": "记忆犹新。", "pinyin": "Jìyì yóu xīn.", "en": "The memory is still fresh."},
     ]},

    {"name": "或 some/perhaps (classical)", "name_zh": "或(文言)", "hsk_level": 9, "category": "particle",
     "description": "Classical word meaning 'some (people)', 'perhaps', or 'someone': broader than modern 或者",
     "difficulty": 0.85,
     "examples": [
         {"zh": "人或有一失。", "pinyin": "Rén huò yǒu yì shī.", "en": "A person may perhaps have one mistake."},
         {"zh": "或曰：不然。", "pinyin": "Huò yuē: bùrán.", "en": "Some say: that is not so."},
         {"zh": "或五十步而笑百步。", "pinyin": "Huò wǔshí bù ér xiào bǎi bù.", "en": "Some who retreat fifty steps laugh at those who retreat a hundred."},
     ]},

    {"name": "即 even if/that is (classical)", "name_zh": "即(文言)", "hsk_level": 9, "category": "connector",
     "description": "Classical word meaning 'even if', 'that is', or 'immediately'",
     "difficulty": 0.85,
     "examples": [
         {"zh": "即知即行。", "pinyin": "Jí zhī jí xíng.", "en": "Act as soon as you know."},
         {"zh": "即日起生效。", "pinyin": "Jí rì qǐ shēngxiào.", "en": "Effective from this day."},
         {"zh": "即使身处逆境，亦不改其志。", "pinyin": "Jíshǐ shēn chǔ nìjìng, yì bù gǎi qí zhì.", "en": "Even if in adversity, one does not change one's resolve."},
     ]},

    {"name": "遂 thereupon (classical)", "name_zh": "遂(文言)", "hsk_level": 9, "category": "connector",
     "description": "Classical conjunction meaning 'thereupon', 'consequently', or 'then'",
     "difficulty": 0.85,
     "examples": [
         {"zh": "心有所感，遂作此文。", "pinyin": "Xīn yǒu suǒ gǎn, suì zuò cǐ wén.", "en": "Moved in the heart, I thereupon wrote this piece."},
         {"zh": "大怒，遂拂袖而去。", "pinyin": "Dà nù, suì fú xiù ér qù.", "en": "Greatly angered, he thereupon left in a huff."},
         {"zh": "未果，遂废。", "pinyin": "Wèi guǒ, suì fèi.", "en": "It bore no fruit, and was thereupon abandoned."},
     ]},

    {"name": "皆 all (classical)", "name_zh": "皆(文言)", "hsk_level": 9, "category": "particle",
     "description": "Classical adverb meaning 'all' or 'entirely'",
     "difficulty": 0.85,
     "examples": [
         {"zh": "天下皆知美之为美。", "pinyin": "Tiānxià jiē zhī měi zhī wéi měi.", "en": "All under heaven know beauty as beauty."},
         {"zh": "四海之内，皆兄弟也。", "pinyin": "Sìhǎi zhī nèi, jiē xiōngdì yě.", "en": "Within the four seas, all are brothers."},
         {"zh": "万事皆有因果。", "pinyin": "Wànshì jiē yǒu yīnguǒ.", "en": "All things have cause and effect."},
     ]},

    {"name": "莫 don't/none (classical)", "name_zh": "莫(文言)", "hsk_level": 9, "category": "particle",
     "description": "Classical negative meaning 'don't', 'none', or 'no one': used as prohibition or universal negation",
     "difficulty": 0.85,
     "examples": [
         {"zh": "莫等闲，白了少年头。", "pinyin": "Mò děngxián, bái le shàonián tóu.", "en": "Don't idle away time; your youthful hair will turn white."},
         {"zh": "莫愁前路无知己。", "pinyin": "Mò chóu qiánlù wú zhījǐ.", "en": "Don't worry that ahead there will be no kindred spirit."},
         {"zh": "相见争如不见，有情何似无情。莫道不消魂。", "pinyin": "Xiāngjiàn zhēng rú bú jiàn, yǒuqíng hé sì wúqíng. Mò dào bù xiāohún.", "en": "Meeting is no better than not meeting; having feelings, how is it better than having none? Don't say it doesn't break the heart."},
     ]},

    {"name": "唯/惟 only (classical)", "name_zh": "唯/惟(文言)", "hsk_level": 9, "category": "particle",
     "description": "Classical adverb meaning 'only' or 'solely'",
     "difficulty": 0.85,
     "examples": [
         {"zh": "唯德动天，无远弗届。", "pinyin": "Wéi dé dòng tiān, wú yuǎn fú jiè.", "en": "Only virtue moves heaven; no distance is too far to reach."},
         {"zh": "惟精惟一。", "pinyin": "Wéi jīng wéi yī.", "en": "Only through refinement and single-mindedness."},
         {"zh": "唯才是举。", "pinyin": "Wéi cái shì jǔ.", "en": "Only talent should be the basis for appointment."},
     ]},

    {"name": "未 not yet (classical)", "name_zh": "未(文言)", "hsk_level": 9, "category": "particle",
     "description": "Classical negation meaning 'not yet' or 'have not': precedes the verb",
     "difficulty": 0.85,
     "examples": [
         {"zh": "革命尚未成功，同志仍须努力。", "pinyin": "Gémìng shàng wèi chénggōng, tóngzhì réng xū nǔlì.", "en": "The revolution has not yet succeeded; comrades must still strive."},
         {"zh": "未可知也。", "pinyin": "Wèi kě zhī yě.", "en": "It is not yet knowable."},
         {"zh": "言犹未尽。", "pinyin": "Yán yóu wèi jìn.", "en": "There is more yet to be said."},
     ]},

    {"name": "非 not/is not (classical)", "name_zh": "非(文言)", "hsk_level": 9, "category": "particle",
     "description": "Classical negation of identity or fact: 'is not' or 'it is wrong to'",
     "difficulty": 0.85,
     "examples": [
         {"zh": "人非草木，孰能无情？", "pinyin": "Rén fēi cǎomù, shú néng wúqíng?", "en": "People are not plants or trees; who can be without feelings?"},
         {"zh": "非淡泊无以明志。", "pinyin": "Fēi dànbó wúyǐ míng zhì.", "en": "Without tranquility one cannot make one's ambitions clear."},
         {"zh": "非学无以广才。", "pinyin": "Fēi xué wúyǐ guǎng cái.", "en": "Without study one cannot broaden one's talents."},
     ]},

    {"name": "相 each other/mutually (classical)", "name_zh": "相(文言)", "hsk_level": 9, "category": "particle",
     "description": "Classical adverb meaning 'each other' or 'mutually'; placed before the verb",
     "difficulty": 0.85,
     "examples": [
         {"zh": "相逢何必曾相识。", "pinyin": "Xiāngféng hébì céng xiāngshí.", "en": "When meeting, why must we have been acquainted before?"},
         {"zh": "相看两不厌，只有敬亭山。", "pinyin": "Xiāng kàn liǎng bú yàn, zhǐyǒu Jìngtíng Shān.", "en": "Gazing at each other without tiring, only Jingting Mountain remains."},
         {"zh": "士别三日，当刮目相待。", "pinyin": "Shì bié sān rì, dāng guāmù xiāngdài.", "en": "When a scholar has been away three days, one should look at him with new eyes."},
     ]},

    {"name": "如...何 what to do about (classical)", "name_zh": "如…何", "hsk_level": 9, "category": "structure",
     "description": "Classical pattern asking 'what is to be done about X': 如之何",
     "difficulty": 0.9,
     "examples": [
         {"zh": "如之何？", "pinyin": "Rú zhī hé?", "en": "What is to be done about it?"},
         {"zh": "奈何不可，如之何哉？", "pinyin": "Nàihé bùkě, rú zhī hé zāi?", "en": "It cannot be helped; what is to be done?"},
         {"zh": "天下已定，如残敌何？", "pinyin": "Tiānxià yǐ dìng, rú cán dí hé?", "en": "The realm is settled; what shall we do about the remaining enemies?"},
     ]},

    {"name": "无乃...乎 isn't it that (classical rhetorical)", "name_zh": "无乃…乎", "hsk_level": 9, "category": "structure",
     "description": "Classical rhetorical pattern expressing gentle concern: 'isn't it perhaps that...'",
     "difficulty": 0.9,
     "examples": [
         {"zh": "无乃太过乎？", "pinyin": "Wúnǎi tài guò hū?", "en": "Isn't this perhaps going too far?"},
         {"zh": "无乃尔是过与？", "pinyin": "Wúnǎi ěr shì guò yú?", "en": "Isn't this perhaps your fault?"},
         {"zh": "无乃不可乎？", "pinyin": "Wúnǎi bùkě hū?", "en": "Isn't this perhaps unacceptable?"},
     ]},

    {"name": "何...之有 what X is there (classical rhetorical)", "name_zh": "何…之有", "hsk_level": 9, "category": "structure",
     "description": "Classical rhetorical pattern meaning 'what X is there?' to deny something exists: inverted object",
     "difficulty": 0.9,
     "examples": [
         {"zh": "何难之有？", "pinyin": "Hé nán zhī yǒu?", "en": "What difficulty is there?"},
         {"zh": "何陋之有？", "pinyin": "Hé lòu zhī yǒu?", "en": "What shabbiness is there? (from The Humble Room)"},
         {"zh": "何惧之有？", "pinyin": "Hé jù zhī yǒu?", "en": "What is there to fear?"},
     ]},

    {"name": "得无...乎 could it be that (classical)", "name_zh": "得无…乎", "hsk_level": 9, "category": "structure",
     "description": "Classical pattern expressing cautious suspicion: 'could it be that...?'",
     "difficulty": 0.9,
     "examples": [
         {"zh": "得无异乎？", "pinyin": "Dé wú yì hū?", "en": "Could it be that it is different?"},
         {"zh": "得无有怨乎？", "pinyin": "Dé wú yǒu yuàn hū?", "en": "Could it be that there is resentment?"},
         {"zh": "得无失其本心乎？", "pinyin": "Dé wú shī qí běnxīn hū?", "en": "Could it be that one has lost one's original heart?"},
     ]},

    {"name": "所以...者 the reason why (classical)", "name_zh": "所以…者", "hsk_level": 9, "category": "structure",
     "description": "Classical pattern meaning 'the reason why': 所以然者",
     "difficulty": 0.9,
     "examples": [
         {"zh": "所以然者何？", "pinyin": "Suǒyǐ rán zhě hé?", "en": "What is the reason it is so?"},
         {"zh": "所以遣将守关者，备他盗出入也。", "pinyin": "Suǒyǐ qiǎn jiàng shǒu guān zhě, bèi tā dào chūrù yě.", "en": "The reason for dispatching generals to guard the pass was to prevent bandits from coming and going."},
         {"zh": "所以谓之文者，以其质而有文也。", "pinyin": "Suǒyǐ wèi zhī wén zhě, yǐ qí zhì ér yǒu wén yě.", "en": "The reason it is called 'refined' is that its substance has ornamentation."},
     ]},

    {"name": "为...所 passive (classical)", "name_zh": "为…所(古文被动)", "hsk_level": 9, "category": "structure",
     "description": "Classical passive construction: the subject is acted upon by the agent",
     "difficulty": 0.9,
     "examples": [
         {"zh": "信而见疑，忠而被谤，为世所弃。", "pinyin": "Xìn ér jiàn yí, zhōng ér bèi bàng, wéi shì suǒ qì.", "en": "Trusted yet doubted, loyal yet slandered, abandoned by the world."},
         {"zh": "为人所笑。", "pinyin": "Wéi rén suǒ xiào.", "en": "Laughed at by people."},
         {"zh": "不为外物所惑。", "pinyin": "Bù wéi wàiwù suǒ huò.", "en": "Not misled by external things."},
     ]},

    {"name": "不亦...乎 isn't it (classical rhetorical)", "name_zh": "不亦…乎", "hsk_level": 9, "category": "structure",
     "description": "Classical rhetorical pattern expressing mild affirmation: 'is it not...?'",
     "difficulty": 0.9,
     "examples": [
         {"zh": "学而时习之，不亦说乎？", "pinyin": "Xué ér shí xí zhī, bú yì yuè hū?", "en": "To study and regularly practice it, is that not a pleasure?"},
         {"zh": "有朋自远方来，不亦乐乎？", "pinyin": "Yǒu péng zì yuǎnfāng lái, bú yì lè hū?", "en": "When friends come from afar, is that not a joy?"},
         {"zh": "人不知而不愠，不亦君子乎？", "pinyin": "Rén bù zhī ér bú yùn, bú yì jūnzǐ hū?", "en": "To not be resentful when others don't understand you, is that not the mark of a gentleman?"},
     ]},

    {"name": "何其 how very (exclamatory classical)", "name_zh": "何其", "hsk_level": 9, "category": "structure",
     "description": "Classical exclamatory expression meaning 'how very' or 'what a'",
     "difficulty": 0.85,
     "examples": [
         {"zh": "何其壮观！", "pinyin": "Héqí zhuàngguān!", "en": "How magnificent!"},
         {"zh": "何其相似乃尔！", "pinyin": "Héqí xiāngsì nǎi ěr!", "en": "How very similar!"},
         {"zh": "何其不幸！", "pinyin": "Héqí búxìng!", "en": "How unfortunate!"},
     ]},

    {"name": "也 classical affirmative sentence-final", "name_zh": "也(判断句末)", "hsk_level": 9, "category": "particle",
     "description": "Classical sentence-final particle marking a judgment or definition, distinct from the HSK 7 explanatory usage",
     "difficulty": 0.9,
     "examples": [
         {"zh": "陈胜者，阳城人也。", "pinyin": "Chén Shèng zhě, Yángchéng rén yě.", "en": "Chen Sheng was a person from Yangcheng."},
         {"zh": "鱼，我所欲也。", "pinyin": "Yú, wǒ suǒ yù yě.", "en": "Fish is what I desire."},
         {"zh": "此所谓战胜于朝廷也。", "pinyin": "Cǐ suǒwèi zhàn shèng yú cháotíng yě.", "en": "This is what is called winning the battle at court."},
     ]},
]
