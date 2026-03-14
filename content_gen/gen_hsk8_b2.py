# -*- coding: utf-8 -*-
import json

P = []

def add(id, title, title_zh, text_zh, text_pinyin, text_en, q1, q2, q3):
    P.append({
        "id": id, "title": title, "title_zh": title_zh, "hsk_level": 8,
        "text_zh": text_zh, "text_pinyin": text_pinyin, "text_en": text_en,
        "questions": [q1, q2, q3]
    })

def mc(q_zh, q_en, opts, diff):
    return {"type": "mc", "q_zh": q_zh, "q_en": q_en, "options": opts, "difficulty": diff}

def o(text, pinyin, text_en, correct=False):
    return {"text": text, "pinyin": pinyin, "text_en": text_en, "correct": correct}

# 1
add("j8_observe_004",
    "The Geometry of Drying Laundry",
    "\u664e\u8863\u7ef3\u4e0a\u7684\u51e0\u4f55\u5b66",
    "\u4ece\u6211\u5bb6\u9633\u53f0\u671b\u51fa\u53bb\uff0c\u5bf9\u9762\u90a3\u680b\u8001\u516c\u5bd3\u7684\u664e\u8863\u7ef3\u6784\u6210\u4e86\u4e00\u5e45\u6bcf\u5929\u90fd\u4e0d\u4e00\u6837\u7684\u62bd\u8c61\u753b\u3002\u5468\u4e00\u65e9\u6668\uff0c\u4e09\u697c\u7684\u5f20\u963f\u59e8\u4f1a\u6302\u51fa\u4e00\u6392\u767d\u8272\u7684\u5e8a\u5355\uff0c\u5b83\u4eec\u5728\u98ce\u4e2d\u9f13\u80c0\u6210\u5f27\u5f62\uff0c\u50cf\u4e00\u9762\u9762\u6c89\u9ed8\u7684\u5e06\u3002\u56db\u697c\u7684\u5e74\u8f7b\u592b\u5987\u504f\u7231\u6df1\u8272\u8863\u7269\uff0c\u9ed1\u7070\u76f8\u95f4\u7684T\u6064\u548c\u725b\u4ed4\u88e4\u5782\u76f4\u60ac\u6302\uff0c\u5f62\u6210\u4e00\u79cd\u5de5\u4e1a\u611f\u7684\u8282\u594f\u3002\u4e94\u697c\u90a3\u4f4d\u72ec\u5c45\u7684\u8001\u5148\u751f\u53ea\u664e\u4e24\u4ef6\u4e1c\u897f\uff1a\u4e00\u4ef6\u7070\u8272\u7684\u4e2d\u5c71\u88c5\u548c\u4e00\u6761\u767d\u6bdb\u5dfe\uff0c\u65e5\u590d\u4e00\u65e5\uff0c\u4ece\u672a\u6539\u53d8\u3002\u6211\u66fe\u8bd5\u56fe\u4ece\u664e\u8863\u7ef3\u4e0a\u89e3\u8bfb\u6bcf\u6237\u4eba\u5bb6\u7684\u751f\u6d3b\uff0c\u5c31\u50cf\u8003\u53e4\u5b66\u5bb6\u4ece\u5730\u5c42\u4e2d\u63a8\u6d4b\u6587\u660e\u7684\u5174\u8870\u3002\u5e8a\u5355\u7684\u6570\u91cf\u6697\u793a\u5bb6\u5ead\u6210\u5458\u7684\u591a\u5c11\uff0c\u8863\u7269\u7684\u8272\u5f69\u900f\u9732\u5ba1\u7f8e\u503e\u5411\uff0c\u664e\u6652\u7684\u65f6\u95f4\u5219\u53cd\u6620\u4f5c\u606f\u89c4\u5f8b\u3002\u6709\u4e00\u6bb5\u65f6\u95f4\uff0c\u56db\u697c\u7a81\u7136\u53ea\u51fa\u73b0\u4e00\u4e2a\u4eba\u7684\u8863\u7269\uff0c\u6301\u7eed\u4e86\u5927\u7ea6\u4e09\u4e2a\u6708\uff0c\u7136\u540e\u53c8\u6062\u590d\u4e86\u4e24\u4e2a\u4eba\u7684\u89c4\u6a21\u3002\u6211\u4e0d\u77e5\u9053\u90a3\u4e09\u4e2a\u6708\u91cc\u53d1\u751f\u4e86\u4ec0\u4e48\uff0c\u4f46\u664e\u8863\u7ef3\u5fe0\u5b9e\u5730\u8bb0\u5f55\u4e86\u8fd9\u6bb5\u7a7a\u767d\u3002\u5728\u8fd9\u4e2a\u9690\u79c1\u88ab\u6570\u636e\u5b9a\u4e49\u7684\u65f6\u4ee3\uff0c\u664e\u8863\u7ef3\u6216\u8bb8\u662f\u6700\u53e4\u8001\u4e5f\u6700\u8bda\u5b9e\u7684\u793e\u4ea4\u5a92\u4f53\u2014\u2014\u5b83\u4ece\u4e0d\u7f8e\u5316\uff0c\u4ece\u4e0d\u7b5b\u9009\uff0c\u53ea\u662f\u628a\u751f\u6d3b\u6700\u6734\u7d20\u7684\u622a\u9762\u66b4\u9732\u5728\u9633\u5149\u4e0b\u3002",
    "C\u00f3ng w\u01d2 ji\u0101 y\u00e1ngt\u00e1i w\u00e0ng ch\u016bq\u00f9, du\u00ecmi\u00e0n n\u00e0 d\u00f2ng l\u01ceo g\u014dngy\u00f9 de li\u00e0ngy\u012bsh\u00e9ng g\u00f2uch\u00e9ng le y\u012b f\u00fa m\u011bi ti\u0101n d\u014du b\u00f9 y\u012by\u00e0ng de ch\u014dux\u00ec\u00e0ng hu\u00e0.",
    "Looking out from my balcony, the clotheslines of the old apartment opposite form an abstract painting that changes daily. Monday mornings, Auntie Zhang on the third floor hangs white bedsheets that billow like silent sails. The young couple on the fourth floor favors dark clothing\u2014black and grey T-shirts and jeans hang vertically in an industrial rhythm. The elderly man on the fifth floor dries only two things: a grey Mao suit and a white towel, day after day, never changing. I once tried to read each household\u2019s life from the clotheslines, like an archaeologist inferring civilization\u2019s rise and fall from strata. The number of bedsheets hints at family size, colors reveal aesthetic inclinations, timing reflects routines. For a while, the fourth floor suddenly displayed only one person\u2019s clothing for about three months, then returned to two. I don\u2019t know what happened, but the clothesline faithfully recorded the gap. In an age where privacy is defined by data, the clothesline is perhaps the oldest and most honest social media\u2014it never embellishes, never filters, simply exposes the most unadorned cross-section of life to sunlight.",
    mc("\u4f5c\u8005\u5c06\u664e\u8863\u7ef3\u6bd4\u4f5c\u300c\u793e\u4ea4\u5a92\u4f53\u300d\uff0c\u6838\u5fc3\u89c2\u70b9\u662f\u4ec0\u4e48\uff1f",
       "What is the core point of comparing clotheslines to social media?",
       [o("\u664e\u8863\u7ef3\u5c55\u793a\u7684\u751f\u6d3b\u4fe1\u606f\u672a\u7ecf\u4fee\u9970\uff0c\u6bd4\u7f51\u7edc\u793e\u4ea4\u66f4\u771f\u5b9e","li\u00e0ngy\u012bsh\u00e9ng zh\u01cen sh\u00ec de sh\u0113nghu\u00f3 x\u00ecnx\u012b w\u00e8i j\u012bng xi\u016bsh\u00ec, b\u01d0 w\u01cenglu\u00f2 sh\u00e8ji\u0101o g\u00e8ng zh\u0113nsh\u00ed","Clothesline information is unembellished, more authentic than online social media",True),
        o("\u664e\u8863\u7ef3\u662f\u4e00\u79cd\u8fc7\u65f6\u7684\u901a\u8baf\u65b9\u5f0f","li\u00e0ngy\u012bsh\u00e9ng sh\u00ec y\u012b zh\u01d2ng gu\u00f2sh\u00ed de t\u014dngx\u00f9n f\u0101ngsh\u00ec","Clotheslines are outdated communication"),
        o("\u4eba\u4eec\u5e94\u8be5\u51cf\u5c11\u4f7f\u7528\u793e\u4ea4\u5a92\u4f53","r\u00e9nmen y\u012bngg\u0101i ji\u01cen sh\u01ceo sh\u01d0y\u00f2ng sh\u00e8ji\u0101o m\u00e9it\u01d0","People should use social media less"),
        o("\u664e\u8863\u670d\u4f1a\u6cc4\u9732\u4e2a\u4eba\u9690\u79c1","li\u00e0ng y\u012bfu hu\u00ec xi\u00e8l\u00f9 g\u00e8r\u00e9n y\u01d0ns\u012b","Drying clothes leaks privacy")], 0.45),
    mc("\u56db\u697c\u8863\u7269\u6570\u91cf\u53d8\u5316\u7684\u7ec6\u8282\uff0c\u5728\u6587\u4e2d\u8d77\u5230\u4ec0\u4e48\u4f5c\u7528\uff1f",
       "What role does the fourth floor clothing change detail serve?",
       [o("\u8bf4\u660e\u664e\u8863\u7ef3\u80fd\u6620\u5c04\u4eba\u9645\u5173\u7cfb\u7684\u53d8\u5316","shu\u014dm\u00edng li\u00e0ngy\u012bsh\u00e9ng n\u00e9ng y\u00ecngsh\u00e8 r\u00e9nj\u00ec gu\u0101nx\u00ec de bi\u00e0nhu\u00e0","Shows clotheslines reflect relationship changes",True),
        o("\u6279\u8bc4\u5e74\u8f7b\u4eba\u7684\u5a5a\u59fb\u4e0d\u7a33\u5b9a","p\u012bp\u00edng ni\u00e1nq\u012bng r\u00e9n de h\u016bny\u012bn b\u00f9 w\u011bnd\u00ecng","Criticizes unstable marriages"),
        o("\u8868\u8fbe\u4f5c\u8005\u5bf9\u90bb\u5c45\u7684\u597d\u5947\u5fc3","bi\u01ced\u00e1 zu\u00f2zh\u011b du\u00ec l\u00ednj\u016b de h\u00e0oq\u00edx\u012bn","Expresses curiosity about neighbors"),
        o("\u8bc1\u660e\u56db\u697c\u592b\u5987\u7ecf\u5e38\u51fa\u5dee","zh\u00e8ngm\u00edng s\u00ec l\u00f3u f\u016bf\u00f9 j\u012bngch\u00e1ng ch\u016bch\u0101i","Proves the couple travels often")], 0.5),
    mc("\u4f5c\u8005\u7528\u8003\u53e4\u5b66\u5bb6\u7684\u7c7b\u6bd4\uff0c\u6700\u4e3b\u8981\u60f3\u8868\u8fbe\u4ec0\u4e48\uff1f",
       "What does the archaeologist analogy primarily convey?",
       [o("\u664e\u8863\u7ef3\u50cf\u5730\u5c42\u4e00\u6837\u4fdd\u5b58\u65e5\u5e38\u751f\u6d3b\u7684\u75d5\u8ff9","li\u00e0ngy\u012bsh\u00e9ng xi\u00e0ng d\u00eccéng y\u012by\u00e0ng b\u01ceoc\u00fan r\u00ecch\u00e1ng sh\u0113nghu\u00f3 de h\u00e9nj\u00ec","Clotheslines preserve daily life traces like strata",True),
        o("\u8003\u53e4\u5b66\u662f\u4e00\u95e8\u6709\u8da3\u7684\u5b66\u79d1","k\u01ceog\u01d4xu\u00e9 sh\u00ec y\u012b m\u00e9n y\u01d2uq\u00f9 de xu\u00e9k\u0113","Archaeology is interesting"),
        o("\u8001\u516c\u5bd3\u5e94\u88ab\u5217\u4e3a\u6587\u5316\u9057\u4ea7","l\u01ceo g\u014dngy\u00f9 y\u012bngg\u0101i b\u00e8i li\u00e8 w\u00e9i w\u00e9nhu\u00e0 y\u00edch\u01cen","Old apartments should be heritage"),
        o("\u73b0\u4ee3\u751f\u6d3b\u6b63\u5728\u8d70\u5411\u8870\u843d","xi\u00e0nd\u00e0i sh\u0113nghu\u00f3 zh\u00e8ngz\u00e0i z\u01d2uxi\u00e0ng shu\u0101ilu\u00f2","Modern life is declining")], 0.45))

with open("/Users/jasongerson/mandarin/content_gen/hsk8_batch2.json", "w", encoding="utf-8") as f:
    json.dump(P, f, ensure_ascii=False, indent=2)

data = json.load(open("/Users/jasongerson/mandarin/content_gen/hsk8_batch2.json", encoding="utf-8"))
print(f"Written {len(data)} passages, valid JSON")
for p in data:
    print(f"  {p['id']}: {len(p['questions'])}q")
