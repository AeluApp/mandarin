#!/usr/bin/env python3
"""Build all 139 HSK5 reading passages and write to passages_hsk5.json"""
import json
import os

passages = []

# ============================================================================
# QUIET OBSERVATION (24 passages): j5_observe_001 - j5_observe_024
# ============================================================================

passages.append({
    "id": "j5_observe_001",
    "title": "The Last Light on the Wall",
    "title_zh": "墙上最后的光",
    "hsk_level": 5,
    "text_zh": "每天傍晚六点左右，对面那栋楼的墙上会出现一小块金色的光。它停留大约十五分钟，然后慢慢地消失。我不知道这束光从哪里来——也许是某扇窗户的反射，也许是某个我看不见的角度。我搬来这里已经三年了，每天都能看到它。有一次我出差回来晚了两天，心里竟然有点担心那块光是不是还在。当然它还在。城市里大部分东西都在变，但这束光好像跟时间没有关系。邻居们大概从来没注意过。也许只有像我这样每天坐在窗前发呆的人，才会把一块光当成老朋友。",
    "text_pinyin": "Mei tian bangwan liu dian zuoyou, duimian na dong lou de qiang shang hui chuxian yi xiao kuai jinse de guang. Ta tingliu dayue shiwu fenzhong, ranhou manman de xiaoshi. Wo bu zhidao zhe shu guang cong nali lai -- yexu shi mou shan chuanghu de fanshe, yexu shi mou ge wo kan bu jian de jiaodu. Wo ban lai zheli yijing san nian le, mei tian dou neng kan dao ta. You yi ci wo chuchai huilai wan le liang tian, xinli jingran youdian danxin na kuai guang shi bu shi hai zai. Dangran ta hai zai. Chengshi li da bufen dongxi dou zai bian, dan zhe shu guang haoxiang gen shijian meiyou guanxi. Linjumen dagai conglai mei zhuyi guo. Yexu zhiyou xiang wo zheyang mei tian zuo zai chuang qian fadai de ren, cai hui ba yi kuai guang dangcheng lao pengyou.",
    "text_en": "Every evening around six, a small patch of golden light appears on the wall of the building across the way. It lingers for about fifteen minutes, then slowly disappears. I don't know where this beam comes from -- perhaps the reflection of some window, perhaps some angle I can't see. I've lived here three years now, and I see it every day. Once I came back from a business trip two days late, and I actually felt a twinge of worry that the patch of light might be gone. Of course it was still there. Most things in the city keep changing, but this beam seems to have nothing to do with time. The neighbors probably never noticed. Maybe only someone like me, who sits by the window spacing out every day, would treat a patch of light like an old friend.",
    "questions": [
        {"type": "mc", "q_zh": "作者为什么会担心那块光？", "q_en": "Why did the author worry about the light?",
         "options": [
             {"text": "因为天气变了", "pinyin": "yinwei tianqi bian le", "text_en": "Because the weather changed", "correct": False},
             {"text": "因为出差回来晚了", "pinyin": "yinwei chuchai huilai wan le", "text_en": "Because returning from a business trip late", "correct": True},
             {"text": "因为对面的楼拆了", "pinyin": "yinwei duimian de lou chai le", "text_en": "Because the opposite building was demolished", "correct": False},
             {"text": "因为邻居告诉他光没了", "pinyin": "yinwei linju gaosu ta guang mei le", "text_en": "Because a neighbor told him the light was gone", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "这篇文章暗示作者是什么样的人？", "q_en": "What kind of person does this passage imply the author is?",
         "options": [
             {"text": "一个忙碌的商人", "pinyin": "yi ge manglu de shangren", "text_en": "A busy businessman", "correct": False},
             {"text": "一个善于观察、内心安静的人", "pinyin": "yi ge shanyu guancha, neixin anjing de ren", "text_en": "An observant, inwardly quiet person", "correct": True},
             {"text": "一个孤独不开心的人", "pinyin": "yi ge gudu bu kaixin de ren", "text_en": "A lonely, unhappy person", "correct": False},
             {"text": "一个喜欢科学研究的人", "pinyin": "yi ge xihuan kexue yanjiu de ren", "text_en": "A person who likes scientific research", "correct": False}
         ], "difficulty": 0.5},
        {"type": "mc", "q_zh": "\"这束光好像跟时间没有关系\"是什么意思？", "q_en": "What does 'this beam seems to have nothing to do with time' mean?",
         "options": [
             {"text": "光永远不会消失", "pinyin": "guang yongyuan bu hui xiaoshi", "text_en": "The light will never disappear", "correct": False},
             {"text": "周围一切在变，光却始终如一", "pinyin": "zhouwei yiqie zai bian, guang que shizhong ruyi", "text_en": "Everything around changes, but the light remains constant", "correct": True},
             {"text": "光出现的时间不固定", "pinyin": "guang chuxian de shijian bu guding", "text_en": "The light appears at irregular times", "correct": False},
             {"text": "作者觉得时间过得太快", "pinyin": "zuozhe juede shijian guo de tai kuai", "text_en": "The author feels time passes too quickly", "correct": False}
         ], "difficulty": 0.5}
    ]
})

passages.append({
    "id": "j5_observe_002",
    "title": "Rain on the Tin Roof",
    "title_zh": "铁皮屋顶上的雨",
    "hsk_level": 5,
    "text_zh": "小时候外婆家的厨房有一个铁皮屋顶。下雨的时候声音特别大，好像有人在上面敲鼓。外婆从来不觉得吵，她说那是老天爷在说话。长大以后我住过很多地方，都是水泥屋顶或者玻璃窗户，雨声被隔得很远。有一年冬天我回去看外婆，刚好下了一场大雨。我站在厨房里，突然觉得那个声音把二十年的距离一下子缩短了。外婆已经走了，厨房也旧了，但雨打铁皮的声音一点都没变。我想，有些记忆不是存在脑子里的，而是存在声音里的。",
    "text_pinyin": "Xiao shihou waipo jia de chufang you yi ge tiepi wuding. Xia yu de shihou shengyin tebie da, haoxiang you ren zai shangmian qiao gu. Waipo conglai bu juede chao, ta shuo na shi laotianye zai shuohua. Zhang da yihou wo zhuguo hen duo difang, dou shi shuini wuding huozhe boli chuanghu, yu sheng bei ge de hen yuan. You yi nian dongtian wo huiqu kan waipo, ganghao xia le yi chang da yu. Wo zhan zai chufang li, turan juede nage shengyin ba ershi nian de juli yixiazi suoduan le. Waipo yijing zou le, chufang ye jiu le, dan yu da tiepi de shengyin yidian dou mei bian. Wo xiang, youxie jiyi bu shi cun zai naozi li de, er shi cun zai shengyin li de.",
    "text_en": "When I was little, the kitchen at my grandmother's house had a tin roof. When it rained the sound was especially loud, as if someone were beating drums up there. Grandma never found it noisy -- she said it was the heavens talking. After I grew up I lived in many places, all concrete roofs or glass windows, the rain muffled far away. One winter I went back to visit Grandma, and it happened to rain heavily. I stood in the kitchen and suddenly felt that sound had collapsed twenty years of distance in an instant. Grandma was already gone, the kitchen had aged, but the sound of rain on tin hadn't changed at all. I think some memories aren't stored in the mind -- they're stored in sound.",
    "questions": [
        {"type": "mc", "q_zh": "外婆怎么看待铁皮屋顶上的雨声？", "q_en": "How did the grandmother view the rain on the tin roof?",
         "options": [
             {"text": "觉得太吵了", "pinyin": "juede tai chao le", "text_en": "Found it too noisy", "correct": False},
             {"text": "觉得是自然的声音，不介意", "pinyin": "juede shi ziran de shengyin, bu jieyi", "text_en": "Saw it as natural sound, didn't mind", "correct": True},
             {"text": "觉得应该换屋顶", "pinyin": "juede yinggai huan wuding", "text_en": "Thought the roof should be replaced", "correct": False},
             {"text": "觉得下雨很危险", "pinyin": "juede xia yu hen weixian", "text_en": "Found rain dangerous", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "\"把二十年的距离一下子缩短了\"是什么意思？", "q_en": "What does 'collapsed twenty years of distance in an instant' mean?",
         "options": [
             {"text": "作者觉得自己变年轻了", "pinyin": "zuozhe juede ziji bian nianqing le", "text_en": "The author felt younger", "correct": False},
             {"text": "熟悉的声音让过去的感觉突然回来了", "pinyin": "shuxi de shengyin rang guoqu de ganjue turan huilai le", "text_en": "A familiar sound brought past feelings rushing back", "correct": True},
             {"text": "作者开车只用了很短的时间", "pinyin": "zuozhe kai che zhi yong le hen duan de shijian", "text_en": "The author drove there in very little time", "correct": False},
             {"text": "外婆家离他现在的家很近", "pinyin": "waipo jia li ta xianzai de jia hen jin", "text_en": "Grandma's house is close to his current home", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "作者最后得出了什么结论？", "q_en": "What conclusion does the author reach?",
         "options": [
             {"text": "老房子应该保留下来", "pinyin": "lao fangzi yinggai baoliu xialai", "text_en": "Old houses should be preserved", "correct": False},
             {"text": "现代建筑隔音太好了", "pinyin": "xiandai jianzhu geyin tai hao le", "text_en": "Modern buildings are too soundproof", "correct": False},
             {"text": "有些记忆是通过声音保存的", "pinyin": "youxie jiyi shi tongguo shengyin baocun de", "text_en": "Some memories are preserved through sound", "correct": True},
             {"text": "人应该多回老家看看", "pinyin": "ren yinggai duo hui laojia kankan", "text_en": "People should visit their hometown more", "correct": False}
         ], "difficulty": 0.3}
    ]
})

passages.append({
    "id": "j5_observe_003",
    "title": "The Cat Who Keeps Hours",
    "title_zh": "守时的猫",
    "hsk_level": 5,
    "text_zh": "楼下便利店门口有一只橘色的猫。它每天早上七点准时出现在门口的台阶上，下午三点左右离开，不知道去哪里。店主说这只猫不是他的，但他每天都给它留一小碗水。附近的人都认识这只猫，有人给它起了名字叫小橘。我观察了几个月，发现小橘的时间比大部分上班族都准。下雨天它会坐在屋檐下面，但从不迟到。有一天小橘没来，整条街的人都在议论。第二天它又出现了，好像什么都没发生。我忽然意识到，一只猫的日常竟然成了一条街的节奏。没有人安排它，但每个人都在不知不觉中依赖它。",
    "text_pinyin": "Lou xia bianli dian menkou you yi zhi juse de mao. Ta mei tian zaoshang qi dian zhunshi chuxian zai menkou de taijie shang, xiawu san dian zuoyou likai, bu zhidao qu nali. Dianzhu shuo zhe zhi mao bu shi ta de, dan ta mei tian dou gei ta liu yi xiao wan shui. Fujin de ren dou renshi zhe zhi mao, you ren gei ta qi le mingzi jiao Xiao Ju. Wo guancha le ji ge yue, faxian Xiao Ju de shijian bi da bufen shangbanzu dou zhun. Xia yu tian ta hui zuo zai wuyan xiamian, dan cong bu chidao. You yi tian Xiao Ju mei lai, zheng tiao jie de ren dou zai yilun. Di-er tian ta you chuxian le, haoxiang shenme dou mei fasheng. Wo huran yishi dao, yi zhi mao de richang jingran cheng le yi tiao jie de jiezou. Meiyou ren anpai ta, dan mei ge ren dou zai buzhi bujue zhong yilai ta.",
    "text_en": "There's an orange cat outside the convenience store downstairs. It appears punctually at seven every morning on the front steps, leaves around three in the afternoon -- no one knows where it goes. The shop owner says the cat isn't his, but he leaves it a small bowl of water every day. Everyone nearby knows this cat; someone named it Little Orange. I observed for months and found Little Orange keeps better time than most office workers. On rainy days it sits under the eaves, but it's never late. One day Little Orange didn't come, and the whole street was talking about it. The next day it appeared again, as if nothing had happened. I suddenly realized that one cat's routine had become the rhythm of an entire street. No one assigned it this role, but everyone had come to depend on it without realizing.",
    "questions": [
        {"type": "mc", "q_zh": "店主和小橘是什么关系？", "q_en": "What is the relationship between the shop owner and Little Orange?",
         "options": [
             {"text": "小橘是店主养的宠物", "pinyin": "Xiao Ju shi dianzhu yang de chongwu", "text_en": "Little Orange is the owner's pet", "correct": False},
             {"text": "店主不认识这只猫", "pinyin": "dianzhu bu renshi zhe zhi mao", "text_en": "The owner doesn't know the cat", "correct": False},
             {"text": "猫不是他的，但他照顾它", "pinyin": "mao bu shi ta de, dan ta zhaogu ta", "text_en": "The cat isn't his, but he looks after it", "correct": True},
             {"text": "店主想把猫赶走", "pinyin": "dianzhu xiang ba mao gan zou", "text_en": "The owner wants to chase the cat away", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "小橘有一天没来，发生了什么？", "q_en": "What happened when Little Orange didn't come one day?",
         "options": [
             {"text": "没有人注意到", "pinyin": "meiyou ren zhuyi dao", "text_en": "Nobody noticed", "correct": False},
             {"text": "街上的人都在讨论这件事", "pinyin": "jie shang de ren dou zai taolun zhe jian shi", "text_en": "People on the street all discussed it", "correct": True},
             {"text": "店主去找猫了", "pinyin": "dianzhu qu zhao mao le", "text_en": "The owner went looking for the cat", "correct": False},
             {"text": "大家觉得猫搬家了", "pinyin": "dajia juede mao banjia le", "text_en": "Everyone thought the cat moved away", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "这篇文章想表达什么？", "q_en": "What is this passage trying to express?",
         "options": [
             {"text": "猫比人更守时", "pinyin": "mao bi ren geng shoushi", "text_en": "Cats are more punctual than people", "correct": False},
             {"text": "人和动物应该互相帮助", "pinyin": "ren he dongwu yinggai huxiang bangzhu", "text_en": "People and animals should help each other", "correct": False},
             {"text": "不起眼的存在可以悄悄成为生活的一部分", "pinyin": "bu qiyan de cunzai keyi qiaoqiao chengwei shenghuo de yi bufen", "text_en": "An unassuming presence can quietly become part of life", "correct": True},
             {"text": "城市里应该多养流浪猫", "pinyin": "chengshi li yinggai duo yang liulang mao", "text_en": "Cities should keep more stray cats", "correct": False}
         ], "difficulty": 0.5}
    ]
})

passages.append({
    "id": "j5_observe_004",
    "title": "The Bench Nobody Sits On",
    "title_zh": "没人坐的长椅",
    "hsk_level": 5,
    "text_zh": "公园东边有一张长椅，位置其实很好，旁边有树，前面能看到湖。但我几乎没见过有人坐在那里。我猜可能是因为它对面有一排更新的椅子，那些椅子旁边有垃圾桶，也离厕所更近。人们的选择往往是实际的，不是浪漫的。有一天傍晚我特意去坐了一下。角度确实很好，风刚好从湖面吹过来，空气里有一种淡淡的泥土味。我在那里坐了半个小时，没有一个人经过。后来我每周都会去坐一次。这件事让我想到，生活中也许有很多被忽略的好位置，只是因为大家都跟着大多数人走，就错过了。",
    "text_pinyin": "Gongyuan dongbian you yi zhang changyi, weizhi qishi hen hao, pangbian you shu, qianmian neng kan dao hu. Dan wo jihu mei jianguo you ren zuo zai nali. Wo cai keneng shi yinwei ta duimian you yi pai geng xin de yizi, naxie yizi pangbian you laji tong, ye li cesuo geng jin. Renmen de xuanze wangwang shi shiji de, bu shi langman de. You yi tian bangwan wo teyi qu zuo le yixia. Jiaodu queshi hen hao, feng ganghao cong humian chui guolai, kongqi li you yi zhong dandan de nitu wei. Wo zai nali zuo le ban ge xiaoshi, meiyou yi ge ren jingguo. Houlai wo mei zhou dou hui qu zuo yi ci. Zhe jian shi rang wo xiang dao, shenghuo zhong yexu you hen duo bei hulue de hao weizhi, zhishi yinwei dajia dou genzhe daduoshu ren zou, jiu cuoguo le.",
    "text_en": "On the east side of the park there's a bench in what's actually a great spot -- trees beside it, a view of the lake ahead. But I've almost never seen anyone sit there. My guess is the row of newer benches opposite, which have trash cans nearby and are closer to the restroom. People's choices tend to be practical, not romantic. One evening I went and sat there deliberately. The angle really was good, the breeze blew right off the lake, and the air had a faint earthy smell. I sat there for half an hour without a single person passing by. After that I started going once a week. It made me think that in life there are probably many good positions being overlooked, just because everyone follows the majority and misses them.",
    "questions": [
        {"type": "mc", "q_zh": "为什么没有人坐那张长椅？", "q_en": "Why does nobody sit on that bench?",
         "options": [
             {"text": "椅子坏了", "pinyin": "yizi huai le", "text_en": "The bench is broken", "correct": False},
             {"text": "对面有更方便的椅子", "pinyin": "duimian you geng fangbian de yizi", "text_en": "There are more convenient benches opposite", "correct": True},
             {"text": "那个位置太危险了", "pinyin": "nage weizhi tai weixian le", "text_en": "That spot is too dangerous", "correct": False},
             {"text": "公园不让人坐那里", "pinyin": "gongyuan bu rang ren zuo nali", "text_en": "The park doesn't allow sitting there", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "\"人们的选择往往是实际的，不是浪漫的\"是什么意思？", "q_en": "What does 'people's choices tend to be practical, not romantic' mean?",
         "options": [
             {"text": "人们不喜欢谈恋爱", "pinyin": "renmen bu xihuan tan lian'ai", "text_en": "People don't like romance", "correct": False},
             {"text": "人们选择方便的东西而不是美好的东西", "pinyin": "renmen xuanze fangbian de dongxi er bu shi meihao de dongxi", "text_en": "People choose what's convenient over what's beautiful", "correct": True},
             {"text": "公园的设计不够浪漫", "pinyin": "gongyuan de sheji bu gou langman", "text_en": "The park design isn't romantic enough", "correct": False},
             {"text": "实际的人比浪漫的人多", "pinyin": "shiji de ren bi langman de ren duo", "text_en": "There are more practical people than romantic ones", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "作者最后的感悟是什么？", "q_en": "What is the author's final insight?",
         "options": [
             {"text": "公园应该把旧椅子换掉", "pinyin": "gongyuan yinggai ba jiu yizi huan diao", "text_en": "The park should replace the old bench", "correct": False},
             {"text": "人应该多去公园散步", "pinyin": "ren yinggai duo qu gongyuan sanbu", "text_en": "People should walk in the park more", "correct": False},
             {"text": "跟着大多数人走可能会错过好东西", "pinyin": "genzhe daduoshu ren zou keneng hui cuoguo hao dongxi", "text_en": "Following the majority might mean missing good things", "correct": True},
             {"text": "一个人待着比跟朋友一起更好", "pinyin": "yi ge ren daizhe bi gen pengyou yiqi geng hao", "text_en": "Being alone is better than being with friends", "correct": False}
         ], "difficulty": 0.4}
    ]
})

passages.append({
    "id": "j5_observe_005",
    "title": "The Smell of Autumn Arriving",
    "title_zh": "秋天到来的气味",
    "hsk_level": 5,
    "text_zh": "我一直觉得秋天是有气味的。不是桂花的香，虽然那也是秋天的标志。我说的是一种更微妙的东西——空气变干的时候，混合着落叶、远处烧什么东西的烟，还有一种说不清楚的凉意。每年大概九月中旬，我会在某个早晨突然闻到这种气味，然后心里想：秋天到了。这个判断跟温度无关，跟日历也无关，完全是鼻子告诉我的。我问过几个朋友，他们都觉得我在说一种不存在的东西。也许每个人感知季节的方式不同。我的秋天从鼻子开始，也许你的秋天从眼睛开始。",
    "text_pinyin": "Wo yizhi juede qiutian shi you qiwei de. Bu shi guihua de xiang, suiran na ye shi qiutian de biaozhi. Wo shuo de shi yi zhong geng weimiao de dongxi -- kongqi bian gan de shihou, hunhe zhe luoye, yuanchu shao shenme dongxi de yan, hai you yi zhong shuo bu qingchu de liangyi. Mei nian dagai jiu yue zhongxun, wo hui zai mou ge zaochen turan wen dao zhe zhong qiwei, ranhou xinli xiang: qiutian dao le. Zhege panduan gen wendu wuguan, gen rili ye wuguan, wanquan shi bizi gaosu wo de. Wo wenguo ji ge pengyou, tamen dou juede wo zai shuo yi zhong bu cunzai de dongxi. Yexu mei ge ren ganzhi jijie de fangshi butong. Wo de qiutian cong bizi kaishi, yexu ni de qiutian cong yanjing kaishi.",
    "text_en": "I've always felt that autumn has a smell. Not osmanthus fragrance, though that's also a marker of autumn. I mean something more subtle -- when the air turns dry, mixed with fallen leaves, smoke from something burning in the distance, and an indescribable coolness. Every year around mid-September, one morning I'll suddenly catch this scent, and think: autumn has arrived. This judgment has nothing to do with temperature, nothing to do with the calendar -- it's purely what my nose tells me. I asked a few friends and they all thought I was describing something that doesn't exist. Perhaps everyone perceives the seasons differently. My autumn starts with the nose; maybe yours starts with the eyes.",
    "questions": [
        {"type": "mc", "q_zh": "作者说的秋天的气味是什么？", "q_en": "What autumn smell is the author describing?",
         "options": [
             {"text": "桂花的香味", "pinyin": "guihua de xiangwei", "text_en": "Osmanthus fragrance", "correct": False},
             {"text": "干燥空气、落叶和烟的混合", "pinyin": "ganzao kongqi, luoye he yan de hunhe", "text_en": "A mix of dry air, fallen leaves, and smoke", "correct": True},
             {"text": "新鲜水果的味道", "pinyin": "xinxian shuiguo de weidao", "text_en": "The smell of fresh fruit", "correct": False},
             {"text": "泥土和雨水的味道", "pinyin": "nitu he yushui de weidao", "text_en": "The smell of earth and rain", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "朋友们对作者的说法有什么反应？", "q_en": "How did friends react to the author's idea?",
         "options": [
             {"text": "完全同意", "pinyin": "wanquan tongyi", "text_en": "Completely agreed", "correct": False},
             {"text": "觉得他在说不存在的东西", "pinyin": "juede ta zai shuo bu cunzai de dongxi", "text_en": "Thought he was describing something nonexistent", "correct": True},
             {"text": "也分享了自己的感受", "pinyin": "ye fenxiang le ziji de ganshou", "text_en": "Also shared their own feelings", "correct": False},
             {"text": "建议他去看医生", "pinyin": "jianyi ta qu kan yisheng", "text_en": "Suggested he see a doctor", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "作者的核心观点是什么？", "q_en": "What is the author's core point?",
         "options": [
             {"text": "秋天是最好的季节", "pinyin": "qiutian shi zui hao de jijie", "text_en": "Autumn is the best season", "correct": False},
             {"text": "嗅觉是最重要的感官", "pinyin": "xiujue shi zui zhongyao de ganguan", "text_en": "Smell is the most important sense", "correct": False},
             {"text": "每个人感知世界的方式不同", "pinyin": "mei ge ren ganzhi shijie de fangshi butong", "text_en": "Everyone perceives the world differently", "correct": True},
             {"text": "现代人已经失去了对自然的感觉", "pinyin": "xiandai ren yijing shiqu le dui ziran de ganjue", "text_en": "Modern people have lost their sense of nature", "correct": False}
         ], "difficulty": 0.4}
    ]
})

passages.append({
    "id": "j5_observe_006",
    "title": "The Window Cleaner",
    "title_zh": "擦窗户的人",
    "hsk_level": 5,
    "text_zh": "办公楼外面有一个擦窗户的工人，每个月来一次。他的工作平台挂在三十层楼外面，风一吹就会轻轻摇晃。我坐在办公桌前看他工作，觉得他的动作特别从容——一块布，一桶水，从左到右，从上到下，非常有节奏。有一次他看到我在看他，朝我笑了一下。我突然觉得很不好意思，好像是我在被观察而不是他。后来我想，也许从他的角度看进来，我们这些坐在电脑前面一动不动的人才是奇怪的风景。他至少能看到天空和整个城市，而我只能看到一个屏幕。谁的世界更大，真的很难说。",
    "text_pinyin": "Bangonglou waimian you yi ge ca chuanghu de gongren, mei ge yue lai yi ci. Ta de gongzuo pingtai gua zai sanshi ceng lou waimian, feng yi chui jiu hui qingqing yaohuang. Wo zuo zai bangongzhuo qian kan ta gongzuo, juede ta de dongzuo tebie congrong -- yi kuai bu, yi tong shui, cong zuo dao you, cong shang dao xia, feichang you jiezou. You yi ci ta kan dao wo zai kan ta, chao wo xiao le yixia. Wo turan juede hen bu hao yisi, haoxiang shi wo zai bei guancha er bu shi ta. Houlai wo xiang, yexu cong ta de jiaodu kan jinlai, women zhexie zuo zai diannao qianmian yi dong bu dong de ren cai shi qiguai de fengjing. Ta zhishao neng kan dao tiankong he zhengge chengshi, er wo zhi neng kan dao yi ge pingmu. Shei de shijie geng da, zhen de hen nan shuo.",
    "text_en": "Outside the office building there's a window cleaner who comes once a month. His work platform hangs outside the thirtieth floor, swaying gently when the wind blows. I watch him work from my desk and find his movements remarkably composed -- one cloth, one bucket, left to right, top to bottom, very rhythmic. Once he noticed me watching and smiled at me. I suddenly felt embarrassed, as if I were the one being observed, not him. Later I thought: maybe from his angle looking in, we who sit motionless before our computers are the strange scenery. He at least gets to see the sky and the whole city, while I can only see a screen. Whose world is bigger is genuinely hard to say.",
    "questions": [
        {"type": "mc", "q_zh": "作者为什么觉得不好意思？", "q_en": "Why did the author feel embarrassed?",
         "options": [
             {"text": "因为他没有认真工作", "pinyin": "yinwei ta meiyou renzhen gongzuo", "text_en": "Because he wasn't working diligently", "correct": False},
             {"text": "因为他意识到自己也在被观察", "pinyin": "yinwei ta yishi dao ziji ye zai bei guancha", "text_en": "Because he realized he was also being observed", "correct": True},
             {"text": "因为他不应该看窗外", "pinyin": "yinwei ta bu yinggai kan chuang wai", "text_en": "Because he shouldn't look out the window", "correct": False},
             {"text": "因为擦窗工人的工作太辛苦了", "pinyin": "yinwei ca chuang gongren de gongzuo tai xinku le", "text_en": "Because the window cleaner's work is too hard", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "作者觉得擦窗工人的动作怎么样？", "q_en": "How does the author describe the window cleaner's movements?",
         "options": [
             {"text": "紧张害怕", "pinyin": "jinzhang haipa", "text_en": "Nervous and afraid", "correct": False},
             {"text": "从容有节奏", "pinyin": "congrong you jiezou", "text_en": "Composed and rhythmic", "correct": True},
             {"text": "慢得让人着急", "pinyin": "man de rang ren zhaoji", "text_en": "Frustratingly slow", "correct": False},
             {"text": "快得看不清", "pinyin": "kuai de kan bu qing", "text_en": "Too fast to see clearly", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "文章最后想说明什么？", "q_en": "What is the passage ultimately getting at?",
         "options": [
             {"text": "办公室工作不如体力劳动", "pinyin": "bangongshi gongzuo buru tili laodong", "text_en": "Office work is worse than physical labor", "correct": False},
             {"text": "擦窗户的人比白领更快乐", "pinyin": "ca chuanghu de ren bi bailing geng kuaile", "text_en": "Window cleaners are happier than white-collar workers", "correct": False},
             {"text": "看问题的角度不同，结论也不同", "pinyin": "kan wenti de jiaodu butong, jielun ye butong", "text_en": "Different perspectives lead to different conclusions", "correct": True},
             {"text": "高层建筑的工作很危险", "pinyin": "gaoceng jianzhu de gongzuo hen weixian", "text_en": "Working on tall buildings is dangerous", "correct": False}
         ], "difficulty": 0.4}
    ]
})

passages.append({
    "id": "j5_observe_007",
    "title": "The Old Man at the Bus Stop",
    "title_zh": "公交站的老人",
    "hsk_level": 5,
    "text_zh": "每天早上我等公交车的时候，都会看到一个老人坐在站台的椅子上。他从来不上车，也不看手机，就是安安静静地坐在那里，看着来来往往的人。一开始我以为他在等人，后来发现他只是喜欢看。有一次我没忍住问他：您在等谁？他笑着说：不等谁，就是看看。退休以后没什么事，在家里太安静了，到这里来看看人，听听声音，感觉自己还在这个世界上。他的话让我想了很久。我们每天都急着赶路，从来没想过，对有些人来说，只是看着别人赶路就已经是一种参与了。",
    "text_pinyin": "Mei tian zaoshang wo deng gongjiao che de shihou, dou hui kan dao yi ge laoren zuo zai zhantai de yizi shang. Ta conglai bu shang che, ye bu kan shouji, jiu shi anan jingjing de zuo zai nali, kanzhe lai lai wang wang de ren. Yi kaishi wo yiwei ta zai deng ren, houlai faxian ta zhishi xihuan kan. You yi ci wo mei renzhu wen ta: nin zai deng shei? Ta xiaozhe shuo: bu deng shei, jiu shi kankan. Tuixiu yihou mei shenme shi, zai jia li tai anjing le, dao zheli lai kankan ren, tingting shengyin, ganjue ziji hai zai zhege shijie shang. Ta de hua rang wo xiang le hen jiu. Women mei tian dou jizhe ganlu, conglai mei xiangguo, dui youxie ren lai shuo, zhishi kanzhe bieren ganlu jiu yijing shi yi zhong canyu le.",
    "text_en": "Every morning while I wait for the bus, I see an old man sitting on a bench at the stop. He never gets on the bus, never looks at a phone, just sits there quietly watching people come and go. At first I thought he was waiting for someone, but later I realized he just likes to watch. Once I couldn't help asking: who are you waiting for? He smiled and said: no one, just watching. After retirement there's nothing much to do, it's too quiet at home. Coming here to watch people, hear the sounds -- it makes me feel I'm still part of this world. His words stayed with me a long time. We rush through every day, never thinking that for some people, just watching others rush is already a form of participation.",
    "questions": [
        {"type": "mc", "q_zh": "老人为什么每天来公交站？", "q_en": "Why does the old man come to the bus stop every day?",
         "options": [
             {"text": "等公交车去公园", "pinyin": "deng gongjiao che qu gongyuan", "text_en": "To wait for the bus to the park", "correct": False},
             {"text": "等他的孩子", "pinyin": "deng ta de haizi", "text_en": "To wait for his children", "correct": False},
             {"text": "想感受人群的存在", "pinyin": "xiang ganshou renqun de cunzai", "text_en": "To feel the presence of people", "correct": True},
             {"text": "那个位置很舒服", "pinyin": "nage weizhi hen shufu", "text_en": "That spot is comfortable", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "老人说\"感觉自己还在这个世界上\"反映了什么？", "q_en": "What does the old man's saying 'feel I'm still part of this world' reflect?",
         "options": [
             {"text": "他的身体不太好", "pinyin": "ta de shenti bu tai hao", "text_en": "His health isn't great", "correct": False},
             {"text": "退休后容易感到被社会隔离", "pinyin": "tuixiu hou rongyi gandao bei shehui geli", "text_en": "After retirement it's easy to feel socially isolated", "correct": True},
             {"text": "他对现代社会不满意", "pinyin": "ta dui xiandai shehui bu manyi", "text_en": "He's dissatisfied with modern society", "correct": False},
             {"text": "他想找一份新工作", "pinyin": "ta xiang zhao yi fen xin gongzuo", "text_en": "He wants to find a new job", "correct": False}
         ], "difficulty": 0.5},
        {"type": "mc", "q_zh": "作者从这件事学到了什么？", "q_en": "What did the author learn from this?",
         "options": [
             {"text": "退休以后应该多出门", "pinyin": "tuixiu yihou yinggai duo chumen", "text_en": "One should go out more after retirement", "correct": False},
             {"text": "年轻人应该多关心老人", "pinyin": "nianqing ren yinggai duo guanxin laoren", "text_en": "Young people should care more about the elderly", "correct": False},
             {"text": "观看也是一种参与生活的方式", "pinyin": "guankan ye shi yi zhong canyu shenghuo de fangshi", "text_en": "Watching is also a way of participating in life", "correct": True},
             {"text": "公交站应该有更多椅子", "pinyin": "gongjiao zhan yinggai you geng duo yizi", "text_en": "Bus stops should have more seats", "correct": False}
         ], "difficulty": 0.4}
    ]
})

passages.append({
    "id": "j5_observe_008",
    "title": "Shadows at Noon",
    "title_zh": "正午的影子",
    "hsk_level": 5,
    "text_zh": "中午十二点的时候，影子最短。我在阳台上看楼下的行人，发现他们的影子几乎完全缩在脚底下，好像每个人都在踩着自己的秘密。到了下午四五点，影子就拉得很长，一个人能在地上投出两米多的黑色轮廓。我觉得影子这个东西很有意思：它永远跟着你，但你几乎从来不看它。只有在特定的光线下，你才会注意到它的存在。人和人之间可能也是这样。有些关系你一直拥有，但直到某个特别的时刻，你才突然发现它一直都在。也许生活中最可靠的东西，就是那些你从来不去想的东西。",
    "text_pinyin": "Zhongwu shi'er dian de shihou, yingzi zui duan. Wo zai yangtai shang kan louxia de xingren, faxian tamen de yingzi jihu wanquan suo zai jiao dixia, haoxiang mei ge ren dou zai caizhe ziji de mimi. Dao le xiawu si wu dian, yingzi jiu la de hen chang, yi ge ren neng zai di shang touchu liang mi duo de heise lunkuo. Wo juede yingzi zhege dongxi hen you yisi: ta yongyuan genzhe ni, dan ni jihu conglai bu kan ta. Zhiyou zai teding de guangxian xia, ni cai hui zhuyi dao ta de cunzai. Ren he ren zhijian keneng ye shi zheyang. Youxie guanxi ni yizhi yongyou, dan zhidao mou ge tebie de shike, ni cai turan faxian ta yizhi dou zai. Yexu shenghuo zhong zui kekao de dongxi, jiu shi naxie ni conglai bu qu xiang de dongxi.",
    "text_en": "At noon, shadows are shortest. I watch pedestrians below from my balcony and notice their shadows shrunk almost entirely beneath their feet, as if everyone is stepping on their own secrets. By four or five in the afternoon, shadows stretch long -- a person can cast a black silhouette over two meters on the ground. I find shadows interesting: they follow you forever, but you almost never look at them. Only under certain light do you notice they exist. Relationships between people may be the same way. Some connections you always have, but not until a particular moment do you suddenly realize they were there all along. Perhaps life's most reliable things are the ones you never think about.",
    "questions": [
        {"type": "mc", "q_zh": "中午的影子有什么特点？", "q_en": "What characterizes noon shadows?",
         "options": [
             {"text": "最长", "pinyin": "zui chang", "text_en": "Longest", "correct": False},
             {"text": "最短", "pinyin": "zui duan", "text_en": "Shortest", "correct": True},
             {"text": "消失了", "pinyin": "xiaoshi le", "text_en": "They disappear", "correct": False},
             {"text": "颜色最深", "pinyin": "yanse zui shen", "text_en": "Darkest in color", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "\"好像每个人都在踩着自己的秘密\"用了什么修辞手法？", "q_en": "What rhetorical device is used in 'as if everyone is stepping on their own secrets'?",
         "options": [
             {"text": "夸张", "pinyin": "kuazhang", "text_en": "Exaggeration", "correct": False},
             {"text": "比喻", "pinyin": "biyu", "text_en": "Metaphor", "correct": True},
             {"text": "反复", "pinyin": "fanfu", "text_en": "Repetition", "correct": False},
             {"text": "对比", "pinyin": "duibi", "text_en": "Contrast", "correct": False}
         ], "difficulty": 0.4},
        {"type": "mc", "q_zh": "作者把影子比作什么？", "q_en": "What does the author compare shadows to?",
         "options": [
             {"text": "秘密", "pinyin": "mimi", "text_en": "Secrets", "correct": False},
             {"text": "时间的流逝", "pinyin": "shijian de liushi", "text_en": "The passage of time", "correct": False},
             {"text": "被忽略但一直存在的关系", "pinyin": "bei hulue dan yizhi cunzai de guanxi", "text_en": "Relationships that are overlooked but always present", "correct": True},
             {"text": "孤独的感觉", "pinyin": "gudu de ganjue", "text_en": "The feeling of loneliness", "correct": False}
         ], "difficulty": 0.5}
    ]
})

passages.append({
    "id": "j5_observe_009",
    "title": "The Sound Between Songs",
    "title_zh": "歌曲之间的声音",
    "hsk_level": 5,
    "text_zh": "我喜欢听现场音乐会，但不是因为音乐本身——当然音乐很好——而是因为歌曲之间那几秒钟的安静。全场几千个人，在那几秒钟里一起沉默，一起等待。那种安静不是空的，而是满的，充满了刚才音乐留下的震动。有一次我旁边坐的人在那个安静的瞬间轻轻叹了一口气，我觉得那声叹气比任何一首歌都真实。录音里听不到这些。你可以完美地录下每一个音符，但录不下几千个人同时屏住呼吸的感觉。现场和录音的区别，也许就在那几秒钟的空白里。",
    "text_pinyin": "Wo xihuan ting xianchang yinyuehui, dan bu shi yinwei yinyue benshen -- dangran yinyue hen hao -- er shi yinwei gequ zhijian na ji miao zhong de anjing. Quanchang ji qian ge ren, zai na ji miao zhong li yiqi chenmo, yiqi dengdai. Na zhong anjing bu shi kong de, er shi man de, chongman le gangcai yinyue liuxia de zhendong. You yi ci wo pangbian zuo de ren zai nage anjing de shunjian qingqing tan le yi kou qi, wo juede na sheng tanqi bi renhe yi shou ge dou zhenshi. Luyin li ting bu dao zhexie. Ni keyi wanmei de lu xia mei yi ge yinfu, dan lu bu xia ji qian ge ren tongshi pingzhu huxi de ganjue. Xianchang he luyin de qubie, yexu jiu zai na ji miao zhong de kongbai li.",
    "text_en": "I like attending live concerts, not for the music itself -- the music is of course wonderful -- but for those few seconds of silence between songs. Several thousand people, in those few seconds, all fall silent together, all wait together. That kind of silence isn't empty but full, brimming with the vibration the music just left behind. Once the person sitting next to me let out a soft sigh during one of those quiet moments, and I felt that sigh was more real than any song. You can't hear these things in recordings. You can perfectly capture every note, but you can't capture the feeling of thousands of people holding their breath at the same time. The difference between live and recorded may lie entirely in those few seconds of blank space.",
    "questions": [
        {"type": "mc", "q_zh": "作者最喜欢音乐会的什么部分？", "q_en": "What part of concerts does the author like most?",
         "options": [
             {"text": "音乐本身", "pinyin": "yinyue benshen", "text_en": "The music itself", "correct": False},
             {"text": "歌曲之间的安静时刻", "pinyin": "gequ zhijian de anjing shike", "text_en": "The quiet moments between songs", "correct": True},
             {"text": "观众的欢呼声", "pinyin": "guanzhong de huanhu sheng", "text_en": "The audience's cheering", "correct": False},
             {"text": "现场的灯光效果", "pinyin": "xianchang de dengguang xiaoguo", "text_en": "The stage lighting effects", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "\"那种安静不是空的，而是满的\"是什么意思？", "q_en": "What does 'that silence isn't empty but full' mean?",
         "options": [
             {"text": "现场太挤了", "pinyin": "xianchang tai ji le", "text_en": "The venue was too crowded", "correct": False},
             {"text": "沉默中包含着共同的情感体验", "pinyin": "chenmo zhong baohan zhe gongtong de qinggan tiyan", "text_en": "The silence contains a shared emotional experience", "correct": True},
             {"text": "有些人在小声说话", "pinyin": "youxie ren zai xiao sheng shuohua", "text_en": "Some people were whispering", "correct": False},
             {"text": "音响效果很好", "pinyin": "yinxiang xiaoguo hen hao", "text_en": "The sound system was excellent", "correct": False}
         ], "difficulty": 0.5},
        {"type": "mc", "q_zh": "作者认为现场和录音的区别在哪里？", "q_en": "Where does the author see the difference between live and recorded?",
         "options": [
             {"text": "音质不同", "pinyin": "yinzhi butong", "text_en": "Sound quality differs", "correct": False},
             {"text": "录音可以反复听", "pinyin": "luyin keyi fanfu ting", "text_en": "Recordings can be replayed", "correct": False},
             {"text": "现场有录不下来的集体感受", "pinyin": "xianchang you lu bu xialai de jiti ganshou", "text_en": "Live shows have collective feelings that can't be recorded", "correct": True},
             {"text": "现场的歌手唱得更好", "pinyin": "xianchang de geshou chang de geng hao", "text_en": "Singers perform better live", "correct": False}
         ], "difficulty": 0.4}
    ]
})

passages.append({
    "id": "j5_observe_010",
    "title": "The Bookshop That Never Opens",
    "title_zh": "从不开门的书店",
    "hsk_level": 5,
    "text_zh": "我家附近有一间书店，门上写着营业时间是上午十点到晚上八点，但我经过无数次，从来没见它开过门。橱窗里的书一直是同样的几本，封面已经被太阳晒得变了颜色。有一次我看到一个女人从里面走出来，手里拿着一把钥匙。我问她书店还开不开，她说：开啊，只是不是每天都开。我又问她什么时候开，她想了想说：心情好的时候。然后她锁上门走了。我觉得这大概是世界上最诚实的商业模式了。在一个所有东西都要求效率的时代，有人经营一家只在心情好的时候营业的书店，这件事本身就让我觉得安心。",
    "text_pinyin": "Wo jia fujin you yi jian shudian, men shang xiezhe yingye shijian shi shangwu shi dian dao wanshang ba dian, dan wo jingguo wushu ci, conglai mei jian ta kaiguo men. Chuchuang li de shu yizhi shi tongyang de ji ben, fengmian yijing bei taiyang shai de bian le yanse. You yi ci wo kan dao yi ge nuren cong limian zou chulai, shou li nazhe yi ba yaoshi. Wo wen ta shudian hai kai bu kai, ta shuo: kai a, zhishi bu shi mei tian dou kai. Wo you wen ta shenme shihou kai, ta xiang le xiang shuo: xinqing hao de shihou. Ranhou ta suoshang men zou le. Wo juede zhe dagai shi shijie shang zui chengshi de shangye moshi le. Zai yi ge suoyou dongxi dou yaoqiu xiaolv de shidai, you ren jingying yi jia zhi zai xinqing hao de shihou yingye de shudian, zhe jian shi benshen jiu rang wo juede anxin.",
    "text_en": "Near my home there's a bookshop. The door says hours are 10 AM to 8 PM, but I've passed it countless times and never seen it open. The same few books sit in the window, their covers faded by the sun. Once I saw a woman walk out with a key in her hand. I asked if the bookshop still opens. She said: of course, just not every day. I asked when it opens. She thought about it and said: when I'm in a good mood. Then she locked the door and left. I think this is probably the most honest business model in the world. In an era that demands efficiency from everything, someone running a bookshop that only opens when she feels like it -- the mere fact of this is reassuring to me.",
    "questions": [
        {"type": "mc", "q_zh": "书店有什么奇怪的地方？", "q_en": "What's strange about the bookshop?",
         "options": [
             {"text": "卖的书很贵", "pinyin": "mai de shu hen gui", "text_en": "The books are expensive", "correct": False},
             {"text": "虽然写了营业时间但几乎不开门", "pinyin": "suiran xie le yingye shijian dan jihu bu kai men", "text_en": "Despite posted hours, it almost never opens", "correct": True},
             {"text": "没有店主", "pinyin": "meiyou dianzhu", "text_en": "There's no shopkeeper", "correct": False},
             {"text": "只卖一种书", "pinyin": "zhi mai yi zhong shu", "text_en": "Only sells one type of book", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "店主说什么时候开门？", "q_en": "When does the owner say the shop opens?",
         "options": [
             {"text": "每天上午十点", "pinyin": "mei tian shangwu shi dian", "text_en": "Every day at 10 AM", "correct": False},
             {"text": "周末", "pinyin": "zhoumo", "text_en": "Weekends", "correct": False},
             {"text": "心情好的时候", "pinyin": "xinqing hao de shihou", "text_en": "When she's in a good mood", "correct": True},
             {"text": "有客人来的时候", "pinyin": "you keren lai de shihou", "text_en": "When customers come", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "作者为什么觉得这家书店让他安心？", "q_en": "Why does the bookshop reassure the author?",
         "options": [
             {"text": "因为书很便宜", "pinyin": "yinwei shu hen pianyi", "text_en": "Because the books are cheap", "correct": False},
             {"text": "因为它代表了一种不追求效率的生活态度", "pinyin": "yinwei ta daibiao le yi zhong bu zhuiqiu xiaolv de shenghuo taidu", "text_en": "It represents a life attitude that doesn't chase efficiency", "correct": True},
             {"text": "因为店主很友好", "pinyin": "yinwei dianzhu hen youhao", "text_en": "Because the owner is friendly", "correct": False},
             {"text": "因为他喜欢那些旧书", "pinyin": "yinwei ta xihuan naxie jiu shu", "text_en": "Because he likes those old books", "correct": False}
         ], "difficulty": 0.5}
    ]
})

passages.append({
    "id": "j5_observe_011",
    "title": "First Snow, No One Mentions It",
    "title_zh": "初雪，没人提起",
    "hsk_level": 5,
    "text_zh": "今年第一场雪下在一个工作日的下午。我抬头看到窗外飘着雪花，心里有一种小小的激动。但我环顾办公室，没有一个人站起来看窗外。大家都在看屏幕，手指在键盘上快速移动。我想说一句\"下雪了\"，但张了张嘴又觉得不合适——好像在工作时间提起天气是一种浪费。那场雪只下了二十分钟就停了。等大家下班的时候，地上已经干了，什么痕迹都没有留下。也许我是办公室里唯一看到那场雪的人。这让我有一种奇怪的孤独感——不是因为没有人陪我，而是因为一件美好的事情发生了，却没有被任何人分享。",
    "text_pinyin": "Jinnian di-yi chang xue xia zai yi ge gongzuori de xiawu. Wo taitou kan dao chuang wai piaozhe xuehua, xinli you yi zhong xiaoxiao de jidong. Dan wo huangu bangongshi, meiyou yi ge ren zhanqilai kan chuang wai. Dajia dou zai kan pingmu, shouzhi zai jianpan shang kuaisu yidong. Wo xiang shuo yi ju 'xia xue le', dan zhang le zhang zui you juede bu heshi -- haoxiang zai gongzuo shijian tiqi tianqi shi yi zhong langfei. Na chang xue zhi xia le ershi fenzhong jiu ting le. Deng dajia xiaban de shihou, di shang yijing gan le, shenme henji dou meiyou liuxia. Yexu wo shi bangongshi li weiyi kan dao na chang xue de ren. Zhe rang wo you yi zhong qiguai de gudu gan -- bu shi yinwei meiyou ren pei wo, er shi yinwei yi jian meihao de shiqing fasheng le, que meiyou bei renhe ren fenxiang.",
    "text_en": "This year's first snow fell on a workday afternoon. I looked up and saw snowflakes drifting outside the window, feeling a small thrill. But I glanced around the office -- not one person stood up to look outside. Everyone was watching their screens, fingers moving fast on keyboards. I wanted to say 'it's snowing,' but opened my mouth and felt it wasn't appropriate -- as if mentioning the weather during work hours were some kind of waste. The snow lasted only twenty minutes. By the time everyone left work, the ground was already dry, no trace left. Maybe I was the only one in the office who saw that snow. It gave me a strange kind of loneliness -- not because no one was with me, but because something beautiful happened and wasn't shared by anyone.",
    "questions": [
        {"type": "mc", "q_zh": "作者为什么没有说\"下雪了\"？", "q_en": "Why didn't the author say 'it's snowing'?",
         "options": [
             {"text": "他不喜欢雪", "pinyin": "ta bu xihuan xue", "text_en": "He doesn't like snow", "correct": False},
             {"text": "觉得在工作时间提天气不合适", "pinyin": "juede zai gongzuo shijian ti tianqi bu heshi", "text_en": "Felt mentioning weather during work was inappropriate", "correct": True},
             {"text": "他不想打扰别人", "pinyin": "ta bu xiang darao bieren", "text_en": "He didn't want to disturb others", "correct": False},
             {"text": "他以为大家都看到了", "pinyin": "ta yiwei dajia dou kan dao le", "text_en": "He assumed everyone saw it", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "那场雪有什么特别之处？", "q_en": "What was special about that snowfall?",
         "options": [
             {"text": "下得特别大", "pinyin": "xia de tebie da", "text_en": "It was very heavy", "correct": False},
             {"text": "很短暂，没留下任何痕迹", "pinyin": "hen duanzan, mei liuxia renhe henji", "text_en": "Very brief, left no trace", "correct": True},
             {"text": "是十年来的第一场雪", "pinyin": "shi shi nian lai de di-yi chang xue", "text_en": "First snow in ten years", "correct": False},
             {"text": "把交通都堵住了", "pinyin": "ba jiaotong dou duzhu le", "text_en": "It blocked all traffic", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "作者感到的孤独是什么性质的？", "q_en": "What kind of loneliness did the author feel?",
         "options": [
             {"text": "没有朋友的孤独", "pinyin": "meiyou pengyou de gudu", "text_en": "Loneliness of having no friends", "correct": False},
             {"text": "美好经历无人分享的孤独", "pinyin": "meihao jingli wu ren fenxiang de gudu", "text_en": "Loneliness of a beautiful experience shared by no one", "correct": True},
             {"text": "工作太多的孤独", "pinyin": "gongzuo tai duo de gudu", "text_en": "Loneliness of overwork", "correct": False},
             {"text": "想家的孤独", "pinyin": "xiangjia de gudu", "text_en": "Homesickness", "correct": False}
         ], "difficulty": 0.5}
    ]
})

passages.append({
    "id": "j5_observe_012",
    "title": "The Leaking Faucet",
    "title_zh": "漏水的水龙头",
    "hsk_level": 5,
    "text_zh": "厨房的水龙头开始漏水了，不严重，大概两三秒一滴。白天的时候完全听不到，因为有各种其他声音盖住了。但到了深夜，整个房子安静下来以后，那个滴答声变得非常清楚。一开始我觉得很烦，睡不着觉。但几个星期以后，我居然习惯了。更奇怪的是，有一天水管工来修好了以后，那天晚上我反而觉得太安静了，好像少了什么东西。我这才明白，我已经不知不觉地把那个小缺陷当成了生活的一部分。完美并不总是让人舒服的，有时候一个小小的不完美反而让空间变得更真实。",
    "text_pinyin": "Chufang de shuilongtou kaishi lou shui le, bu yanzhong, dagai liang san miao yi di. Baitian de shihou wanquan ting bu dao, yinwei you ge zhong qita shengyin gaizhu le. Dan dao le shenye, zhengge fangzi anjing xialai yihou, nage dida sheng bian de feichang qingchu. Yi kaishi wo juede hen fan, shui bu zhao jiao. Dan ji ge xingqi yihou, wo jingran xiguan le. Geng qiguai de shi, you yi tian shuiguangong lai xiu hao le yihou, na tian wanshang wo fan'er juede tai anjing le, haoxiang shao le shenme dongxi. Wo zhe cai mingbai, wo yijing buzhi bujue de ba nage xiao quexian dangcheng le shenghuo de yi bufen. Wanmei bing bu zongshi rang ren shufu de, youshihou yi ge xiaoxiao de bu wanmei fan'er rang kongjian bian de geng zhenshi.",
    "text_en": "The kitchen faucet started leaking -- not badly, about one drip every two or three seconds. During the day you can't hear it at all because other sounds cover it. But late at night, after the whole house goes quiet, the dripping becomes perfectly clear. At first I found it annoying and couldn't sleep. But after a few weeks I'd actually gotten used to it. Stranger still, the day the plumber came and fixed it, that night I felt it was too quiet, as if something were missing. Only then did I understand: I had unconsciously made that small flaw part of my life. Perfection isn't always comfortable. Sometimes a small imperfection actually makes a space feel more real.",
    "questions": [
        {"type": "mc", "q_zh": "水龙头修好以后作者有什么感觉？", "q_en": "How did the author feel after the faucet was fixed?",
         "options": [
             {"text": "终于可以好好睡觉了", "pinyin": "zhongyu keyi haohao shuijiao le", "text_en": "Finally could sleep well", "correct": False},
             {"text": "觉得太安静了，好像少了什么", "pinyin": "juede tai anjing le, haoxiang shao le shenme", "text_en": "Felt it was too quiet, as if something was missing", "correct": True},
             {"text": "很高兴水费可以省了", "pinyin": "hen gaoxing shuifei keyi sheng le", "text_en": "Happy to save on the water bill", "correct": False},
             {"text": "没有任何感觉", "pinyin": "meiyou renhe ganjue", "text_en": "Felt nothing", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "为什么白天听不到滴水声？", "q_en": "Why can't the dripping be heard during the day?",
         "options": [
             {"text": "白天不漏水", "pinyin": "baitian bu lou shui", "text_en": "It doesn't leak during the day", "correct": False},
             {"text": "被其他声音盖住了", "pinyin": "bei qita shengyin gaizhu le", "text_en": "Other sounds cover it up", "correct": True},
             {"text": "水龙头关着", "pinyin": "shuilongtou guanzhe", "text_en": "The faucet is off", "correct": False},
             {"text": "白天人不在家", "pinyin": "baitian ren bu zai jia", "text_en": "No one is home during the day", "correct": False}
         ], "difficulty": 0.3},
        {"type": "mc", "q_zh": "这篇文章想表达什么道理？", "q_en": "What idea does this passage convey?",
         "options": [
             {"text": "应该及时修理东西", "pinyin": "yinggai jishi xiuli dongxi", "text_en": "Fix things promptly", "correct": False},
             {"text": "习惯是可怕的", "pinyin": "xiguan shi kepa de", "text_en": "Habit is frightening", "correct": False},
             {"text": "不完美有时候比完美更让人觉得真实舒适", "pinyin": "bu wanmei youshihou bi wanmei geng rang ren juede zhenshi shushi", "text_en": "Imperfection sometimes feels more real and comfortable than perfection", "correct": True},
             {"text": "夜晚太安静不好", "pinyin": "yewan tai anjing bu hao", "text_en": "Nights that are too quiet are bad", "correct": False}
         ], "difficulty": 0.4}
    ]
})

# Save progress so far and print count
output_path = "/Users/jasongerson/mandarin/content_gen/passages_hsk5.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(passages, f, ensure_ascii=False, indent=2)
print(f"Saved {len(passages)} passages")
