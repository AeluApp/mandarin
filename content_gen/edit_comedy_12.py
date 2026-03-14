#!/usr/bin/env python3
"""
Targeted comedy surgery on 12 passages scoring 15-18.
Edits text_zh and text_en only. Leaves text_pinyin and questions untouched.
"""

import json
import os

BASEDIR = "/Users/jasongerson/mandarin/content_gen"

# Map of id -> (field, old_text, new_text) tuples
# Each passage gets explicit zh and en replacements.

EDITS = {}

# ── 1. j1_comedy_008 "The Phone Call" (HSK1, 17) ──
# Already tight and funny. The ending "他说「对不起对不起！」" is fine —
# it's concrete action. Actually reads clean. Minor tighten: cut redundant "又说".
EDITS["j1_comedy_008"] = {
    "text_zh": (
        "我的电话响了。一个人说「妈，今天晚上我不回家吃饭了」。"
        "我说「我不是你妈妈」。他说「对不起，打错了」。"
        "过了十分钟，他又打来了。又说「妈，今天……」"
        "我说「你又打错了！」他说「对不起对不起！」"
    ),
    "text_en": (
        "My phone rang. Someone said 'Mom, I'm not coming home for dinner tonight.' "
        "I said 'I'm not your mother.' He said 'Sorry, wrong number.' "
        "Ten minutes later, he called again. Again said 'Mom, today...' "
        "I said 'You got it wrong again!' He said 'Sorry sorry!'"
    ),
    # Tighten: end on the second "妈" — cut the apology, let the repetition land.
    "new_text_zh": (
        "我的电话响了。一个人说「妈，今天晚上我不回家吃饭了」。"
        "我说「我不是你妈妈」。他说「对不起，打错了」。"
        "过了十分钟，电话又响了。「妈，今天晚上——」"
    ),
    "new_text_en": (
        "My phone rang. Someone said 'Mom, I'm not coming home for dinner tonight.' "
        "I said 'I'm not your mother.' He said 'Sorry, wrong number.' "
        "Ten minutes later, the phone rang again. 'Mom, tonight—'"
    ),
}

# ── 2. j1_comedy_010 "Dad's New Phone" (HSK1, 17) ──
# "手机没有回答他" is moralizing/cute-commentary. End on him talking to the phone.
EDITS["j1_comedy_010"] = {
    "text_zh": (
        "爸爸买了一个新手机。他不太会用。"
        "他想给我打电话，但是打给了妈妈。"
        "他想看天气，但是打开了照相机。"
        "他对手机说「你太难了！」手机没有回答他。"
    ),
    "text_en": (
        "Dad bought a new phone. He doesn't really know how to use it. "
        "He wanted to call me but called mom instead. "
        "He wanted to check the weather but opened the camera. "
        "He said to the phone 'You're too hard!' The phone didn't answer him."
    ),
    "new_text_zh": (
        "爸爸买了一个新手机。他不太会用。"
        "他想给我打电话，但是打给了妈妈。"
        "他想看天气，但是打开了照相机。"
        "他把手机放在桌子上，对它说「你太难了！」"
    ),
    "new_text_en": (
        "Dad bought a new phone. He doesn't really know how to use it. "
        "He wanted to call me but called mom instead. "
        "He wanted to check the weather but opened the camera. "
        "He put the phone on the table and said to it 'You're too hard!'"
    ),
}

# ── 3. j1_comedy_013 "Grandpa's Glasses" (HSK1, 16) ──
# Cut "他也笑了" (reflection). End on the concrete discovery.
EDITS["j1_comedy_013"] = {
    "text_zh": (
        "爷爷找不到他的眼镜了。他问奶奶「你看到我的眼镜了吗？」"
        "奶奶看了看他，笑了。她说「在你的头上啊。」"
        "爷爷用手摸了摸头，眼镜果然在那里。他也笑了。"
    ),
    "text_en": (
        "Grandpa can't find his glasses. He asked grandma 'Have you seen my glasses?' "
        "Grandma looked at him and laughed. She said 'They're on your head.' "
        "Grandpa felt his head with his hand — the glasses were indeed there. He laughed too."
    ),
    "new_text_zh": (
        "爷爷找不到他的眼镜了。他问奶奶「你看到我的眼镜了吗？」"
        "奶奶看了看他，笑了。她说「在你的头上啊。」"
        "爷爷用手摸了摸头。眼镜果然在那里。"
    ),
    "new_text_en": (
        "Grandpa can't find his glasses. He asked grandma 'Have you seen my glasses?' "
        "Grandma looked at him and laughed. She said 'They're on your head.' "
        "Grandpa reached up and felt his head. The glasses were right there."
    ),
}

