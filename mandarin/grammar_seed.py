"""Seed grammar points and language skills for HSK 1-9."""

import json

from .grammar_extra_hsk1_3 import EXTRA_GRAMMAR_HSK1_3
from .grammar_extra_hsk4_6 import EXTRA_GRAMMAR_HSK4_6
from .grammar_extra_hsk7_9 import EXTRA_GRAMMAR_HSK7_9
from .grammar_extra_hsk1_2_r2 import EXTRA_GRAMMAR_HSK1_2_R2
from .grammar_extra_hsk3_4_r2 import EXTRA_GRAMMAR_HSK3_4_R2
from .grammar_extra_hsk5_6_r2 import EXTRA_GRAMMAR_HSK5_6_R2
from .grammar_extra_hsk7_9_r2 import EXTRA_GRAMMAR_HSK7_9_R2
from .grammar_extra_hsk1_3_r3 import EXTRA_GRAMMAR_HSK1_3_R3
from .grammar_extra_hsk4_5_r3 import EXTRA_GRAMMAR_HSK4_5_R3
from .grammar_extra_hsk6_9_r3 import EXTRA_GRAMMAR_HSK6_9_R3


GRAMMAR_POINTS = [
    # HSK 1 — basic structures
    {"name": "Subject + 是 + Object", "name_zh": "是", "hsk_level": 1, "category": "structure",
     "description": "Basic 'to be' sentences: 我是学生", "difficulty": 0.2,
     "examples": [
         {"zh": "我是学生。", "pinyin": "Wǒ shì xuéshēng.", "en": "I am a student."},
         {"zh": "他是老师。", "pinyin": "Tā shì lǎoshī.", "en": "He is a teacher."},
         {"zh": "这是我的书。", "pinyin": "Zhè shì wǒ de shū.", "en": "This is my book."},
         {"zh": "她不是中国人。", "pinyin": "Tā bú shì Zhōngguó rén.", "en": "She is not Chinese."},
     ]},
    {"name": "Subject + 很 + Adjective", "name_zh": "很+形容词", "hsk_level": 1, "category": "structure",
     "description": "Expressing degree: 她很高兴", "difficulty": 0.2,
     "examples": [
         {"zh": "今天很热。", "pinyin": "Jīntiān hěn rè.", "en": "Today is hot."},
         {"zh": "这个菜很好吃。", "pinyin": "Zhège cài hěn hǎo chī.", "en": "This dish is delicious."},
         {"zh": "她很漂亮。", "pinyin": "Tā hěn piàoliang.", "en": "She is pretty."},
         {"zh": "中文很有意思。", "pinyin": "Zhōngwén hěn yǒu yìsi.", "en": "Chinese is interesting."},
     ]},
    {"name": "不 negation", "name_zh": "不", "hsk_level": 1, "category": "particle",
     "description": "Negating verbs/adjectives with 不: 我不喝茶", "difficulty": 0.2,
     "examples": [
         {"zh": "我不喝咖啡。", "pinyin": "Wǒ bù hē kāfēi.", "en": "I don't drink coffee."},
         {"zh": "他不是医生。", "pinyin": "Tā bú shì yīshēng.", "en": "He is not a doctor."},
         {"zh": "我不想去。", "pinyin": "Wǒ bù xiǎng qù.", "en": "I don't want to go."},
         {"zh": "这个不贵。", "pinyin": "Zhège bú guì.", "en": "This is not expensive."},
     ]},
    {"name": "没 negation", "name_zh": "没/没有", "hsk_level": 1, "category": "particle",
     "description": "Negating past actions or existence: 他没去", "difficulty": 0.3,
     "examples": [
         {"zh": "我没吃早饭。", "pinyin": "Wǒ méi chī zǎofàn.", "en": "I didn't eat breakfast."},
         {"zh": "他没有钱。", "pinyin": "Tā méiyǒu qián.", "en": "He has no money."},
         {"zh": "昨天没下雨。", "pinyin": "Zuótiān méi xiàyǔ.", "en": "It didn't rain yesterday."},
         {"zh": "她没来上课。", "pinyin": "Tā méi lái shàngkè.", "en": "She didn't come to class."},
     ]},
    {"name": "的 possession/modification", "name_zh": "的", "hsk_level": 1, "category": "particle",
     "description": "Possession and noun modification: 我的书、大的苹果", "difficulty": 0.3,
     "examples": [
         {"zh": "这是我的手机。", "pinyin": "Zhè shì wǒ de shǒujī.", "en": "This is my phone."},
         {"zh": "大的那个。", "pinyin": "Dà de nàge.", "en": "The big one."},
         {"zh": "妈妈做的菜。", "pinyin": "Māma zuò de cài.", "en": "The dish mom made."},
         {"zh": "红色的衣服。", "pinyin": "Hóngsè de yīfu.", "en": "Red clothes."},
     ]},
    {"name": "了 perfective & change-of-state", "name_zh": "了", "hsk_level": 1, "category": "aspect",
     "description": "Two distinct uses: (1) Perfective 了 (after verb) marks completed action: 我吃了饭; (2) Sentence-final 了 marks change of state or new situation: 下雨了. Both can co-occur: 我吃了饭了.",
     "difficulty": 0.4,
     "examples": [
         {"zh": "我买了两本书。", "pinyin": "Wǒ mǎile liǎng běn shū.", "en": "I bought two books.", "note": "Perfective 了: action completed"},
         {"zh": "他喝了三杯水。", "pinyin": "Tā hēle sān bēi shuǐ.", "en": "He drank three cups of water.", "note": "Perfective 了: completed with quantity"},
         {"zh": "下雨了。", "pinyin": "Xiàyǔ le.", "en": "It started raining.", "note": "Change-of-state 了: new situation"},
         {"zh": "他高了。", "pinyin": "Tā gāo le.", "en": "He got taller.", "note": "Change-of-state 了: new condition"},
         {"zh": "我不想吃了。", "pinyin": "Wǒ bù xiǎng chī le.", "en": "I don't want to eat anymore.", "note": "Change-of-state 了: changed desire"},
         {"zh": "我吃了饭了。", "pinyin": "Wǒ chīle fàn le.", "en": "I've eaten (and that's the current situation).", "note": "Both 了: perfective + change-of-state"},
         {"zh": "我学了一年中文了。", "pinyin": "Wǒ xuéle yì nián Zhōngwén le.", "en": "I've been studying Chinese for a year now.", "note": "Both 了: duration + ongoing relevance"},
     ]},
    {"name": "吗 yes/no question", "name_zh": "吗", "hsk_level": 1, "category": "particle",
     "description": "Question particle: 你好吗？", "difficulty": 0.1,
     "examples": [
         {"zh": "你是学生吗？", "pinyin": "Nǐ shì xuéshēng ma?", "en": "Are you a student?"},
         {"zh": "你喜欢吃中国菜吗？", "pinyin": "Nǐ xǐhuan chī Zhōngguó cài ma?", "en": "Do you like Chinese food?"},
         {"zh": "明天有时间吗？", "pinyin": "Míngtiān yǒu shíjiān ma?", "en": "Do you have time tomorrow?"},
     ]},
    {"name": "呢 follow-up question", "name_zh": "呢", "hsk_level": 1, "category": "particle",
     "description": "And you? / What about...?: 你呢？", "difficulty": 0.2,
     "examples": [
         {"zh": "我很好，你呢？", "pinyin": "Wǒ hěn hǎo, nǐ ne?", "en": "I'm fine, and you?"},
         {"zh": "我的书呢？", "pinyin": "Wǒ de shū ne?", "en": "Where's my book?"},
         {"zh": "他去北京了，你呢？", "pinyin": "Tā qù Běijīng le, nǐ ne?", "en": "He went to Beijing, what about you?"},
     ]},
    {"name": "Measure words (个/本/杯)", "name_zh": "量词", "hsk_level": 1, "category": "measure_word",
     "description": "Basic measure words: 一个人、两本书、三杯水", "difficulty": 0.3,
     "examples": [
         {"zh": "一个人。", "pinyin": "Yí gè rén.", "en": "One person."},
         {"zh": "三本书。", "pinyin": "Sān běn shū.", "en": "Three books."},
         {"zh": "两杯茶。", "pinyin": "Liǎng bēi chá.", "en": "Two cups of tea."},
         {"zh": "五个苹果。", "pinyin": "Wǔ gè píngguǒ.", "en": "Five apples."},
     ]},
    {"name": "在 location", "name_zh": "在", "hsk_level": 1, "category": "structure",
     "description": "Location: 我在北京、书在桌子上", "difficulty": 0.3,
     "examples": [
         {"zh": "我在家。", "pinyin": "Wǒ zài jiā.", "en": "I'm at home."},
         {"zh": "猫在桌子上。", "pinyin": "Māo zài zhuōzi shàng.", "en": "The cat is on the table."},
         {"zh": "他在学校学习。", "pinyin": "Tā zài xuéxiào xuéxí.", "en": "He studies at school."},
         {"zh": "超市在银行旁边。", "pinyin": "Chāoshì zài yínháng pángbiān.", "en": "The supermarket is next to the bank."},
     ]},

    # HSK 2 — expanding structures
    {"name": "过 experience", "name_zh": "过", "hsk_level": 2, "category": "aspect",
     "description": "Past experience: 我去过中国", "difficulty": 0.4,
     "examples": [
         {"zh": "我去过上海。", "pinyin": "Wǒ qùguo Shànghǎi.", "en": "I've been to Shanghai."},
         {"zh": "你吃过北京烤鸭吗？", "pinyin": "Nǐ chīguo Běijīng kǎoyā ma?", "en": "Have you ever eaten Peking duck?"},
         {"zh": "我没学过日语。", "pinyin": "Wǒ méi xuéguo Rìyǔ.", "en": "I've never studied Japanese."},
         {"zh": "他来过这里两次。", "pinyin": "Tā láiguo zhèlǐ liǎng cì.", "en": "He's been here twice."},
     ]},
    {"name": "正在 ongoing action", "name_zh": "正在", "hsk_level": 2, "category": "aspect",
     "description": "Progressive aspect: 他正在看书", "difficulty": 0.3,
     "examples": [
         {"zh": "我正在吃饭。", "pinyin": "Wǒ zhèngzài chīfàn.", "en": "I'm eating right now."},
         {"zh": "他正在打电话。", "pinyin": "Tā zhèngzài dǎ diànhuà.", "en": "He's on the phone right now."},
         {"zh": "外面正在下雪。", "pinyin": "Wàimiàn zhèngzài xiàxuě.", "en": "It's snowing outside."},
     ]},
    {"name": "比 comparison", "name_zh": "比", "hsk_level": 2, "category": "comparison",
     "description": "Comparing: 他比我高", "difficulty": 0.4,
     "examples": [
         {"zh": "他比我高。", "pinyin": "Tā bǐ wǒ gāo.", "en": "He is taller than me."},
         {"zh": "坐地铁比打车快。", "pinyin": "Zuò dìtiě bǐ dǎchē kuài.", "en": "Taking the subway is faster than a taxi."},
         {"zh": "今天比昨天冷。", "pinyin": "Jīntiān bǐ zuótiān lěng.", "en": "Today is colder than yesterday."},
         {"zh": "中文比英文难。", "pinyin": "Zhōngwén bǐ Yīngwén nán.", "en": "Chinese is harder than English."},
     ]},
    {"name": "要/想 want/plan", "name_zh": "要/想", "hsk_level": 2, "category": "structure",
     "description": "Expressing desire/intention: 我想去、我要学中文", "difficulty": 0.3,
     "examples": [
         {"zh": "我想学中文。", "pinyin": "Wǒ xiǎng xué Zhōngwén.", "en": "I want to learn Chinese."},
         {"zh": "我要一杯咖啡。", "pinyin": "Wǒ yào yì bēi kāfēi.", "en": "I want a cup of coffee."},
         {"zh": "你想去哪儿？", "pinyin": "Nǐ xiǎng qù nǎr?", "en": "Where do you want to go?"},
         {"zh": "明天要下雨。", "pinyin": "Míngtiān yào xiàyǔ.", "en": "It's going to rain tomorrow."},
     ]},
    {"name": "可以/能 ability/permission", "name_zh": "可以/能", "hsk_level": 2, "category": "structure",
     "description": "Permission/ability: 你可以走了、我能帮你", "difficulty": 0.3,
     "examples": [
         {"zh": "我可以进来吗？", "pinyin": "Wǒ kěyǐ jìnlái ma?", "en": "May I come in?"},
         {"zh": "你能说中文吗？", "pinyin": "Nǐ néng shuō Zhōngwén ma?", "en": "Can you speak Chinese?"},
         {"zh": "这里不能吸烟。", "pinyin": "Zhèlǐ bù néng xīyān.", "en": "You can't smoke here."},
         {"zh": "今天不能去。", "pinyin": "Jīntiān bù néng qù.", "en": "I can't go today."},
     ]},
    {"name": "得 complement degree", "name_zh": "得", "hsk_level": 2, "category": "complement",
     "description": "Degree complement: 他说得很好", "difficulty": 0.5,
     "examples": [
         {"zh": "他中文说得很好。", "pinyin": "Tā Zhōngwén shuō de hěn hǎo.", "en": "He speaks Chinese very well."},
         {"zh": "她跑得很快。", "pinyin": "Tā pǎo de hěn kuài.", "en": "She runs very fast."},
         {"zh": "你写得不错。", "pinyin": "Nǐ xiě de búcuò.", "en": "You write quite well."},
         {"zh": "我起得太晚了。", "pinyin": "Wǒ qǐ de tài wǎn le.", "en": "I got up too late."},
     ]},
    {"name": "从...到 from...to", "name_zh": "从…到", "hsk_level": 2, "category": "structure",
     "description": "Range: 从北京到上海", "difficulty": 0.3,
     "examples": [
         {"zh": "从北京到上海要五个小时。", "pinyin": "Cóng Běijīng dào Shànghǎi yào wǔ gè xiǎoshí.", "en": "It takes 5 hours from Beijing to Shanghai."},
         {"zh": "从早上到晚上。", "pinyin": "Cóng zǎoshang dào wǎnshang.", "en": "From morning to evening."},
         {"zh": "从这儿到学校不远。", "pinyin": "Cóng zhèr dào xuéxiào bù yuǎn.", "en": "From here to school is not far."},
     ]},
    {"name": "Time + 的时候", "name_zh": "的时候", "hsk_level": 2, "category": "structure",
     "description": "When/at the time of: 吃饭的时候", "difficulty": 0.3,
     "examples": [
         {"zh": "吃饭的时候不要看手机。", "pinyin": "Chīfàn de shíhou bú yào kàn shǒujī.", "en": "Don't look at your phone while eating."},
         {"zh": "下雨的时候带伞。", "pinyin": "Xiàyǔ de shíhou dài sǎn.", "en": "Bring an umbrella when it rains."},
         {"zh": "小的时候我住在北京。", "pinyin": "Xiǎo de shíhou wǒ zhù zài Běijīng.", "en": "When I was young I lived in Beijing."},
     ]},

    # HSK 3 — complex patterns
    {"name": "把 disposal", "name_zh": "把", "hsk_level": 3, "category": "structure",
     "description": "Disposal construction: 把门关上", "difficulty": 0.6,
     "examples": [
         {"zh": "请把门关上。", "pinyin": "Qǐng bǎ mén guānshang.", "en": "Please close the door."},
         {"zh": "我把作业做完了。", "pinyin": "Wǒ bǎ zuòyè zuòwán le.", "en": "I finished the homework."},
         {"zh": "他把书放在桌子上。", "pinyin": "Tā bǎ shū fàng zài zhuōzi shàng.", "en": "He put the book on the table."},
         {"zh": "别把这件事忘了。", "pinyin": "Bié bǎ zhè jiàn shì wàng le.", "en": "Don't forget this matter."},
     ]},
    {"name": "被 passive", "name_zh": "被", "hsk_level": 3, "category": "structure",
     "description": "Passive voice: 苹果被吃了", "difficulty": 0.6,
     "examples": [
         {"zh": "蛋糕被他吃了。", "pinyin": "Dàngāo bèi tā chī le.", "en": "The cake was eaten by him."},
         {"zh": "我的手机被偷了。", "pinyin": "Wǒ de shǒujī bèi tōu le.", "en": "My phone was stolen."},
         {"zh": "这本书被翻译成英文了。", "pinyin": "Zhè běn shū bèi fānyì chéng Yīngwén le.", "en": "This book was translated into English."},
         {"zh": "窗户被风吹开了。", "pinyin": "Chuānghu bèi fēng chuīkāi le.", "en": "The window was blown open by the wind."},
     ]},
    {"name": "是...的 emphasis", "name_zh": "是…的", "hsk_level": 3, "category": "structure",
     "description": "Emphasizing time/place/manner: 我是坐飞机来的", "difficulty": 0.5,
     "examples": [
         {"zh": "我是坐飞机来的。", "pinyin": "Wǒ shì zuò fēijī lái de.", "en": "I came by plane (emphasis on how)."},
         {"zh": "他是昨天到的。", "pinyin": "Tā shì zuótiān dào de.", "en": "He arrived yesterday (emphasis on when)."},
         {"zh": "这本书是在北京买的。", "pinyin": "Zhè běn shū shì zài Běijīng mǎi de.", "en": "This book was bought in Beijing (emphasis on where)."},
     ]},
    {"name": "越来越 increasingly", "name_zh": "越来越", "hsk_level": 3, "category": "comparison",
     "description": "Getting more and more: 天气越来越冷", "difficulty": 0.4,
     "examples": [
         {"zh": "天气越来越冷了。", "pinyin": "Tiānqì yuèláiyuè lěng le.", "en": "The weather is getting colder and colder."},
         {"zh": "他的中文越来越好。", "pinyin": "Tā de Zhōngwén yuèláiyuè hǎo.", "en": "His Chinese is getting better and better."},
         {"zh": "学的东西越来越多。", "pinyin": "Xué de dōngxi yuèláiyuè duō.", "en": "There's more and more to learn."},
         {"zh": "城市越来越大了。", "pinyin": "Chéngshì yuèláiyuè dà le.", "en": "The city is getting bigger and bigger."},
     ]},
    {"name": "又...又 both...and", "name_zh": "又…又", "hsk_level": 3, "category": "structure",
     "description": "Both X and Y: 又便宜又好吃", "difficulty": 0.4,
     "examples": [
         {"zh": "这个菜又便宜又好吃。", "pinyin": "Zhège cài yòu piányi yòu hǎochī.", "en": "This dish is both cheap and tasty."},
         {"zh": "她又聪明又漂亮。", "pinyin": "Tā yòu cōngming yòu piàoliang.", "en": "She is both smart and pretty."},
         {"zh": "今天又热又闷。", "pinyin": "Jīntiān yòu rè yòu mēn.", "en": "Today is both hot and stuffy."},
     ]},
    {"name": "Result complement (到/完/好)", "name_zh": "结果补语", "hsk_level": 3, "category": "complement",
     "description": "Verb + result: 找到、吃完、做好", "difficulty": 0.5,
     "examples": [
         {"zh": "我找到了。", "pinyin": "Wǒ zhǎodào le.", "en": "I found it."},
         {"zh": "作业做完了吗？", "pinyin": "Zuòyè zuòwán le ma?", "en": "Is the homework finished?"},
         {"zh": "饭做好了。", "pinyin": "Fàn zuòhǎo le.", "en": "The food is ready."},
         {"zh": "我没听到。", "pinyin": "Wǒ méi tīngdào.", "en": "I didn't hear it."},
     ]},
    {"name": "Direction complement (来/去/上/下)", "name_zh": "趋向补语", "hsk_level": 3, "category": "complement",
     "description": "Verb + direction: 走进来、跑出去", "difficulty": 0.5,
     "examples": [
         {"zh": "请进来。", "pinyin": "Qǐng jìnlái.", "en": "Please come in."},
         {"zh": "他跑出去了。", "pinyin": "Tā pǎo chūqù le.", "en": "He ran out."},
         {"zh": "把行李拿上来。", "pinyin": "Bǎ xíngli ná shànglái.", "en": "Bring the luggage up."},
         {"zh": "我们走过去吧。", "pinyin": "Wǒmen zǒu guòqù ba.", "en": "Let's walk over."},
     ]},
    {"name": "除了...以外", "name_zh": "除了…以外", "hsk_level": 3, "category": "structure",
     "description": "Besides/except: 除了中文以外，我还学日语", "difficulty": 0.5,
     "examples": [
         {"zh": "除了中文以外，我还学日语。", "pinyin": "Chúle Zhōngwén yǐwài, wǒ hái xué Rìyǔ.", "en": "Besides Chinese, I also study Japanese."},
         {"zh": "除了他以外，大家都来了。", "pinyin": "Chúle tā yǐwài, dàjiā dōu lái le.", "en": "Everyone came except him."},
         {"zh": "除了周末以外，我每天都上班。", "pinyin": "Chúle zhōumò yǐwài, wǒ měitiān dōu shàngbān.", "en": "I work every day except weekends."},
     ]},

    # HSK 4 — complex sentences, compound connectors
    {"name": "虽然...但是 although...but", "name_zh": "虽然…但是", "hsk_level": 4, "category": "connector",
     "description": "Concession: 虽然很累，但是很开心", "difficulty": 0.5,
     "examples": [
         {"zh": "虽然很累，但是很开心。", "pinyin": "Suīrán hěn lèi, dànshì hěn kāixīn.", "en": "Although tired, I'm very happy."},
         {"zh": "虽然下雨了，但是我们还是去了。", "pinyin": "Suīrán xiàyǔ le, dànshì wǒmen háishì qù le.", "en": "Although it rained, we still went."},
         {"zh": "虽然他很年轻，但是经验很丰富。", "pinyin": "Suīrán tā hěn niánqīng, dànshì jīngyàn hěn fēngfù.", "en": "Although he's young, he has rich experience."},
     ]},
    {"name": "不但...而且 not only...but also", "name_zh": "不但…而且", "hsk_level": 4, "category": "connector",
     "description": "Progressive: 不但便宜，而且好吃", "difficulty": 0.5,
     "examples": [
         {"zh": "他不但会说中文，而且会说日语。", "pinyin": "Tā búdàn huì shuō Zhōngwén, érqiě huì shuō Rìyǔ.", "en": "He not only speaks Chinese, but also Japanese."},
         {"zh": "这个地方不但漂亮，而且很安静。", "pinyin": "Zhège dìfang búdàn piàoliang, érqiě hěn ānjìng.", "en": "This place is not only beautiful, but also quiet."},
         {"zh": "她不但聪明，而且很努力。", "pinyin": "Tā búdàn cōngmíng, érqiě hěn nǔlì.", "en": "She is not only smart, but also hardworking."},
     ]},
    {"name": "如果...就 if...then", "name_zh": "如果…就", "hsk_level": 4, "category": "connector",
     "description": "Conditional: 如果下雨就不去了", "difficulty": 0.4,
     "examples": [
         {"zh": "如果明天下雨，我就不去了。", "pinyin": "Rúguǒ míngtiān xiàyǔ, wǒ jiù bú qù le.", "en": "If it rains tomorrow, I won't go."},
         {"zh": "如果你有时间，就来找我吧。", "pinyin": "Rúguǒ nǐ yǒu shíjiān, jiù lái zhǎo wǒ ba.", "en": "If you have time, come find me."},
         {"zh": "如果早知道，我就不会来了。", "pinyin": "Rúguǒ zǎo zhīdào, wǒ jiù bú huì lái le.", "en": "If I had known earlier, I wouldn't have come."},
     ]},
    {"name": "因为...所以 because...therefore", "name_zh": "因为…所以", "hsk_level": 4, "category": "connector",
     "description": "Causal: 因为太忙，所以没去", "difficulty": 0.4,
     "examples": [
         {"zh": "因为堵车，所以迟到了。", "pinyin": "Yīnwèi dǔchē, suǒyǐ chídào le.", "en": "Because of traffic, I was late."},
         {"zh": "因为太贵了，所以我没买。", "pinyin": "Yīnwèi tài guì le, suǒyǐ wǒ méi mǎi.", "en": "Because it was too expensive, I didn't buy it."},
         {"zh": "因为生病了，所以请假了。", "pinyin": "Yīnwèi shēngbìng le, suǒyǐ qǐngjià le.", "en": "Because I was sick, I took leave."},
     ]},
    {"name": "连...都/也 even", "name_zh": "连…都/也", "hsk_level": 4, "category": "structure",
     "description": "Emphasis: 连他都不知道", "difficulty": 0.6,
     "examples": [
         {"zh": "连小孩子都知道。", "pinyin": "Lián xiǎo háizi dōu zhīdào.", "en": "Even children know."},
         {"zh": "他连自己的名字都写不好。", "pinyin": "Tā lián zìjǐ de míngzi dōu xiě bù hǎo.", "en": "He can't even write his own name well."},
         {"zh": "我连一句中文都不会说。", "pinyin": "Wǒ lián yí jù Zhōngwén dōu bú huì shuō.", "en": "I can't even say one sentence in Chinese."},
     ]},
    {"name": "一边...一边 while simultaneously", "name_zh": "一边…一边", "hsk_level": 4, "category": "structure",
     "description": "Simultaneous actions: 一边吃饭一边看电视", "difficulty": 0.4,
     "examples": [
         {"zh": "他一边吃饭一边看电视。", "pinyin": "Tā yìbiān chīfàn yìbiān kàn diànshì.", "en": "He eats while watching TV."},
         {"zh": "我一边走一边想。", "pinyin": "Wǒ yìbiān zǒu yìbiān xiǎng.", "en": "I think while walking."},
         {"zh": "她一边唱歌一边跳舞。", "pinyin": "Tā yìbiān chànggē yìbiān tiàowǔ.", "en": "She sings and dances at the same time."},
     ]},
    {"name": "对...来说 for/regarding", "name_zh": "对…来说", "hsk_level": 4, "category": "structure",
     "description": "Perspective: 对我来说很难", "difficulty": 0.4,
     "examples": [
         {"zh": "对我来说，中文很难。", "pinyin": "Duì wǒ lái shuō, Zhōngwén hěn nán.", "en": "For me, Chinese is hard."},
         {"zh": "对学生来说，这很重要。", "pinyin": "Duì xuéshēng lái shuō, zhè hěn zhòngyào.", "en": "For students, this is important."},
         {"zh": "对外国人来说，中国菜很好吃。", "pinyin": "Duì wàiguórén lái shuō, Zhōngguó cài hěn hǎochī.", "en": "For foreigners, Chinese food is delicious."},
     ]},
    {"name": "既然...就 since...then", "name_zh": "既然…就", "hsk_level": 4, "category": "connector",
     "description": "Since already: 既然来了，就坐一会儿", "difficulty": 0.5,
     "examples": [
         {"zh": "既然来了，就坐一会儿吧。", "pinyin": "Jìrán lái le, jiù zuò yíhuìr ba.", "en": "Since you're here, sit for a while."},
         {"zh": "既然决定了，就不要犹豫。", "pinyin": "Jìrán juédìng le, jiù bú yào yóuyù.", "en": "Since you've decided, don't hesitate."},
         {"zh": "既然你知道了，就帮帮忙吧。", "pinyin": "Jìrán nǐ zhīdào le, jiù bāngbāngmáng ba.", "en": "Since you know, help out."},
     ]},

    # HSK 5 — formal/academic connectors, complex structures
    {"name": "即使...也 even if...also", "name_zh": "即使…也", "hsk_level": 5, "category": "connector",
     "description": "Hypothetical concession: 即使失败也不放弃", "difficulty": 0.6,
     "examples": [
         {"zh": "即使失败了，也不要放弃。", "pinyin": "Jíshǐ shībài le, yě bú yào fàngqì.", "en": "Even if you fail, don't give up."},
         {"zh": "即使很忙，他也坚持锻炼。", "pinyin": "Jíshǐ hěn máng, tā yě jiānchí duànliàn.", "en": "Even if he's busy, he persists in exercising."},
         {"zh": "即使下雨，比赛也会继续。", "pinyin": "Jíshǐ xiàyǔ, bǐsài yě huì jìxù.", "en": "Even if it rains, the match will continue."},
     ]},
    {"name": "不管...都 regardless", "name_zh": "不管…都", "hsk_level": 5, "category": "connector",
     "description": "Unconditional: 不管多难都要试", "difficulty": 0.6,
     "examples": [
         {"zh": "不管多难，我都要试试。", "pinyin": "Bùguǎn duō nán, wǒ dōu yào shìshi.", "en": "No matter how hard, I'll try."},
         {"zh": "不管天气怎样，他都去跑步。", "pinyin": "Bùguǎn tiānqì zěnyàng, tā dōu qù pǎobù.", "en": "Regardless of the weather, he goes running."},
         {"zh": "不管你同不同意，事实就是这样。", "pinyin": "Bùguǎn nǐ tóng bù tóngyì, shìshí jiù shì zhèyàng.", "en": "Whether you agree or not, that's the fact."},
     ]},
    {"name": "与其...不如 rather than...better to", "name_zh": "与其…不如", "hsk_level": 5, "category": "connector",
     "description": "Preference: 与其等待不如行动", "difficulty": 0.7,
     "examples": [
         {"zh": "与其在这里等，不如自己去找。", "pinyin": "Yǔqí zài zhèlǐ děng, bùrú zìjǐ qù zhǎo.", "en": "Rather than wait here, better to go look yourself."},
         {"zh": "与其抱怨，不如想办法解决。", "pinyin": "Yǔqí bàoyuàn, bùrú xiǎng bànfǎ jiějué.", "en": "Rather than complain, better to find a solution."},
         {"zh": "与其浪费时间，不如早点开始。", "pinyin": "Yǔqí làngfèi shíjiān, bùrú zǎodiǎn kāishǐ.", "en": "Rather than waste time, better to start early."},
     ]},
    {"name": "之所以...是因为 the reason...is because", "name_zh": "之所以…是因为", "hsk_level": 5, "category": "connector",
     "description": "Reverse causal: 之所以成功是因为努力", "difficulty": 0.7,
     "examples": [
         {"zh": "他之所以成功，是因为一直在努力。", "pinyin": "Tā zhī suǒyǐ chénggōng, shì yīnwèi yìzhí zài nǔlì.", "en": "The reason he succeeded is because he kept working hard."},
         {"zh": "之所以这么说，是因为我有经验。", "pinyin": "Zhī suǒyǐ zhème shuō, shì yīnwèi wǒ yǒu jīngyàn.", "en": "The reason I say this is because I have experience."},
         {"zh": "她之所以生气，是因为你没告诉她。", "pinyin": "Tā zhī suǒyǐ shēngqì, shì yīnwèi nǐ méi gàosu tā.", "en": "The reason she's angry is because you didn't tell her."},
     ]},
    {"name": "以...为 take...as", "name_zh": "以…为", "hsk_level": 5, "category": "structure",
     "description": "Formal 'take X as Y': 以学生为主", "difficulty": 0.7,
     "examples": [
         {"zh": "课堂应该以学生为主。", "pinyin": "Kètáng yīnggāi yǐ xuéshēng wéi zhǔ.", "en": "The classroom should be student-centered."},
         {"zh": "这个活动以交流为目的。", "pinyin": "Zhège huódòng yǐ jiāoliú wéi mùdì.", "en": "This activity aims at exchange."},
         {"zh": "公司以创新为核心竞争力。", "pinyin": "Gōngsī yǐ chuàngxīn wéi héxīn jìngzhēnglì.", "en": "The company takes innovation as its core competitiveness."},
     ]},

    # HSK 6 — literary/formal structures
    {"name": "何况 let alone", "name_zh": "何况", "hsk_level": 6, "category": "connector",
     "description": "A fortiori: 他都做不到，何况我", "difficulty": 0.7,
     "examples": [
         {"zh": "大人都觉得难，何况孩子呢。", "pinyin": "Dàrén dōu juéde nán, hékuàng háizi ne.", "en": "Adults find it hard, let alone children."},
         {"zh": "这么简单的事他都不会，何况那么难的。", "pinyin": "Zhème jiǎndān de shì tā dōu bú huì, hékuàng nàme nán de.", "en": "He can't even do this simple thing, let alone that hard one."},
         {"zh": "中文都那么难了，何况古文。", "pinyin": "Zhōngwén dōu nàme nán le, hékuàng gǔwén.", "en": "Chinese is already so hard, let alone classical Chinese."},
     ]},
    {"name": "以至于 so much that", "name_zh": "以至于", "hsk_level": 6, "category": "connector",
     "description": "Resultative: 忙得以至于忘了吃饭", "difficulty": 0.7,
     "examples": [
         {"zh": "他太忙了，以至于忘了吃饭。", "pinyin": "Tā tài máng le, yǐzhìyú wàng le chīfàn.", "en": "He was so busy that he forgot to eat."},
         {"zh": "演讲太精彩了，以至于大家都忘了时间。", "pinyin": "Yǎnjiǎng tài jīngcǎi le, yǐzhìyú dàjiā dōu wàng le shíjiān.", "en": "The speech was so brilliant that everyone lost track of time."},
         {"zh": "噪音太大了，以至于我无法集中注意力。", "pinyin": "Zàoyīn tài dà le, yǐzhìyú wǒ wúfǎ jízhōng zhùyìlì.", "en": "The noise was so loud that I couldn't concentrate."},
     ]},
    {"name": "固然...但 admittedly...but", "name_zh": "固然…但", "hsk_level": 6, "category": "connector",
     "description": "Concede-then-counter: 固然重要，但不是唯一的", "difficulty": 0.7,
     "examples": [
         {"zh": "学历固然重要，但能力更重要。", "pinyin": "Xuélì gùrán zhòngyào, dàn nénglì gèng zhòngyào.", "en": "Education matters, but ability matters more."},
         {"zh": "这个方法固然有效，但成本太高。", "pinyin": "Zhège fāngfǎ gùrán yǒuxiào, dàn chéngběn tài gāo.", "en": "This method works, but the cost is too high."},
         {"zh": "经验固然重要，但态度更关键。", "pinyin": "Jīngyàn gùrán zhòngyào, dàn tàidù gèng guānjiàn.", "en": "Experience admittedly matters, but attitude is more key."},
     ]},
    {"name": "就...而言 as far as...concerned", "name_zh": "就…而言", "hsk_level": 6, "category": "structure",
     "description": "Scoping: 就质量而言", "difficulty": 0.7,
     "examples": [
         {"zh": "就质量而言，这个品牌最好。", "pinyin": "Jiù zhìliàng ér yán, zhège pǐnpái zuì hǎo.", "en": "As far as quality goes, this brand is best."},
         {"zh": "就目前情况而言，我们需要更多时间。", "pinyin": "Jiù mùqián qíngkuàng ér yán, wǒmen xūyào gèng duō shíjiān.", "en": "As far as the current situation goes, we need more time."},
         {"zh": "就价格而言，这家店最便宜。", "pinyin": "Jiù jiàgé ér yán, zhè jiā diàn zuì piányi.", "en": "As far as price goes, this shop is cheapest."},
     ]},

    # HSK 7 — advanced formal/literary connectors
    {"name": "不仅...反而 not only not...but instead", "name_zh": "不仅…反而", "hsk_level": 7, "category": "connector",
     "description": "Contrary expectation: 不仅没减少，反而增加了", "difficulty": 0.8,
     "examples": [
         {"zh": "他不仅没道歉，反而更生气了。", "pinyin": "Tā bùjǐn méi dàoqiàn, fǎn'ér gèng shēngqì le.", "en": "He not only didn't apologize, but got even angrier."},
         {"zh": "问题不仅没解决，反而更复杂了。", "pinyin": "Wèntí bùjǐn méi jiějué, fǎn'ér gèng fùzá le.", "en": "The problem not only wasn't solved, it became more complex."},
         {"zh": "成本不仅没降低，反而上升了。", "pinyin": "Chéngběn bùjǐn méi jiàngdī, fǎn'ér shàngshēng le.", "en": "Costs not only didn't decrease, they actually rose."},
     ]},
    {"name": "非但...反而 not only not...but on the contrary", "name_zh": "非但…反而", "hsk_level": 7, "category": "connector",
     "description": "Stronger contrary: 非但不帮忙，反而添乱", "difficulty": 0.8,
     "examples": [
         {"zh": "他非但不帮忙，反而添乱。", "pinyin": "Tā fēidàn bù bāngmáng, fǎn'ér tiānluàn.", "en": "He not only didn't help, but made things worse."},
         {"zh": "非但没有改善，反而恶化了。", "pinyin": "Fēidàn méiyǒu gǎishàn, fǎn'ér èhuà le.", "en": "Not only did it not improve, it deteriorated."},
         {"zh": "她非但不生气，反而笑了起来。", "pinyin": "Tā fēidàn bù shēngqì, fǎn'ér xiào le qǐlái.", "en": "She not only wasn't angry, she actually started laughing."},
     ]},
    {"name": "无论如何 no matter what", "name_zh": "无论如何", "hsk_level": 7, "category": "connector",
     "description": "Absolute unconditional: 无论如何都要完成", "difficulty": 0.7,
     "examples": [
         {"zh": "无论如何，我们都要按时完成。", "pinyin": "Wúlùn rúhé, wǒmen dōu yào ànshí wánchéng.", "en": "No matter what, we must finish on time."},
         {"zh": "无论如何也不能放弃。", "pinyin": "Wúlùn rúhé yě bù néng fàngqì.", "en": "We must not give up no matter what."},
         {"zh": "无论如何，请给我一个机会。", "pinyin": "Wúlùn rúhé, qǐng gěi wǒ yí gè jīhuì.", "en": "No matter what, please give me a chance."},
     ]},
    {"name": "至于 as for / regarding", "name_zh": "至于", "hsk_level": 7, "category": "structure",
     "description": "Topic shift: 至于其他的问题，以后再说", "difficulty": 0.7,
     "examples": [
         {"zh": "至于价格，我们可以再商量。", "pinyin": "Zhìyú jiàgé, wǒmen kěyǐ zài shāngliáng.", "en": "As for the price, we can discuss further."},
         {"zh": "至于他为什么走了，我也不清楚。", "pinyin": "Zhìyú tā wèishéme zǒu le, wǒ yě bù qīngchǔ.", "en": "As for why he left, I'm not sure either."},
         {"zh": "至于结果如何，还要看情况。", "pinyin": "Zhìyú jiéguǒ rúhé, hái yào kàn qíngkuàng.", "en": "As for the outcome, we'll have to see."},
     ]},
    {"name": "从而 thereby / thus", "name_zh": "从而", "hsk_level": 7, "category": "connector",
     "description": "Logical consequence: 改进了方法，从而提高了效率", "difficulty": 0.8,
     "examples": [
         {"zh": "我们改进了方法，从而提高了效率。", "pinyin": "Wǒmen gǎijìn le fāngfǎ, cóng'ér tígāo le xiàolǜ.", "en": "We improved the method, thereby increasing efficiency."},
         {"zh": "他加强了训练，从而取得了好成绩。", "pinyin": "Tā jiāqiáng le xùnliàn, cóng'ér qǔdé le hǎo chéngjì.", "en": "He intensified training, thereby achieving good results."},
         {"zh": "减少了浪费，从而节约了成本。", "pinyin": "Jiǎnshǎo le làngfèi, cóng'ér jiéyuē le chéngběn.", "en": "Reduced waste, thus saving costs."},
     ]},
    {"name": "以免 in order to avoid", "name_zh": "以免", "hsk_level": 7, "category": "connector",
     "description": "Preventive purpose: 早点出发，以免迟到", "difficulty": 0.7,
     "examples": [
         {"zh": "请早点出发，以免迟到。", "pinyin": "Qǐng zǎodiǎn chūfā, yǐmiǎn chídào.", "en": "Please leave early to avoid being late."},
         {"zh": "多带些钱，以免不够用。", "pinyin": "Duō dài xiē qián, yǐmiǎn bú gòu yòng.", "en": "Bring more money to avoid running short."},
         {"zh": "仔细检查，以免出错。", "pinyin": "Zǐxì jiǎnchá, yǐmiǎn chūcuò.", "en": "Check carefully to avoid mistakes."},
     ]},
    {"name": "尽管 despite / even though", "name_zh": "尽管", "hsk_level": 7, "category": "connector",
     "description": "Strong concession: 尽管困难很大，我们还是成功了", "difficulty": 0.7,
     "examples": [
         {"zh": "尽管困难很大，他们还是成功了。", "pinyin": "Jǐnguǎn kùnnan hěn dà, tāmen háishì chénggōng le.", "en": "Despite great difficulty, they still succeeded."},
         {"zh": "尽管下着大雨，比赛照常进行。", "pinyin": "Jǐnguǎn xiàzhe dàyǔ, bǐsài zhàocháng jìnxíng.", "en": "Despite heavy rain, the match continued as scheduled."},
         {"zh": "尽管如此，我仍然支持这个计划。", "pinyin": "Jǐnguǎn rúcǐ, wǒ réngrán zhīchí zhège jìhuà.", "en": "Despite this, I still support the plan."},
     ]},
    {"name": "况且 moreover / besides", "name_zh": "况且", "hsk_level": 7, "category": "connector",
     "description": "Additive reasoning: 时间不够，况且也没准备好", "difficulty": 0.7,
     "examples": [
         {"zh": "时间不够了，况且我们也没准备好。", "pinyin": "Shíjiān bú gòu le, kuàngqiě wǒmen yě méi zhǔnbèi hǎo.", "en": "There's not enough time, besides we're not prepared either."},
         {"zh": "这个方案太贵了，况且效果也不确定。", "pinyin": "Zhège fāng'àn tài guì le, kuàngqiě xiàoguǒ yě bú quèdìng.", "en": "This plan is too expensive, and moreover the effect is uncertain."},
         {"zh": "路太远了，况且天也快黑了。", "pinyin": "Lù tài yuǎn le, kuàngqiě tiān yě kuài hēi le.", "en": "The road is too far, besides it's getting dark."},
     ]},

    # HSK 8 — classical/literary connectors
    {"name": "倘若 if / supposing", "name_zh": "倘若", "hsk_level": 8, "category": "connector",
     "description": "Formal conditional: 倘若失败了怎么办", "difficulty": 0.8,
     "examples": [
         {"zh": "倘若他不同意，我们该怎么办？", "pinyin": "Tǎngruò tā bù tóngyì, wǒmen gāi zěnme bàn?", "en": "Supposing he doesn't agree, what should we do?"},
         {"zh": "倘若一切顺利，我们明天就能完成。", "pinyin": "Tǎngruò yíqiè shùnlì, wǒmen míngtiān jiù néng wánchéng.", "en": "If all goes smoothly, we can finish tomorrow."},
         {"zh": "倘若有机会，我一定去看看。", "pinyin": "Tǎngruò yǒu jīhuì, wǒ yídìng qù kànkan.", "en": "If I had the chance, I would definitely go see."},
     ]},
    {"name": "鉴于 in view of / considering", "name_zh": "鉴于", "hsk_level": 8, "category": "connector",
     "description": "Formal reasoning: 鉴于目前的情况", "difficulty": 0.8,
     "examples": [
         {"zh": "鉴于目前的情况，我们决定推迟。", "pinyin": "Jiànyú mùqián de qíngkuàng, wǒmen juédìng tuīchí.", "en": "In view of the current situation, we decided to postpone."},
         {"zh": "鉴于他的表现，我们给予了表扬。", "pinyin": "Jiànyú tā de biǎoxiàn, wǒmen jǐyǔ le biǎoyáng.", "en": "Considering his performance, we gave him recognition."},
         {"zh": "鉴于以上原因，建议修改方案。", "pinyin": "Jiànyú yǐshàng yuányīn, jiànyì xiūgǎi fāng'àn.", "en": "In view of the above reasons, we recommend revising the plan."},
     ]},
    {"name": "有鉴于此 in light of this", "name_zh": "有鉴于此", "hsk_level": 8, "category": "connector",
     "description": "Formal conclusion marker: 有鉴于此，我们建议…", "difficulty": 0.8,
     "examples": [
         {"zh": "有鉴于此，我们建议重新考虑。", "pinyin": "Yǒu jiànyú cǐ, wǒmen jiànyì chóngxīn kǎolǜ.", "en": "In light of this, we recommend reconsidering."},
         {"zh": "有鉴于此，委员会做出了新的决定。", "pinyin": "Yǒu jiànyú cǐ, wěiyuánhuì zuòchū le xīn de juédìng.", "en": "In light of this, the committee made a new decision."},
         {"zh": "有鉴于此，政策需要做出调整。", "pinyin": "Yǒu jiànyú cǐ, zhèngcè xūyào zuòchū tiáozhěng.", "en": "In light of this, the policy needs adjustment."},
     ]},
    {"name": "纵然 even if / even though", "name_zh": "纵然", "hsk_level": 8, "category": "connector",
     "description": "Literary concession: 纵然失败也不后悔", "difficulty": 0.8,
     "examples": [
         {"zh": "纵然失败，也不后悔。", "pinyin": "Zòngrán shībài, yě bù hòuhuǐ.", "en": "Even if I fail, I won't regret it."},
         {"zh": "纵然困难重重，我们也要前进。", "pinyin": "Zòngrán kùnnan chóngchóng, wǒmen yě yào qiánjìn.", "en": "Even though difficulties are many, we must press forward."},
         {"zh": "纵然他不来，我们也会按计划进行。", "pinyin": "Zòngrán tā bù lái, wǒmen yě huì àn jìhuà jìnxíng.", "en": "Even if he doesn't come, we'll proceed as planned."},
     ]},
    {"name": "不外乎 nothing more than", "name_zh": "不外乎", "hsk_level": 8, "category": "structure",
     "description": "Limiting scope: 原因不外乎两个", "difficulty": 0.8,
     "examples": [
         {"zh": "原因不外乎两个：时间和金钱。", "pinyin": "Yuányīn bùwàihū liǎng gè: shíjiān hé jīnqián.", "en": "The reasons are nothing more than two: time and money."},
         {"zh": "他的爱好不外乎读书和旅行。", "pinyin": "Tā de àihào bùwàihū dúshū hé lǚxíng.", "en": "His hobbies are nothing more than reading and traveling."},
         {"zh": "成功的秘诀不外乎坚持和努力。", "pinyin": "Chénggōng de mìjué bùwàihū jiānchí hé nǔlì.", "en": "The secret to success is nothing more than persistence and effort."},
     ]},
    {"name": "未免 rather / unavoidably", "name_zh": "未免", "hsk_level": 8, "category": "structure",
     "description": "Mild criticism: 这样做未免太草率了", "difficulty": 0.8,
     "examples": [
         {"zh": "这样做未免太草率了。", "pinyin": "Zhèyàng zuò wèimiǎn tài cǎoshuài le.", "en": "Doing it this way is rather hasty."},
         {"zh": "他的要求未免有些过分。", "pinyin": "Tā de yāoqiú wèimiǎn yǒuxiē guòfèn.", "en": "His demands are somewhat excessive."},
         {"zh": "这个解释未免太简单了。", "pinyin": "Zhège jiěshì wèimiǎn tài jiǎndān le.", "en": "This explanation is rather too simplistic."},
     ]},

    # HSK 9 — near-native/classical markers
    {"name": "岂非 isn't it / rhetorical question", "name_zh": "岂非", "hsk_level": 9, "category": "structure",
     "description": "Rhetorical: 岂非自相矛盾", "difficulty": 0.9,
     "examples": [
         {"zh": "这岂非自相矛盾？", "pinyin": "Zhè qǐfēi zìxiāng máodùn?", "en": "Isn't this self-contradictory?"},
         {"zh": "如此处理，岂非本末倒置？", "pinyin": "Rúcǐ chǔlǐ, qǐfēi běnmò dàozhì?", "en": "Handling it this way, isn't that putting the cart before the horse?"},
         {"zh": "放弃努力，岂非前功尽弃？", "pinyin": "Fàngqì nǔlì, qǐfēi qiángōng jìnqì?", "en": "Giving up effort — wouldn't that waste all previous work?"},
     ]},
    {"name": "莫非 could it be that", "name_zh": "莫非", "hsk_level": 9, "category": "structure",
     "description": "Speculative: 莫非他已经知道了", "difficulty": 0.9,
     "examples": [
         {"zh": "莫非他已经知道了？", "pinyin": "Mòfēi tā yǐjīng zhīdào le?", "en": "Could it be that he already knows?"},
         {"zh": "莫非这就是传说中的地方？", "pinyin": "Mòfēi zhè jiùshì chuánshuō zhōng de dìfang?", "en": "Could this be the legendary place?"},
         {"zh": "莫非你不愿意帮忙？", "pinyin": "Mòfēi nǐ bú yuànyì bāngmáng?", "en": "Could it be that you're unwilling to help?"},
     ]},
    {"name": "无非 nothing but / merely", "name_zh": "无非", "hsk_level": 9, "category": "structure",
     "description": "Dismissive: 无非就是想引起注意", "difficulty": 0.8,
     "examples": [
         {"zh": "他这样做无非是想引起注意。", "pinyin": "Tā zhèyàng zuò wúfēi shì xiǎng yǐnqǐ zhùyì.", "en": "He's just doing this to attract attention."},
         {"zh": "无非就是多花点时间而已。", "pinyin": "Wúfēi jiùshì duō huā diǎn shíjiān éryǐ.", "en": "It's merely spending a bit more time, that's all."},
         {"zh": "他的意思无非是让我们小心。", "pinyin": "Tā de yìsi wúfēi shì ràng wǒmen xiǎoxīn.", "en": "His point is merely that we should be careful."},
     ]},
    {"name": "诚然 admittedly / indeed", "name_zh": "诚然", "hsk_level": 9, "category": "connector",
     "description": "Formal concession: 诚然，这有一定道理", "difficulty": 0.9,
     "examples": [
         {"zh": "诚然，这种方法有一定道理。", "pinyin": "Chéngrán, zhè zhǒng fāngfǎ yǒu yídìng dàolǐ.", "en": "Admittedly, this approach has some merit."},
         {"zh": "诚然，改革不是一蹴而就的。", "pinyin": "Chéngrán, gǎigé bú shì yìcù ér jiù de.", "en": "Indeed, reform cannot happen overnight."},
         {"zh": "诚然如此，但我们不能忽视风险。", "pinyin": "Chéngrán rúcǐ, dàn wǒmen bù néng hūshì fēngxiǎn.", "en": "Admittedly so, but we cannot ignore the risks."},
     ]},
    {"name": "姑且 for the time being", "name_zh": "姑且", "hsk_level": 9, "category": "structure",
     "description": "Provisional: 姑且不论对错", "difficulty": 0.8,
     "examples": [
         {"zh": "姑且不论对错，先把事情做完。", "pinyin": "Gūqiě bú lùn duìcuò, xiān bǎ shìqing zuòwán.", "en": "Setting aside right and wrong for now, let's finish the task."},
         {"zh": "我们姑且同意他的方案。", "pinyin": "Wǒmen gūqiě tóngyì tā de fāng'àn.", "en": "Let's agree to his plan for the time being."},
         {"zh": "姑且相信他说的话吧。", "pinyin": "Gūqiě xiāngxìn tā shuō de huà ba.", "en": "Let's take his word for it for now."},
     ]},
]

