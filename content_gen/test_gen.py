# -*- coding: utf-8 -*-
import json

data = [{"id": "test", "text_zh": "晾衣绳上的几何学，作者说「这很好」。"}]

with open("/Users/jasongerson/mandarin/content_gen/test_out.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

v = json.load(open("/Users/jasongerson/mandarin/content_gen/test_out.json", encoding="utf-8"))
print(f"OK: {v[0]['text_zh']}")