# ── 4. j2_comedy_002 "The Birthday Surprise" (HSK2, 16) ──
# Cut the neat resolution dialogue at the end. End on the phone call reveal.
EDITS["j2_comedy_002"] = {
    "text_zh": (
        "今天是我的生日。我的朋友们说要给我一个惊喜，让我晚上去他们家。"
        "我到了以后，门关着，灯也没开。我开了门，大声说：「我来了！」"
        "没有人回答。我找了半天，他们都不在家。"
        "后来他们打电话告诉我：「我们在你家等你呢！惊喜！」"
        "我笑了：「你们在我家，我在你们家，这是什么惊喜？」"
    ),
    "text_en": (
        "Today is my birthday. My friends said they'd give me a surprise and told me to come to their place tonight. "
        "When I arrived, the door was shut and lights off. I opened the door and called out: 'I'm here!' "
        "No answer. I looked around forever — nobody home. "
        "Later they called: 'We're at YOUR place waiting for you! Surprise!' "
        "I laughed: 'You're at my place, I'm at yours — what kind of surprise is this?'"
    ),
    # End on the awkward phone call moment — cut the narrator's neat summary line.
    "new_text_zh": (
        "今天是我的生日。我的朋友们说要给我一个惊喜，让我晚上去他们家。"
        "我到了以后，门关着，灯也没开。我开了门，大声说：「我来了！」"
        "没有人回答。我找了半天，他们都不在家。"
        "后来他们打电话告诉我：「我们在你家等你呢！惊喜！」"
        "我站在他们空空的客厅里，看着他们的电视。"
    ),
    "new_text_en": (
        "Today is my birthday. My friends said they'd give me a surprise and told me to come to their place tonight. "
        "When I arrived, the door was shut and lights off. I opened the door and called out: 'I'm here!' "
        "No answer. I looked around forever — nobody home. "
        "Later they called: 'We're at YOUR place waiting for you! Surprise!' "
        "I was standing in their empty living room, staring at their TV."
    ),
}

# ── 5. j2_comedy_007 "The Photo That Won't Work" (HSK2, 15) ──
# Mom's line is a fortune cookie. Replace with a behavioral observation / comic turn.
EDITS["j2_comedy_007"] = {
    "text_zh": (
        "我们一家人去公园拍照。妈妈让大家站好，说「一二三」。"
        "但是每次都有人没准备好。第一次弟弟在看别的地方。"
        "第二次爸爸的眼睛闭着。第三次我在笑。"
        "拍了十多次以后，妈妈说：「算了，这些不完美的照片可能比完美的更好看。」"
    ),
    "text_en": (
        "Our whole family went to the park to take photos. Mom told everyone to stand ready and said 'one two three.' "
        "But every time someone wasn't ready. First time, my brother was looking elsewhere. "
        "Second time, Dad's eyes were closed. Third time, I was laughing. "
        "After more than ten tries, Mom said: 'Forget it. These imperfect photos are probably better than perfect ones.'"
    ),
    "new_text_zh": (
        "我们一家人去公园拍照。妈妈让大家站好，说「一二三」。"
        "但是每次都有人没准备好。第一次弟弟在看别的地方。"
        "第二次爸爸的眼睛闭着。第三次我在笑。"
        "拍了十多次以后，妈妈看了看手机里的照片，发现每一张里只有她自己是完美的。"
    ),
    "new_text_en": (
        "Our whole family went to the park to take photos. Mom told everyone to stand ready and said 'one two three.' "
        "But every time someone wasn't ready. First time, my brother was looking elsewhere. "
        "Second time, Dad's eyes were closed. Third time, I was laughing. "
        "After more than ten tries, Mom looked through the photos on her phone and realized the only one perfect in every shot was herself."
    ),
}

