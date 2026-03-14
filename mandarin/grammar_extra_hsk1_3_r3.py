"""Extra HSK 1-3 grammar points, round 3 — filling remaining gaps from official syllabus."""

EXTRA_GRAMMAR_HSK1_3_R3 = [
    # =========================================================================
    # HSK 1 — additional grammar points
    # =========================================================================

    {"name": "Noun predicate sentence", "name_zh": "名词谓语句", "hsk_level": 1, "category": "structure",
     "description": "Sentences where a noun phrase serves as the predicate without 是, typically for dates, age, weather, and prices: 今天星期三、他二十岁", "difficulty": 0.2,
     "examples": [
         {"zh": "今天星期三。", "pinyin": "Jīntiān xīngqīsān.", "en": "Today is Wednesday."},
         {"zh": "现在三点。", "pinyin": "Xiànzài sān diǎn.", "en": "It is three o'clock now."},
         {"zh": "这个苹果五块钱。", "pinyin": "Zhège píngguǒ wǔ kuài qián.", "en": "This apple is five yuan."},
         {"zh": "明天晴天。", "pinyin": "Míngtiān qíngtiān.", "en": "Tomorrow is a sunny day."},
     ]},

    {"name": "年/月/日 date format", "name_zh": "年月日", "hsk_level": 1, "category": "structure",
     "description": "Chinese date format follows year-month-day order: 年 (year), 月 (month), 日/号 (day). Largest unit first, smallest last.", "difficulty": 0.2,
     "examples": [
         {"zh": "今天是二〇二四年八月六日。", "pinyin": "Jīntiān shì èr líng èr sì nián bā yuè liù rì.", "en": "Today is August 6, 2024."},
         {"zh": "她的生日是三月十五号。", "pinyin": "Tā de shēngrì shì sān yuè shíwǔ hào.", "en": "Her birthday is March 15th."},
         {"zh": "我二〇一九年来中国的。", "pinyin": "Wǒ èr líng yī jiǔ nián lái Zhōngguó de.", "en": "I came to China in 2019."},
         {"zh": "一月一号是新年。", "pinyin": "Yī yuè yī hào shì xīnnián.", "en": "January 1st is New Year."},
     ]},

    {"name": "点/分 telling time", "name_zh": "点/分", "hsk_level": 1, "category": "structure",
     "description": "Telling time with 点 (o'clock) and 分 (minutes). 半 means half past, 刻 means quarter.", "difficulty": 0.2,
     "examples": [
         {"zh": "现在三点半。", "pinyin": "Xiànzài sān diǎn bàn.", "en": "It is half past three now."},
         {"zh": "我八点十五分上课。", "pinyin": "Wǒ bā diǎn shíwǔ fēn shàngkè.", "en": "I have class at 8:15."},
         {"zh": "她六点一刻起床。", "pinyin": "Tā liù diǎn yí kè qǐchuáng.", "en": "She gets up at a quarter past six."},
         {"zh": "现在差五分十二点。", "pinyin": "Xiànzài chà wǔ fēn shí'èr diǎn.", "en": "It is five minutes to twelve now."},
     ]},

    {"name": "Double object V+IO+DO", "name_zh": "双宾语结构", "hsk_level": 1, "category": "structure",
     "description": "Verbs like 给, 教, 告诉, 送 can take two objects: an indirect object (person) and a direct object (thing): 给我一本书", "difficulty": 0.3,
     "examples": [
         {"zh": "请给我一杯水。", "pinyin": "Qǐng gěi wǒ yì bēi shuǐ.", "en": "Please give me a glass of water."},
         {"zh": "老师教我们中文。", "pinyin": "Lǎoshī jiāo wǒmen Zhōngwén.", "en": "The teacher teaches us Chinese."},
         {"zh": "他告诉我一个好消息。", "pinyin": "Tā gàosu wǒ yí gè hǎo xiāoxi.", "en": "He told me a piece of good news."},
         {"zh": "妈妈送我一本书。", "pinyin": "Māma sòng wǒ yì běn shū.", "en": "Mom gave me a book as a gift."},
     ]},

    {"name": "SVO basic word order", "name_zh": "SVO基本语序", "hsk_level": 1, "category": "structure",
     "description": "Chinese basic word order is Subject-Verb-Object, same as English. Modifiers (time, place) generally come before the verb.", "difficulty": 0.1,
     "examples": [
         {"zh": "我吃饭。", "pinyin": "Wǒ chīfàn.", "en": "I eat."},
         {"zh": "他看书。", "pinyin": "Tā kàn shū.", "en": "He reads books."},
         {"zh": "我们学中文。", "pinyin": "Wǒmen xué Zhōngwén.", "en": "We study Chinese."},
         {"zh": "她喝咖啡。", "pinyin": "Tā hē kāfēi.", "en": "She drinks coffee."},
     ]},

    {"name": "Adjective predicate without 是", "name_zh": "形容词谓语句", "hsk_level": 1, "category": "structure",
     "description": "Adjectives act as predicates directly without 是. In positive statements, an adverb like 很 is usually added to fill the rhythm, but does not always mean 'very'.", "difficulty": 0.2,
     "examples": [
         {"zh": "天气冷。", "pinyin": "Tiānqì lěng.", "en": "The weather is cold."},
         {"zh": "这个菜好吃。", "pinyin": "Zhège cài hǎochī.", "en": "This dish is delicious."},
         {"zh": "中文难不难？", "pinyin": "Zhōngwén nán bu nán?", "en": "Is Chinese hard?"},
         {"zh": "今天不热。", "pinyin": "Jīntiān bú rè.", "en": "Today is not hot."},
     ]},

    {"name": "Number + measure word + noun", "name_zh": "数+量词+名词", "hsk_level": 1, "category": "measure_word",
     "description": "In Chinese, a measure word (classifier) must appear between a number and a noun. Different nouns require different measure words, with 个 as the most common default.", "difficulty": 0.2,
     "examples": [
         {"zh": "三个人。", "pinyin": "Sān gè rén.", "en": "Three people."},
         {"zh": "两本书。", "pinyin": "Liǎng běn shū.", "en": "Two books."},
         {"zh": "一条鱼。", "pinyin": "Yì tiáo yú.", "en": "One fish."},
         {"zh": "五张桌子。", "pinyin": "Wǔ zhāng zhuōzi.", "en": "Five tables."},
     ]},

    {"name": "是不是 A-not-A question", "name_zh": "是不是", "hsk_level": 1, "category": "structure",
     "description": "Forming a yes/no question by inserting 是不是, either before the verb or at the end, seeking confirmation: 你是不是学生？", "difficulty": 0.2,
     "examples": [
         {"zh": "你是不是学生？", "pinyin": "Nǐ shì bu shì xuéshēng?", "en": "Are you a student (or not)?"},
         {"zh": "他是不是中国人？", "pinyin": "Tā shì bu shì Zhōngguó rén?", "en": "Is he Chinese?"},
         {"zh": "这个是不是你的？", "pinyin": "Zhège shì bu shì nǐ de?", "en": "Is this yours?"},
         {"zh": "你是不是想去？", "pinyin": "Nǐ shì bu shì xiǎng qù?", "en": "Is it that you want to go?"},
     ]},

    {"name": "V不V A-not-A question", "name_zh": "V不V问句", "hsk_level": 1, "category": "structure",
     "description": "Forming a yes/no question by repeating the verb in affirmative-negative form: 去不去？好不好？The listener chooses the affirmative or negative.", "difficulty": 0.3,
     "examples": [
         {"zh": "你去不去？", "pinyin": "Nǐ qù bu qù?", "en": "Are you going or not?"},
         {"zh": "好不好？", "pinyin": "Hǎo bu hǎo?", "en": "Is it good? / Okay?"},
         {"zh": "你喜欢不喜欢？", "pinyin": "Nǐ xǐhuan bu xǐhuan?", "en": "Do you like it or not?"},
         {"zh": "你吃不吃饭？", "pinyin": "Nǐ chī bu chī fàn?", "en": "Are you going to eat?"},
     ]},

    {"name": "想/要 expressing desire", "name_zh": "想/要(愿望)", "hsk_level": 1, "category": "structure",
     "description": "想 expresses a wish or desire (softer), 要 expresses a stronger want or intention. Both are followed directly by a verb.", "difficulty": 0.2,
     "examples": [
         {"zh": "我想去中国。", "pinyin": "Wǒ xiǎng qù Zhōngguó.", "en": "I want to go to China."},
         {"zh": "他想学做菜。", "pinyin": "Tā xiǎng xué zuò cài.", "en": "He wants to learn to cook."},
         {"zh": "我要买这个。", "pinyin": "Wǒ yào mǎi zhège.", "en": "I want to buy this one."},
         {"zh": "你想不想看电影？", "pinyin": "Nǐ xiǎng bu xiǎng kàn diànyǐng?", "en": "Do you want to watch a movie?"},
     ]},

    {"name": "岁 expressing age", "name_zh": "岁", "hsk_level": 1, "category": "structure",
     "description": "Age is expressed with number + 岁, typically in a noun predicate sentence without 是: 我二十岁. For asking age, use 多大 (general) or 几岁 (children).", "difficulty": 0.1,
     "examples": [
         {"zh": "我二十岁。", "pinyin": "Wǒ èrshí suì.", "en": "I am twenty years old."},
         {"zh": "她今年五岁了。", "pinyin": "Tā jīnnián wǔ suì le.", "en": "She is five years old this year."},
         {"zh": "你多大了？", "pinyin": "Nǐ duō dà le?", "en": "How old are you?"},
         {"zh": "他的孩子三岁半。", "pinyin": "Tā de háizi sān suì bàn.", "en": "His child is three and a half years old."},
     ]},

    # =========================================================================
    # HSK 2 — additional grammar points
    # =========================================================================

    {"name": "要是...就 if...then (colloquial)", "name_zh": "要是…就", "hsk_level": 2, "category": "connector",
     "description": "Colloquial conditional: 要是 means 'if' (less formal than 如果), paired with 就 for 'then'. Common in spoken Chinese.", "difficulty": 0.3,
     "examples": [
         {"zh": "要是下雨，我们就不去了。", "pinyin": "Yàoshi xiàyǔ, wǒmen jiù bú qù le.", "en": "If it rains, we won't go."},
         {"zh": "要是你不想吃，就别吃了。", "pinyin": "Yàoshi nǐ bù xiǎng chī, jiù bié chī le.", "en": "If you don't want to eat, then don't."},
         {"zh": "要是有时间，我就去看你。", "pinyin": "Yàoshi yǒu shíjiān, wǒ jiù qù kàn nǐ.", "en": "If I have time, I'll go visit you."},
     ]},

    {"name": "V+得多 much more (degree)", "name_zh": "V+得多", "hsk_level": 2, "category": "comparison",
     "description": "Used after 比 comparisons to indicate a large difference: A比B + adj + 得多. Emphasizes the gap is significant.", "difficulty": 0.4,
     "examples": [
         {"zh": "他比我高得多。", "pinyin": "Tā bǐ wǒ gāo de duō.", "en": "He is much taller than me."},
         {"zh": "坐飞机比坐火车快得多。", "pinyin": "Zuò fēijī bǐ zuò huǒchē kuài de duō.", "en": "Flying is much faster than taking the train."},
         {"zh": "这个好得多。", "pinyin": "Zhège hǎo de duō.", "en": "This one is much better."},
     ]},

    {"name": "又...又 both...and (HSK2 intro)", "name_zh": "又…又(初级)", "hsk_level": 2, "category": "structure",
     "description": "Basic pattern connecting two adjectives or states that coexist: 又大又好. Introduced at HSK 2 with simple adjective pairs.", "difficulty": 0.3,
     "examples": [
         {"zh": "这个房间又大又亮。", "pinyin": "Zhège fángjiān yòu dà yòu liàng.", "en": "This room is both big and bright."},
         {"zh": "她又高兴又紧张。", "pinyin": "Tā yòu gāoxìng yòu jǐnzhāng.", "en": "She is both happy and nervous."},
         {"zh": "今天又冷又下雨。", "pinyin": "Jīntiān yòu lěng yòu xiàyǔ.", "en": "Today is both cold and rainy."},
     ]},

    {"name": "比+adj+一点 a bit more", "name_zh": "比+一点", "hsk_level": 2, "category": "comparison",
     "description": "Adding 一点 after a comparative adjective to indicate a small difference: A比B + adj + 一点. Softens the comparison.", "difficulty": 0.3,
     "examples": [
         {"zh": "这个比那个大一点。", "pinyin": "Zhège bǐ nàge dà yìdiǎn.", "en": "This one is a little bigger than that one."},
         {"zh": "今天比昨天冷一点。", "pinyin": "Jīntiān bǐ zuótiān lěng yìdiǎn.", "en": "Today is a bit colder than yesterday."},
         {"zh": "她比我高一点儿。", "pinyin": "Tā bǐ wǒ gāo yìdiǎnr.", "en": "She is a little taller than me."},
     ]},

    {"name": "V+到 result 'arrive/reach'", "name_zh": "V+到(结果)", "hsk_level": 2, "category": "complement",
     "description": "Result complement 到 after a verb indicates reaching, achieving, or continuing to a point: 找到 (found), 看到 (saw), 学到 (learned).", "difficulty": 0.4,
     "examples": [
         {"zh": "我找到了我的钥匙。", "pinyin": "Wǒ zhǎodào le wǒ de yàoshi.", "en": "I found my keys."},
         {"zh": "你看到那个人了吗？", "pinyin": "Nǐ kàndào nàge rén le ma?", "en": "Did you see that person?"},
         {"zh": "我学到了很多东西。", "pinyin": "Wǒ xuédào le hěn duō dōngxi.", "en": "I learned a lot of things."},
     ]},

    {"name": "V+见 result 'perceive'", "name_zh": "V+见(感知)", "hsk_level": 2, "category": "complement",
     "description": "Result complement 见 after perception verbs means the action was successfully perceived: 看见 (saw), 听见 (heard), 遇见 (met).", "difficulty": 0.4,
     "examples": [
         {"zh": "我看见他了。", "pinyin": "Wǒ kànjiàn tā le.", "en": "I saw him."},
         {"zh": "你听见了吗？", "pinyin": "Nǐ tīngjiàn le ma?", "en": "Did you hear it?"},
         {"zh": "我在路上遇见了一个老朋友。", "pinyin": "Wǒ zài lùshang yùjiàn le yí gè lǎo péngyou.", "en": "I ran into an old friend on the road."},
     ]},

    {"name": "V+懂 result 'understand'", "name_zh": "V+懂(理解)", "hsk_level": 2, "category": "complement",
     "description": "Result complement 懂 means the action leads to understanding: 听懂 (understood by listening), 看懂 (understood by reading).", "difficulty": 0.4,
     "examples": [
         {"zh": "你听懂了吗？", "pinyin": "Nǐ tīngdǒng le ma?", "en": "Did you understand (what was said)?"},
         {"zh": "这本书我看不懂。", "pinyin": "Zhè běn shū wǒ kàn bu dǒng.", "en": "I can't understand this book."},
         {"zh": "她说的话我都听懂了。", "pinyin": "Tā shuō de huà wǒ dōu tīngdǒng le.", "en": "I understood everything she said."},
     ]},

    {"name": "V+会 result 'learn/master'", "name_zh": "V+会(学会)", "hsk_level": 2, "category": "complement",
     "description": "Result complement 会 means the action results in having learned or mastered a skill: 学会 (learned how to), 记会 (memorized).", "difficulty": 0.4,
     "examples": [
         {"zh": "我学会了游泳。", "pinyin": "Wǒ xuéhuì le yóuyǒng.", "en": "I learned how to swim."},
         {"zh": "这首歌你学会了吗？", "pinyin": "Zhè shǒu gē nǐ xuéhuì le ma?", "en": "Have you learned this song?"},
         {"zh": "他终于学会开车了。", "pinyin": "Tā zhōngyú xuéhuì kāichē le.", "en": "He finally learned to drive."},
     ]},

    {"name": "V+完 result 'finish'", "name_zh": "V+完(完成)", "hsk_level": 2, "category": "complement",
     "description": "Result complement 完 means the action has been completed or finished: 吃完 (finished eating), 做完 (finished doing), 看完 (finished reading/watching).", "difficulty": 0.3,
     "examples": [
         {"zh": "你吃完了吗？", "pinyin": "Nǐ chīwán le ma?", "en": "Have you finished eating?"},
         {"zh": "我做完作业了。", "pinyin": "Wǒ zuòwán zuòyè le.", "en": "I finished my homework."},
         {"zh": "这本书我还没看完。", "pinyin": "Zhè běn shū wǒ hái méi kànwán.", "en": "I haven't finished reading this book yet."},
     ]},

    {"name": "V+开 result 'open/apart'", "name_zh": "V+开(打开/分开)", "hsk_level": 2, "category": "complement",
     "description": "Result complement 开 means the action opens, separates, or moves away: 打开 (opened), 离开 (left), 拿开 (moved away).", "difficulty": 0.4,
     "examples": [
         {"zh": "请把窗户打开。", "pinyin": "Qǐng bǎ chuānghu dǎkāi.", "en": "Please open the window."},
         {"zh": "他离开了北京。", "pinyin": "Tā líkāi le Běijīng.", "en": "He left Beijing."},
         {"zh": "请把手拿开。", "pinyin": "Qǐng bǎ shǒu nákāi.", "en": "Please take your hand away."},
     ]},

    {"name": "V+上 directional 'up/attach'", "name_zh": "V+上(向上/接触)", "hsk_level": 2, "category": "complement",
     "description": "Directional complement 上 indicates upward motion, attachment, or achieving a goal: 穿上 (put on), 关上 (close), 爱上 (fall in love with).", "difficulty": 0.4,
     "examples": [
         {"zh": "请把门关上。", "pinyin": "Qǐng bǎ mén guānshang.", "en": "Please close the door."},
         {"zh": "快穿上外套，外面冷。", "pinyin": "Kuài chuānshang wàitào, wàimiàn lěng.", "en": "Put on your coat quickly, it's cold outside."},
         {"zh": "他爱上了那个姑娘。", "pinyin": "Tā àishang le nàge gūniang.", "en": "He fell in love with that girl."},
     ]},

    {"name": "V+下 directional 'down/remain'", "name_zh": "V+下(向下/留下)", "hsk_level": 2, "category": "complement",
     "description": "Directional complement 下 indicates downward motion, removal, or remaining/recording: 坐下 (sit down), 写下 (write down), 留下 (stay/leave behind).", "difficulty": 0.4,
     "examples": [
         {"zh": "请坐下。", "pinyin": "Qǐng zuòxia.", "en": "Please sit down."},
         {"zh": "把这个电话号码写下来。", "pinyin": "Bǎ zhège diànhuà hàomǎ xiěxialai.", "en": "Write down this phone number."},
         {"zh": "他留下了一封信。", "pinyin": "Tā liúxia le yì fēng xìn.", "en": "He left behind a letter."},
     ]},

    {"name": "V+来 directional 'towards speaker'", "name_zh": "V+来(靠近)", "hsk_level": 2, "category": "complement",
     "description": "Directional complement 来 indicates movement towards the speaker: 过来 (come over), 进来 (come in), 回来 (come back).", "difficulty": 0.3,
     "examples": [
         {"zh": "请进来。", "pinyin": "Qǐng jìnlái.", "en": "Please come in."},
         {"zh": "他走过来了。", "pinyin": "Tā zǒu guòlái le.", "en": "He walked over (towards me)."},
         {"zh": "你什么时候回来？", "pinyin": "Nǐ shénme shíhou huílái?", "en": "When are you coming back?"},
     ]},

    {"name": "V+去 directional 'away from speaker'", "name_zh": "V+去(远离)", "hsk_level": 2, "category": "complement",
     "description": "Directional complement 去 indicates movement away from the speaker: 出去 (go out), 过去 (go over), 回去 (go back).", "difficulty": 0.3,
     "examples": [
         {"zh": "他跑出去了。", "pinyin": "Tā pǎo chūqù le.", "en": "He ran out."},
         {"zh": "我们走过去吧。", "pinyin": "Wǒmen zǒu guòqù ba.", "en": "Let's walk over there."},
         {"zh": "你先回去吧。", "pinyin": "Nǐ xiān huíqù ba.", "en": "You go back first."},
     ]},

    {"name": "一会儿 a moment", "name_zh": "一会儿", "hsk_level": 2, "category": "structure",
     "description": "Indicates a short period of time, meaning 'a moment' or 'in a little while': 等一会儿、过一会儿.", "difficulty": 0.3,
     "examples": [
         {"zh": "等一会儿。", "pinyin": "Děng yíhuìr.", "en": "Wait a moment."},
         {"zh": "我过一会儿再来。", "pinyin": "Wǒ guò yíhuìr zài lái.", "en": "I'll come back in a little while."},
         {"zh": "他一会儿就回来。", "pinyin": "Tā yíhuìr jiù huílái.", "en": "He'll be back in a moment."},
     ]},

    {"name": "多么 how (exclamatory)", "name_zh": "多么", "hsk_level": 2, "category": "structure",
     "description": "Exclamatory adverb meaning 'how' or 'what a', used to express strong emotion or admiration: 多么漂亮！", "difficulty": 0.3,
     "examples": [
         {"zh": "这里的风景多么美啊！", "pinyin": "Zhèlǐ de fēngjǐng duōme měi a!", "en": "How beautiful the scenery is here!"},
         {"zh": "多么好的天气！", "pinyin": "Duōme hǎo de tiānqì!", "en": "What wonderful weather!"},
         {"zh": "他多么想回家啊。", "pinyin": "Tā duōme xiǎng huíjiā a.", "en": "How much he wants to go home."},
     ]},

    {"name": "Exclamatory particles 哦/啊/呀", "name_zh": "感叹助词", "hsk_level": 2, "category": "particle",
     "description": "Sentence-final particles expressing emotion: 啊 (surprise, admiration), 呀 (variant of 啊 after certain vowels), 哦 (realization, acknowledgment).", "difficulty": 0.3,
     "examples": [
         {"zh": "太好了啊！", "pinyin": "Tài hǎo le a!", "en": "That's wonderful!"},
         {"zh": "哦，原来是这样。", "pinyin": "Ó, yuánlái shì zhèyàng.", "en": "Oh, so that's how it is."},
         {"zh": "下雨了呀！", "pinyin": "Xiàyǔ le ya!", "en": "Oh, it's raining!"},
         {"zh": "你来了啊！", "pinyin": "Nǐ lái le a!", "en": "Oh, you're here!"},
     ]},

    {"name": "一共 altogether", "name_zh": "一共", "hsk_level": 2, "category": "particle",
     "description": "Adverb meaning 'altogether/in total', placed before the verb or number phrase: 一共多少钱？", "difficulty": 0.3,
     "examples": [
         {"zh": "一共多少钱？", "pinyin": "Yígòng duōshao qián?", "en": "How much is it altogether?"},
         {"zh": "我们一共五个人。", "pinyin": "Wǒmen yígòng wǔ gè rén.", "en": "There are five of us in total."},
         {"zh": "他一共买了三本书。", "pinyin": "Tā yígòng mǎile sān běn shū.", "en": "He bought three books in total."},
     ]},

    {"name": "当然 of course", "name_zh": "当然", "hsk_level": 2, "category": "particle",
     "description": "Adverb meaning 'of course/naturally', expressing that something is obvious or expected: 当然可以.", "difficulty": 0.3,
     "examples": [
         {"zh": "当然可以。", "pinyin": "Dāngrán kěyǐ.", "en": "Of course you can."},
         {"zh": "你会来吗？——当然！", "pinyin": "Nǐ huì lái ma? ——Dāngrán!", "en": "Will you come? — Of course!"},
         {"zh": "当然，学中文需要时间。", "pinyin": "Dāngrán, xué Zhōngwén xūyào shíjiān.", "en": "Of course, learning Chinese takes time."},
     ]},

    {"name": "几+MW approximate small number", "name_zh": "几+量词(概数)", "hsk_level": 2, "category": "structure",
     "description": "When not in a question, 几 means 'a few/several' (approximately 2-9), always with a measure word: 我等了几分钟.", "difficulty": 0.3,
     "examples": [
         {"zh": "桌子上有几本书。", "pinyin": "Zhuōzi shàng yǒu jǐ běn shū.", "en": "There are a few books on the table."},
         {"zh": "我等了几分钟。", "pinyin": "Wǒ děngle jǐ fēnzhōng.", "en": "I waited a few minutes."},
         {"zh": "他买了几个苹果。", "pinyin": "Tā mǎile jǐ gè píngguǒ.", "en": "He bought several apples."},
     ]},

    {"name": "百/千/万 large numbers", "name_zh": "百/千/万", "hsk_level": 2, "category": "structure",
     "description": "Large number system: 百 (hundred), 千 (thousand), 万 (ten thousand). Chinese groups by 万 (10,000) rather than by thousand.", "difficulty": 0.4,
     "examples": [
         {"zh": "这个学校有三千个学生。", "pinyin": "Zhège xuéxiào yǒu sānqiān gè xuéshēng.", "en": "This school has three thousand students."},
         {"zh": "一百块钱。", "pinyin": "Yìbǎi kuài qián.", "en": "One hundred yuan."},
         {"zh": "北京有两千多万人。", "pinyin": "Běijīng yǒu liǎngqiān duō wàn rén.", "en": "Beijing has over twenty million people."},
         {"zh": "五万块。", "pinyin": "Wǔ wàn kuài.", "en": "Fifty thousand yuan."},
     ]},

    {"name": "第+number ordinal", "name_zh": "第+数字", "hsk_level": 2, "category": "structure",
     "description": "第 before a number creates an ordinal number (first, second, third...): 第一、第二、第三.", "difficulty": 0.3,
     "examples": [
         {"zh": "他是第一名。", "pinyin": "Tā shì dì yī míng.", "en": "He is first place."},
         {"zh": "这是我第二次来中国。", "pinyin": "Zhè shì wǒ dì èr cì lái Zhōngguó.", "en": "This is my second time coming to China."},
         {"zh": "请翻到第三十五页。", "pinyin": "Qǐng fāndào dì sānshíwǔ yè.", "en": "Please turn to page thirty-five."},
     ]},

    {"name": "得 complement marker (structural)", "name_zh": "得(补语标记)", "hsk_level": 2, "category": "complement",
     "description": "The particle 得 links a verb to its complement, describing how or to what degree the action is performed. The complement after 得 can be an adjective, phrase, or clause.", "difficulty": 0.5,
     "examples": [
         {"zh": "他跑得很快。", "pinyin": "Tā pǎo de hěn kuài.", "en": "He runs very fast."},
         {"zh": "她唱得非常好。", "pinyin": "Tā chàng de fēicháng hǎo.", "en": "She sings extremely well."},
         {"zh": "我累得不想动。", "pinyin": "Wǒ lèi de bù xiǎng dòng.", "en": "I'm so tired I don't want to move."},
         {"zh": "他高兴得跳起来了。", "pinyin": "Tā gāoxìng de tiào qǐlái le.", "en": "He was so happy he jumped up."},
     ]},

    {"name": "Topic-comment structure", "name_zh": "话题-评论结构", "hsk_level": 2, "category": "structure",
     "description": "Chinese often fronts the topic before commenting on it. The topic sets the frame, then the comment follows: 这本书我看过了 (this book, I've read it).", "difficulty": 0.4,
     "examples": [
         {"zh": "这本书我看过了。", "pinyin": "Zhè běn shū wǒ kànguo le.", "en": "This book, I've read it."},
         {"zh": "中国菜我很喜欢。", "pinyin": "Zhōngguó cài wǒ hěn xǐhuan.", "en": "Chinese food, I like it a lot."},
         {"zh": "那个地方我去过。", "pinyin": "Nàge dìfang wǒ qùguo.", "en": "That place, I've been there."},
         {"zh": "这件事你知道吗？", "pinyin": "Zhè jiàn shì nǐ zhīdào ma?", "en": "This matter, do you know about it?"},
     ]},

    {"name": "每...都 every...all", "name_zh": "每…都", "hsk_level": 2, "category": "structure",
     "description": "每 (every) is typically paired with 都 (all) in the predicate: 每个人都来了. Without 都, the sentence sounds incomplete.", "difficulty": 0.3,
     "examples": [
         {"zh": "每个人都来了。", "pinyin": "Měi gè rén dōu lái le.", "en": "Everyone came."},
         {"zh": "我每天都六点起床。", "pinyin": "Wǒ měitiān dōu liù diǎn qǐchuáng.", "en": "I get up at six every day."},
         {"zh": "她每次都迟到。", "pinyin": "Tā měi cì dōu chídào.", "en": "She is late every time."},
     ]},

    {"name": "V+了+number+MW+noun completed quantity", "name_zh": "V+了+数量", "hsk_level": 2, "category": "aspect",
     "description": "Verb + 了 + number + measure word + noun describes a completed action with a specific quantity: 我买了三本书.", "difficulty": 0.4,
     "examples": [
         {"zh": "我买了三本书。", "pinyin": "Wǒ mǎile sān běn shū.", "en": "I bought three books."},
         {"zh": "她喝了两杯咖啡。", "pinyin": "Tā hēle liǎng bēi kāfēi.", "en": "She drank two cups of coffee."},
         {"zh": "他吃了一个苹果。", "pinyin": "Tā chīle yí gè píngguǒ.", "en": "He ate an apple."},
         {"zh": "我们看了两部电影。", "pinyin": "Wǒmen kànle liǎng bù diànyǐng.", "en": "We watched two movies."},
     ]},

    {"name": "多长时间 asking duration", "name_zh": "多长时间", "hsk_level": 2, "category": "structure",
     "description": "Question phrase asking 'how long' (duration). Placed after the verb or at the beginning: 你学了多长时间？", "difficulty": 0.3,
     "examples": [
         {"zh": "你学了多长时间中文？", "pinyin": "Nǐ xuéle duō cháng shíjiān Zhōngwén?", "en": "How long have you been studying Chinese?"},
         {"zh": "从这儿到那儿要多长时间？", "pinyin": "Cóng zhèr dào nàr yào duō cháng shíjiān?", "en": "How long does it take from here to there?"},
         {"zh": "你在中国住了多长时间？", "pinyin": "Nǐ zài Zhōngguó zhùle duō cháng shíjiān?", "en": "How long have you lived in China?"},
     ]},

    {"name": "怎么样 how about / what's it like", "name_zh": "怎么样", "hsk_level": 2, "category": "structure",
     "description": "Used to ask for opinions, evaluations, or to make suggestions: 这个怎么样？天气怎么样？", "difficulty": 0.3,
     "examples": [
         {"zh": "这个怎么样？", "pinyin": "Zhège zěnmeyàng?", "en": "How about this one? / What do you think of this?"},
         {"zh": "今天天气怎么样？", "pinyin": "Jīntiān tiānqì zěnmeyàng?", "en": "How is the weather today?"},
         {"zh": "我们明天去，怎么样？", "pinyin": "Wǒmen míngtiān qù, zěnmeyàng?", "en": "Let's go tomorrow, how about it?"},
         {"zh": "你最近怎么样？", "pinyin": "Nǐ zuìjìn zěnmeyàng?", "en": "How have you been lately?"},
     ]},

    {"name": "因为 because (standalone)", "name_zh": "因为(单独)", "hsk_level": 2, "category": "connector",
     "description": "因为 can be used alone without 所以, especially in answers or when the result is obvious from context.", "difficulty": 0.3,
     "examples": [
         {"zh": "他没来，因为他生病了。", "pinyin": "Tā méi lái, yīnwèi tā shēngbìng le.", "en": "He didn't come, because he was sick."},
         {"zh": "因为太贵了，我没买。", "pinyin": "Yīnwèi tài guì le, wǒ méi mǎi.", "en": "Because it was too expensive, I didn't buy it."},
         {"zh": "你为什么迟到？——因为堵车。", "pinyin": "Nǐ wèishénme chídào? ——Yīnwèi dǔchē.", "en": "Why were you late? — Because of traffic."},
     ]},

    {"name": "虽然...但是 concessive (HSK2 full)", "name_zh": "虽然…但是(完整)", "hsk_level": 2, "category": "connector",
     "description": "Full concessive pattern: 虽然 introduces the conceded point, 但是 introduces the contrasting main point. 但是 can be replaced by 可是.", "difficulty": 0.4,
     "examples": [
         {"zh": "虽然他很忙，但是每天都锻炼。", "pinyin": "Suīrán tā hěn máng, dànshì měitiān dōu duànliàn.", "en": "Although he is very busy, he exercises every day."},
         {"zh": "虽然很难，但是我不放弃。", "pinyin": "Suīrán hěn nán, dànshì wǒ bù fàngqì.", "en": "Although it is difficult, I won't give up."},
         {"zh": "虽然天气不好，但是我们还是出去了。", "pinyin": "Suīrán tiānqì bù hǎo, dànshì wǒmen háishi chūqù le.", "en": "Although the weather was bad, we still went out."},
     ]},

    {"name": "不但...而且 additive (HSK2 full)", "name_zh": "不但…而且(完整)", "hsk_level": 2, "category": "connector",
     "description": "Progressive pattern: 不但 introduces the first point, 而且 adds a stronger second point. The two clauses should share the same subject.", "difficulty": 0.4,
     "examples": [
         {"zh": "他不但聪明，而且很努力。", "pinyin": "Tā búdàn cōngming, érqiě hěn nǔlì.", "en": "He is not only smart, but also very hardworking."},
         {"zh": "这里不但便宜，而且东西好。", "pinyin": "Zhèlǐ búdàn piányi, érqiě dōngxi hǎo.", "en": "This place is not only cheap, but also has good stuff."},
         {"zh": "她不但会唱歌，而且会弹钢琴。", "pinyin": "Tā búdàn huì chànggē, érqiě huì tán gāngqín.", "en": "She can not only sing, but also play the piano."},
     ]},

    {"name": "Frequency complement 次/遍/回", "name_zh": "频率补语", "hsk_level": 2, "category": "complement",
     "description": "Counting occurrences with 次 (times), 遍 (from start to finish), 回 (occasions). Placed after the verb: 去过三次.", "difficulty": 0.4,
     "examples": [
         {"zh": "我去过北京两次。", "pinyin": "Wǒ qùguo Běijīng liǎng cì.", "en": "I've been to Beijing twice."},
         {"zh": "请再说一遍。", "pinyin": "Qǐng zài shuō yí biàn.", "en": "Please say it one more time (from start to finish)."},
         {"zh": "这部电影我看了三回。", "pinyin": "Zhè bù diànyǐng wǒ kànle sān huí.", "en": "I've watched this movie three times."},
     ]},

    {"name": "不+adj+吗 rhetorical confirmation", "name_zh": "不+adj+吗(反问)", "hsk_level": 2, "category": "structure",
     "description": "Rhetorical question pattern seeking agreement or confirmation: 不好吗？(Isn't it good?) implies the speaker thinks it IS good.", "difficulty": 0.4,
     "examples": [
         {"zh": "这样不好吗？", "pinyin": "Zhèyàng bù hǎo ma?", "en": "Isn't this good? (I think it is.)"},
         {"zh": "他不是你的朋友吗？", "pinyin": "Tā bú shì nǐ de péngyou ma?", "en": "Isn't he your friend?"},
         {"zh": "你不喜欢吗？", "pinyin": "Nǐ bù xǐhuan ma?", "en": "Don't you like it? (I thought you did.)"},
     ]},

    {"name": "除了...以外 except/besides (HSK2 intro)", "name_zh": "除了…以外(初级)", "hsk_level": 2, "category": "structure",
     "description": "Basic introduction of 除了...以外 at HSK 2 level: 'except for' (with 都) or 'besides' (with 还/也). The meaning depends on the following adverb.", "difficulty": 0.4,
     "examples": [
         {"zh": "除了他以外，大家都来了。", "pinyin": "Chúle tā yǐwài, dàjiā dōu lái le.", "en": "Everyone came except him."},
         {"zh": "除了中文，我还学英文。", "pinyin": "Chúle Zhōngwén, wǒ hái xué Yīngwén.", "en": "Besides Chinese, I also study English."},
         {"zh": "除了星期天以外，我每天都上班。", "pinyin": "Chúle xīngqītiān yǐwài, wǒ měitiān dōu shàngbān.", "en": "I work every day except Sunday."},
     ]},

    {"name": "连...都/也 even (HSK2 intro)", "name_zh": "连…都/也(初级)", "hsk_level": 2, "category": "structure",
     "description": "Basic emphatic pattern: 连 highlights something extreme or unexpected, followed by 都 or 也 to emphasize: 连小孩子都知道.", "difficulty": 0.5,
     "examples": [
         {"zh": "他连饭都没吃。", "pinyin": "Tā lián fàn dōu méi chī.", "en": "He didn't even eat."},
         {"zh": "连孩子也会。", "pinyin": "Lián háizi yě huì.", "en": "Even children can do it."},
         {"zh": "我连他的名字都不知道。", "pinyin": "Wǒ lián tā de míngzi dōu bù zhīdào.", "en": "I don't even know his name."},
     ]},

    {"name": "越来越 more and more (HSK2 intro)", "name_zh": "越来越(初级)", "hsk_level": 2, "category": "comparison",
     "description": "Basic introduction of the 越来越 pattern: indicates a trend of continuous increase or change: 天越来越冷了.", "difficulty": 0.4,
     "examples": [
         {"zh": "天越来越冷了。", "pinyin": "Tiān yuèláiyuè lěng le.", "en": "It's getting colder and colder."},
         {"zh": "他的中文越来越好。", "pinyin": "Tā de Zhōngwén yuèláiyuè hǎo.", "en": "His Chinese is getting better and better."},
         {"zh": "生活越来越方便了。", "pinyin": "Shēnghuó yuèláiyuè fāngbiàn le.", "en": "Life is getting more and more convenient."},
     ]},

    {"name": "千万 by all means/absolutely must", "name_zh": "千万", "hsk_level": 2, "category": "particle",
     "description": "Adverb used to strongly urge or warn, meaning 'by all means' or 'whatever you do (don't)': 千万别忘了. Often used with 别 or 要.", "difficulty": 0.4,
     "examples": [
         {"zh": "千万别忘了带护照。", "pinyin": "Qiānwàn bié wàngle dài hùzhào.", "en": "Whatever you do, don't forget to bring your passport."},
         {"zh": "千万要小心！", "pinyin": "Qiānwàn yào xiǎoxīn!", "en": "You absolutely must be careful!"},
         {"zh": "千万别迟到。", "pinyin": "Qiānwàn bié chídào.", "en": "By all means don't be late."},
     ]},

    {"name": "其中 among (them)", "name_zh": "其中", "hsk_level": 2, "category": "structure",
     "description": "Pronoun meaning 'among them/of which', referring to a subset within a previously mentioned group: 其中三个是中国人.", "difficulty": 0.4,
     "examples": [
         {"zh": "我们班有二十个学生，其中五个是外国人。", "pinyin": "Wǒmen bān yǒu èrshí gè xuéshēng, qízhōng wǔ gè shì wàiguórén.", "en": "Our class has twenty students, five of whom are foreigners."},
         {"zh": "他买了很多水果，其中有苹果和香蕉。", "pinyin": "Tā mǎile hěn duō shuǐguǒ, qízhōng yǒu píngguǒ hé xiāngjiāo.", "en": "He bought a lot of fruit, including apples and bananas."},
         {"zh": "我去过很多国家，其中最喜欢日本。", "pinyin": "Wǒ qùguo hěn duō guójiā, qízhōng zuì xǐhuan Rìběn.", "en": "I've been to many countries, among which I like Japan the most."},
     ]},

    # =========================================================================
    # HSK 3 — additional grammar points
    # =========================================================================

    {"name": "差点(儿) almost/nearly", "name_zh": "差点(儿)", "hsk_level": 3, "category": "particle",
     "description": "Indicates something nearly happened (but didn't, or implies relief/regret). For undesirable events, 差点儿 = almost (but didn't); for desirable events, 差点儿没 = almost didn't (but did).", "difficulty": 0.5,
     "examples": [
         {"zh": "我差点儿迟到了。", "pinyin": "Wǒ chàdiǎnr chídào le.", "en": "I almost arrived late."},
         {"zh": "他差点儿摔倒。", "pinyin": "Tā chàdiǎnr shuāidǎo.", "en": "He almost fell down."},
         {"zh": "我差点儿没赶上飞机。", "pinyin": "Wǒ chàdiǎnr méi gǎnshàng fēijī.", "en": "I almost missed the plane (but caught it)."},
     ]},

    {"name": "本来 originally", "name_zh": "本来", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'originally/at first', implying a change from the original plan or situation: 我本来想去，后来没去.", "difficulty": 0.5,
     "examples": [
         {"zh": "我本来想去，后来没去。", "pinyin": "Wǒ běnlái xiǎng qù, hòulái méi qù.", "en": "I originally planned to go, but didn't in the end."},
         {"zh": "他本来不想说，可是还是说了。", "pinyin": "Tā běnlái bù xiǎng shuō, kěshì háishi shuō le.", "en": "He originally didn't want to say anything, but he said it anyway."},
         {"zh": "这件事本来很简单。", "pinyin": "Zhè jiàn shì běnlái hěn jiǎndān.", "en": "This matter was originally very simple."},
     ]},

    {"name": "幸好/幸亏 fortunately", "name_zh": "幸好/幸亏", "hsk_level": 3, "category": "particle",
     "description": "Adverbs meaning 'fortunately/luckily', indicating relief that a bad outcome was avoided: 幸好你来了. 幸亏 is slightly more emphatic.", "difficulty": 0.5,
     "examples": [
         {"zh": "幸好你提醒我了。", "pinyin": "Xìnghǎo nǐ tíxǐng wǒ le.", "en": "Fortunately you reminded me."},
         {"zh": "幸亏带了伞，不然就淋雨了。", "pinyin": "Xìngkuī dàile sǎn, bùrán jiù lín yǔ le.", "en": "Luckily I brought an umbrella, otherwise I'd have gotten soaked."},
         {"zh": "幸好没有受伤。", "pinyin": "Xìnghǎo méiyǒu shòushāng.", "en": "Fortunately no one was hurt."},
     ]},

    {"name": "可惜 it's a pity", "name_zh": "可惜", "hsk_level": 3, "category": "particle",
     "description": "Expresses regret or pity about something: 可惜他不能来. Can be used at the beginning or middle of a sentence.", "difficulty": 0.4,
     "examples": [
         {"zh": "可惜他不能来。", "pinyin": "Kěxī tā bù néng lái.", "en": "It's a pity he can't come."},
         {"zh": "票卖完了，太可惜了。", "pinyin": "Piào mài wán le, tài kěxī le.", "en": "The tickets are sold out, what a pity."},
         {"zh": "这么好的机会，可惜我错过了。", "pinyin": "Zhème hǎo de jīhuì, kěxī wǒ cuòguò le.", "en": "Such a good opportunity, it's a pity I missed it."},
     ]},

    {"name": "大概 probably/roughly", "name_zh": "大概", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'probably/roughly/approximately': 大概要两个小时. Indicates estimation or uncertainty.", "difficulty": 0.4,
     "examples": [
         {"zh": "大概要两个小时。", "pinyin": "Dàgài yào liǎng gè xiǎoshí.", "en": "It'll probably take about two hours."},
         {"zh": "他大概不会来了。", "pinyin": "Tā dàgài bú huì lái le.", "en": "He probably won't come."},
         {"zh": "这个大概多少钱？", "pinyin": "Zhège dàgài duōshao qián?", "en": "Roughly how much is this?"},
     ]},

    {"name": "另外 in addition/another", "name_zh": "另外(此外)", "hsk_level": 3, "category": "connector",
     "description": "As a conjunction, 另外 means 'in addition/moreover'. As a determiner, it means 'another/other': 另外一个. Both uses are common.", "difficulty": 0.5,
     "examples": [
         {"zh": "另外，我还想说一件事。", "pinyin": "Lìngwài, wǒ hái xiǎng shuō yí jiàn shì.", "en": "In addition, I'd like to mention one more thing."},
         {"zh": "你还有另外的办法吗？", "pinyin": "Nǐ hái yǒu lìngwài de bànfǎ ma?", "en": "Do you have another way?"},
         {"zh": "另外两个人也来了。", "pinyin": "Lìngwài liǎng gè rén yě lái le.", "en": "The other two people also came."},
     ]},

    {"name": "反而 on the contrary", "name_zh": "反而", "hsk_level": 3, "category": "connector",
     "description": "Adverb indicating a result opposite to what was expected: instead of X, Y happened. Often used after a clause stating the expectation.", "difficulty": 0.6,
     "examples": [
         {"zh": "吃了药，病反而更重了。", "pinyin": "Chīle yào, bìng fǎn'ér gèng zhòng le.", "en": "After taking medicine, the illness got worse instead."},
         {"zh": "他没有生气，反而笑了。", "pinyin": "Tā méiyǒu shēngqì, fǎn'ér xiào le.", "en": "He wasn't angry; on the contrary, he laughed."},
         {"zh": "帮了忙，他反而不高兴。", "pinyin": "Bāngle máng, tā fǎn'ér bù gāoxìng.", "en": "After helping him, he was unhappy instead."},
     ]},

    {"name": "甚至 even (emphasis)", "name_zh": "甚至(强调)", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'even/going so far as to', used to emphasize an extreme example in a progression: 他甚至不知道.", "difficulty": 0.5,
     "examples": [
         {"zh": "他很忙，甚至周末都在工作。", "pinyin": "Tā hěn máng, shènzhì zhōumò dōu zài gōngzuò.", "en": "He's very busy; he even works on weekends."},
         {"zh": "她甚至不知道这件事。", "pinyin": "Tā shènzhì bù zhīdào zhè jiàn shì.", "en": "She didn't even know about this matter."},
         {"zh": "天太冷了，甚至湖面都结冰了。", "pinyin": "Tiān tài lěng le, shènzhì húmiàn dōu jiébīng le.", "en": "It's so cold that even the lake surface has frozen."},
     ]},

    {"name": "果然 as expected (full pattern)", "name_zh": "果然(完整)", "hsk_level": 3, "category": "particle",
     "description": "Confirms that a prediction or expectation was proven correct. Used when the speaker had prior reason to expect the outcome: 我就知道，他果然来了.", "difficulty": 0.5,
     "examples": [
         {"zh": "我就知道，他果然来了。", "pinyin": "Wǒ jiù zhīdào, tā guǒrán lái le.", "en": "I knew it — he came, just as expected."},
         {"zh": "天气预报说会下雨，果然下了。", "pinyin": "Tiānqì yùbào shuō huì xiàyǔ, guǒrán xià le.", "en": "The forecast said it would rain, and sure enough it did."},
         {"zh": "大家都说这家餐厅好，果然很好吃。", "pinyin": "Dàjiā dōu shuō zhè jiā cāntīng hǎo, guǒrán hěn hǎochī.", "en": "Everyone said this restaurant was good, and it really is delicious."},
     ]},

    {"name": "并+不/没 actually not", "name_zh": "并+不/没", "hsk_level": 3, "category": "particle",
     "description": "并 before 不 or 没 adds emphasis, correcting a false assumption or expectation: 'actually not/in fact not': 事情并不简单.", "difficulty": 0.5,
     "examples": [
         {"zh": "事情并不简单。", "pinyin": "Shìqing bìng bù jiǎndān.", "en": "The matter is actually not simple."},
         {"zh": "他并没有生气。", "pinyin": "Tā bìng méiyǒu shēngqì.", "en": "He actually wasn't angry."},
         {"zh": "我并不是不想去。", "pinyin": "Wǒ bìng bú shì bù xiǎng qù.", "en": "It's not that I don't want to go."},
     ]},

    {"name": "赶紧 hurry up/quickly", "name_zh": "赶紧", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'hurry up/quickly', urging someone to do something without delay: 赶紧走吧.", "difficulty": 0.4,
     "examples": [
         {"zh": "赶紧走吧，要迟到了。", "pinyin": "Gǎnjǐn zǒu ba, yào chídào le.", "en": "Hurry up and go, we're going to be late."},
         {"zh": "你赶紧吃饭。", "pinyin": "Nǐ gǎnjǐn chīfàn.", "en": "Hurry up and eat."},
         {"zh": "下雨了，赶紧回家！", "pinyin": "Xiàyǔ le, gǎnjǐn huíjiā!", "en": "It's raining, hurry home!"},
     ]},

    {"name": "随便 casual/whatever", "name_zh": "随便", "hsk_level": 3, "category": "particle",
     "description": "Means 'casually/as one pleases/whatever'. As an adjective: 'casual'. As an adverb: 'freely/at will'. As a response: 'whatever/I don't mind'.", "difficulty": 0.5,
     "examples": [
         {"zh": "你想吃什么？——随便。", "pinyin": "Nǐ xiǎng chī shénme? ——Suíbiàn.", "en": "What do you want to eat? — Whatever."},
         {"zh": "别随便动别人的东西。", "pinyin": "Bié suíbiàn dòng biéren de dōngxi.", "en": "Don't casually touch other people's things."},
         {"zh": "随便坐吧。", "pinyin": "Suíbiàn zuò ba.", "en": "Sit wherever you like."},
     ]},

    {"name": "顺便 conveniently/while at it", "name_zh": "顺便", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'conveniently/while you're at it/by the way': doing something as a secondary action while doing the main thing.", "difficulty": 0.5,
     "examples": [
         {"zh": "你去超市的时候，顺便帮我买点牛奶。", "pinyin": "Nǐ qù chāoshì de shíhou, shùnbiàn bāng wǒ mǎi diǎn niúnǎi.", "en": "When you go to the supermarket, could you pick up some milk for me while you're at it?"},
         {"zh": "顺便问一下，明天有空吗？", "pinyin": "Shùnbiàn wèn yíxià, míngtiān yǒu kòng ma?", "en": "By the way, are you free tomorrow?"},
         {"zh": "我去邮局寄信，顺便买了几张邮票。", "pinyin": "Wǒ qù yóujú jì xìn, shùnbiàn mǎile jǐ zhāng yóupiào.", "en": "I went to the post office to mail a letter and bought some stamps while I was there."},
     ]},

    {"name": "使/让/叫+sb+V full causative", "name_zh": "使/让/叫(使役完整)", "hsk_level": 3, "category": "structure",
     "description": "Full causative construction: 使 (formal), 让 (neutral), 叫 (colloquial) + person + verb. 使 is more formal/written; 让 and 叫 are spoken.", "difficulty": 0.5,
     "examples": [
         {"zh": "这件事使他很难过。", "pinyin": "Zhè jiàn shì shǐ tā hěn nánguò.", "en": "This matter made him very sad."},
         {"zh": "妈妈让我早点回家。", "pinyin": "Māma ràng wǒ zǎodiǎn huíjiā.", "en": "Mom told me to come home early."},
         {"zh": "老师叫我们写一篇作文。", "pinyin": "Lǎoshī jiào wǒmen xiě yì piān zuòwén.", "en": "The teacher had us write an essay."},
         {"zh": "这个消息使大家很高兴。", "pinyin": "Zhège xiāoxi shǐ dàjiā hěn gāoxìng.", "en": "This news made everyone very happy."},
     ]},

    {"name": "把+obj+V+在/到/给 ba with locative/dative", "name_zh": "把+V+在/到/给", "hsk_level": 3, "category": "structure",
     "description": "Extended 把 construction with directional/locative complements: 把+obj+V+在 (place at), 把+obj+V+到 (move to), 把+obj+V+给 (give to).", "difficulty": 0.6,
     "examples": [
         {"zh": "请把书放在桌子上。", "pinyin": "Qǐng bǎ shū fàng zài zhuōzi shàng.", "en": "Please put the book on the table."},
         {"zh": "他把行李搬到楼上了。", "pinyin": "Tā bǎ xíngli bān dào lóushàng le.", "en": "He moved the luggage upstairs."},
         {"zh": "请把这个交给老师。", "pinyin": "Qǐng bǎ zhège jiāo gěi lǎoshī.", "en": "Please hand this to the teacher."},
         {"zh": "我把车停在门口了。", "pinyin": "Wǒ bǎ chē tíng zài ménkǒu le.", "en": "I parked the car at the entrance."},
     ]},

    {"name": "被+agent+V+complement full passive", "name_zh": "被+施事+V+补语", "hsk_level": 3, "category": "structure",
     "description": "Full passive with an agent and a result/directional complement: 被+agent+V+complement. The verb must have a complement; bare 被+V is incomplete.", "difficulty": 0.6,
     "examples": [
         {"zh": "我的手机被他摔坏了。", "pinyin": "Wǒ de shǒujī bèi tā shuāihuài le.", "en": "My phone was broken by him (from dropping it)."},
         {"zh": "那封信被风吹走了。", "pinyin": "Nà fēng xìn bèi fēng chuīzǒu le.", "en": "That letter was blown away by the wind."},
         {"zh": "蛋糕被弟弟吃完了。", "pinyin": "Dàngāo bèi dìdi chīwán le.", "en": "The cake was all eaten up by my younger brother."},
     ]},

    {"name": "V+起来 start to / seem", "name_zh": "V+起来(开始/看似)", "hsk_level": 3, "category": "complement",
     "description": "Directional complement 起来 has extended meanings: (1) 'start to' — 笑起来 (started laughing); (2) 'seem/appear' — 看起来 (looks like); (3) 'gather up' — 收起来 (put away).", "difficulty": 0.5,
     "examples": [
         {"zh": "他突然笑起来了。", "pinyin": "Tā tūrán xiào qǐlái le.", "en": "He suddenly started laughing."},
         {"zh": "天慢慢暖和起来了。", "pinyin": "Tiān mànmàn nuǎnhuo qǐlái le.", "en": "The weather is gradually warming up."},
         {"zh": "把这些东西收起来吧。", "pinyin": "Bǎ zhèxiē dōngxi shōu qǐlái ba.", "en": "Put these things away."},
         {"zh": "说起来容易，做起来难。", "pinyin": "Shuō qǐlái róngyì, zuò qǐlái nán.", "en": "It's easy to say, but hard to do."},
     ]},

    {"name": "V+出来 perceive/detect", "name_zh": "V+出来(识别)", "hsk_level": 3, "category": "complement",
     "description": "Complement 出来 after verbs of perception means to detect, recognize, or figure out: 看出来 (can tell by looking), 听出来 (recognized by hearing).", "difficulty": 0.5,
     "examples": [
         {"zh": "我看出来他不高兴。", "pinyin": "Wǒ kàn chūlái tā bù gāoxìng.", "en": "I could tell he was unhappy."},
         {"zh": "你听出来是谁了吗？", "pinyin": "Nǐ tīng chūlái shì shéi le ma?", "en": "Could you tell who it was by their voice?"},
         {"zh": "这个字我想不出来。", "pinyin": "Zhège zì wǒ xiǎng bu chūlái.", "en": "I can't recall this character."},
     ]},

    {"name": "V+下来 settle/continue", "name_zh": "V+下来(定下/持续)", "hsk_level": 3, "category": "complement",
     "description": "Complement 下来 has extended meanings: (1) 'settle/calm down' — 安静下来 (quieted down); (2) 'continue from past to present' — 坚持下来 (persisted); (3) 'record/preserve' — 记下来 (noted down).", "difficulty": 0.5,
     "examples": [
         {"zh": "教室里安静下来了。", "pinyin": "Jiàoshì lǐ ānjìng xiàlái le.", "en": "The classroom quieted down."},
         {"zh": "他坚持下来了。", "pinyin": "Tā jiānchí xiàlái le.", "en": "He persisted (and kept going)."},
         {"zh": "请把这个地址记下来。", "pinyin": "Qǐng bǎ zhège dìzhǐ jì xiàlái.", "en": "Please write down this address."},
     ]},

    {"name": "V+下去 continue further", "name_zh": "V+下去(继续)", "hsk_level": 3, "category": "complement",
     "description": "Complement 下去 indicates continuing an action into the future: 'keep doing/go on'. Often implies persistence despite difficulty.", "difficulty": 0.5,
     "examples": [
         {"zh": "你要坚持学下去。", "pinyin": "Nǐ yào jiānchí xué xiàqù.", "en": "You need to keep studying."},
         {"zh": "说下去，我在听。", "pinyin": "Shuō xiàqù, wǒ zài tīng.", "en": "Go on, I'm listening."},
         {"zh": "这样下去不行。", "pinyin": "Zhèyàng xiàqù bùxíng.", "en": "It won't work to continue like this."},
     ]},

    {"name": "连...都 full emphatic", "name_zh": "连…都(完整强调)", "hsk_level": 3, "category": "structure",
     "description": "Full emphatic pattern with 连...都 at HSK 3 level, used in more complex sentences with complements and embedded clauses.", "difficulty": 0.6,
     "examples": [
         {"zh": "他连一口水都没喝就走了。", "pinyin": "Tā lián yì kǒu shuǐ dōu méi hē jiù zǒu le.", "en": "He left without even drinking a sip of water."},
         {"zh": "她忙得连吃饭的时间都没有。", "pinyin": "Tā máng de lián chīfàn de shíjiān dōu méiyǒu.", "en": "She's so busy she doesn't even have time to eat."},
         {"zh": "这么简单的题，他连做都不想做。", "pinyin": "Zhème jiǎndān de tí, tā lián zuò dōu bù xiǎng zuò.", "en": "Such a simple question, and he doesn't even want to try."},
     ]},

    {"name": "除了...还/也 besides...also", "name_zh": "除了…还/也", "hsk_level": 3, "category": "structure",
     "description": "除了 with 还 or 也 means 'besides/in addition to' (inclusive). Contrasts with 除了...都 which means 'except for' (exclusive).", "difficulty": 0.5,
     "examples": [
         {"zh": "除了中文，他还会说法语。", "pinyin": "Chúle Zhōngwén, tā hái huì shuō Fǎyǔ.", "en": "Besides Chinese, he can also speak French."},
         {"zh": "除了跑步，我也喜欢游泳。", "pinyin": "Chúle pǎobù, wǒ yě xǐhuan yóuyǒng.", "en": "Besides running, I also like swimming."},
         {"zh": "除了他，还有谁知道这件事？", "pinyin": "Chúle tā, hái yǒu shéi zhīdào zhè jiàn shì?", "en": "Besides him, who else knows about this?"},
     ]},

    {"name": "要是 if (colloquial standalone)", "name_zh": "要是(口语)", "hsk_level": 3, "category": "connector",
     "description": "Colloquial conditional 'if', used alone without 就 in casual speech. Less formal than 如果 and very common in conversation.", "difficulty": 0.4,
     "examples": [
         {"zh": "要是你不去，我也不去。", "pinyin": "Yàoshi nǐ bú qù, wǒ yě bú qù.", "en": "If you don't go, I won't go either."},
         {"zh": "要是明天有空，我们出去玩吧。", "pinyin": "Yàoshi míngtiān yǒu kòng, wǒmen chūqù wán ba.", "en": "If you're free tomorrow, let's go out and have fun."},
         {"zh": "要是早知道就好了。", "pinyin": "Yàoshi zǎo zhīdào jiù hǎo le.", "en": "If only I had known earlier."},
     ]},

    {"name": "不管...都 no matter (basic)", "name_zh": "不管…都(基础)", "hsk_level": 3, "category": "connector",
     "description": "Basic unconditional pattern at HSK 3 level: 'no matter what/how, still...'. The first clause sets any condition; 都 asserts the result holds regardless.", "difficulty": 0.6,
     "examples": [
         {"zh": "不管天气好不好，我都去跑步。", "pinyin": "Bùguǎn tiānqì hǎo bu hǎo, wǒ dōu qù pǎobù.", "en": "No matter whether the weather is good or not, I go running."},
         {"zh": "不管谁来，都欢迎。", "pinyin": "Bùguǎn shéi lái, dōu huānyíng.", "en": "No matter who comes, they're all welcome."},
         {"zh": "不管多贵，我都要买。", "pinyin": "Bùguǎn duō guì, wǒ dōu yào mǎi.", "en": "No matter how expensive, I'm going to buy it."},
     ]},

    {"name": "既...又 both...and (balanced)", "name_zh": "既…又(基础)", "hsk_level": 3, "category": "connector",
     "description": "Pattern indicating two qualities or states coexist, slightly more formal than 又...又: 既好看又好吃. Can also use 既...也.", "difficulty": 0.5,
     "examples": [
         {"zh": "这个既好看又好吃。", "pinyin": "Zhège jì hǎokàn yòu hǎochī.", "en": "This is both good-looking and delicious."},
         {"zh": "他既聪明又勤奋。", "pinyin": "Tā jì cōngming yòu qínfèn.", "en": "He is both smart and diligent."},
         {"zh": "这份工作既有趣又有挑战性。", "pinyin": "Zhè fèn gōngzuò jì yǒuqù yòu yǒu tiǎozhànxìng.", "en": "This job is both interesting and challenging."},
     ]},

    {"name": "即使...也 even if (basic intro)", "name_zh": "即使…也(基础)", "hsk_level": 3, "category": "connector",
     "description": "Basic hypothetical concession at HSK 3 level: 'even if X happens, Y still holds'. Expresses a stronger concession than 虽然...但是.", "difficulty": 0.6,
     "examples": [
         {"zh": "即使下雨，我也去。", "pinyin": "Jíshǐ xiàyǔ, wǒ yě qù.", "en": "Even if it rains, I'll still go."},
         {"zh": "即使很难，我也不放弃。", "pinyin": "Jíshǐ hěn nán, wǒ yě bù fàngqì.", "en": "Even if it's hard, I won't give up."},
         {"zh": "即使你不说，我也知道。", "pinyin": "Jíshǐ nǐ bù shuō, wǒ yě zhīdào.", "en": "Even if you don't say it, I know."},
     ]},

    {"name": "不过 however/but (mild)", "name_zh": "不过", "hsk_level": 3, "category": "connector",
     "description": "Mild adversative conjunction meaning 'however/but/though'. Softer than 但是, often adds a minor qualification or afterthought.", "difficulty": 0.4,
     "examples": [
         {"zh": "这个菜很好吃，不过有点儿辣。", "pinyin": "Zhège cài hěn hǎochī, búguò yǒudiǎnr là.", "en": "This dish is delicious, though it's a bit spicy."},
         {"zh": "他很聪明，不过不太努力。", "pinyin": "Tā hěn cōngming, búguò bú tài nǔlì.", "en": "He's smart, but not very hardworking."},
         {"zh": "我想去，不过明天有事。", "pinyin": "Wǒ xiǎng qù, búguò míngtiān yǒu shì.", "en": "I'd like to go, but I have something tomorrow."},
     ]},

    {"name": "而且 moreover/and also", "name_zh": "而且(递进)", "hsk_level": 3, "category": "connector",
     "description": "Conjunction meaning 'moreover/furthermore/and also', adding information that reinforces or builds on the previous statement. Can be used alone or in 不但...而且.", "difficulty": 0.4,
     "examples": [
         {"zh": "他很高，而且很帅。", "pinyin": "Tā hěn gāo, érqiě hěn shuài.", "en": "He is tall, and also handsome."},
         {"zh": "这个地方很美，而且人很少。", "pinyin": "Zhège dìfang hěn měi, érqiě rén hěn shǎo.", "en": "This place is beautiful, and moreover there aren't many people."},
         {"zh": "价格便宜，而且质量好。", "pinyin": "Jiàgé piányi, érqiě zhìliàng hǎo.", "en": "The price is cheap, and the quality is good too."},
     ]},

    {"name": "于是 so/thereupon (narrative)", "name_zh": "于是(叙事)", "hsk_level": 3, "category": "connector",
     "description": "Narrative conjunction meaning 'so/thereupon/then'. Introduces a natural next action in a sequence of events. More literary than 所以.", "difficulty": 0.5,
     "examples": [
         {"zh": "他觉得饿了，于是去了餐厅。", "pinyin": "Tā juéde è le, yúshì qùle cāntīng.", "en": "He felt hungry, so he went to a restaurant."},
         {"zh": "开始下雨了，于是我们回家了。", "pinyin": "Kāishǐ xiàyǔ le, yúshì wǒmen huíjiā le.", "en": "It started raining, so we went home."},
         {"zh": "她想了想，于是答应了。", "pinyin": "Tā xiǎngle xiǎng, yúshì dāying le.", "en": "She thought about it, and then agreed."},
     ]},

    {"name": "否则 otherwise (HSK3 intro)", "name_zh": "否则(书面)", "hsk_level": 3, "category": "connector",
     "description": "Conjunction meaning 'otherwise/or else', more formal than 要不然. States the negative consequence of not doing something.", "difficulty": 0.5,
     "examples": [
         {"zh": "你得早点出发，否则会迟到。", "pinyin": "Nǐ děi zǎodiǎn chūfā, fǒuzé huì chídào.", "en": "You need to leave early, otherwise you'll be late."},
         {"zh": "快做决定，否则来不及了。", "pinyin": "Kuài zuò juédìng, fǒuzé láibují le.", "en": "Make a decision quickly, otherwise there won't be enough time."},
         {"zh": "多穿点衣服，否则会感冒。", "pinyin": "Duō chuān diǎn yīfu, fǒuzé huì gǎnmào.", "en": "Wear more clothes, otherwise you'll catch a cold."},
     ]},

    {"name": "尽量 to the best of ability", "name_zh": "尽量", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'to the best of one's ability/as much as possible/try to': 我尽量来. Indicates effort without guaranteeing the result.", "difficulty": 0.5,
     "examples": [
         {"zh": "我尽量早点到。", "pinyin": "Wǒ jǐnliàng zǎodiǎn dào.", "en": "I'll try to arrive as early as possible."},
         {"zh": "请尽量用中文说。", "pinyin": "Qǐng jǐnliàng yòng Zhōngwén shuō.", "en": "Please try to speak in Chinese as much as possible."},
         {"zh": "我会尽量帮你的。", "pinyin": "Wǒ huì jǐnliàng bāng nǐ de.", "en": "I'll do my best to help you."},
     ]},

    {"name": "干脆 simply/just (decisive)", "name_zh": "干脆", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'simply/just/might as well', indicating a direct or decisive approach, often after weighing options: 干脆别去了.", "difficulty": 0.5,
     "examples": [
         {"zh": "等了这么久，干脆别去了。", "pinyin": "Děngle zhème jiǔ, gāncuì bié qù le.", "en": "We've waited so long, let's just not go."},
         {"zh": "路这么近，干脆走路去吧。", "pinyin": "Lù zhème jìn, gāncuì zǒulù qù ba.", "en": "The road is so close, let's just walk."},
         {"zh": "你干脆自己去问他。", "pinyin": "Nǐ gāncuì zìjǐ qù wèn tā.", "en": "You might as well go ask him yourself."},
     ]},

    {"name": "明明 clearly/obviously", "name_zh": "明明", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'clearly/obviously', expressing frustration or emphasis that something is evident but being denied or contradicted: 你明明知道.", "difficulty": 0.5,
     "examples": [
         {"zh": "你明明知道，为什么不说？", "pinyin": "Nǐ míngmíng zhīdào, wèishénme bù shuō?", "en": "You clearly know, so why won't you say?"},
         {"zh": "他明明在家，就是不开门。", "pinyin": "Tā míngmíng zài jiā, jiùshì bù kāimén.", "en": "He's obviously at home, but he just won't open the door."},
         {"zh": "明明是你的错！", "pinyin": "Míngmíng shì nǐ de cuò!", "en": "It's clearly your fault!"},
     ]},

    {"name": "往往 often/usually (tendency)", "name_zh": "往往", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'often/usually/tend to', describing a general tendency or pattern rather than a specific instance. More analytical than 常常.", "difficulty": 0.5,
     "examples": [
         {"zh": "周末的时候，商场往往很拥挤。", "pinyin": "Zhōumò de shíhou, shāngchǎng wǎngwǎng hěn yōngjǐ.", "en": "On weekends, shopping malls tend to be very crowded."},
         {"zh": "第一次往往做不好。", "pinyin": "Dì yī cì wǎngwǎng zuò bu hǎo.", "en": "The first time, one usually doesn't do well."},
         {"zh": "成功的人往往很努力。", "pinyin": "Chénggōng de rén wǎngwǎng hěn nǔlì.", "en": "Successful people tend to work very hard."},
     ]},

    {"name": "恰好/恰恰 precisely/exactly", "name_zh": "恰好/恰恰", "hsk_level": 3, "category": "particle",
     "description": "Adverbs meaning 'precisely/exactly/as it happens'. 恰好 means 'coincidentally/just right'; 恰恰 emphasizes 'precisely/exactly (contrary to expectation)'.", "difficulty": 0.5,
     "examples": [
         {"zh": "我到的时候，他恰好也在。", "pinyin": "Wǒ dào de shíhou, tā qiàhǎo yě zài.", "en": "When I arrived, he happened to be there too."},
         {"zh": "恰恰相反，我觉得很好。", "pinyin": "Qiàqià xiāngfǎn, wǒ juéde hěn hǎo.", "en": "On the contrary, I think it's very good."},
         {"zh": "他打电话的时候，我恰好出门了。", "pinyin": "Tā dǎ diànhuà de shíhou, wǒ qiàhǎo chūmén le.", "en": "When he called, I happened to have gone out."},
     ]},

    {"name": "好不容易 with great difficulty", "name_zh": "好不容易", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'with great difficulty/after much effort'. Emphasizes that something was hard-won. Interchangeable with 好容易 (same meaning despite apparent contradiction).", "difficulty": 0.5,
     "examples": [
         {"zh": "我好不容易才找到这个地方。", "pinyin": "Wǒ hǎo bù róngyì cái zhǎodào zhège dìfang.", "en": "I found this place only with great difficulty."},
         {"zh": "好不容易等到周末了。", "pinyin": "Hǎo bù róngyì děngdào zhōumò le.", "en": "We finally made it to the weekend."},
         {"zh": "他好不容易才考上大学。", "pinyin": "Tā hǎo bù róngyì cái kǎoshàng dàxué.", "en": "He got into university only after great effort."},
     ]},

    {"name": "动不动 at the slightest provocation", "name_zh": "动不动", "hsk_level": 3, "category": "particle",
     "description": "Adverb meaning 'at the slightest provocation/at every turn/easily'. Implies frequency and often disapproval: 他动不动就生气.", "difficulty": 0.5,
     "examples": [
         {"zh": "他动不动就生气。", "pinyin": "Tā dòngbudòng jiù shēngqì.", "en": "He gets angry at the slightest thing."},
         {"zh": "她动不动就哭。", "pinyin": "Tā dòngbudòng jiù kū.", "en": "She cries at the drop of a hat."},
         {"zh": "这台电脑动不动就死机。", "pinyin": "Zhè tái diànnǎo dòngbudòng jiù sǐjī.", "en": "This computer freezes all the time."},
     ]},

    {"name": "接着 then/next (continuation)", "name_zh": "接着", "hsk_level": 3, "category": "connector",
     "description": "Verb/conjunction meaning 'then/next/continue'. Indicates immediate succession or continuation: 接着说. More immediate than 然后.", "difficulty": 0.4,
     "examples": [
         {"zh": "他说完以后，接着就走了。", "pinyin": "Tā shuōwán yǐhòu, jiēzhe jiù zǒu le.", "en": "After he finished speaking, he left right away."},
         {"zh": "请接着说。", "pinyin": "Qǐng jiēzhe shuō.", "en": "Please continue (speaking)."},
         {"zh": "吃完饭，我们接着看电影。", "pinyin": "Chīwán fàn, wǒmen jiēzhe kàn diànyǐng.", "en": "After dinner, we'll continue with the movie."},
     ]},

    {"name": "分之 fraction/percentage", "name_zh": "分之", "hsk_level": 3, "category": "structure",
     "description": "Fractions and percentages use the pattern: denominator + 分之 + numerator. For percentages: 百分之 + number. Read from the whole to the part.", "difficulty": 0.5,
     "examples": [
         {"zh": "三分之一的学生是女生。", "pinyin": "Sān fēn zhī yī de xuéshēng shì nǚshēng.", "en": "One third of the students are female."},
         {"zh": "百分之八十的人同意了。", "pinyin": "Bǎi fēn zhī bāshí de rén tóngyì le.", "en": "Eighty percent of people agreed."},
         {"zh": "他吃了四分之三的蛋糕。", "pinyin": "Tā chīle sì fēn zhī sān de dàngāo.", "en": "He ate three quarters of the cake."},
     ]},

    {"name": "倍 multiple/times", "name_zh": "倍", "hsk_level": 3, "category": "structure",
     "description": "Measure word for multiples: number + 倍 means 'X times as much'. 两倍 = double, 三倍 = triple. Used with 是...的 or comparison structures.", "difficulty": 0.5,
     "examples": [
         {"zh": "他的工资是我的两倍。", "pinyin": "Tā de gōngzī shì wǒ de liǎng bèi.", "en": "His salary is twice mine."},
         {"zh": "这个城市的人口增加了三倍。", "pinyin": "Zhège chéngshì de rénkǒu zēngjiāle sān bèi.", "en": "This city's population has tripled."},
         {"zh": "今年的收入比去年多了一倍。", "pinyin": "Jīnnián de shōurù bǐ qùnián duōle yí bèi.", "en": "This year's income is double last year's."},
     ]},

    {"name": "Adj+死了 extremely (colloquial)", "name_zh": "Adj+死了", "hsk_level": 3, "category": "complement",
     "description": "Colloquial intensifier 死了 after an adjective means 'extremely/to death': 累死了 (dead tired), 热死了 (unbearably hot). Very common in spoken Chinese.", "difficulty": 0.4,
     "examples": [
         {"zh": "今天热死了！", "pinyin": "Jīntiān rè sǐ le!", "en": "It's unbearably hot today!"},
         {"zh": "我累死了。", "pinyin": "Wǒ lèi sǐ le.", "en": "I'm exhausted."},
         {"zh": "这个笑话笑死我了。", "pinyin": "Zhège xiàohua xiào sǐ wǒ le.", "en": "This joke had me dying of laughter."},
         {"zh": "饿死了，快去吃饭吧。", "pinyin": "È sǐ le, kuài qù chīfàn ba.", "en": "I'm starving, let's go eat."},
     ]},

    {"name": "一点都不/也不 not at all", "name_zh": "一点都不/也不", "hsk_level": 3, "category": "structure",
     "description": "Emphatic negation meaning 'not at all/not even a little bit'. 一点 + 都不/也不 + adjective/verb: 一点都不难.", "difficulty": 0.4,
     "examples": [
         {"zh": "这个一点都不难。", "pinyin": "Zhège yìdiǎn dōu bù nán.", "en": "This is not difficult at all."},
         {"zh": "我一点也不累。", "pinyin": "Wǒ yìdiǎn yě bú lèi.", "en": "I'm not tired at all."},
         {"zh": "她一点都不喜欢这个菜。", "pinyin": "Tā yìdiǎn dōu bù xǐhuan zhège cài.", "en": "She doesn't like this dish at all."},
         {"zh": "我一点也不知道。", "pinyin": "Wǒ yìdiǎn yě bù zhīdào.", "en": "I don't know at all."},
     ]},

    {"name": "越...越 the more...the more (full)", "name_zh": "越…越(完整)", "hsk_level": 3, "category": "comparison",
     "description": "Full correlative comparison: 越 + A + 越 + B means 'the more A, the more B'. Both A and B can be verbs or adjectives. Distinct from 越来越 (progressive change).", "difficulty": 0.5,
     "examples": [
         {"zh": "越吃越胖。", "pinyin": "Yuè chī yuè pàng.", "en": "The more you eat, the fatter you get."},
         {"zh": "中文越学越有意思。", "pinyin": "Zhōngwén yuè xué yuè yǒu yìsi.", "en": "The more you study Chinese, the more interesting it gets."},
         {"zh": "雨越下越大。", "pinyin": "Yǔ yuè xià yuè dà.", "en": "The rain is getting heavier and heavier."},
         {"zh": "他越想越生气。", "pinyin": "Tā yuè xiǎng yuè shēngqì.", "en": "The more he thought about it, the angrier he got."},
     ]},
]