# Extend with comprehensive HSK 1-9 grammar coverage
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK1_3)
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK4_6)
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK7_9)
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK1_2_R2)
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK3_4_R2)
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK5_6_R2)
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK7_9_R2)
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK1_3_R3)
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK4_5_R3)
GRAMMAR_POINTS.extend(EXTRA_GRAMMAR_HSK6_9_R3)


SKILLS = [
    # Pragmatic skills
    {"name": "ordering food", "category": "pragmatic", "hsk_level": 1,
     "description": "Ordering at restaurants, specifying preferences"},
    {"name": "asking directions", "category": "pragmatic", "hsk_level": 1,
     "description": "Asking for and understanding directions"},
    {"name": "making introductions", "category": "pragmatic", "hsk_level": 1,
     "description": "Introducing yourself and others"},
    {"name": "shopping and bargaining", "category": "pragmatic", "hsk_level": 2,
     "description": "Buying things, asking prices, negotiating"},
    {"name": "making plans", "category": "pragmatic", "hsk_level": 2,
     "description": "Suggesting activities, agreeing on time/place"},
    {"name": "phone conversations", "category": "pragmatic", "hsk_level": 2,
     "description": "Phone etiquette, making appointments"},
    {"name": "expressing complaints", "category": "pragmatic", "hsk_level": 3,
     "description": "Politely expressing dissatisfaction, returning items"},

    # Register skills
    {"name": "casual vs formal greeting", "category": "register", "hsk_level": 1,
     "description": "你好 vs 您好, appropriate greeting selection"},
    {"name": "politeness softening", "category": "register", "hsk_level": 2,
     "description": "Using 请, 麻烦你, 不好意思 appropriately"},
    {"name": "respectful address forms", "category": "register", "hsk_level": 2,
     "description": "Using 您, titles, and respectful forms"},

    # Cultural skills
    {"name": "deflecting compliments", "category": "cultural", "hsk_level": 2,
     "description": "Modest responses to praise: 哪里哪里, 过奖了"},
    {"name": "gift-giving language", "category": "cultural", "hsk_level": 3,
     "description": "Offering/receiving gifts with appropriate modesty"},

    # Phonetic skills
    {"name": "tone pair discrimination", "category": "phonetic", "hsk_level": 1,
     "description": "Distinguishing tone combinations in two-syllable words"},
    {"name": "third tone sandhi", "category": "phonetic", "hsk_level": 2,
     "description": "Recognizing 3-3 → 2-3 tone change patterns"},

    # HSK 4 — pragmatic and professional skills
    {"name": "job interviews", "category": "pragmatic", "hsk_level": 4,
     "description": "Discussing qualifications, experience, and goals"},
    {"name": "explaining reasons", "category": "pragmatic", "hsk_level": 4,
     "description": "Using 因为/所以, 由于 to explain causal relationships"},
    {"name": "news comprehension", "category": "pragmatic", "hsk_level": 4,
     "description": "Understanding and discussing current events"},
    {"name": "formal requests", "category": "register", "hsk_level": 4,
     "description": "Using appropriate formality for official requests"},

    # HSK 5 — academic and professional skills
    {"name": "academic discussion", "category": "pragmatic", "hsk_level": 5,
     "description": "Discussing research, theories, and academic topics"},
    {"name": "business negotiation", "category": "pragmatic", "hsk_level": 5,
     "description": "Negotiating terms, proposing solutions, compromising"},
    {"name": "public speaking", "category": "pragmatic", "hsk_level": 5,
     "description": "Giving presentations and structured arguments"},

    # HSK 6 — advanced communication
    {"name": "formal debate", "category": "pragmatic", "hsk_level": 6,
     "description": "Structured argumentation with evidence and rebuttal"},
    {"name": "diplomatic language", "category": "register", "hsk_level": 6,
     "description": "Hedging, indirect criticism, face-saving expressions"},
    {"name": "humor and irony", "category": "cultural", "hsk_level": 6,
     "description": "Understanding and using humor, sarcasm, and wordplay"},

    # HSK 7 — scholarly and rhetorical
    {"name": "scholarly argumentation", "category": "pragmatic", "hsk_level": 7,
     "description": "Building evidence-based arguments in academic contexts"},
    {"name": "rhetorical persuasion", "category": "pragmatic", "hsk_level": 7,
     "description": "Using rhetorical techniques to convince an audience"},
    {"name": "technical explanation", "category": "pragmatic", "hsk_level": 7,
     "description": "Explaining complex technical concepts clearly"},

    # HSK 8 — literary and cultural mastery
    {"name": "literary analysis", "category": "cultural", "hsk_level": 8,
     "description": "Analyzing literary works, themes, and stylistic devices"},
    {"name": "cultural allusion comprehension", "category": "cultural", "hsk_level": 8,
     "description": "Understanding references to Chinese history, literature, and philosophy"},
    {"name": "register switching", "category": "register", "hsk_level": 8,
     "description": "Fluidly shifting between formal, informal, and literary registers"},

    # HSK 9 — near-native competence
    {"name": "simultaneous interpretation register", "category": "register", "hsk_level": 9,
     "description": "Professional-level register control for interpretation contexts"},
    {"name": "classical Chinese recognition", "category": "cultural", "hsk_level": 9,
     "description": "Recognizing and understanding classical Chinese (文言文) in modern contexts"},
    {"name": "cross-dialectal comprehension", "category": "cultural", "hsk_level": 9,
     "description": "Understanding dialectal influence in standard Mandarin speech"},
]