# ── 6. j2_comedy_010 "The Wrong Floor" (HSK2, 15) ──
# "希望五楼的邻居没有听到…" is decent but a bit soft. Sharpen the comic beat.
EDITS["j2_comedy_010"] = {
    "text_zh": (
        "昨天晚上很累，我走到五楼，用钥匙开门——开不了。试了三次都不行。"
        "我正要打电话给房东，突然看到门上的号码：502。我住的是602。"
        "我上了一层楼，门一下子就开了。"
        "希望五楼的邻居没有听到我在他们门口试了三次钥匙。"
    ),
    "text_en": (
        "Last night I was tired. I walked to the fifth floor and tried to open the door with my key — it wouldn't open. "
        "Tried three times, no luck. Just as I was about to call the landlord, I noticed the number on the door: 502. I live in 602. "
        "I went up one floor and the door opened right away. "
        "I hope the fifth-floor neighbor didn't hear me trying their lock three times."
    ),
    "new_text_zh": (
        "昨天晚上很累，我走到五楼，用钥匙开门——开不了。试了三次都不行。"
        "我正要打电话给房东，突然看到门上的号码：502。我住的是602。"
        "我上了一层楼，门一下子就开了。"
        "进门的时候，我听到楼下502的门打开了。"
    ),
    "new_text_en": (
        "Last night I was tired. I walked to the fifth floor and tried to open the door with my key — it wouldn't open. "
        "Tried three times, no luck. Just as I was about to call the landlord, I noticed the number on the door: 502. I live in 602. "
        "I went up one floor and the door opened right away. "
        "As I stepped inside, I heard the door of 502 open below me."
    ),
}

# ── 7. j3_comedy_006 "The Wrong Delivery" (HSK3, 15) ──
# Cut the moralizing last two lines. End on the "lived next door for a year" absurdity.
EDITS["j3_comedy_006"] = {
    "text_zh": (
        "今天中午我点了一份炒饭。外卖送到的时候，我打开一看——是一碗面条。"
        "我打电话给外卖员，他说：「不好意思，可能跟别人的换了。」我说没关系。"
        "但是五分钟以后，我接到一个陌生人的电话：「你好，我点的是面条，但是收到了炒饭。你是不是收到了我的面条？」"
        "我说是的。她笑了：「那我们换回来？」"
        "我们约在楼下见面。到了以后我发现，她就住在我隔壁。我们认识了十秒钟就把外卖换了回来。"
        "她说：「我搬来一年了，今天第一次跟邻居说话。」"
        "我说：「如果不是送错了外卖，我们可能永远不会认识。」"
    ),
    "text_en": (
        "Today at noon I ordered fried rice. When the delivery arrived, I opened it — it was a bowl of noodles. "
        "I called the delivery person. He said: 'Sorry, it probably got switched with someone else's.' I said no problem. "
        "But five minutes later, a stranger called: 'Hi, I ordered noodles but got fried rice. Did you get my noodles?' "
        "I said yes. She laughed: 'Swap back?' We agreed to meet downstairs. "
        "When I got there, I found she lives right next door. We met and swapped in ten seconds. "
        "She said: 'I've lived here a year and this is the first time I've talked to a neighbor.' "
        "I said: 'If the delivery hadn't been mixed up, we might never have met.'"
    ),
    "new_text_zh": (
        "今天中午我点了一份炒饭。外卖送到的时候，我打开一看——是一碗面条。"
        "我打电话给外卖员，他说：「不好意思，可能跟别人的换了。」我说没关系。"
        "但是五分钟以后，我接到一个陌生人的电话：「你好，我点的是面条，但是收到了炒饭。你是不是收到了我的面条？」"
        "我说是的。她笑了：「那我们换回来？」"
        "我们约在楼下见面。到了以后我发现，她就住在我隔壁。"
        "她说：「我搬来一年了，今天第一次跟邻居说话。」我们站在走廊里，各自端着对方的午饭。"
    ),
    "new_text_en": (
        "Today at noon I ordered fried rice. When the delivery arrived, I opened it — it was a bowl of noodles. "
        "I called the delivery person. He said: 'Sorry, it probably got switched with someone else's.' I said no problem. "
        "But five minutes later, a stranger called: 'Hi, I ordered noodles but got fried rice. Did you get my noodles?' "
        "I said yes. She laughed: 'Swap back?' We agreed to meet downstairs. "
        "When I got there, I found she lives right next door. "
        "She said: 'I've lived here a year and this is the first time I've talked to a neighbor.' We stood in the hallway, each holding the other's lunch."
    ),
}

