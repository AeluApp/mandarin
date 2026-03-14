#!/usr/bin/env python3
"""Edit comedy passages to follow comedy standard: compress, single mechanism, end on image/action."""

import json

def fix_hsk8():
    with open('passages_hsk8.json', 'r') as f:
        data = json.load(f)

    for p in data:
        if p['id'] == 'j8_comedy_001':
            p['text_zh'] = (
                "我粗略统计过，在过去五年的职业生涯中，我参加的会议里至少有百分之六十"
                "可以用一封三行的邮件替代。典型的无效会议有一套固定的剧本：首先，组织者"
                "会提前十五分钟发一个模糊的议题，比如「讨论一下下季度的方向」，这种议题"
                "的信息量约等于「我们聊聊天吧」。其次，会议开始后的头五分钟用于等待迟到"
                "的人，这五分钟里已到场的人假装看手机，实则在计算这次迟到将浪费多少人的"
                "多少小时。然后进入正题——如果它存在的话。通常的情况是，说话时间的分配"
                "遵循一条隐形的权力曲线：职位最高的人说得最多，但信息密度最低；真正掌握"
                "关键数据的人往往在最后三分钟才被点名发言。会议结束时，组织者总结道：「那"
                "我们下次再详细讨论。」这句话翻译成人话就是：「这次会议什么结论也没达成。」"
                "散会后，两个人在走廊里站了三十秒，把会上一小时没解决的问题解决了。"
            )
            p['text_en'] = (
                "By rough count, at least sixty percent of the meetings I've attended over "
                "my five-year career could have been replaced by a three-line email. The typical "
                "ineffective meeting follows a fixed script: first, the organizer sends a vague "
                "agenda fifteen minutes in advance, something like 'discuss next quarter's "
                "direction'—an agenda whose information content roughly equals 'let's chat.' "
                "Next, the first five minutes after the meeting starts are spent waiting for "
                "latecomers, during which those already present pretend to look at their phones "
                "while actually calculating how many person-hours this tardiness will waste. "
                "Then comes the main topic—if it exists. Usually, speaking time is distributed "
                "along an invisible power curve: the highest-ranking person speaks the most but "
                "with the lowest information density; the person who actually holds the key data "
                "typically isn't called on until the last three minutes. When the meeting ends, "
                "the organizer summarizes: 'Let's discuss this in more detail next time.' "
                "Translated into plain language: 'This meeting reached no conclusion whatsoever.' "
                "After the meeting, two people stood in the hallway for thirty seconds and solved "
                "what the meeting failed to solve in an hour."
            )

        elif p['id'] == 'j8_comedy_002':
            p['text_zh'] = (
                "我们小区的业主微信群有四百七十二人，理论上是用来讨论物业管理事务的。"
                "实际上，它更像是一部连续剧，每天都有新剧情。最经典的分歧发生在养狗问题"
                "上。养狗的业主和不养狗的业主之间的对立，其激烈程度堪比任何政治辩论。一方"
                "认为狗是家庭成员，另一方认为狗粪是公共卫生事件。双方在群里你来我往，论据"
                "从个人经历升级到法律条款，再到人性哲学，最后以互相拉黑告终。但无论昨晚群"
                "里吵得多凶，每天早上七号楼的王大妈都会准时发一句「早安，今天天气不错」，"
                "配一张她在小区花园拍的花。她从来不参与任何争论。她的早安总能让大家暂时忘记"
                "恩怨。后来有人说：「这个群不需要管理员，需要的是王大妈。」"
            )
            p['text_en'] = (
                "Our compound's homeowner WeChat group has 472 members. In theory it's for "
                "discussing property management matters. In practice, it's more like a TV drama "
                "with new plot developments every day. The most classic conflict concerns the dog "
                "issue. The opposition between dog owners and non-dog-owners rivals any political "
                "debate in intensity. One side considers dogs family members; the other considers "
                "dog droppings a public health incident. They go back and forth in the group, "
                "arguments escalating from personal experience to legal clauses to the philosophy "
                "of human nature, ultimately ending in mutual blocking. But no matter how fierce "
                "the fighting was the night before, every morning Auntie Wang from Building 7 "
                "posts: 'Good morning, nice weather today,' accompanied by a photo of flowers "
                "she took in the compound garden. She never participates in any argument. Her "
                "good-morning always makes everyone temporarily forget their grudges. Someone "
                "eventually said: 'This group doesn't need an admin—it needs Auntie Wang.'"
            )

    with open('passages_hsk8.json', 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Fixed passages_hsk8.json")


def fix_hsk9():
    with open('passages_hsk9.json', 'r') as f:
        data = json.load(f)

    for p in data:
        if p['id'] == 'j9_comedy_001':
            p['text_zh'] = (
                "我们小区曾经成立过一个「绿化委员会」，由七位退休业主组成，每月开一次会，"
                "讨论小区内的树木花草事务。第一次会议的核心议题是：三号楼前的那棵银杏树在"
                "秋天掉落的白果气味太大，有业主投诉。委员们讨论了三个方案：一、砍树；二、"
                "摇树让果子提前掉完；三、什么都不做但发一封告业主书解释银杏果有药用价值。"
                "投票结果是四比二比一，选了第三方案。但争论并没有结束，因为负责起草告业主书"
                "的委员老钱写了一篇两千字的文章，从银杏的进化史讲到中药的药理学，被其他"
                "委员批评「太长了，没人会看」。最终由秘书杨阿姨改写成三行字：「银杏果有"
                "药用价值。味道是暂时的。请理解。」最精彩的一次会议发生在春天。有人提议在"
                "小区空地上种樱花树，理由是「日本的樱花很美」。这个提议立刻引发了激烈的"
                "争论——不是关于美学的，而是关于国族情感的。赵叔坚持应该种梅花，因为"
                "「梅花才是中国的精神」；张阿姨说应该种桃树，因为「桃子可以吃，樱花能吃"
                "吗」。最终的折中方案是种了一棵海棠——理由是海棠既有中国传统审美的典雅，"
                "又不涉及任何政治敏感性，而且「海棠花开的时候很好看，落了以后不臭」。"
            )
            p['text_en'] = (
                "Our compound once established a 'Greening Committee,' composed of seven retired "
                "homeowners, meeting monthly to discuss the community's trees and plants. The "
                "first meeting's core agenda item: the ginkgo tree in front of Building 3 drops "
                "fruit in autumn whose smell is too strong; residents complained. The committee "
                "discussed three proposals: 1) cut the tree down; 2) shake it to make the fruit "
                "fall early; 3) do nothing but issue a letter to homeowners explaining ginkgo "
                "fruit has medicinal value. The vote was 4-2-1 in favor of the third option. But "
                "the debate didn't end, because Committee Member Old Qian, tasked with drafting "
                "the letter, wrote a two-thousand-character essay spanning the evolutionary "
                "history of ginkgo to the pharmacology of traditional Chinese medicine. Other "
                "members criticized it as 'too long—nobody will read it.' Secretary Auntie Yang "
                "ultimately rewrote it into three lines: 'Ginkgo fruit has medicinal value. The "
                "smell is temporary. Please understand.' The most spectacular meeting occurred in "
                "spring. Someone proposed planting cherry trees in the compound's open space, "
                "reasoning that 'Japanese cherry blossoms are beautiful.' This immediately "
                "triggered fierce debate—not about aesthetics but about national sentiment. Uncle "
                "Zhao insisted on plum blossoms because 'plum blossoms represent the Chinese "
                "spirit.' Auntie Zhang said they should plant peach trees because 'you can eat "
                "peaches—can you eat cherry blossoms?' The final compromise was a crabapple "
                "tree—the reasoning being that crabapples possess the elegance of traditional "
                "Chinese aesthetics without any political sensitivity, and 'crabapple blossoms "
                "look beautiful when in bloom and don't stink when they fall.'"
            )

    with open('passages_hsk9.json', 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Fixed passages_hsk9.json")


if __name__ == '__main__':
    fix_hsk8()
    fix_hsk9()
    print("Done.")