def seed_grammar_and_skills(conn) -> tuple:
    """Insert seed grammar points and skills. Returns (grammar_added, skills_added)."""
    g_added = 0
    examples_json_data = json.dumps([])
    for gp in GRAMMAR_POINTS:
        examples_json_data = json.dumps(gp.get("examples", []))
        existing = conn.execute(
            "SELECT id FROM grammar_point WHERE name = ?", (gp["name"],)
        ).fetchone()
        if existing:
            # Update examples if they've changed
            conn.execute(
                "UPDATE grammar_point SET examples_json = ? WHERE id = ?",
                (examples_json_data, existing["id"])
            )
            continue
        conn.execute("""
            INSERT INTO grammar_point (name, name_zh, hsk_level, category, description, difficulty, examples_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (gp["name"], gp.get("name_zh"), gp["hsk_level"], gp["category"],
              gp.get("description"), gp.get("difficulty", 0.5), examples_json_data))
        g_added += 1

    s_added = 0
    for sk in SKILLS:
        existing = conn.execute(
            "SELECT id FROM skill WHERE name = ?", (sk["name"],)
        ).fetchone()
        if existing:
            continue
        conn.execute("""
            INSERT INTO skill (name, category, description, hsk_level)
            VALUES (?, ?, ?, ?)
        """, (sk["name"], sk["category"], sk.get("description"), sk["hsk_level"]))
        s_added += 1

    conn.commit()
    return g_added, s_added