# ── 8. j3_comedy_008 "The Birthday Surprise" (HSK3, 15) ──
# Cut "笑得差点把面喷出来" (narrated laughter) and the final line (told-funny).
# End on the image of the wrong-name cake in the restaurant.
EDITS["j3_comedy_008"] = {
    "text_zh": (
        "今天是同事小王的生日。我们几个人决定给他一个惊喜。"
        "计划很简单：中午的时候，我们假装去开会，把他一个人留在办公室。然后带着蛋糕回来，唱生日歌。"
        "但是出了两个问题。第一，蛋糕上的名字被写错了——写成了「小黄」，不是「小王」。"
        "第二，我们回到办公室的时候，小王已经出去吃午饭了。"
        "我们只好带着蛋糕去餐厅找他。他正在吃面。"
        "我们端着蛋糕进去的时候，整个餐厅的人都在看我们。"
        "小王先是愣了一下，然后看到蛋糕上的名字，笑得差点把面喷出来。"
        "他说：「这是我收到的最好笑的惊喜。」"
    ),
    "text_en": (
        "Today is colleague Xiao Wang's birthday. A few of us decided to surprise him. "
        "Simple plan: at noon, we'd pretend to go to a meeting, leaving him alone. Then come back with cake and sing. "
        "But two things went wrong. First, the name on the cake was wrong — it said 'Xiao Huang' instead of 'Xiao Wang.' "
        "Second, when we returned to the office, Xiao Wang had already gone out for lunch. "
        "We had to take the cake to the restaurant to find him. He was eating noodles. "
        "When we walked in carrying the cake, the entire restaurant stared. "
        "Xiao Wang was stunned for a moment, then saw the name on the cake and nearly spat out his noodles laughing. "
        "He said: 'This is the funniest surprise I've ever gotten.'"
    ),
    "new_text_zh": (
        "今天是同事小王的生日。我们几个人决定给他一个惊喜。"
        "计划很简单：中午的时候，我们假装去开会，把他一个人留在办公室。然后带着蛋糕回来，唱生日歌。"
        "但是出了两个问题。第一，蛋糕上的名字被写错了——写成了「小黄」，不是「小王」。"
        "第二，我们回到办公室的时候，小王已经出去吃午饭了。"
        "我们只好带着蛋糕去餐厅找他。他正在吃面。"
        "我们端着蛋糕进去的时候，整个餐厅的人都在看我们。"
        "小王看了一眼蛋糕，嘴里还含着面条。蛋糕上写的是「小黄」。"
    ),
    "new_text_en": (
        "Today is colleague Xiao Wang's birthday. A few of us decided to surprise him. "
        "Simple plan: at noon, we'd pretend to go to a meeting, leaving him alone. Then come back with cake and sing. "
        "But two things went wrong. First, the name on the cake was wrong — it said 'Xiao Huang' instead of 'Xiao Wang.' "
        "Second, when we returned to the office, Xiao Wang had already gone out for lunch. "
        "We had to take the cake to the restaurant to find him. He was eating noodles. "
        "When we walked in carrying the cake, the entire restaurant stared. "
        "Xiao Wang looked at the cake, noodles still hanging from his mouth. The cake said 'Xiao Huang.'"
    ),
}

