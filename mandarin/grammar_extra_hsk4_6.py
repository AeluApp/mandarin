"""Extra HSK 4-6 grammar points to supplement grammar_seed.py."""

EXTRA_GRAMMAR_HSK4_6 = [
    # ── HSK 4 (14 new) ──────────────────────────────────────────────

    {"name": "竟然 unexpectedly", "name_zh": "竟然", "hsk_level": 4, "category": "particle",
     "description": "Expresses surprise at an unexpected outcome: 他竟然不知道", "difficulty": 0.6,
     "examples": [
         {"zh": "他竟然不知道这件事。", "pinyin": "Tā jìngrán bù zhīdào zhè jiàn shì.", "en": "He unexpectedly didn't know about this."},
         {"zh": "她竟然通过了考试。", "pinyin": "Tā jìngrán tōngguò le kǎoshì.", "en": "She actually passed the exam."},
         {"zh": "这么简单的问题，你竟然不会？", "pinyin": "Zhème jiǎndān de wèntí, nǐ jìngrán bú huì?", "en": "Such a simple question, and you actually can't answer it?"},
     ]},

    {"name": "反正 anyway", "name_zh": "反正", "hsk_level": 4, "category": "particle",
     "description": "Indicates that the result is the same regardless: 反正我不去", "difficulty": 0.5,
     "examples": [
         {"zh": "反正我不去，你自己去吧。", "pinyin": "Fǎnzhèng wǒ bú qù, nǐ zìjǐ qù ba.", "en": "Anyway, I'm not going — go by yourself."},
         {"zh": "反正还有时间，不着急。", "pinyin": "Fǎnzhèng hái yǒu shíjiān, bù zháojí.", "en": "There's still time anyway, no rush."},
         {"zh": "反正你也不信，我就不说了。", "pinyin": "Fǎnzhèng nǐ yě bú xìn, wǒ jiù bù shuō le.", "en": "You won't believe me anyway, so I won't bother saying it."},
     ]},

    {"name": "难道 rhetorical question", "name_zh": "难道", "hsk_level": 4, "category": "particle",
     "description": "Marks a rhetorical question implying the answer is obvious: 难道你不知道吗？", "difficulty": 0.6,
     "examples": [
         {"zh": "难道你不知道吗？", "pinyin": "Nándào nǐ bù zhīdào ma?", "en": "Don't you know? (You should know!)"},
         {"zh": "难道这还不够吗？", "pinyin": "Nándào zhè hái bú gòu ma?", "en": "Isn't this enough already?"},
         {"zh": "难道我说错了？", "pinyin": "Nándào wǒ shuō cuò le?", "en": "Could it be that I was wrong?"},
     ]},

    {"name": "至少 at least", "name_zh": "至少", "hsk_level": 4, "category": "particle",
     "description": "Sets a minimum: 至少要学一个小时", "difficulty": 0.5,
     "examples": [
         {"zh": "每天至少要学一个小时。", "pinyin": "Měitiān zhìshǎo yào xué yí gè xiǎoshí.", "en": "You should study at least one hour every day."},
         {"zh": "至少告诉我原因。", "pinyin": "Zhìshǎo gàosu wǒ yuányīn.", "en": "At least tell me the reason."},
         {"zh": "这件事至少需要三天。", "pinyin": "Zhè jiàn shì zhìshǎo xūyào sān tiān.", "en": "This matter needs at least three days."},
     ]},

    {"name": "甚至 even", "name_zh": "甚至", "hsk_level": 4, "category": "particle",
     "description": "Indicates an extreme case to emphasize degree: 他甚至不会写自己的名字", "difficulty": 0.6,
     "examples": [
         {"zh": "他甚至不会写自己的名字。", "pinyin": "Tā shènzhì bú huì xiě zìjǐ de míngzi.", "en": "He can't even write his own name."},
         {"zh": "天气太热了，甚至连风扇都不够用。", "pinyin": "Tiānqì tài rè le, shènzhì lián fēngshàn dōu bú gòu yòng.", "en": "It's so hot that even a fan isn't enough."},
         {"zh": "她紧张得甚至说不出话来。", "pinyin": "Tā jǐnzhāng de shènzhì shuō bu chū huà lái.", "en": "She was so nervous that she couldn't even speak."},
     ]},

    {"name": "尤其 especially", "name_zh": "尤其", "hsk_level": 4, "category": "particle",
     "description": "Highlights a particular element: 我喜欢水果，尤其是苹果", "difficulty": 0.5,
     "examples": [
         {"zh": "我喜欢水果，尤其是苹果。", "pinyin": "Wǒ xǐhuan shuǐguǒ, yóuqí shì píngguǒ.", "en": "I like fruit, especially apples."},
         {"zh": "北京的冬天很冷，尤其是晚上。", "pinyin": "Běijīng de dōngtiān hěn lěng, yóuqí shì wǎnshang.", "en": "Beijing winters are cold, especially at night."},
         {"zh": "这里的菜都好吃，尤其是鱼。", "pinyin": "Zhèlǐ de cài dōu hǎochī, yóuqí shì yú.", "en": "The dishes here are all good, especially the fish."},
     ]},

    {"name": "首先...其次 firstly...secondly", "name_zh": "首先…其次", "hsk_level": 4, "category": "connector",
     "description": "Enumerates points in order: 首先要准备好，其次要认真做", "difficulty": 0.5,
     "examples": [
         {"zh": "首先要准备好材料，其次要认真做。", "pinyin": "Shǒuxiān yào zhǔnbèi hǎo cáiliào, qícì yào rènzhēn zuò.", "en": "First prepare the materials, then do it carefully."},
         {"zh": "首先，我要感谢大家；其次，我想说几句话。", "pinyin": "Shǒuxiān, wǒ yào gǎnxiè dàjiā; qícì, wǒ xiǎng shuō jǐ jù huà.", "en": "Firstly, I want to thank everyone; secondly, I'd like to say a few words."},
         {"zh": "首先考虑安全，其次考虑成本。", "pinyin": "Shǒuxiān kǎolǜ ānquán, qícì kǎolǜ chéngběn.", "en": "First consider safety, then consider cost."},
     ]},

    {"name": "总之 in short", "name_zh": "总之", "hsk_level": 4, "category": "connector",
     "description": "Summarizes the main point: 总之我们需要努力", "difficulty": 0.5,
     "examples": [
         {"zh": "总之，我们需要更加努力。", "pinyin": "Zǒngzhī, wǒmen xūyào gèngjiā nǔlì.", "en": "In short, we need to work harder."},
         {"zh": "总之这件事很重要。", "pinyin": "Zǒngzhī zhè jiàn shì hěn zhòngyào.", "en": "In short, this matter is very important."},
         {"zh": "理由很多，总之我不同意。", "pinyin": "Lǐyóu hěn duō, zǒngzhī wǒ bù tóngyì.", "en": "There are many reasons — in short, I disagree."},
     ]},

    {"name": "另外 in addition", "name_zh": "另外", "hsk_level": 4, "category": "connector",
     "description": "Adds supplementary information: 另外还有一个问题", "difficulty": 0.5,
     "examples": [
         {"zh": "另外还有一个问题想问你。", "pinyin": "Lìngwài hái yǒu yí gè wèntí xiǎng wèn nǐ.", "en": "In addition, there's another question I want to ask you."},
         {"zh": "我买了书，另外还买了笔。", "pinyin": "Wǒ mǎi le shū, lìngwài hái mǎi le bǐ.", "en": "I bought books, and also bought pens."},
         {"zh": "另外，请注意安全。", "pinyin": "Lìngwài, qǐng zhùyì ānquán.", "en": "In addition, please pay attention to safety."},
     ]},

    {"name": "否则 otherwise", "name_zh": "否则", "hsk_level": 4, "category": "connector",
     "description": "Warns of consequence if condition not met: 快走，否则就迟到了", "difficulty": 0.6,
     "examples": [
         {"zh": "快走，否则就迟到了。", "pinyin": "Kuài zǒu, fǒuzé jiù chídào le.", "en": "Hurry up, otherwise we'll be late."},
         {"zh": "你得好好准备，否则考试会不及格。", "pinyin": "Nǐ děi hǎohǎo zhǔnbèi, fǒuzé kǎoshì huì bù jígé.", "en": "You must prepare well, otherwise you'll fail the exam."},
         {"zh": "多穿点儿，否则会感冒。", "pinyin": "Duō chuān diǎnr, fǒuzé huì gǎnmào.", "en": "Wear more clothes, otherwise you'll catch a cold."},
     ]},

    {"name": "除非 unless", "name_zh": "除非", "hsk_level": 4, "category": "connector",
     "description": "States the only condition under which something would happen: 除非你帮我", "difficulty": 0.6,
     "examples": [
         {"zh": "除非你帮我，否则我做不完。", "pinyin": "Chúfēi nǐ bāng wǒ, fǒuzé wǒ zuò bu wán.", "en": "Unless you help me, I can't finish."},
         {"zh": "除非下雨，我们都会去。", "pinyin": "Chúfēi xiàyǔ, wǒmen dōu huì qù.", "en": "Unless it rains, we'll all go."},
         {"zh": "除非他亲自来，我不会相信。", "pinyin": "Chúfēi tā qīnzì lái, wǒ bú huì xiāngxìn.", "en": "Unless he comes in person, I won't believe it."},
     ]},

    {"name": "倒 contrary to expectation", "name_zh": "倒", "hsk_level": 4, "category": "particle",
     "description": "Indicates something contrary to expectation or concedes a point: 他倒是很聪明", "difficulty": 0.6,
     "examples": [
         {"zh": "他倒是很聪明，就是太懒了。", "pinyin": "Tā dào shì hěn cōngmíng, jiùshì tài lǎn le.", "en": "He is quite smart, it's just that he's too lazy."},
         {"zh": "这个办法倒不错。", "pinyin": "Zhège bànfǎ dào búcuò.", "en": "This method is actually not bad."},
         {"zh": "你倒说说看，有什么好主意？", "pinyin": "Nǐ dào shuōshuo kàn, yǒu shénme hǎo zhǔyi?", "en": "Go ahead and tell me then — any good ideas?"},
     ]},

    {"name": "毕竟 after all", "name_zh": "毕竟", "hsk_level": 4, "category": "particle",
     "description": "Acknowledges a fundamental reason: 他毕竟还是个孩子", "difficulty": 0.6,
     "examples": [
         {"zh": "他毕竟还是个孩子，别太严格了。", "pinyin": "Tā bìjìng háishì gè háizi, bié tài yángé le.", "en": "He's still a child after all — don't be too strict."},
         {"zh": "毕竟是第一次，做得不好很正常。", "pinyin": "Bìjìng shì dì yī cì, zuò de bù hǎo hěn zhèngcháng.", "en": "After all it's the first time — it's normal not to do well."},
         {"zh": "毕竟我们是朋友，应该互相帮助。", "pinyin": "Bìjìng wǒmen shì péngyou, yīnggāi hùxiāng bāngzhù.", "en": "After all we're friends — we should help each other."},
     ]},

    {"name": "万一 in case", "name_zh": "万一", "hsk_level": 4, "category": "connector",
     "description": "Introduces an unlikely but possible scenario: 万一下雨怎么办？", "difficulty": 0.6,
     "examples": [
         {"zh": "万一下雨怎么办？", "pinyin": "Wànyī xiàyǔ zěnme bàn?", "en": "What if it rains?"},
         {"zh": "带把伞吧，万一下雨呢。", "pinyin": "Dài bǎ sǎn ba, wànyī xiàyǔ ne.", "en": "Bring an umbrella, just in case it rains."},
         {"zh": "万一他不来，我们就自己开始。", "pinyin": "Wànyī tā bù lái, wǒmen jiù zìjǐ kāishǐ.", "en": "In case he doesn't come, we'll start on our own."},
     ]},

    # ── HSK 5 (12 new) ──────────────────────────────────────────────

    {"name": "难免 hard to avoid", "name_zh": "难免", "hsk_level": 5, "category": "particle",
     "description": "Indicates something is inevitable or unavoidable: 初学者难免犯错", "difficulty": 0.7,
     "examples": [
         {"zh": "初学者难免犯错。", "pinyin": "Chūxuézhě nánmiǎn fàncuò.", "en": "Beginners inevitably make mistakes."},
         {"zh": "第一次做难免紧张。", "pinyin": "Dì yī cì zuò nánmiǎn jǐnzhāng.", "en": "It's hard not to be nervous the first time."},
         {"zh": "长时间不见，难免会生疏。", "pinyin": "Cháng shíjiān bú jiàn, nánmiǎn huì shēngshū.", "en": "Not seeing each other for a long time, it's inevitable to grow distant."},
     ]},

    {"name": "何必 why bother", "name_zh": "何必", "hsk_level": 5, "category": "particle",
     "description": "Rhetorically questions the need for something: 何必这么着急呢？", "difficulty": 0.7,
     "examples": [
         {"zh": "何必这么着急呢？", "pinyin": "Hébì zhème zháojí ne?", "en": "Why bother being so anxious?"},
         {"zh": "何必跟他生气？不值得。", "pinyin": "Hébì gēn tā shēngqì? Bù zhídé.", "en": "Why bother getting angry at him? It's not worth it."},
         {"zh": "既然不喜欢，何必勉强自己？", "pinyin": "Jìrán bù xǐhuan, hébì miǎnqiǎng zìjǐ?", "en": "Since you don't like it, why force yourself?"},
     ]},

    {"name": "未必 not necessarily", "name_zh": "未必", "hsk_level": 5, "category": "particle",
     "description": "Expresses that something is not certain: 贵的未必好", "difficulty": 0.7,
     "examples": [
         {"zh": "贵的未必好，便宜的未必差。", "pinyin": "Guì de wèibì hǎo, piányi de wèibì chà.", "en": "Expensive doesn't necessarily mean good; cheap doesn't necessarily mean bad."},
         {"zh": "他说的未必是真的。", "pinyin": "Tā shuō de wèibì shì zhēn de.", "en": "What he said is not necessarily true."},
         {"zh": "人多未必力量大。", "pinyin": "Rén duō wèibì lìliàng dà.", "en": "More people doesn't necessarily mean more power."},
     ]},

    {"name": "果然 as expected", "name_zh": "果然", "hsk_level": 5, "category": "particle",
     "description": "Confirms something happened as predicted: 他果然来了", "difficulty": 0.6,
     "examples": [
         {"zh": "他果然来了，跟我猜的一样。", "pinyin": "Tā guǒrán lái le, gēn wǒ cāi de yíyàng.", "en": "He came as expected, just as I guessed."},
         {"zh": "天气预报说会下雨，果然下了。", "pinyin": "Tiānqì yùbào shuō huì xiàyǔ, guǒrán xià le.", "en": "The forecast said it would rain, and sure enough it did."},
         {"zh": "大家都说这家餐厅好吃，果然名不虚传。", "pinyin": "Dàjiā dōu shuō zhè jiā cāntīng hǎochī, guǒrán míng bù xū chuán.", "en": "Everyone said this restaurant was good, and it truly lives up to its reputation."},
     ]},

    {"name": "似乎 seemingly", "name_zh": "似乎", "hsk_level": 5, "category": "particle",
     "description": "Indicates an uncertain impression or observation: 他似乎不太高兴", "difficulty": 0.6,
     "examples": [
         {"zh": "他似乎不太高兴。", "pinyin": "Tā sìhū bú tài gāoxìng.", "en": "He seems unhappy."},
         {"zh": "这个问题似乎很复杂。", "pinyin": "Zhège wèntí sìhū hěn fùzá.", "en": "This problem seems quite complex."},
         {"zh": "她似乎忘了我们的约定。", "pinyin": "Tā sìhū wàng le wǒmen de yuēdìng.", "en": "She seems to have forgotten our agreement."},
     ]},

    {"name": "到底 after all/ultimately", "name_zh": "到底", "hsk_level": 5, "category": "particle",
     "description": "Presses for an answer or emphasizes finally reaching a result: 你到底想干什么？", "difficulty": 0.6,
     "examples": [
         {"zh": "你到底想干什么？", "pinyin": "Nǐ dàodǐ xiǎng gàn shénme?", "en": "What on earth do you want to do?"},
         {"zh": "他到底来不来？", "pinyin": "Tā dàodǐ lái bu lái?", "en": "Is he coming or not, after all?"},
         {"zh": "经过努力，他到底成功了。", "pinyin": "Jīngguò nǔlì, tā dàodǐ chénggōng le.", "en": "After much effort, he finally succeeded."},
     ]},

    {"name": "从此 from then on", "name_zh": "从此", "hsk_level": 5, "category": "connector",
     "description": "Marks a turning point from which things change: 从此他再也没回来", "difficulty": 0.7,
     "examples": [
         {"zh": "从此他再也没回来过。", "pinyin": "Cóngcǐ tā zài yě méi huílái guo.", "en": "From then on, he never came back."},
         {"zh": "那次经历改变了他，从此他变得更加努力。", "pinyin": "Nà cì jīnglì gǎibiàn le tā, cóngcǐ tā biàn de gèngjiā nǔlì.", "en": "That experience changed him; from then on he became more hardworking."},
         {"zh": "他们吵了一架，从此再也不说话了。", "pinyin": "Tāmen chǎo le yí jià, cóngcǐ zài yě bù shuōhuà le.", "en": "They had a fight, and from then on they never spoke again."},
     ]},

    {"name": "据说 it is said", "name_zh": "据说", "hsk_level": 5, "category": "particle",
     "description": "Introduces hearsay or reported information: 据说明天会下雪", "difficulty": 0.6,
     "examples": [
         {"zh": "据说明天会下雪。", "pinyin": "Jùshuō míngtiān huì xiàxuě.", "en": "It's said that it will snow tomorrow."},
         {"zh": "据说这家店的老板是外国人。", "pinyin": "Jùshuō zhè jiā diàn de lǎobǎn shì wàiguó rén.", "en": "It's said that the owner of this shop is a foreigner."},
         {"zh": "据说他已经辞职了。", "pinyin": "Jùshuō tā yǐjīng cízhí le.", "en": "Reportedly, he has already resigned."},
     ]},

    {"name": "可见 it can be seen", "name_zh": "可见", "hsk_level": 5, "category": "connector",
     "description": "Draws a conclusion from preceding evidence: 可见这件事很重要", "difficulty": 0.7,
     "examples": [
         {"zh": "大家都这么关心，可见这件事很重要。", "pinyin": "Dàjiā dōu zhème guānxīn, kějiàn zhè jiàn shì hěn zhòngyào.", "en": "Everyone is so concerned — it shows how important this matter is."},
         {"zh": "他准备了这么久，可见他很认真。", "pinyin": "Tā zhǔnbèi le zhème jiǔ, kějiàn tā hěn rènzhēn.", "en": "He prepared for so long — you can tell he's very serious."},
         {"zh": "效果这么好，可见方法是对的。", "pinyin": "Xiàoguǒ zhème hǎo, kějiàn fāngfǎ shì duì de.", "en": "The results are so good — clearly the method was right."},
     ]},

    {"name": "此外 furthermore", "name_zh": "此外", "hsk_level": 5, "category": "connector",
     "description": "Adds formal supplementary information: 此外还要注意安全", "difficulty": 0.7,
     "examples": [
         {"zh": "此外，还要注意安全问题。", "pinyin": "Cǐwài, hái yào zhùyì ānquán wèntí.", "en": "Furthermore, we need to pay attention to safety."},
         {"zh": "他会说英语和法语，此外还会一点儿日语。", "pinyin": "Tā huì shuō Yīngyǔ hé Fǎyǔ, cǐwài hái huì yìdiǎnr Rìyǔ.", "en": "He speaks English and French; furthermore, he knows a little Japanese."},
         {"zh": "此外，我还想提一个建议。", "pinyin": "Cǐwài, wǒ hái xiǎng tí yí gè jiànyì.", "en": "Furthermore, I'd like to make a suggestion."},
     ]},

    {"name": "因此 therefore", "name_zh": "因此", "hsk_level": 5, "category": "connector",
     "description": "Formal marker of logical consequence: 因此我们决定推迟", "difficulty": 0.7,
     "examples": [
         {"zh": "天气不好，因此我们决定推迟出发。", "pinyin": "Tiānqì bù hǎo, yīncǐ wǒmen juédìng tuīchí chūfā.", "en": "The weather is bad; therefore we decided to delay departure."},
         {"zh": "他工作很努力，因此得到了提升。", "pinyin": "Tā gōngzuò hěn nǔlì, yīncǐ dédào le tíshēng.", "en": "He works very hard; therefore he got promoted."},
         {"zh": "资金不足，因此项目暂停了。", "pinyin": "Zījīn bùzú, yīncǐ xiàngmù zàntíng le.", "en": "Funding is insufficient; therefore the project is on hold."},
     ]},

    {"name": "向来 always/all along", "name_zh": "向来", "hsk_level": 5, "category": "particle",
     "description": "Indicates a longstanding habit or characteristic: 他向来很准时", "difficulty": 0.7,
     "examples": [
         {"zh": "他向来很准时，从不迟到。", "pinyin": "Tā xiànglái hěn zhǔnshí, cóng bù chídào.", "en": "He has always been punctual and never late."},
         {"zh": "她向来不太爱说话。", "pinyin": "Tā xiànglái bú tài ài shuōhuà.", "en": "She has never been much of a talker."},
         {"zh": "我们公司向来重视客户反馈。", "pinyin": "Wǒmen gōngsī xiànglái zhòngshì kèhù fǎnkuì.", "en": "Our company has always valued customer feedback."},
     ]},

    # ── HSK 6 (10 new) ──────────────────────────────────────────────

    {"name": "不免 inevitably", "name_zh": "不免", "hsk_level": 6, "category": "particle",
     "description": "Indicates something is unavoidable given the circumstances: 生活中不免有困难", "difficulty": 0.7,
     "examples": [
         {"zh": "生活中不免有困难。", "pinyin": "Shēnghuó zhōng bùmiǎn yǒu kùnnan.", "en": "There are inevitably difficulties in life."},
         {"zh": "离开家乡，不免会想念家人。", "pinyin": "Líkāi jiāxiāng, bùmiǎn huì xiǎngniàn jiārén.", "en": "Leaving one's hometown, one can't help but miss family."},
         {"zh": "独自出国留学，不免感到孤独。", "pinyin": "Dúzì chūguó liúxué, bùmiǎn gǎndào gūdú.", "en": "Studying abroad alone, one inevitably feels lonely."},
     ]},

    {"name": "反之 on the contrary", "name_zh": "反之", "hsk_level": 6, "category": "connector",
     "description": "Introduces the opposite case: 反之也是一样的", "difficulty": 0.8,
     "examples": [
         {"zh": "努力就会进步，反之就会退步。", "pinyin": "Nǔlì jiù huì jìnbù, fǎnzhī jiù huì tuìbù.", "en": "If you work hard you'll progress; otherwise you'll regress."},
         {"zh": "反之，如果不注意健康，后果很严重。", "pinyin": "Fǎnzhī, rúguǒ bù zhùyì jiànkāng, hòuguǒ hěn yánzhòng.", "en": "On the contrary, if you don't pay attention to health, the consequences are serious."},
         {"zh": "好的态度能带来好结果，反之亦然。", "pinyin": "Hǎo de tàidù néng dàilái hǎo jiéguǒ, fǎnzhī yìrán.", "en": "A good attitude can bring good results, and vice versa."},
     ]},

    {"name": "无疑 undoubtedly", "name_zh": "无疑", "hsk_level": 6, "category": "particle",
     "description": "Asserts certainty: 这无疑是最好的选择", "difficulty": 0.8,
     "examples": [
         {"zh": "这无疑是最好的选择。", "pinyin": "Zhè wúyí shì zuì hǎo de xuǎnzé.", "en": "This is undoubtedly the best choice."},
         {"zh": "他的成功无疑归功于坚持不懈。", "pinyin": "Tā de chénggōng wúyí guīgōng yú jiānchí bùxiè.", "en": "His success is undoubtedly due to perseverance."},
         {"zh": "这项技术无疑将改变我们的生活。", "pinyin": "Zhè xiàng jìshù wúyí jiāng gǎibiàn wǒmen de shēnghuó.", "en": "This technology will undoubtedly change our lives."},
     ]},

    {"name": "不禁 can't help but", "name_zh": "不禁", "hsk_level": 6, "category": "particle",
     "description": "Indicates an involuntary emotional reaction: 他不禁笑了起来", "difficulty": 0.8,
     "examples": [
         {"zh": "听到这个消息，他不禁笑了起来。", "pinyin": "Tīngdào zhège xiāoxi, tā bùjīn xiào le qǐlái.", "en": "Hearing the news, he couldn't help but laugh."},
         {"zh": "看到家乡的变化，她不禁感叹万千。", "pinyin": "Kàndào jiāxiāng de biànhuà, tā bùjīn gǎntàn wànqiān.", "en": "Seeing the changes in her hometown, she couldn't help but be deeply moved."},
         {"zh": "回忆往事，我不禁流下了眼泪。", "pinyin": "Huíyì wǎngshì, wǒ bùjīn liúxià le yǎnlèi.", "en": "Recalling the past, I couldn't help but shed tears."},
     ]},

    {"name": "简直 simply/virtually", "name_zh": "简直", "hsk_level": 6, "category": "particle",
     "description": "Intensifies to the point of exaggeration: 这简直太好了", "difficulty": 0.7,
     "examples": [
         {"zh": "这简直太好了！", "pinyin": "Zhè jiǎnzhí tài hǎo le!", "en": "This is simply wonderful!"},
         {"zh": "他简直不敢相信自己的眼睛。", "pinyin": "Tā jiǎnzhí bù gǎn xiāngxìn zìjǐ de yǎnjing.", "en": "He simply couldn't believe his eyes."},
         {"zh": "今天的交通简直是一场噩梦。", "pinyin": "Jīntiān de jiāotōng jiǎnzhí shì yì chǎng èmèng.", "en": "Today's traffic was virtually a nightmare."},
     ]},

    {"name": "偏偏 contrary to expectations", "name_zh": "偏偏", "hsk_level": 6, "category": "particle",
     "description": "Emphasizes that something happened contrary to what was desired: 我偏偏忘了带伞", "difficulty": 0.8,
     "examples": [
         {"zh": "下雨了，我偏偏忘了带伞。", "pinyin": "Xiàyǔ le, wǒ piānpiān wàng le dài sǎn.", "en": "It rained, and of all things I forgot my umbrella."},
         {"zh": "大家都来了，他偏偏不来。", "pinyin": "Dàjiā dōu lái le, tā piānpiān bù lái.", "en": "Everyone came, but he just had to be the one who didn't."},
         {"zh": "我不想见他，偏偏在路上碰到了。", "pinyin": "Wǒ bù xiǎng jiàn tā, piānpiān zài lùshang pèngdào le.", "en": "I didn't want to see him, but wouldn't you know it, I ran into him on the street."},
     ]},

    {"name": "归根结底 in the final analysis", "name_zh": "归根结底", "hsk_level": 6, "category": "connector",
     "description": "Gets to the root cause or ultimate conclusion: 归根结底是态度问题", "difficulty": 0.8,
     "examples": [
         {"zh": "归根结底，这是一个态度问题。", "pinyin": "Guīgēn jiédǐ, zhè shì yí gè tàidù wèntí.", "en": "In the final analysis, this is a matter of attitude."},
         {"zh": "归根结底，成功靠的是坚持。", "pinyin": "Guīgēn jiédǐ, chénggōng kào de shì jiānchí.", "en": "Ultimately, success depends on perseverance."},
         {"zh": "问题很多，但归根结底还是资金不足。", "pinyin": "Wèntí hěn duō, dàn guīgēn jiédǐ háishì zījīn bùzú.", "en": "There are many problems, but fundamentally it comes down to insufficient funding."},
     ]},

    {"name": "总而言之 in summary", "name_zh": "总而言之", "hsk_level": 6, "category": "connector",
     "description": "Formal summary marker: 总而言之我们需要改变", "difficulty": 0.8,
     "examples": [
         {"zh": "总而言之，我们需要做出改变。", "pinyin": "Zǒng'ér yánzhī, wǒmen xūyào zuòchū gǎibiàn.", "en": "In summary, we need to make changes."},
         {"zh": "总而言之，这次会议很成功。", "pinyin": "Zǒng'ér yánzhī, zhè cì huìyì hěn chénggōng.", "en": "All in all, this meeting was very successful."},
         {"zh": "总而言之，健康比什么都重要。", "pinyin": "Zǒng'ér yánzhī, jiànkāng bǐ shénme dōu zhòngyào.", "en": "In summary, health is more important than anything."},
     ]},

    {"name": "进而 and then further", "name_zh": "进而", "hsk_level": 6, "category": "connector",
     "description": "Introduces a further step or progression: 先理解然后进而应用", "difficulty": 0.8,
     "examples": [
         {"zh": "先理解基础知识，进而学会应用。", "pinyin": "Xiān lǐjiě jīchǔ zhīshi, jìn'ér xuéhuì yìngyòng.", "en": "First understand the basics, then further learn to apply them."},
         {"zh": "我们要发现问题，进而解决问题。", "pinyin": "Wǒmen yào fāxiàn wèntí, jìn'ér jiějué wèntí.", "en": "We need to identify problems, and then further solve them."},
         {"zh": "通过阅读提高词汇量，进而提升写作水平。", "pinyin": "Tōngguò yuèdú tígāo cíhuìliàng, jìn'ér tíshēng xiězuò shuǐpíng.", "en": "Increase vocabulary through reading, and further improve writing skills."},
     ]},

    {"name": "与其说...不如说 rather than...better to say", "name_zh": "与其说…不如说", "hsk_level": 6, "category": "connector",
     "description": "Reframes one characterization as more accurate than another: 与其说是失败，不如说是经验", "difficulty": 0.9,
     "examples": [
         {"zh": "与其说是失败，不如说是一次宝贵的经验。", "pinyin": "Yǔqí shuō shì shībài, bùrú shuō shì yí cì bǎoguì de jīngyàn.", "en": "Rather than calling it a failure, it's better to call it a valuable experience."},
         {"zh": "与其说他聪明，不如说他努力。", "pinyin": "Yǔqí shuō tā cōngmíng, bùrú shuō tā nǔlì.", "en": "Rather than saying he's smart, it's more accurate to say he works hard."},
         {"zh": "与其说是运气好，不如说是准备充分。", "pinyin": "Yǔqí shuō shì yùnqi hǎo, bùrú shuō shì zhǔnbèi chōngfèn.", "en": "Rather than saying it was good luck, it's better to say he was well prepared."},
     ]},
]
