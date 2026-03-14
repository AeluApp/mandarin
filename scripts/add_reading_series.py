#!/usr/bin/env python3
"""
Add 10-episode narrative reading series: 小雨's New City (小雨的新城市)
HSK 1 vocabulary only for episodes 1-5, HSK 1-2 for episodes 6-10.
"""

import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "reading_passages.json"

SERIES_EPISODES = [
    {
        "id": "series1_ep1",
        "title": "Arriving at the Train Station",
        "title_zh": "到了火车站",
        "hsk_level": 1,
        "series": "xiayu_city",
        "episode": 1,
        "text_zh": (
            "小雨今天坐火车来了。她一个人到了这个大城市。"
            "火车站里人很多。她不认识这里的人。"
            "她想：我的新家在哪里？她看了看手里的电话。"
            "明天，她要去看房子。"
        ),
        "text_pinyin": (
            "Xiǎoyǔ jīntiān zuò huǒchē lái le. Tā yí gè rén dàole zhège dà chéngshì. "
            "Huǒchēzhàn lǐ rén hěn duō. Tā bú rènshi zhèlǐ de rén. "
            "Tā xiǎng: wǒ de xīn jiā zài nǎlǐ? Tā kànle kàn shǒu lǐ de diànhuà. "
            "Míngtiān, tā yào qù kàn fángzi."
        ),
        "text_en": (
            "Xiaoyu arrived by train today. She came to this big city alone. "
            "There are many people in the train station. She doesn't know anyone here. "
            "She thinks: where is my new home? She looked at the phone in her hand. "
            "Tomorrow, she will go look at apartments."
        ),
        "questions": [
            {
                "q_zh": "小雨怎么来的？",
                "q_en": "How did Xiaoyu get here?",
                "answer": "坐火车"
            },
            {
                "q_zh": "她在这个城市认识人吗？",
                "q_en": "Does she know anyone in this city?",
                "answer": "不认识"
            }
        ]
    },
    {
        "id": "series1_ep2",
        "title": "Looking for an Apartment",
        "title_zh": "找房子",
        "hsk_level": 1,
        "series": "xiayu_city",
        "episode": 2,
        "text_zh": (
            "小雨去看了三个房子。第一个太小了。第二个太贵了。"
            "第三个很好——有大房间，也不太贵。"
            "住在左边的人叫王大姐。王大姐说：“你好！你是新来的吗？"
            "小雨很高兴，她在这里有朋友了。下个星期，王大姐想请她吃饭。"
        ),
        "text_pinyin": (
            "Xiǎoyǔ qù kànle sān gè fángzi. Dì yī gè tài xiǎo le. Dì èr gè tài guì le. "
            "Dì sān gè hěn hǎo — yǒu dà fángjiān, yě bú tài guì. "
            "Zhù zài zuǒbian de rén jiào Wáng Dàjiě. Wáng Dàjiě shuō: 'Nǐ hǎo! Nǐ shì xīn lái de ma?' "
            "Xiǎoyǔ hěn gāoxìng, tā zài zhèlǐ yǒu péngyou le. Xià ge xīngqī, Wáng Dàjiě xiǎng qǐng tā chīfàn."
        ),
        "text_en": (
            "Xiaoyu went to see three apartments. The first was too small. The second was too expensive. "
            "The third was great — it has a big room, and it's not too expensive. "
            "The person living on the left is called Sister Wang. Sister Wang said: 'Hello! Are you new here?' "
            "Xiaoyu is happy — she has a friend here now. Next week, Sister Wang wants to invite her for dinner."
        ),
        "questions": [
            {
                "q_zh": "小雨看了几个房子？",
                "q_en": "How many apartments did Xiaoyu look at?",
                "answer": "三个"
            },
            {
                "q_zh": "住在左边的人叫什么？",
                "q_en": "What is the neighbor on the left called?",
                "answer": "王大姐"
            }
        ]
    },
    {
        "id": "series1_ep3",
        "title": "Finding a Good Restaurant",
        "title_zh": "找到好饭店",
        "hsk_level": 1,
        "series": "xiayu_city",
        "episode": 3,
        "text_zh": (
            "今天小雨出去走了走。这个城市很大，东西也很多。"
            "她走到一个小饭店前面。里面的菜很好吃，也不贵。"
            "她吃了一个菜、喝了一杯茶。饭店的人很好，对她说：“欢迎你下次再来！”"
            "回家的时候，她在商店买了一些水。明天她想去看看书店。"
        ),
        "text_pinyin": (
            "Jīntiān Xiǎoyǔ chūqù zǒule zǒu. Zhège chéngshì hěn dà, dōngxi yě hěn duō. "
            "Tā zǒu dào yí gè xiǎo fàndiàn qiánmiàn. Lǐmiàn de cài hěn hǎochī, yě bú guì. "
            "Tā chīle yí gè cài, hēle yì bēi chá. Fàndiàn de rén hěn hǎo, duì tā shuō: 'Huānyíng nǐ xià cì zài lái!' "
            "Huí jiā de shíhou, tā zài shāngdiàn mǎile yìxiē shuǐ. Míngtiān tā xiǎng qù kànkan shūdiàn."
        ),
        "text_en": (
            "Today Xiaoyu went out for a walk. This city is big, with lots of things. "
            "She walked to a small restaurant. The food inside was delicious and not expensive. "
            "She ate a dish and drank a cup of tea. The restaurant people were nice, saying: 'Welcome back next time!' "
            "On the way home, she bought some water at a shop. Tomorrow she wants to check out a bookstore."
        ),
        "questions": [
            {
                "q_zh": "饭店的菜怎么样？",
                "q_en": "How was the restaurant food?",
                "answer": "很好吃"
            },
            {
                "q_zh": "她明天想去哪里？",
                "q_en": "Where does she want to go tomorrow?",
                "answer": "书店"
            }
        ]
    },
    {
        "id": "series1_ep4",
        "title": "The Bookstore",
        "title_zh": "在书店",
        "hsk_level": 1,
        "series": "xiayu_city",
        "episode": 4,
        "text_zh": (
            "小雨来到了书店。书店很大，书也很多。"
            "她在看一本书的时候，一个人对她说：“你好，你也喜欢这本书吗？”"
            "他叫李明，是这个城市的大学老师。他们说了很多话。"
            "李明说他有一个朋友住在医院。小雨说：“他怎么了？”"
            "李明没有说。他看了看时间，走了。"
        ),
        "text_pinyin": (
            "Xiǎoyǔ lái dào le shūdiàn. Shūdiàn hěn dà, shū yě hěn duō. "
            "Tā zài kàn yì běn shū de shíhou, yí gè rén duì tā shuō: 'Nǐ hǎo, nǐ yě xǐhuan zhè běn shū ma?' "
            "Tā jiào Lǐ Míng, shì zhège chéngshì de dàxué lǎoshī. Tāmen shuōle hěn duō huà. "
            "Lǐ Míng shuō tā yǒu yí gè péngyou zhù zài yīyuàn. Xiǎoyǔ shuō: 'Tā zěnme le?' "
            "Lǐ Míng méiyǒu shuō. Tā kànle kàn shíjiān, zǒu le."
        ),
        "text_en": (
            "Xiaoyu arrived at the bookstore. The bookstore is big, with many books. "
            "While she was looking at a book, someone said to her: 'Hello, do you like this book too?' "
            "His name is Li Ming, a university teacher in this city. They talked a lot. "
            "Li Ming said he has a friend staying at the hospital. Xiaoyu asked: 'What happened to him?' "
            "Li Ming didn't say. He looked at the time and left."
        ),
        "questions": [
            {
                "q_zh": "李明是做什么工作的？",
                "q_en": "What does Li Ming do?",
                "answer": "大学老师"
            },
            {
                "q_zh": "李明的朋友在哪里？",
                "q_en": "Where is Li Ming's friend?",
                "answer": "医院"
            }
        ]
    },
    {
        "id": "series1_ep5",
        "title": "Where Is the Hospital?",
        "title_zh": "医院在哪里？",
        "hsk_level": 1,
        "series": "xiayu_city",
        "episode": 5,
        "text_zh": (
            "小雨想去医院看看李明的朋友。可是她不知道医院在哪里。"
            "她问了一个人：“请问，医院在哪里？”那个人说：“往前走，在右边。”"
            "她走了很长时间，可是没看到医院。她又问了一个人。"
            "那个人说：“不对，医院在左边，不在右边！”"
            "天快黑了。小雨的电话响了——是李明打来的。他说：“你快来医院！”"
        ),
        "text_pinyin": (
            "Xiǎoyǔ xiǎng qù yīyuàn kànkan Lǐ Míng de péngyou. Kěshì tā bù zhīdào yīyuàn zài nǎlǐ. "
            "Tā wènle yí gè rén: 'Qǐngwèn, yīyuàn zài nǎlǐ?' Nàge rén shuō: 'Wǎng qián zǒu, zài yòubian.' "
            "Tā zǒule hěn cháng shíjiān, kěshì méi kàn dào yīyuàn. Tā yòu wènle yí gè rén. "
            "Nàge rén shuō: 'Bú duì, yīyuàn zài zuǒbian, bú zài yòubian!' "
            "Tiān kuài hēi le. Xiǎoyǔ de diànhuà xiǎng le — shì Lǐ Míng dǎ lái de. Tā shuō: 'Nǐ kuài lái yīyuàn!'"
        ),
        "text_en": (
            "Xiaoyu wants to go to the hospital to visit Li Ming's friend. But she doesn't know where the hospital is. "
            "She asked someone: 'Excuse me, where is the hospital?' The person said: 'Go straight, it's on the right.' "
            "She walked for a long time but didn't see the hospital. She asked another person. "
            "That person said: 'No, the hospital is on the left, not the right!' "
            "It's getting dark. Xiaoyu's phone rang — it was Li Ming calling. He said: 'Come to the hospital quickly!'"
        ),
        "questions": [
            {
                "q_zh": "小雨为什么找不到医院？",
                "q_en": "Why couldn't Xiaoyu find the hospital?",
                "answer": "第一个人说错了"
            },
            {
                "q_zh": "谁给小雨打电话了？",
                "q_en": "Who called Xiaoyu?",
                "answer": "李明"
            }
        ]
    },
    {
        "id": "series1_ep6",
        "title": "At the Hospital",
        "title_zh": "在医院",
        "hsk_level": 2,
        "series": "xiayu_city",
        "episode": 6,
        "text_zh": (
            "小雨到了医院。李明在门口等她。"
            "李明说：“我的朋友叫小陈，他上个星期生病了，现在好多了。”"
            "小雨见到了小陈，他笑着说：“谢谢你来看我！”"
            "小陈告诉她，他下个星期就能离开医院了。"
            "小雨很高兴。离开医院以后，李明问她：“你周末有空吗？我想带你去市场买东西。”"
        ),
        "text_pinyin": (
            "Xiǎoyǔ dào le yīyuàn. Lǐ Míng zài ménkǒu děng tā. "
            "Lǐ Míng shuō: 'Wǒ de péngyou jiào Xiǎo Chén, tā shàng ge xīngqī shēngbìng le, xiànzài hǎo duō le.' "
            "Xiǎoyǔ jiàn dào le Xiǎo Chén, tā xiàozhe shuō: 'Xièxie nǐ lái kàn wǒ!' "
            "Xiǎo Chén gàosu tā, tā xià ge xīngqī jiù néng líkāi yīyuàn le. "
            "Xiǎoyǔ hěn gāoxìng. Líkāi yīyuàn yǐhòu, Lǐ Míng wèn tā: 'Nǐ zhōumò yǒu kòng ma? Wǒ xiǎng dài nǐ qù shìchǎng mǎi dōngxi.'"
        ),
        "text_en": (
            "Xiaoyu arrived at the hospital. Li Ming was waiting for her at the entrance. "
            "Li Ming said: 'My friend is called Xiao Chen. He got sick last week, but he's much better now.' "
            "Xiaoyu met Xiao Chen, who said with a smile: 'Thank you for coming to see me!' "
            "Xiao Chen told her he can leave the hospital next week. "
            "Xiaoyu was happy. After leaving the hospital, Li Ming asked: 'Are you free this weekend? I want to take you to the market to buy things.'"
        ),
        "questions": [
            {
                "q_zh": "小陈怎么了？",
                "q_en": "What happened to Xiao Chen?",
                "answer": "他生病了"
            },
            {
                "q_zh": "李明周末想带小雨去哪里？",
                "q_en": "Where does Li Ming want to take Xiaoyu this weekend?",
                "answer": "市场"
            }
        ]
    },
    {
        "id": "series1_ep7",
        "title": "Learning to Bargain",
        "title_zh": "学会买东西",
        "hsk_level": 2,
        "series": "xiayu_city",
        "episode": 7,
        "text_zh": (
            "周末到了，李明带小雨去了市场。市场里什么都有。"
            "小雨想买一些水果。她问：“苹果多少钱一斤？”"
            "卖水果的人说：“十块。”李明小声说：“太贵了，你说五块。”"
            "小雨说：“五块可以吗？”那个人笑了：“七块吧。”小雨说：“好！”"
            "小雨买了很多东西。她觉得很开心。回家以后，她想自己做饭。"
        ),
        "text_pinyin": (
            "Zhōumò dào le, Lǐ Míng dài Xiǎoyǔ qùle shìchǎng. Shìchǎng lǐ shénme dōu yǒu. "
            "Xiǎoyǔ xiǎng mǎi yìxiē shuǐguǒ. Tā wèn: 'Píngguǒ duōshao qián yì jīn?' "
            "Mài shuǐguǒ de rén shuō: 'Shí kuài.' Lǐ Míng xiǎo shēng shuō: 'Tài guì le, nǐ shuō wǔ kuài.' "
            "Xiǎoyǔ shuō: 'Wǔ kuài kěyǐ ma?' Nàge rén xiào le: 'Qī kuài ba.' Xiǎoyǔ shuō: 'Hǎo!' "
            "Xiǎoyǔ mǎile hěn duō dōngxi. Tā juéde hěn kāixīn. Huí jiā yǐhòu, tā xiǎng zìjǐ zuòfàn."
        ),
        "text_en": (
            "The weekend arrived, and Li Ming took Xiaoyu to the market. The market has everything. "
            "Xiaoyu wanted to buy some fruit. She asked: 'How much are apples per jin?' "
            "The fruit seller said: 'Ten yuan.' Li Ming whispered: 'Too expensive — say five.' "
            "Xiaoyu said: 'Can you do five?' The person laughed: 'How about seven?' Xiaoyu said: 'Deal!' "
            "Xiaoyu bought lots of things. She felt very happy. After getting home, she wanted to cook by herself."
        ),
        "questions": [
            {
                "q_zh": "苹果最后多少钱一斤？",
                "q_en": "How much were the apples per jin in the end?",
                "answer": "七块"
            },
            {
                "q_zh": "回家以后小雨想做什么？",
                "q_en": "What does Xiaoyu want to do after getting home?",
                "answer": "自己做饭"
            }
        ]
    },
    {
        "id": "series1_ep8",
        "title": "Cooking for the First Time",
        "title_zh": "第一次做饭",
        "hsk_level": 2,
        "series": "xiayu_city",
        "episode": 8,
        "text_zh": (
            "小雨决定做一个西红柿炒鸡蛋。这是最简单的中国菜。"
            "她先洗了西红柿，然后打了三个鸡蛋。"
            "可是她放了太多盐，菜太咸了！她又做了一次，这次好多了。"
            "王大姐闻到了，过来说：“好香啊！明天是我的生日，你能来吗？”"
            "小雨说：“当然可以！我要带什么？”"
        ),
        "text_pinyin": (
            "Xiǎoyǔ juédìng zuò yí gè xīhóngshì chǎo jīdàn. Zhè shì zuì jiǎndān de Zhōngguó cài. "
            "Tā xiān xǐle xīhóngshì, ránhòu dǎle sān gè jīdàn. "
            "Kěshì tā fàngle tài duō yán, cài tài xián le! Tā yòu zuòle yí cì, zhè cì hǎo duō le. "
            "Wáng Dàjiě wén dào le, guòlái shuō: 'Hǎo xiāng a! Míngtiān shì wǒ de shēngrì, nǐ néng lái ma?' "
            "Xiǎoyǔ shuō: 'Dāngrán kěyǐ! Wǒ yào dài shénme?'"
        ),
        "text_en": (
            "Xiaoyu decided to make tomato scrambled eggs. This is the simplest Chinese dish. "
            "She first washed the tomatoes, then cracked three eggs. "
            "But she added too much salt — it was too salty! She made it again, and this time it was much better. "
            "Sister Wang smelled it and came over: 'Smells great! Tomorrow is my birthday — can you come?' "
            "Xiaoyu said: 'Of course! What should I bring?'"
        ),
        "questions": [
            {
                "q_zh": "小雨做了什么菜？",
                "q_en": "What dish did Xiaoyu make?",
                "answer": "西红柿炒鸡蛋"
            },
            {
                "q_zh": "明天是谁的生日？",
                "q_en": "Whose birthday is tomorrow?",
                "answer": "王大姐的"
            }
        ]
    },
    {
        "id": "series1_ep9",
        "title": "The Birthday Party",
        "title_zh": "生日聚会",
        "hsk_level": 2,
        "series": "xiayu_city",
        "episode": 9,
        "text_zh": (
            "王大姐的生日聚会来了很多人。小雨做了西红柿炒鸡蛋带过去。"
            "李明和小陈也来了。小陈已经出院了，身体好多了。"
            "大家一起吃饭、唱歌、说笑话。小雨觉得这些人就像家人一样。"
            "李明问她：“你喜欢这个城市吗？”小雨笑了，没有说话。"
            "晚上回家的路上，她看着这个城市的灯光，心里想了很多。"
        ),
        "text_pinyin": (
            "Wáng Dàjiě de shēngrì jùhuì lái le hěn duō rén. Xiǎoyǔ zuòle xīhóngshì chǎo jīdàn dài guòqù. "
            "Lǐ Míng hé Xiǎo Chén yě lái le. Xiǎo Chén yǐjīng chūyuàn le, shēntǐ hǎo duō le. "
            "Dàjiā yìqǐ chīfàn, chàng gē, shuō xiàohua. Xiǎoyǔ juéde zhèxiē rén jiù xiàng jiārén yíyàng. "
            "Lǐ Míng wèn tā: 'Nǐ xǐhuan zhège chéngshì ma?' Xiǎoyǔ xiào le, méiyǒu shuōhuà. "
            "Wǎnshang huí jiā de lùshang, tā kànzhe zhège chéngshì de dēngguāng, xīnlǐ xiǎngle hěn duō."
        ),
        "text_en": (
            "Many people came to Sister Wang's birthday party. Xiaoyu brought her tomato scrambled eggs. "
            "Li Ming and Xiao Chen came too. Xiao Chen had already left the hospital and was feeling much better. "
            "Everyone ate, sang, and told jokes together. Xiaoyu felt these people were like family. "
            "Li Ming asked her: 'Do you like this city?' Xiaoyu smiled but didn't answer. "
            "On the way home that night, she looked at the city lights and thought about many things."
        ),
        "questions": [
            {
                "q_zh": "小雨带了什么去聚会？",
                "q_en": "What did Xiaoyu bring to the party?",
                "answer": "西红柿炒鸡蛋"
            },
            {
                "q_zh": "小陈的身体怎么样了？",
                "q_en": "How is Xiao Chen's health now?",
                "answer": "好多了"
            }
        ]
    },
    {
        "id": "series1_ep10",
        "title": "This Is Home Now",
        "title_zh": "这里就是家",
        "hsk_level": 2,
        "series": "xiayu_city",
        "episode": 10,
        "text_zh": (
            "小雨的妈妈打电话问她：“你什么时候回来？”"
            "小雨想了想。她想到了王大姐、李明、小陈，想到了那个好吃的小饭店。"
            "她想到了市场、书店、还有她自己做的菜。"
            "她说：“妈妈，我很喜欢这里。这里已经是我的家了。"
            "你和爸爸什么时候来看我？“"
            "妈妈笑了：“好，我们下个月来！”"
        ),
        "text_pinyin": (
            "Xiǎoyǔ de māma dǎ diànhuà wèn tā: 'Nǐ shénme shíhou huílái?' "
            "Xiǎoyǔ xiǎngle xiǎng. Tā xiǎng dào le Wáng Dàjiě, Lǐ Míng, Xiǎo Chén, xiǎng dào le nàge hǎochī de xiǎo fàndiàn. "
            "Tā xiǎng dào le shìchǎng, shūdiàn, háiyǒu tā zìjǐ zuò de cài. "
            "Tā shuō: 'Māma, wǒ hěn xǐhuan zhèlǐ. Zhèlǐ yǐjīng shì wǒ de jiā le. "
            "Nǐ hé bàba shénme shíhou lái kàn wǒ?' "
            "Māma xiào le: 'Hǎo, wǒmen xià ge yuè lái!'"
        ),
        "text_en": (
            "Xiaoyu's mom called and asked: 'When are you coming back?' "
            "Xiaoyu thought about it. She thought of Sister Wang, Li Ming, Xiao Chen, and that delicious little restaurant. "
            "She thought of the market, the bookstore, and the food she cooked herself. "
            "She said: 'Mom, I really like it here. This is already my home. "
            "When will you and dad come visit me?' "
            "Mom laughed: 'Okay, we'll come next month!'"
        ),
        "questions": [
            {
                "q_zh": "小雨的妈妈问她什么？",
                "q_en": "What did Xiaoyu's mom ask her?",
                "answer": "什么时候回来"
            },
            {
                "q_zh": "小雨觉得这个城市是什么？",
                "q_en": "What does Xiaoyu feel this city is?",
                "answer": "她的家"
            }
        ]
    },
]


def main():
    # Read existing data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Check for duplicate IDs
    existing_ids = {p["id"] for p in data["passages"]}
    for ep in SERIES_EPISODES:
        if ep["id"] in existing_ids:
            print(f"WARNING: id '{ep['id']}' already exists — skipping")
        else:
            data["passages"].append(ep)
            print(f"Added {ep['id']}: {ep['title']}")

    # Save
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Total passages: {len(data['passages'])}")


if __name__ == "__main__":
    main()
