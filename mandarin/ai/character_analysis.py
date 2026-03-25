"""Character decomposition and radical/phonetic family analysis.

Implements component-based character teaching per Shen (2005) and
Taft & Zhu (1997). Characters are decomposed into semantic radicals
and phonetic components, enabling family-based learning.

Chinese characters are NOT atomic -- they are composed of semantic radicals
(indicating meaning category) and phonetic components (hinting at
pronunciation). Teaching this system dramatically accelerates character
learning by revealing structure that rote memorisation obscures.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Hand-coded decomposition data ─────────────────────────────────
#
# ~200 most common radicals and their meanings.  The value tuple is
# (english_meaning, pinyin_of_radical).  Example characters using
# each radical appear as comments for maintainability.

_RADICAL_MEANINGS: dict[str, tuple[str, str]] = {
    # Water
    '氵': ('water', 'shuǐ'),       # 河 湖 海 洋 洗 活 流 汽 池 沙 泪 浪 漂 深 温
    '水': ('water', 'shuǐ'),       # full form
    # Fire
    '火': ('fire', 'huǒ'),         # 烧 烤 灯 灭 炒 烟 燃 炸
    '灬': ('fire', 'huǒ'),         # 热 煮 照 然 熟 点 烈
    # Wood / Tree
    '木': ('wood/tree', 'mù'),     # 林 森 树 桌 椅 板 桥 杯 柜 枝 根 梅 桃
    # Mouth
    '口': ('mouth', 'kǒu'),       # 吃 喝 唱 吹 听 叫 呢 吗 呀 啊 吧 嘴 啡
    # Heart / Mind
    '心': ('heart/mind', 'xīn'),   # 想 思 感 情 忙 快 愿 态 意 恋
    '忄': ('heart/mind', 'xīn'),   # 快 忙 怕 惊 悟 惜 恨 慢 懒 惯 悲 愉
    # Hand
    '手': ('hand', 'shǒu'),       # 拿 掌
    '扌': ('hand', 'shǒu'),       # 打 拉 推 拿 抓 找 把 报 拍 拼 提 换 摸 按 排
    # Person
    '人': ('person', 'rén'),       # full form
    '亻': ('person', 'rén'),       # 们 你 他 住 作 做 信 像 什 伙 休 位 低 体 但
    # Woman
    '女': ('woman', 'nǚ'),        # 妈 姐 妹 好 她 奶 姑 娘 婚 嫁 如 始 姓
    # Sun / Day
    '日': ('sun/day', 'rì'),      # 明 早 晚 时 昨 星 映 昏 暗 暖 春 景 晴 晒
    # Moon / Month / Flesh
    '月': ('moon/month', 'yuè'),  # 朋 有 明 期 肉 腿 脸 脑 胖 脚 膀 腰
    # Earth / Soil
    '土': ('earth', 'tǔ'),       # 地 城 场 坐 块 坏 堆 塔 境 培 基 堂
    # Metal / Gold
    '金': ('metal/gold', 'jīn'),  # full form
    '钅': ('metal/gold', 'jīn'),  # 银 钱 铁 钟 铅 铜 钥 锁 链 镜 针 钢
    # Speech / Words
    '言': ('speech', 'yán'),      # full form
    '讠': ('speech', 'yán'),      # 说 话 语 读 课 让 认 记 词 许 论 请 谁 谢
    # Walk / Movement
    '走': ('walk', 'zǒu'),       # 起 越 赶 趣
    '辶': ('walk', 'chuò'),      # 这 那 还 进 远 近 道 过 边 送 速 逃 迟 选 连
    # Foot
    '足': ('foot', 'zú'),        # 跑 跳 踢 路 蹲 跟 跌
    '⻊': ('foot', 'zú'),        # simplified form
    # Eye
    '目': ('eye', 'mù'),         # 看 眼 睡 相 盲 盯 瞧 眨 睁
    # Ear
    '耳': ('ear', 'ěr'),         # 听 闻 聪 耻
    # Food / Eat
    '食': ('food', 'shí'),       # full form
    '饣': ('food', 'shí'),       # 饭 饿 饱 饮 饼 馆 饺 馒
    # Door / Gate
    '门': ('door/gate', 'mén'),  # 开 关 闭 问 间 闲 闷 闪 阅 阔
    # Clothing
    '衣': ('clothing', 'yī'),    # full form
    '衤': ('clothing', 'yī'),    # 衬 衫 被 裤 袜 裙 袋 裸 补
    # Shell / Money
    '贝': ('shell/money', 'bèi'), # 买 卖 贵 贱 货 贸 费 赚 赔 账
    # Vehicle / Car
    '车': ('vehicle', 'chē'),    # 辆 转 轮 轻 较 载 输
    # Horse
    '马': ('horse', 'mǎ'),      # 骑 驾 妈 码 骂 驴
    # Fish
    '鱼': ('fish', 'yú'),       # 鲜 鲸 鲤 鱿
    # Bird
    '鸟': ('bird', 'niǎo'),     # 鸡 鸭 鹅 鸽 鹰
    # Rain
    '雨': ('rain', 'yǔ'),       # 雪 雷 电 云 雾 霜 露 霸
    # Grass / Plant
    '艹': ('grass/plant', 'cǎo'), # 花 草 茶 药 菜 蓝 苹 葡 萄 莲 菊 荷 藏
    # Bamboo
    '竹': ('bamboo', 'zhú'),     # full form
    '⺮': ('bamboo', 'zhú'),     # 笔 篇 笑 第 算 管 答 箱 筷 筑 简
    # Silk / Thread
    '丝': ('silk/thread', 'sī'), # full form
    '纟': ('silk/thread', 'sī'), # 红 绿 给 经 练 终 细 组 级 纸 约 线 绝 继 纪
    # Stone
    '石': ('stone', 'shí'),      # 碗 硬 破 砖 碎 础 确 磨
    # Field
    '田': ('field', 'tián'),     # 男 界 思 留 略 番
    # Power / Strength
    '力': ('power', 'lì'),      # 动 办 努 加 助 勇 功 劳 励
    # Knife
    '刀': ('knife', 'dāo'),     # full form
    '刂': ('knife', 'dāo'),     # 刻 利 别 剪 割 创 划 刮 剧
    # Mountain
    '山': ('mountain', 'shān'),  # 岛 岸 岩 崇 峰 峡
    # Shelter / Wide
    '广': ('shelter', 'guǎng'),  # 店 床 庄 座 库 府 度 庆 康 底 庭 废
    # Roof / House
    '宀': ('roof', 'mián'),     # 家 宝 安 字 完 室 客 官 定 宿 宫 容 害 密
    # Cave / Hole
    '穴': ('cave', 'xué'),      # 空 穿 窗 穷 究 突
    # Page / Head
    '页': ('page/head', 'yè'),  # 顺 须 颜 题 额 预 顿 颗
    # Spirit / Show
    '示': ('show/spirit', 'shì'), # full form
    '礻': ('show/spirit', 'shì'), # 神 社 祝 礼 祖 福 祥 禁 禅
    # Disease
    '疒': ('illness', 'nè'),    # 病 痛 疼 症 疯 疲 癌 痒 瘦
    # Roof / Lean-to
    '厂': ('cliff/factory', 'chǎng'), # 厅 厨 原 压 厉
    # Enclosure
    '囗': ('enclosure', 'wéi'),  # 国 图 园 团 围 固 圆 困
    # Ice
    '冫': ('ice', 'bīng'),      # 冷 冰 冻 净 凉 准 减
    # Eight / Divide
    '八': ('eight/divide', 'bā'), # 公 分 兴
    # Big
    '大': ('big', 'dà'),        # 太 天 夫 头 央 奇 套 奖
    # Small
    '小': ('small', 'xiǎo'),    # 少 尖 尘
    # Rice
    '米': ('rice', 'mǐ'),      # 粮 粉 精 糖 糕 类 粗 糊
    # Leather / Skin
    '皮': ('skin', 'pí'),       # 被 波 破 疲 坡
    # Corpse / Body
    '尸': ('body', 'shī'),      # 居 屋 层 屏 展 局 屈
    # Stand
    '立': ('stand', 'lì'),      # 站 章 竞 端 童 亲
    # Grain
    '禾': ('grain', 'hé'),      # 种 秋 秘 科 程 积 稳 称 和 利
    # White
    '白': ('white', 'bái'),     # 百 的 皂 泉
    # King / Jade
    '王': ('king/jade', 'wáng'), # 玩 现 球 理 环 珠
    '玉': ('jade', 'yù'),       # full form
    # Bow
    '弓': ('bow', 'gōng'),      # 张 弯 强 弱 引
    # Tile / Pottery
    '瓦': ('tile', 'wǎ'),       # 瓶 瓷
    # Dot / Drop
    '丶': ('dot', 'zhǔ'),       # 主 义 丸
    # Also / Wing
    '又': ('again', 'yòu'),     # 又 双 友 对 欢 发 取 叔 观
    # Inch
    '寸': ('inch', 'cùn'),      # 对 封 导 寺 射 寿
    # Cross / Ten
    '十': ('ten', 'shí'),       # 十 千 半 南 博
    # Child
    '子': ('child', 'zǐ'),      # 子 学 孩 存 孙 字
    # Stop
    '止': ('stop', 'zhǐ'),      # 正 此 步 歧
    # Sunset / Evening
    '夕': ('evening', 'xī'),    # 多 梦 外 夜 名
    # Spear
    '戈': ('spear', 'gē'),      # 我 成 战 戏 或 感 截
    # Mound
    '阝': ('mound/city', 'fù'),  # (left: mound, right: city) 队 防 阳 阴 院 陆 附 隔 随 险
    # Clothing cover
    '冖': ('cover', 'mì'),       # 写 军 冠 农
    # Grass top
    '廾': ('hands joined', 'gǒng'),  # 开 弄
    # Feather
    '羽': ('feather', 'yǔ'),     # 翅 习 翻
    # Leather
    '革': ('leather', 'gé'),     # 鞋 靴
    # Corpse body
    '骨': ('bone', 'gǔ'),       # 骨 骼
    # Net
    '罒': ('net', 'wǎng'),      # 罗 置 罪 署
    # Horn / Angle
    '角': ('horn/angle', 'jiǎo'), # 解 触
}

# ── Phonetic component families ───────────────────────────────────
#
# Characters sharing a phonetic component tend to share similar
# pronunciations (though tones often differ).  Each key is the
# phonetic component; the value dict maps pinyin -> characters.

_PHONETIC_FAMILIES: dict[str, dict[str, str]] = {
    '青': {'qīng': '清', 'qǐng': '请', 'qíng': '情晴', 'jīng': '精睛静'},
    '方': {'fáng': '房防', 'fǎng': '访仿纺', 'fàng': '放'},
    '寺': {'shí': '时', 'shī': '诗', 'tè': '特', 'děng': '等', 'chí': '持'},
    '包': {'bāo': '包', 'páo': '跑袍', 'bào': '抱饱', 'pào': '泡炮'},
    '马': {'mā': '妈', 'mǎ': '码', 'mà': '骂'},
    '工': {'gōng': '功攻', 'jiāng': '江', 'hóng': '红虹'},
    '分': {'fēn': '芬纷', 'fěn': '粉', 'fèn': '份', 'pén': '盆'},
    '可': {'kě': '可', 'hé': '河何', 'gē': '哥歌'},
    '白': {'bái': '白', 'pāi': '拍', 'bǎi': '百柏'},
    '每': {'méi': '每莓', 'hǎi': '海', 'huǐ': '悔毁'},
    '己': {'jǐ': '己', 'jì': '记纪', 'qǐ': '起'},
    '令': {'líng': '零铃玲', 'lǐng': '领岭', 'lìng': '另'},
    '果': {'guǒ': '果裹', 'kè': '课', 'kē': '颗棵'},
    '生': {'shēng': '生笙', 'xìng': '性姓', 'xīng': '星'},
    '台': {'tái': '台抬', 'zhì': '治', 'shǐ': '始', 'tāi': '胎'},
    '占': {'zhàn': '占战', 'diàn': '店电', 'zhān': '粘'},
    '交': {'jiāo': '交郊', 'jiào': '较校教', 'xiào': '校效'},
    '各': {'gè': '各', 'kè': '客', 'luò': '落络', 'gé': '格阁'},
    '反': {'fǎn': '反返', 'bǎn': '板版', 'fàn': '饭贩'},
    '中': {'zhōng': '中钟忠', 'zhòng': '种重仲'},
    '主': {'zhǔ': '主煮', 'zhù': '住注柱', 'wǎng': '往'},
    '巴': {'bā': '巴吧', 'bǎ': '把', 'bà': '爸坝', 'pá': '爬'},
    '皮': {'pí': '皮', 'bō': '波', 'pō': '坡泼', 'pò': '破被'},
    '且': {'jū': '居', 'zǔ': '组祖租', 'zhù': '助'},
    '古': {'gǔ': '古', 'gù': '故固顾', 'hú': '湖胡', 'kǔ': '苦'},
    '长': {'cháng': '长肠', 'zhāng': '张账'},
    '合': {'hé': '合', 'gěi': '给', 'dā': '答搭塔'},
    '见': {'jiàn': '见现', 'guān': '观', 'lǎn': '览'},
    '力': {'lì': '力历', 'bàn': '办', 'jiā': '加'},
    '平': {'píng': '平苹评瓶'},
    '艮': {'gēn': '跟根', 'hěn': '很恨狠', 'yín': '银'},
    '圭': {'guī': '龟', 'wā': '蛙娃洼', 'guà': '挂'},
    '先': {'xiān': '先', 'xǐ': '洗', 'tiǎn': '舔'},
    '少': {'shǎo': '少', 'shā': '沙纱砂', 'chǎo': '炒吵妙'},
    '十': {'shí': '十', 'jì': '计', 'zhēn': '针'},
    '不': {'bù': '不', 'bēi': '杯', 'huái': '坏怀还'},
    '里': {'lǐ': '里理', 'mái': '埋'},
    '元': {'yuán': '元园远', 'wán': '完玩'},
    '发': {'fā': '发', 'fèi': '废', 'bō': '拨'},
    '文': {'wén': '文纹蚊', 'mín': '闵'},
    '正': {'zhèng': '正证政整', 'zhēng': '征'},
    '相': {'xiāng': '相', 'xiǎng': '想', 'xiàng': '象像'},
    '尧': {'shāo': '烧', 'rào': '绕', 'jiǎo': '搅'},
    '肖': {'xiāo': '消削', 'xiào': '笑'},
    '夬': {'kuài': '快块', 'jué': '决'},
    '失': {'shī': '失', 'tiě': '铁'},
    '对': {'duì': '对', 'shù': '树竖'},
    '半': {'bàn': '半伴拌', 'pàn': '判盼'},
}

# ── Reverse indices (built once at import) ────────────────────────

# Map from character -> (radical, radical_meaning, radical_pinyin)
_CHAR_TO_RADICAL: dict[str, tuple[str, str, str]] = {}

# Map from character -> (phonetic_component, phonetic_pinyin_hint, family_examples)
_CHAR_TO_PHONETIC: dict[str, tuple[str, str, list[str]]] = {}


def _build_reverse_indices() -> None:
    """Build reverse lookup tables from the radical and phonetic data."""
    global _CHAR_TO_RADICAL, _CHAR_TO_PHONETIC

    # Build character -> radical mapping
    for radical, (meaning, _pinyin) in _RADICAL_MEANINGS.items():
        # Find characters that contain this radical.
        # We check all characters referenced in phonetic families and
        # also scan _PHONETIC_FAMILIES values for known characters.
        pass  # We fill this from _PHONETIC_FAMILIES + explicit mapping below

    # Build a comprehensive character -> radical mapping
    # Strategy: for each radical, find characters that use it.
    # We use a manually curated mapping for the most common characters.
    _RADICAL_TO_CHARS: dict[str, list[str]] = {
        '氵': list('河湖海洋洗活流汽池沙泪浪漂深温清洒浇济消渡港湾液滴溪'),
        '水': list('泉'),
        '火': list('烧烤灯灭炒烟燃炸灿灾'),
        '灬': list('热煮照然熟点烈蒸'),
        '木': list('林森树桌椅板桥杯柜枝根梅桃机村材松极检样梦标格植棵楼模概'),
        '口': list('吃喝唱吹叫呢吗呀啊吧嘴啡品响咖喊咱咳另只吸喂呼叹呆'),
        '心': list('想思感情忙快愿态意恋念忘您悲忍志怎'),
        '忄': list('快忙怕惊悟惜恨慢懒惯悲愉怀懂惨恢忆性怪惭'),
        '手': list('拿掌拳'),
        '扌': list('打拉推抓找把报拍拼提换摸按排抱拨拾搬搅握撞掉揭扔扫拐招扶'),
        '亻': list('们你他住作做信像什伙休位低体但使便保修倒借假健值偶侧份似侯传'),
        '人': list('从众令全'),
        '女': list('妈姐妹好她奶姑娘婚嫁如始姓妇姨媳嫂妨'),
        '日': list('明早晚时昨星映昏暗暖春景晴晒普昌是旧最'),
        '月': list('朋有期肉腿脸脑胖脚膀腰肝肺肩背能望朗'),
        '土': list('地城场坐块坏堆塔境培基堂坚均圾坡墙在'),
        '钅': list('银钱铁钟铅铜钥锁链镜针钢铃错'),
        '金': list('鑫'),
        '讠': list('说话语读课让认记词许论请谁谢该诉识试议调谈诚证设访评译'),
        '言': list('警'),
        '走': list('起越赶趣趟'),
        '辶': list('这那还进远近道过边送速逃迟选连运通达遍追透遇遗适遍逻'),
        '足': list('跑跳踢路蹲跟跌距跃踩蹈'),
        '目': list('看眼睡相盲盯瞧眨睁瞬眉'),
        '耳': list('听闻聪耻取联'),
        '饣': list('饭饿饱饮饼馆饺馒饶'),
        '食': list('餐'),
        '门': list('开关闭问间闲闷闪阅阔闯'),
        '衤': list('衬衫被裤袜裙袋裸补'),
        '衣': list('装表裂'),
        '贝': list('买卖贵贱货贸费赚赔账贫财负败'),
        '车': list('辆转轮轻较载输辈'),
        '马': list('骑驾码骂驴'),
        '鱼': list('鲜鲸鲤鱿'),
        '鸟': list('鸡鸭鹅鸽鹰'),
        '雨': list('雪雷电雾霜露霸震需'),
        '艹': list('花草茶药菜蓝苹葡萄莲菊荷藏蒙落蔬薄荐著芳营'),
        '⺮': list('笔篇笑第算管答箱筷筑简笨策筋'),
        '竹': list('竿'),
        '纟': list('红绿给经练终细组级纸约线绝继纪纯织绕纷缘编绩缺'),
        '石': list('碗硬破砖碎础确磨矿砍研'),
        '田': list('男界思留略番画'),
        '力': list('动办努加助勇功劳励勉'),
        '刂': list('刻利别剪割创划刮剧刘到制则前削'),
        '刀': list('切分初'),
        '山': list('岛岸岩崇峰峡崖'),
        '广': list('店床庄座库府度庆康底庭废应'),
        '宀': list('家宝安字完室客官定宿宫容害密宜宇守实宽审'),
        '穴': list('空穿窗穷究突窄'),
        '页': list('顺须颜题额预顿颗'),
        '礻': list('神社祝礼祖福祥禁'),
        '示': list('票'),
        '疒': list('病痛疼症疯疲癌痒瘦'),
        '厂': list('厅厨原压厉'),
        '囗': list('国图园团围固圆困'),
        '冫': list('冷冰冻净凉准减决况'),
        '大': list('太天夫头央奇套奖夹'),
        '小': list('少尖尘'),
        '米': list('粮粉精糖糕类粗糊糟'),
        '尸': list('居屋层屏展局屈尾属'),
        '立': list('站章竞端童亲音'),
        '禾': list('种秋秘科程积稳称和利秀私季'),
        '白': list('百的泉皂'),
        '王': list('玩现球理环珠班'),
        '玉': list('宝'),
        '弓': list('张弯强弱引弹'),
        '又': list('双友对欢发取叔观鸡难'),
        '寸': list('对封导射寿'),
        '子': list('学孩存孙字孝孤'),
        '止': list('正此步歧武'),
        '夕': list('多梦外夜名'),
        '戈': list('我成战戏或感截'),
        '阝': list('队防阳阴院陆附隔随险际邮都那邻部'),
        '冖': list('写军冠农'),
        '羽': list('翅习翻'),
        '革': list('鞋靴'),
        '罒': list('罗置罪署'),
    }

    for radical, chars in _RADICAL_TO_CHARS.items():
        if radical not in _RADICAL_MEANINGS:
            continue
        meaning, r_pinyin = _RADICAL_MEANINGS[radical]
        for char in chars:
            if char not in _CHAR_TO_RADICAL:
                _CHAR_TO_RADICAL[char] = (radical, meaning, r_pinyin)

    # Build character -> phonetic mapping
    for phonetic, pronunciations in _PHONETIC_FAMILIES.items():
        # Collect all characters in this family as examples
        all_chars = []
        for pinyin_str, chars_str in pronunciations.items():
            for ch in chars_str:
                all_chars.append(ch)

        for pinyin_str, chars_str in pronunciations.items():
            for ch in chars_str:
                # Family examples: other characters in the same phonetic group
                examples = [c for c in all_chars if c != ch]
                _CHAR_TO_PHONETIC[ch] = (phonetic, pinyin_str, examples[:6])


# Build indices at module load time
_build_reverse_indices()


# ── Public API ────────────────────────────────────────────────────

def decompose(hanzi: str) -> dict | None:
    """Decompose a single character into radical + phonetic components.

    Returns a dict with keys:
        character: the input character
        radical: the semantic radical (if found)
        radical_meaning: english meaning of the radical
        radical_pinyin: pinyin of the radical
        phonetic: the phonetic component (if found)
        phonetic_hint: pronunciation suggested by the phonetic component
        family_examples: other characters sharing the phonetic component

    Returns None if the character cannot be decomposed (not CJK, or no
    decomposition data available).
    """
    if not hanzi or len(hanzi) != 1:
        return None

    # Verify it's a CJK character
    cp = ord(hanzi)
    if not (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF):
        return None

    radical_info = _CHAR_TO_RADICAL.get(hanzi)
    phonetic_info = _CHAR_TO_PHONETIC.get(hanzi)

    if not radical_info and not phonetic_info:
        return None

    result: dict = {'character': hanzi}

    if radical_info:
        result['radical'] = radical_info[0]
        result['radical_meaning'] = radical_info[1]
        result['radical_pinyin'] = radical_info[2]

    if phonetic_info:
        result['phonetic'] = phonetic_info[0]
        result['phonetic_hint'] = phonetic_info[1]
        result['family_examples'] = phonetic_info[2]

    return result


def get_component_family(radical: str) -> list[str]:
    """Get all common characters sharing this radical.

    Returns a list of characters that use the given radical as their
    semantic component.
    """
    return [
        char for char, (r, _, _) in _CHAR_TO_RADICAL.items()
        if r == radical
    ]


def get_phonetic_family(phonetic: str) -> dict[str, str]:
    """Get characters sharing this phonetic component, grouped by pronunciation.

    Returns a dict mapping pinyin -> characters_string for the given
    phonetic component. Returns empty dict if the phonetic is unknown.
    """
    return dict(_PHONETIC_FAMILIES.get(phonetic, {}))


def get_radical_for_character(hanzi: str) -> tuple[str, str, str] | None:
    """Get (radical, radical_meaning, radical_pinyin) for a character.

    Returns None if the character is not in the decomposition database.
    """
    return _CHAR_TO_RADICAL.get(hanzi)


def generate_decomposition_overlay(hanzi: str) -> dict | None:
    """Generate a decomposition display for first-exposure teaching moment.

    Returns a dict suitable for sending to the frontend as a
    character_decomposition message, or None if no decomposition
    data is available for this character.

    Keys:
        character: the character
        radical: semantic radical
        radical_meaning: english meaning of the radical
        phonetic: phonetic component (if any)
        phonetic_hint: pronunciation hint from phonetic component
        family_examples: list of related characters (up to 4)
    """
    info = decompose(hanzi)
    if not info:
        return None

    overlay: dict = {
        'character': hanzi,
        'radical': info.get('radical', ''),
        'radical_meaning': info.get('radical_meaning', ''),
    }

    if 'phonetic' in info:
        overlay['phonetic'] = info['phonetic']
        overlay['phonetic_hint'] = info.get('phonetic_hint', '')
        # Limit family examples for the overlay (don't overwhelm)
        examples = info.get('family_examples', [])
        overlay['family_examples'] = examples[:4]
    else:
        overlay['phonetic'] = ''
        overlay['phonetic_hint'] = ''
        overlay['family_examples'] = []

    return overlay
