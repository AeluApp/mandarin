"""Extra HSK 3-4 grammar points, round 2 — fills remaining gaps."""

EXTRA_GRAMMAR_HSK3_4_R2 = [
    # =========================================================================
    # HSK 3 — 18 additional grammar points
    # =========================================================================

    {"name": "其实 actually", "name_zh": "其实", "hsk_level": 3, "category": "particle",
     "description": "Reveals the true situation, correcting a misconception: 其实我不想去", "difficulty": 0.4,
     "examples": [
         {"zh": "其实我不想去。", "pinyin": "Qíshí wǒ bù xiǎng qù.", "en": "Actually, I don't want to go."},
         {"zh": "其实这个问题不难。", "pinyin": "Qíshí zhège wèntí bù nán.", "en": "Actually, this problem isn't hard."},
         {"zh": "他看起来很严肃，其实很有趣。", "pinyin": "Tā kàn qǐlái hěn yánsù, qíshí hěn yǒuqù.", "en": "He looks serious, but actually he's quite fun."},
     ]},

    {"name": "终于 finally", "name_zh": "终于", "hsk_level": 3, "category": "particle",
     "description": "Indicates something long-awaited has finally happened: 他终于来了", "difficulty": 0.4,
     "examples": [
         {"zh": "他终于来了！", "pinyin": "Tā zhōngyú lái le!", "en": "He finally came!"},
         {"zh": "我终于找到了工作。", "pinyin": "Wǒ zhōngyú zhǎodào le gōngzuò.", "en": "I finally found a job."},
         {"zh": "雨终于停了。", "pinyin": "Yǔ zhōngyú tíng le.", "en": "The rain finally stopped."},
     ]},

    {"name": "刚才 just now", "name_zh": "刚才", "hsk_level": 3, "category": "other",
     "description": "Refers to a moment ago or the recent past: 你刚才说什么？", "difficulty": 0.4,
     "examples": [
         {"zh": "你刚才说什么？", "pinyin": "Nǐ gāngcái shuō shénme?", "en": "What did you just say?"},
         {"zh": "刚才有人找你。", "pinyin": "Gāngcái yǒu rén zhǎo nǐ.", "en": "Someone was looking for you just now."},
         {"zh": "我刚才看到他了。", "pinyin": "Wǒ gāngcái kàndào tā le.", "en": "I just saw him a moment ago."},
     ]},

    {"name": "特别 especially/particularly", "name_zh": "特别", "hsk_level": 3, "category": "particle",
     "description": "Adverb intensifying an adjective or verb: 今天特别冷", "difficulty": 0.4,
     "examples": [
         {"zh": "今天特别冷。", "pinyin": "Jīntiān tèbié lěng.", "en": "It's especially cold today."},
         {"zh": "这个菜特别好吃。", "pinyin": "Zhège cài tèbié hǎochī.", "en": "This dish is particularly delicious."},
         {"zh": "她对学中文特别有兴趣。", "pinyin": "Tā duì xué Zhōngwén tèbié yǒu xìngqù.", "en": "She's particularly interested in learning Chinese."},
     ]},

    {"name": "几乎 almost", "name_zh": "几乎", "hsk_level": 3, "category": "particle",
     "description": "Indicates something nearly happened or is nearly the case: 我几乎忘了", "difficulty": 0.5,
     "examples": [
         {"zh": "我几乎忘了。", "pinyin": "Wǒ jīhū wàng le.", "en": "I almost forgot."},
         {"zh": "他几乎每天都迟到。", "pinyin": "Tā jīhū měitiān dōu chídào.", "en": "He is late almost every day."},
         {"zh": "这个班几乎所有人都通过了考试。", "pinyin": "Zhège bān jīhū suǒyǒu rén dōu tōngguò le kǎoshì.", "en": "Almost everyone in this class passed the exam."},
     ]},

    {"name": "突然 suddenly", "name_zh": "突然", "hsk_level": 3, "category": "other",
     "description": "Indicates an abrupt, unexpected occurrence: 他突然站起来了", "difficulty": 0.4,
     "examples": [
         {"zh": "他突然站起来了。", "pinyin": "Tā tūrán zhàn qǐlái le.", "en": "He suddenly stood up."},
         {"zh": "突然下起雨来了。", "pinyin": "Tūrán xià qǐ yǔ lái le.", "en": "It suddenly started raining."},
         {"zh": "她突然不说话了。", "pinyin": "Tā tūrán bù shuōhuà le.", "en": "She suddenly stopped talking."},
     ]},

    {"name": "虽然...可是 although...but (variant)", "name_zh": "虽然…可是", "hsk_level": 3, "category": "connector",
     "description": "Concessive pattern using 可是 instead of 但是: 虽然贵，可是很好", "difficulty": 0.5,
     "examples": [
         {"zh": "虽然贵，可是质量很好。", "pinyin": "Suīrán guì, kěshì zhìliàng hěn hǎo.", "en": "Although expensive, the quality is very good."},
         {"zh": "虽然很累，可是我很开心。", "pinyin": "Suīrán hěn lèi, kěshì wǒ hěn kāixīn.", "en": "Although tired, I'm very happy."},
         {"zh": "虽然路很远，可是风景很美。", "pinyin": "Suīrán lù hěn yuǎn, kěshì fēngjǐng hěn měi.", "en": "Although the road is long, the scenery is beautiful."},
     ]},

    {"name": "因为...所以 because...so (basic)", "name_zh": "因为…所以(基础)", "hsk_level": 3, "category": "connector",
     "description": "Basic causal pattern at HSK 3 level: 因为下雨，所以没去", "difficulty": 0.4,
     "examples": [
         {"zh": "因为下雨，所以我没去。", "pinyin": "Yīnwèi xiàyǔ, suǒyǐ wǒ méi qù.", "en": "Because it rained, I didn't go."},
         {"zh": "因为太贵了，所以没买。", "pinyin": "Yīnwèi tài guì le, suǒyǐ méi mǎi.", "en": "Because it was too expensive, I didn't buy it."},
         {"zh": "因为他生病了，所以没来上课。", "pinyin": "Yīnwèi tā shēngbìng le, suǒyǐ méi lái shàngkè.", "en": "Because he was sick, he didn't come to class."},
     ]},

    {"name": "一边...一边 while doing (basic)", "name_zh": "一边…一边(基础)", "hsk_level": 3, "category": "structure",
     "description": "Basic simultaneous-action pattern at HSK 3 level: 一边吃一边说", "difficulty": 0.4,
     "examples": [
         {"zh": "她一边吃饭一边看书。", "pinyin": "Tā yìbiān chīfàn yìbiān kànshū.", "en": "She reads while eating."},
         {"zh": "他一边走一边打电话。", "pinyin": "Tā yìbiān zǒu yìbiān dǎ diànhuà.", "en": "He talks on the phone while walking."},
         {"zh": "孩子们一边唱歌一边跳舞。", "pinyin": "Háizimen yìbiān chànggē yìbiān tiàowǔ.", "en": "The children sing and dance at the same time."},
     ]},

    {"name": "不但...而且 not only...but (basic)", "name_zh": "不但…而且(基础)", "hsk_level": 3, "category": "connector",
     "description": "Basic progressive pattern at HSK 3 level: 不但好看，而且好吃", "difficulty": 0.5,
     "examples": [
         {"zh": "这个菜不但好看，而且好吃。", "pinyin": "Zhège cài búdàn hǎokàn, érqiě hǎochī.", "en": "This dish is not only pretty, but also delicious."},
         {"zh": "他不但会说中文，而且说得很好。", "pinyin": "Tā búdàn huì shuō Zhōngwén, érqiě shuō de hěn hǎo.", "en": "He not only speaks Chinese, but speaks it very well."},
         {"zh": "这个地方不但远，而且不好找。", "pinyin": "Zhège dìfang búdàn yuǎn, érqiě bù hǎo zhǎo.", "en": "This place is not only far, but also hard to find."},
     ]},

    {"name": "恐怕 I'm afraid that", "name_zh": "恐怕", "hsk_level": 3, "category": "particle",
     "description": "Expresses a worried estimate or polite pessimism: 恐怕来不及了", "difficulty": 0.5,
     "examples": [
         {"zh": "恐怕来不及了。", "pinyin": "Kǒngpà lái bu jí le.", "en": "I'm afraid there's not enough time."},
         {"zh": "恐怕他不会同意。", "pinyin": "Kǒngpà tā bú huì tóngyì.", "en": "I'm afraid he won't agree."},
         {"zh": "今天恐怕要下雨。", "pinyin": "Jīntiān kǒngpà yào xiàyǔ.", "en": "I'm afraid it's going to rain today."},
     ]},

    {"name": "果然 as expected (basic)", "name_zh": "果然(基础)", "hsk_level": 3, "category": "particle",
     "description": "Confirms a prediction came true at HSK 3 level: 他果然没来", "difficulty": 0.5,
     "examples": [
         {"zh": "他果然没来。", "pinyin": "Tā guǒrán méi lái.", "en": "He didn't come, just as expected."},
         {"zh": "果然下雨了。", "pinyin": "Guǒrán xiàyǔ le.", "en": "Sure enough, it rained."},
         {"zh": "这个菜果然很好吃。", "pinyin": "Zhège cài guǒrán hěn hǎochī.", "en": "This dish really is delicious, as expected."},
     ]},

    {"name": "居然 surprisingly", "name_zh": "居然", "hsk_level": 3, "category": "particle",
     "description": "Expresses surprise at an unexpected fact: 她居然会中文", "difficulty": 0.5,
     "examples": [
         {"zh": "她居然会说中文！", "pinyin": "Tā jūrán huì shuō Zhōngwén!", "en": "She can actually speak Chinese!"},
         {"zh": "他居然迟到了。", "pinyin": "Tā jūrán chídào le.", "en": "He was actually late, surprisingly."},
         {"zh": "这么难的题，他居然做对了。", "pinyin": "Zhème nán de tí, tā jūrán zuòduì le.", "en": "Such a hard question, and he actually got it right."},
     ]},

    {"name": "A比B+adj+多了 much more than", "name_zh": "比+多了", "hsk_level": 3, "category": "comparison",
     "description": "Emphasizes a large difference in comparison: 他比我高多了", "difficulty": 0.5,
     "examples": [
         {"zh": "他比我高多了。", "pinyin": "Tā bǐ wǒ gāo duō le.", "en": "He is much taller than me."},
         {"zh": "今天比昨天冷多了。", "pinyin": "Jīntiān bǐ zuótiān lěng duō le.", "en": "Today is much colder than yesterday."},
         {"zh": "坐飞机比坐火车快多了。", "pinyin": "Zuò fēijī bǐ zuò huǒchē kuài duō le.", "en": "Flying is much faster than taking the train."},
     ]},

    {"name": "越A越B the more...the more", "name_zh": "越A越B", "hsk_level": 3, "category": "structure",
     "description": "Correlative pattern: as one thing increases, so does another: 越吃越想吃", "difficulty": 0.5,
     "examples": [
         {"zh": "越吃越想吃。", "pinyin": "Yuè chī yuè xiǎng chī.", "en": "The more you eat, the more you want to eat."},
         {"zh": "中文越学越难。", "pinyin": "Zhōngwén yuè xué yuè nán.", "en": "The more you study Chinese, the harder it gets."},
         {"zh": "他越说越快。", "pinyin": "Tā yuè shuō yuè kuài.", "en": "The more he talks, the faster he speaks."},
     ]},

    {"name": "不是...而是 not X but Y", "name_zh": "不是…而是", "hsk_level": 3, "category": "structure",
     "description": "Corrects a wrong assumption by contrasting: 不是不想，而是不能", "difficulty": 0.5,
     "examples": [
         {"zh": "不是我不想去，而是我没有时间。", "pinyin": "Bú shì wǒ bù xiǎng qù, ér shì wǒ méiyǒu shíjiān.", "en": "It's not that I don't want to go, but that I don't have time."},
         {"zh": "问题不是钱，而是时间。", "pinyin": "Wèntí bú shì qián, ér shì shíjiān.", "en": "The problem isn't money, but time."},
         {"zh": "他不是不喜欢，而是太害羞了。", "pinyin": "Tā bú shì bù xǐhuan, ér shì tài hàixiū le.", "en": "It's not that he doesn't like it, but that he's too shy."},
     ]},

    {"name": "到处 everywhere", "name_zh": "到处", "hsk_level": 3, "category": "other",
     "description": "Adverb meaning 'everywhere/all over': 到处都是人", "difficulty": 0.4,
     "examples": [
         {"zh": "到处都是人。", "pinyin": "Dàochù dōu shì rén.", "en": "There are people everywhere."},
         {"zh": "他到处找他的钥匙。", "pinyin": "Tā dàochù zhǎo tā de yàoshi.", "en": "He looked everywhere for his keys."},
         {"zh": "春天到了，到处都是花。", "pinyin": "Chūntiān dào le, dàochù dōu shì huā.", "en": "Spring has arrived; there are flowers everywhere."},
     ]},

    {"name": "一直 continuously (directional)", "name_zh": "一直(方向)", "hsk_level": 3, "category": "particle",
     "description": "Indicates continuous action along a direction or unchanged state: 一直走到路口", "difficulty": 0.5,
     "examples": [
         {"zh": "一直走到路口，然后左转。", "pinyin": "Yìzhí zǒu dào lùkǒu, ránhòu zuǒ zhuǎn.", "en": "Walk straight to the intersection, then turn left."},
         {"zh": "他一直在学中文。", "pinyin": "Tā yìzhí zài xué Zhōngwén.", "en": "He has been studying Chinese all along."},
         {"zh": "我一直等到十点。", "pinyin": "Wǒ yìzhí děng dào shí diǎn.", "en": "I waited all the way until ten o'clock."},
     ]},

    # =========================================================================
    # HSK 4 — 18 additional grammar points
    # =========================================================================

    {"name": "不得不 have no choice but to", "name_zh": "不得不", "hsk_level": 4, "category": "structure",
     "description": "Double negation expressing compulsion: 我不得不同意", "difficulty": 0.6,
     "examples": [
         {"zh": "我不得不同意他的看法。", "pinyin": "Wǒ bùdébù tóngyì tā de kànfǎ.", "en": "I have no choice but to agree with his view."},
         {"zh": "因为堵车，他不得不走路去上班。", "pinyin": "Yīnwèi dǔchē, tā bùdébù zǒulù qù shàngbān.", "en": "Because of traffic, he had to walk to work."},
         {"zh": "时间不够了，我们不得不放弃。", "pinyin": "Shíjiān bú gòu le, wǒmen bùdébù fàngqì.", "en": "There's not enough time; we have no choice but to give up."},
     ]},

    {"name": "宁可...也不 would rather...than", "name_zh": "宁可…也不", "hsk_level": 4, "category": "connector",
     "description": "Expresses a strong preference, even at a cost: 宁可走路也不坐车", "difficulty": 0.6,
     "examples": [
         {"zh": "我宁可走路也不坐车。", "pinyin": "Wǒ nìngkě zǒulù yě bú zuòchē.", "en": "I'd rather walk than take a car."},
         {"zh": "她宁可少吃一点也不浪费。", "pinyin": "Tā nìngkě shǎo chī yìdiǎn yě bú làngfèi.", "en": "She'd rather eat less than waste food."},
         {"zh": "他宁可自己辛苦也不让家人担心。", "pinyin": "Tā nìngkě zìjǐ xīnkǔ yě bú ràng jiārén dānxīn.", "en": "He'd rather suffer himself than worry his family."},
     ]},

    {"name": "无论...都 regardless of", "name_zh": "无论…都", "hsk_level": 4, "category": "connector",
     "description": "Unconditional: no matter what, the result is the same: 无论如何都要去", "difficulty": 0.6,
     "examples": [
         {"zh": "无论多难，我都要试试。", "pinyin": "Wúlùn duō nán, wǒ dōu yào shìshi.", "en": "No matter how hard, I'll give it a try."},
         {"zh": "无论天气怎么样，他都去跑步。", "pinyin": "Wúlùn tiānqì zěnmeyàng, tā dōu qù pǎobù.", "en": "Regardless of the weather, he goes running."},
         {"zh": "无论你去哪儿，我都跟你去。", "pinyin": "Wúlùn nǐ qù nǎr, wǒ dōu gēn nǐ qù.", "en": "Wherever you go, I'll go with you."},
     ]},

    {"name": "由于 due to", "name_zh": "由于", "hsk_level": 4, "category": "connector",
     "description": "Formal causal preposition: 由于天气原因", "difficulty": 0.6,
     "examples": [
         {"zh": "由于天气原因，航班取消了。", "pinyin": "Yóuyú tiānqì yuányīn, hángbān qǔxiāo le.", "en": "Due to weather conditions, the flight was cancelled."},
         {"zh": "由于他的努力，项目成功了。", "pinyin": "Yóuyú tā de nǔlì, xiàngmù chénggōng le.", "en": "Due to his efforts, the project succeeded."},
         {"zh": "由于时间有限，我们只能讨论两个问题。", "pinyin": "Yóuyú shíjiān yǒuxiàn, wǒmen zhǐ néng tǎolùn liǎng gè wèntí.", "en": "Due to limited time, we can only discuss two issues."},
     ]},

    {"name": "随着 along with / as", "name_zh": "随着", "hsk_level": 4, "category": "connector",
     "description": "Indicates change accompanying another change: 随着时间的推移", "difficulty": 0.6,
     "examples": [
         {"zh": "随着时间的推移，他的中文越来越好了。", "pinyin": "Suízhe shíjiān de tuīyí, tā de Zhōngwén yuèláiyuè hǎo le.", "en": "As time goes on, his Chinese gets better and better."},
         {"zh": "随着科技的发展，生活变得更方便了。", "pinyin": "Suízhe kējì de fāzhǎn, shēnghuó biàn de gèng fāngbiàn le.", "en": "With the development of technology, life has become more convenient."},
         {"zh": "随着年龄的增长，他变得更成熟了。", "pinyin": "Suízhe niánlíng de zēngzhǎng, tā biàn de gèng chéngshú le.", "en": "As he gets older, he becomes more mature."},
     ]},

    {"name": "相反 on the contrary", "name_zh": "相反", "hsk_level": 4, "category": "connector",
     "description": "Introduces the opposite of what was expected: 相反，他很高兴", "difficulty": 0.6,
     "examples": [
         {"zh": "我以为他会生气，相反，他很高兴。", "pinyin": "Wǒ yǐwéi tā huì shēngqì, xiāngfǎn, tā hěn gāoxìng.", "en": "I thought he'd be angry; on the contrary, he was happy."},
         {"zh": "结果不但没变好，相反更糟了。", "pinyin": "Jiéguǒ búdàn méi biàn hǎo, xiāngfǎn gèng zāo le.", "en": "Not only didn't it improve, on the contrary it got worse."},
         {"zh": "他没有放弃，相反更加努力了。", "pinyin": "Tā méiyǒu fàngqì, xiāngfǎn gèngjiā nǔlì le.", "en": "He didn't give up; on the contrary, he tried even harder."},
     ]},

    {"name": "不仅...而且 not only...but also (formal)", "name_zh": "不仅…而且", "hsk_level": 4, "category": "connector",
     "description": "Formal progressive pattern, synonym of 不但…而且: 不仅会中文，而且会日语", "difficulty": 0.6,
     "examples": [
         {"zh": "她不仅会说中文，而且会说日语。", "pinyin": "Tā bùjǐn huì shuō Zhōngwén, érqiě huì shuō Rìyǔ.", "en": "She not only speaks Chinese, but also speaks Japanese."},
         {"zh": "这个方法不仅简单，而且有效。", "pinyin": "Zhège fāngfǎ bùjǐn jiǎndān, érqiě yǒuxiào.", "en": "This method is not only simple, but also effective."},
         {"zh": "他不仅是我的同事，而且是我的好朋友。", "pinyin": "Tā bùjǐn shì wǒ de tóngshì, érqiě shì wǒ de hǎo péngyou.", "en": "He is not only my colleague, but also my good friend."},
     ]},

    {"name": "只有...才 only if...then", "name_zh": "只有…才", "hsk_level": 4, "category": "connector",
     "description": "States the sole necessary condition: 只有努力才能成功", "difficulty": 0.6,
     "examples": [
         {"zh": "只有努力，才能成功。", "pinyin": "Zhǐyǒu nǔlì, cái néng chénggōng.", "en": "Only through hard work can you succeed."},
         {"zh": "只有你亲自去，他才会相信。", "pinyin": "Zhǐyǒu nǐ qīnzì qù, tā cái huì xiāngxìn.", "en": "Only if you go in person will he believe it."},
         {"zh": "只有多练习，才能提高水平。", "pinyin": "Zhǐyǒu duō liànxí, cái néng tígāo shuǐpíng.", "en": "Only by practicing more can you improve your level."},
     ]},

    {"name": "要不然 otherwise (colloquial)", "name_zh": "要不然", "hsk_level": 4, "category": "connector",
     "description": "Colloquial way of saying 'otherwise': 快走，要不然迟到了", "difficulty": 0.5,
     "examples": [
         {"zh": "快走，要不然迟到了。", "pinyin": "Kuài zǒu, yàobùrán chídào le.", "en": "Hurry up, otherwise we'll be late."},
         {"zh": "你得好好复习，要不然考试过不了。", "pinyin": "Nǐ děi hǎohǎo fùxí, yàobùrán kǎoshì guò bu liǎo.", "en": "You need to review well, otherwise you won't pass the exam."},
         {"zh": "多穿点儿，要不然会感冒。", "pinyin": "Duō chuān diǎnr, yàobùrán huì gǎnmào.", "en": "Wear more clothes, otherwise you'll catch a cold."},
     ]},

    {"name": "并 and/moreover (formal conjunction)", "name_zh": "并", "hsk_level": 4, "category": "connector",
     "description": "Formal conjunction linking two parallel actions: 发现并解决问题", "difficulty": 0.6,
     "examples": [
         {"zh": "我们需要发现并解决问题。", "pinyin": "Wǒmen xūyào fāxiàn bìng jiějué wèntí.", "en": "We need to find and solve problems."},
         {"zh": "他接受并完成了任务。", "pinyin": "Tā jiēshòu bìng wánchéng le rènwu.", "en": "He accepted and completed the task."},
         {"zh": "请仔细阅读并签名。", "pinyin": "Qǐng zǐxì yuèdú bìng qiānmíng.", "en": "Please read carefully and sign."},
     ]},

    {"name": "以及 as well as", "name_zh": "以及", "hsk_level": 4, "category": "connector",
     "description": "Formal conjunction connecting noun phrases: 老师以及学生", "difficulty": 0.5,
     "examples": [
         {"zh": "老师以及学生都参加了活动。", "pinyin": "Lǎoshī yǐjí xuéshēng dōu cānjiā le huódòng.", "en": "Teachers as well as students all participated in the activity."},
         {"zh": "请带好护照以及签证。", "pinyin": "Qǐng dàihǎo hùzhào yǐjí qiānzhèng.", "en": "Please bring your passport as well as your visa."},
         {"zh": "我喜欢音乐以及电影。", "pinyin": "Wǒ xǐhuan yīnyuè yǐjí diànyǐng.", "en": "I like music as well as movies."},
     ]},

    {"name": "于是 thereupon/so", "name_zh": "于是", "hsk_level": 4, "category": "connector",
     "description": "Introduces a natural consequence in narrative: 我很饿，于是去吃饭了", "difficulty": 0.5,
     "examples": [
         {"zh": "我很饿，于是去吃饭了。", "pinyin": "Wǒ hěn è, yúshì qù chīfàn le.", "en": "I was hungry, so I went to eat."},
         {"zh": "下雨了，于是我们回家了。", "pinyin": "Xiàyǔ le, yúshì wǒmen huíjiā le.", "en": "It started raining, so we went home."},
         {"zh": "他觉得无聊，于是出去散步了。", "pinyin": "Tā juéde wúliáo, yúshì chūqù sànbù le.", "en": "He felt bored, so he went out for a walk."},
     ]},

    {"name": "实际上 actually/in fact", "name_zh": "实际上", "hsk_level": 4, "category": "particle",
     "description": "Reveals the factual reality versus appearance: 实际上他很努力", "difficulty": 0.6,
     "examples": [
         {"zh": "实际上他很努力。", "pinyin": "Shíjìshang tā hěn nǔlì.", "en": "In fact, he works very hard."},
         {"zh": "看起来简单，实际上很难。", "pinyin": "Kàn qǐlái jiǎndān, shíjìshang hěn nán.", "en": "It looks simple, but in fact it's very hard."},
         {"zh": "实际上，这个问题比我们想的复杂。", "pinyin": "Shíjìshang, zhège wèntí bǐ wǒmen xiǎng de fùzá.", "en": "In fact, this problem is more complex than we thought."},
     ]},

    {"name": "一方面...另一方面 on one hand...on the other", "name_zh": "一方面…另一方面", "hsk_level": 4, "category": "connector",
     "description": "Presents two sides of a situation: 一方面要学习，另一方面要工作", "difficulty": 0.6,
     "examples": [
         {"zh": "一方面要学习，另一方面要工作。", "pinyin": "Yì fāngmiàn yào xuéxí, lìng yì fāngmiàn yào gōngzuò.", "en": "On one hand you need to study, on the other hand you need to work."},
         {"zh": "一方面我想去，另一方面我没有钱。", "pinyin": "Yì fāngmiàn wǒ xiǎng qù, lìng yì fāngmiàn wǒ méiyǒu qián.", "en": "On one hand I want to go, on the other I don't have money."},
         {"zh": "一方面要注意速度，另一方面要保证质量。", "pinyin": "Yì fāngmiàn yào zhùyì sùdù, lìng yì fāngmiàn yào bǎozhèng zhìliàng.", "en": "On one hand we need to watch the speed, on the other we need to ensure quality."},
     ]},

    {"name": "到...为止 up until", "name_zh": "到…为止", "hsk_level": 4, "category": "structure",
     "description": "Marks a temporal endpoint: 到明天为止", "difficulty": 0.5,
     "examples": [
         {"zh": "到明天为止，你必须完成。", "pinyin": "Dào míngtiān wéizhǐ, nǐ bìxū wánchéng.", "en": "You must finish by tomorrow."},
         {"zh": "到目前为止，一切顺利。", "pinyin": "Dào mùqián wéizhǐ, yíqiè shùnlì.", "en": "So far, everything is going smoothly."},
         {"zh": "到上个月为止，我已经学了半年中文。", "pinyin": "Dào shàng gè yuè wéizhǐ, wǒ yǐjīng xuéle bàn nián Zhōngwén.", "en": "As of last month, I had been studying Chinese for half a year."},
     ]},

    {"name": "按照 according to", "name_zh": "按照", "hsk_level": 4, "category": "structure",
     "description": "Preposition meaning 'in accordance with': 按照计划进行", "difficulty": 0.5,
     "examples": [
         {"zh": "按照计划进行。", "pinyin": "Ànzhào jìhuà jìnxíng.", "en": "Proceed according to plan."},
         {"zh": "请按照老师说的做。", "pinyin": "Qǐng ànzhào lǎoshī shuō de zuò.", "en": "Please do as the teacher said."},
         {"zh": "按照规定，这里不能停车。", "pinyin": "Ànzhào guīdìng, zhèlǐ bù néng tíngchē.", "en": "According to the rules, you can't park here."},
     ]},

    {"name": "代替 instead of / in place of", "name_zh": "代替", "hsk_level": 4, "category": "structure",
     "description": "To substitute one thing or person for another: 我代替他去开会", "difficulty": 0.6,
     "examples": [
         {"zh": "我代替他去开会。", "pinyin": "Wǒ dàitì tā qù kāihuì.", "en": "I'm attending the meeting in his place."},
         {"zh": "没有什么可以代替经验。", "pinyin": "Méiyǒu shénme kěyǐ dàitì jīngyàn.", "en": "Nothing can replace experience."},
         {"zh": "她用电子邮件代替了打电话。", "pinyin": "Tā yòng diànzǐ yóujiàn dàitì le dǎ diànhuà.", "en": "She replaced phone calls with email."},
     ]},

    {"name": "恐怕 I'm afraid (formal context)", "name_zh": "恐怕(正式)", "hsk_level": 4, "category": "particle",
     "description": "Polite hedging in more formal or complex contexts: 恐怕不太方便", "difficulty": 0.6,
     "examples": [
         {"zh": "恐怕这个方案不太合适。", "pinyin": "Kǒngpà zhège fāng'àn bú tài héshì.", "en": "I'm afraid this plan isn't quite suitable."},
         {"zh": "恐怕我们需要重新考虑。", "pinyin": "Kǒngpà wǒmen xūyào chóngxīn kǎolǜ.", "en": "I'm afraid we need to reconsider."},
         {"zh": "恐怕不太方便，改天吧。", "pinyin": "Kǒngpà bú tài fāngbiàn, gǎitiān ba.", "en": "I'm afraid it's not very convenient; let's do it another day."},
     ]},
]