# ── 9. j4_comedy_008 "The Delivery Driver's Revenge" (HSK4, 17) ──
# Cut "我在网上看到一个很有趣的故事。" (make first-person).
# Cut final moral sentence. End on "he decided not to delete it."
EDITS["j4_comedy_008"] = {
    "text_zh": (
        "我在网上看到一个很有趣的故事。有一个人点了外卖，在备注里写了很多很过分的要求："
        "「送快一点！」「不要按门铃，打我电话！」「如果迟到了就别来了！」「汤不能洒出来！」"
        "外卖员看到以后没有生气，他只是在送餐的时候多带了一样东西——一张纸条。"
        "纸条上写着：「亲爱的顾客，您好！感谢您今天的订单。汤没有洒，我也没有迟到。"
        "希望您吃得开心。另外，我帮您在外卖平台上写了一个好评，内容是：'外卖员很帅，服务很好，建议加薪。'」"
        "那个人看了以后，又生气又想笑。他打开外卖平台一看，发现外卖员真的用他的账号写了这条评价。"
        "他犹豫了一下，最后没有删掉它。也许这就是最好的报复——让你生气的人笑出来。"
    ),
    "text_en": (
        "I saw a funny story online. Someone ordered delivery and wrote many unreasonable demands in the notes: "
        "'Deliver faster!' 'Don't ring the doorbell, call me!' 'If you're late, don't bother coming!' 'Don't spill the soup!' "
        "The delivery driver wasn't angry. He just brought an extra item when delivering — a note. "
        "It read: 'Dear customer, hello! Thank you for today's order. The soup didn't spill, and I wasn't late. "
        "Hope you enjoy your meal. Also, I helped you write a review on the delivery platform: "
        "\"The delivery driver is very handsome, great service, recommend a raise.\"' "
        "The customer was both angry and amused after reading it. He opened the delivery app and found the driver "
        "had actually written that review using his account. He hesitated for a moment, then decided not to delete it. "
        "Maybe this is the best revenge — making the person who angers you laugh."
    ),
    "new_text_zh": (
        "我点了外卖，在备注里写了很多要求："
        "「送快一点！」「不要按门铃，打我电话！」「如果迟到了就别来了！」「汤不能洒出来！」"
        "外卖员看到以后没有生气，他只是在送餐的时候多带了一样东西——一张纸条。"
        "纸条上写着：「亲爱的顾客，您好！感谢您今天的订单。汤没有洒，我也没有迟到。"
        "希望您吃得开心。另外，我帮您在外卖平台上写了一个好评，内容是：'外卖员很帅，服务很好，建议加薪。'」"
        "我看了以后，又生气又想笑。我打开外卖平台一看，他真的用我的账号写了这条评价。"
        "我犹豫了一下，最后没有删掉它。"
    ),
    "new_text_en": (
        "I ordered delivery and wrote a bunch of demands in the notes: "
        "'Deliver faster!' 'Don't ring the doorbell, call me!' 'If you're late, don't bother coming!' 'Don't spill the soup!' "
        "The delivery driver wasn't angry. He just brought an extra item — a note. "
        "It read: 'Dear customer, hello! Thank you for today's order. The soup didn't spill, and I wasn't late. "
        "Hope you enjoy your meal. Also, I helped you write a review on the delivery platform: "
        "\"The delivery driver is very handsome, great service, recommend a raise.\"' "
        "I was both angry and amused. I opened the app and found he had actually written that review using my account. "
        "I hesitated for a moment, then didn't delete it."
    ),
}

# ── 10. j5_comedy_004 "The Office Plant Nobody Waters" (HSK5, 18) ──
# Cut everything after "原来你也在浇？" — the group chat solution and TED talk moral.
EDITS["j5_comedy_004"] = {
    "text_zh": (
        "办公室角落有一盆绿萝，不知道谁买来的，也不知道放了多久。神奇的是，它一直活着。"
        "我仔细观察了一个月，终于发现了秘密：不是没有人浇水，而是每个人都以为只有自己在浇。"
        "小王周一浇，因为他觉得「周末两天没人管它」。小李周三浇，因为那天她心情好。"
        "老张每天下班前都倒一点剩茶水进去。实习生小陈甚至买了植物营养液，每周偷偷滴几滴。"
        "结果这盆可怜的绿萝被浇了太多水，叶子开始发黄。"
        "我把这个发现告诉了大家，所有人都惊讶地说「原来你也在浇？」"
        "后来我们建了一个小群，规定只有周一和周四浇水，每次由一个人负责。"
        "现在绿萝长得比以前好多了。"
        "有时候太多的关心和没有关心一样危险——关键不是付出多少，而是有没有沟通。"
    ),
    "text_en": (
        "In the office corner there's a pothos plant — nobody knows who bought it or how long it's been there. "
        "Miraculously, it's still alive. I observed carefully for a month and finally discovered the secret: "
        "it's not that nobody waters it, but that everyone thinks only they are watering it. "
        "Xiao Wang waters it Monday because 'nobody takes care of it over the weekend.' "
        "Xiao Li waters it Wednesday because she's in a good mood that day. "
        "Old Zhang pours in leftover tea before leaving work every day. "
        "Even the intern Xiao Chen bought plant nutrient solution and secretly adds drops each week. "
        "As a result the poor pothos was overwatered and its leaves started yellowing. "
        "When I told everyone about my discovery, they all said in surprise 'you water it too?' "
        "We then created a small group chat, establishing that watering happens only Monday and Thursday, "
        "one person responsible each time. Now the pothos is growing much better than before. "
        "Sometimes too much care is as dangerous as no care at all — what matters isn't how much you give, but whether you communicate."
    ),
    "new_text_zh": (
        "办公室角落有一盆绿萝，不知道谁买来的，也不知道放了多久。神奇的是，它一直活着。"
        "我仔细观察了一个月，终于发现了秘密：不是没有人浇水，而是每个人都以为只有自己在浇。"
        "小王周一浇，因为他觉得「周末两天没人管它」。小李周三浇，因为那天她心情好。"
        "老张每天下班前都倒一点剩茶水进去。实习生小陈甚至买了植物营养液，每周偷偷滴几滴。"
        "结果这盆可怜的绿萝被浇了太多水，叶子开始发黄。"
        "我把这个发现告诉了大家，所有人都惊讶地说「原来你也在浇？」"
    ),
    "new_text_en": (
        "In the office corner there's a pothos plant — nobody knows who bought it or how long it's been there. "
        "Miraculously, it's still alive. I observed carefully for a month and finally discovered the secret: "
        "it's not that nobody waters it, but that everyone thinks only they are watering it. "
        "Xiao Wang waters it Monday because 'nobody takes care of it over the weekend.' "
        "Xiao Li waters it Wednesday because she's in a good mood that day. "
        "Old Zhang pours in leftover tea before leaving work every day. "
        "Even the intern Xiao Chen bought plant nutrient solution and secretly adds drops each week. "
        "As a result the poor pothos was overwatered and its leaves started yellowing. "
        "When I told everyone about my discovery, they all said in surprise 'you water it too?'"
    ),
}

# ── 11. j7_comedy_002 "The Elevator Etiquette Incident" (HSK7, 18) ──
# Moral was already cut. Check for essay voice / tighten narration.
# "效果出人意料。不是说大家真的按照规则来了，而是..." is essay-voice explanation.
# Tighten it — let the behavior speak.
EDITS["j7_comedy_002"] = {
    "text_zh": (
        "我们这栋楼只有两部电梯，早上八点是最挤的时候。"
        "大家都在赶时间上班，电梯门一开，所有人都往里冲。"
        "有一天早上，住在十八楼的赵叔按住开门键让一位抱着孩子的年轻妈妈先进去，"
        "结果后面的人嫌他耽误时间，小声嘀咕了几句。"
        "赵叔没说什么，但第二天他在电梯里贴了一张手写的告示："
        "「早高峰电梯使用建议：一、抱小孩的优先。二、拿很多东西的优先。"
        "三、赶飞机的优先（请提前说明）。四、以上都不符合的，请微笑排队。」"
        "告示贴出去以后，效果出人意料。不是说大家真的按照规则来了，"
        "而是每天早上等电梯的时候，大家会站在那里读一遍，然后互相笑一下。"
        "有人补充了第五条：「带狗的请走楼梯，因为狗会按所有的楼层按钮。」"
        "又有人加了第六条：「如果你昨晚吃了大蒜，请等下一趟。」"
    ),
    "text_en": (
        "Our building has only two elevators, and 8 AM is the most crowded time. "
        "Everyone is rushing to work, and the moment the elevator doors open, people charge in. "
        "One morning, Uncle Zhao from the 18th floor held the door-open button to let a young mother carrying a child go first, "
        "but people behind him grumbled about the delay. "
        "Uncle Zhao said nothing, but the next day he posted a handwritten notice in the elevator: "
        "'Morning rush elevator usage suggestions: 1. Those carrying small children go first. "
        "2. Those carrying many things go first. 3. Those catching a flight go first (please state in advance). "
        "4. If none of the above apply, please smile and queue.' "
        "The effect after posting was unexpected. Not that everyone actually followed the rules, "
        "but each morning while waiting for the elevator, people would stand there reading through the list, then share a laugh. "
        "Someone added a fifth rule: 'Those with dogs, please take the stairs, because dogs press every floor button.' "
        "Another added a sixth: 'If you ate garlic last night, please wait for the next one.'"
    ),
    # Cut the essay-voice explanation. Let the added rules follow directly.
    "new_text_zh": (
        "我们这栋楼只有两部电梯，早上八点是最挤的时候。"
        "电梯门一开，所有人都往里冲。"
        "有一天早上，住在十八楼的赵叔按住开门键让一位抱着孩子的年轻妈妈先进去，"
        "后面的人小声嘀咕了几句。"
        "赵叔没说什么，但第二天他在电梯里贴了一张手写的告示："
        "「早高峰电梯使用建议：一、抱小孩的优先。二、拿很多东西的优先。"
        "三、赶飞机的优先（请提前说明）。四、以上都不符合的，请微笑排队。」"
        "一周以后，告示上多了两条。"
        "第五条：「带狗的请走楼梯，因为狗会按所有的楼层按钮。」"
        "第六条：「如果你昨晚吃了大蒜，请等下一趟。」"
    ),
    "new_text_en": (
        "Our building has only two elevators, and 8 AM is the most crowded time. "
        "The moment the doors open, people charge in. "
        "One morning, Uncle Zhao from the 18th floor held the door-open button to let a young mother carrying a child go first. "
        "People behind him grumbled. "
        "Uncle Zhao said nothing, but the next day he posted a handwritten notice in the elevator: "
        "'Morning rush elevator usage suggestions: 1. Those carrying small children go first. "
        "2. Those carrying many things go first. 3. Those catching a flight go first (please state in advance). "
        "4. If none of the above apply, please smile and queue.' "
        "A week later, two more rules had appeared on the notice. "
        "Number five: 'Those with dogs, please take the stairs, because dogs press every floor button.' "
        "Number six: 'If you ate garlic last night, please wait for the next one.'"
    ),
}

# ── 12. j8_comedy_001 "Meeting That Could've Been an Email" (HSK8, 16) ──
# Cut "我粗略统计过" opening. Add one dialogue exchange. Keep the hallway punchline.
EDITS["j8_comedy_001"] = {
    "text_zh": (
        "我粗略统计过，在过去五年的职业生涯中，我参加的会议里至少有百分之六十可以用一封三行的邮件替代。"
        "典型的无效会议有一套固定的剧本：首先，组织者会提前十五分钟发一个模糊的议题，"
        "比如「讨论一下下季度的方向」，这种议题的信息量约等于「我们聊聊天吧」。"
        "其次，会议开始后的头五分钟用于等待迟到的人，这五分钟里已到场的人假装看手机，"
        "实则在计算这次迟到将浪费多少人的多少小时。"
        "然后进入正题——如果它存在的话。"
        "通常的情况是，说话时间的分配遵循一条隐形的权力曲线：职位最高的人说得最多，但信息密度最低；"
        "真正掌握关键数据的人往往在最后三分钟才被点名发言。"
        "会议结束时，组织者总结道：「那我们下次再详细讨论。」"
        "这句话翻译成人话就是：「这次会议什么结论也没达成。」"
        "散会后，两个人在走廊里站了三十秒，把会上一小时没解决的问题解决了。"
    ),
    "text_en": (
        "By rough count, at least sixty percent of the meetings I've attended over my five-year career "
        "could have been replaced by a three-line email. The typical ineffective meeting follows a fixed script: "
        "first, the organizer sends a vague agenda fifteen minutes in advance, something like "
        "'discuss next quarter's direction'—an agenda whose information content roughly equals 'let's chat.' "
        "Next, the first five minutes after the meeting starts are spent waiting for latecomers, during which "
        "those already present pretend to look at their phones while actually calculating how many person-hours "
        "this tardiness will waste. Then comes the main topic—if it exists. Usually, speaking time is distributed "
        "along an invisible power curve: the highest-ranking person speaks the most but with the lowest information "
        "density; the person who actually holds the key data typically isn't called on until the last three minutes. "
        "When the meeting ends, the organizer summarizes: 'Let's discuss this in more detail next time.' "
        "Translated into plain language: 'This meeting reached no conclusion whatsoever.' "
        "After the meeting, two people stood in the hallway for thirty seconds and solved what the meeting "
        "failed to solve in an hour."
    ),
    "new_text_zh": (
        "在过去五年的职业生涯中，我参加的会议里至少有百分之六十可以用一封三行的邮件替代。"
        "典型的无效会议有一套固定的剧本：首先，组织者会提前十五分钟发一个模糊的议题，"
        "比如「讨论一下下季度的方向」，这种议题的信息量约等于「我们聊聊天吧」。"
        "其次，会议开始后的头五分钟用于等待迟到的人，这五分钟里已到场的人假装看手机，"
        "实则在计算这次迟到将浪费多少人的多少小时。"
        "然后进入正题——如果它存在的话。"
        "通常的情况是，说话时间的分配遵循一条隐形的权力曲线：职位最高的人说得最多，但信息密度最低；"
        "真正掌握关键数据的人往往在最后三分钟才被点名发言。"
        "上周的会上，主管讲了四十分钟，最后问：「小刘，数据准备好了吗？」小刘说：「我发在群里了，上周二。」"
        "会议结束时，组织者总结道：「那我们下次再详细讨论。」"
        "散会后，两个人在走廊里站了三十秒，把会上一小时没解决的问题解决了。"
    ),
    "new_text_en": (
        "At least sixty percent of the meetings I've attended over my five-year career "
        "could have been replaced by a three-line email. The typical ineffective meeting follows a fixed script: "
        "first, the organizer sends a vague agenda fifteen minutes in advance, something like "
        "'discuss next quarter's direction' — an agenda whose information content roughly equals 'let's chat.' "
        "Next, the first five minutes are spent waiting for latecomers, during which "
        "those already present pretend to look at their phones while actually calculating how many person-hours "
        "this tardiness will waste. Then comes the main topic — if it exists. Usually, speaking time is distributed "
        "along an invisible power curve: the highest-ranking person speaks the most but with the lowest information "
        "density; the person who actually holds the key data typically isn't called on until the last three minutes. "
        "In last week's meeting, the manager spoke for forty minutes, then asked: 'Xiao Liu, is the data ready?' "
        "Xiao Liu said: 'I posted it in the group chat. Last Tuesday.' "
        "When the meeting ended, the organizer summarized: 'Let's discuss this in more detail next time.' "
        "After the meeting, two people stood in the hallway for thirty seconds and solved what the meeting "
        "failed to solve in an hour."
    ),
}


def count_chars(text, lang):
    """Count meaningful units: characters for zh, words for en."""
    if lang == "zh":
        return len([c for c in text if c.strip() and c not in '，。！？「」、：；""''——…… '])
    else:
        return len(text.split())


def main():
    # Group edits by HSK level
    id_to_level = {
        "j1_comedy_008": 1, "j1_comedy_010": 1, "j1_comedy_013": 1,
        "j2_comedy_002": 2, "j2_comedy_007": 2, "j2_comedy_010": 2,
        "j3_comedy_006": 3, "j3_comedy_008": 3,
        "j4_comedy_008": 4,
        "j5_comedy_004": 5,
        "j7_comedy_002": 7,
        "j8_comedy_001": 8,
    }

    levels_to_edit = sorted(set(id_to_level.values()))
    edited_count = 0

    for level in levels_to_edit:
        filepath = os.path.join(BASEDIR, f"passages_hsk{level}.json")
        with open(filepath, "r", encoding="utf-8") as f:
            passages = json.load(f)

        modified = False
        for p in passages:
            if p["id"] not in EDITS:
                continue

            edit = EDITS[p["id"]]
            print(f"\n{'='*60}")
            print(f"  {p['id']} — \"{p['title']}\" (HSK {level})")
            print(f"{'='*60}")

            # Verify old text matches (sanity check)
            old_zh = p["text_zh"]
            old_en = p["text_en"]

            # Print before counts
            zh_before = count_chars(old_zh, "zh")
            en_before = count_chars(old_en, "en")

            # Apply edits
            p["text_zh"] = edit["new_text_zh"]
            p["text_en"] = edit["new_text_en"]

            # Print after counts
            zh_after = count_chars(p["text_zh"], "zh")
            en_after = count_chars(p["text_en"], "en")

            print(f"  ZH chars: {zh_before} → {zh_after} ({zh_after - zh_before:+d})")
            print(f"  EN words: {en_before} → {en_after} ({en_after - en_before:+d})")
            print(f"  New ending ZH: ...{p['text_zh'][-40:]}")
            print(f"  New ending EN: ...{p['text_en'][-50:]}")

            modified = True
            edited_count += 1

        if modified:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(passages, f, ensure_ascii=False, indent=2)
            print(f"\n  ✓ Saved {filepath}")

    print(f"\n{'='*60}")
    print(f"  Done. Edited {edited_count} passages across {len(levels_to_edit)} files.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
