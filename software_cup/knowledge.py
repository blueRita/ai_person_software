import re
import pandas as pd
try:
    from docx import Document
except ImportError:
    Document = None


ZH_DIGITS = "零一二三四五六七八九"
FACT_WORDS = {"多高", "高度", "多少", "几年", "哪年", "几点", "时间", "价格", "门票", "面积", "长度", "宽度", "距离", "海拔"}
FACT_INTENTS = {
    "height": {
        "query": ["多高", "高度", "高", "通高", "海拔"],
        "fields": ["多高", "高度", "通高", "高达", "总高", "身高", "佛体高", "海拔"],
        "units": ["米", "m", "厘米"],
    },
    "time": {
        "query": ["几点", "时间", "开放", "演出", "多久", "多长"],
        "fields": ["时间", "开放", "演出", "开演", "营业", "时段", "场次", "时长"],
        "units": ["时", "分", "点", ":", "："],
    },
    "price": {
        "query": ["多少钱", "价格", "票价", "门票", "费用", "多少元"],
        "fields": ["价格", "票价", "门票", "费用", "元"],
        "units": ["元", "￥", "¥"],
    },
    "year": {
        "query": ["哪年", "几年", "年份", "历史", "建成", "开放"],
        "fields": ["年份", "建成", "开放", "始建", "历史", "年"],
        "units": ["年"],
    },
}


def number_to_zh_text(value: int) -> str:
    if value < 0:
        return "负" + number_to_zh_text(abs(value))
    if value < 10:
        return ZH_DIGITS[value]
    if value < 20:
        return "十" + (ZH_DIGITS[value % 10] if value % 10 else "")
    if value < 100:
        return ZH_DIGITS[value // 10] + "十" + (ZH_DIGITS[value % 10] if value % 10 else "")
    if value < 1000:
        tail = value % 100
        return ZH_DIGITS[value // 100] + "百" + (number_to_zh_text(tail) if tail else "")
    if value < 10000:
        tail = value % 1000
        return ZH_DIGITS[value // 1000] + "千" + (number_to_zh_text(tail) if tail else "")
    return str(value)


def normalize_search_text(text: str) -> str:
    text = (text or "").lower()
    text = text.translate(str.maketrans("０１２３４５６７８９．：，", "0123456789.:,"))
    text = re.sub(r"(?<=\d)\.0+(?=\D|$)", "", text)
    text = re.sub(r"(?<=\d)\s+(?=[米元年月日时分秒公里万%％])", "", text)
    text = re.sub(r"(?<=[第])\s+(?=\d)", "", text)
    return text


def numeric_variants(text: str):
    variants = set()
    normalized = normalize_search_text(text)
    for match in re.findall(r"\d+(?:\.\d+)?", normalized):
        variants.add(match)
        if match.endswith(".0"):
            variants.add(match[:-2])
        if "." not in match:
            try:
                variants.add(number_to_zh_text(int(match)))
            except Exception:
                pass
    return variants


def detect_fact_intents(query: str):
    normalized = normalize_search_text(query)
    return [
        name for name, spec in FACT_INTENTS.items()
        if any(word in normalized for word in spec["query"])
    ]


def extract_subject_terms(query: str):
    normalized = normalize_search_text(query)
    stop_words = {"什么", "多少", "多高", "高度", "几点", "时间", "价格", "门票", "哪里", "怎么", "介绍", "一下", "有没有"}
    subjects = set()
    aliases = {
        "大佛": ["大佛", "灵山大佛", "佛体"],
        "梵宫": ["梵宫", "灵山梵宫"],
        "九龙": ["九龙", "九龙灌浴"],
        "祥符": ["祥符", "祥符禅寺"],
        "坛城": ["坛城", "五印坛城"],
        "拈花": ["拈花", "拈花湾"],
    }
    for key, values in aliases.items():
        if key in normalized:
            subjects.update(values)
    for length in [6, 5, 4, 3, 2]:
        for i in range(len(normalized) - length + 1):
            token = normalized[i:i + length]
            if token in stop_words:
                continue
            if any(stop in token for stop in stop_words):
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]{2,6}", token):
                subjects.add(token)
    return subjects

# =========================================
# 数据路径
# =========================================
EXCEL_PATH = r"景点景区旅游数据行为分析数据.xlsx"
DOCX_PATH_1 = r"灵山胜境 景点结构化数据集.docx"
DOCX_PATH_2 = r"灵山胜境：历史、文化、景点特色与个性化游览指南.docx"

# =========================================
# 权威知识片段：演艺时刻与人流潮汐规律
# =========================================
CROWD_AND_TIME_ANALYSIS_CHUNK = """【景区权威演艺时刻表与人流潮汐避峰指南】
1. 核心定时演艺与活动时间：
- 九龙灌浴（大型动态喷泉大秀）：平日固定演出4场，具体时间为 10:00、11:30、13:30、15:00（每场时长约15分钟，建议提前10分钟占位，晴天可看彩虹佛光，结束后可接祈福圣水）。
- 灵山梵宫（《灵山吉祥颂》大型演出）：每日固定演出4场，具体时间为 10:35、11:30、14:00、16:00（每场时长约20分钟，全球唯一大型旋转舞台与全息投影）。
- 佛教文化博览馆（展馆免费人工讲解服务）：每日时段为 09:30、11:00、14:30、16:00（一层入口集合，另有沉浸式投影每30分钟循环一场）。
- 拈花湾禅意小镇拈花堂（小型禅意讲座）：每日时段为 10:30、15:30（每场约40分钟，无需预约，现场参与）。
2. 黄金避峰错峰与人流迁徙规律（什么时间段人最少、如何避开拥堵）：
- 黄金错峰期①【早间清幽期 08:00 - 09:30】：此时景区各大定时大秀均未开演，团队游客尚未大批入园，全天人流量降至冰点。是前往核心地标灵山大佛登顶“抱佛脚”、在五明桥拍摄汉白玉石桥完美倒影的绝佳清静时机。
- 黄金错峰期②【午间演艺断档期 12:00 - 13:30】：12:00后九龙灌浴与梵宫进入1.5小时的演艺静默空窗期，大批游客被分流至餐饮区排队就餐。此时去参观灵山梵宫内部的静态非遗艺术（如金丝楠木东阳木雕群、28米星空穹顶、华藏世界巨型琉璃壁画）人最少、最舒适！
- 全天最拥堵对撞点【11:30】：九龙灌浴和梵宫《吉祥颂》同时开演，两处大节点会把人流锁死，人流量密度达到全天最高峰，且周边就餐区开始大排长龙，强烈建议游客避开此时间点。
- 散场流向：10:00和13:30看完九龙灌浴喷泉的游客，会迅速向西侧梵宫步行迁徙赶10:35和14:00的演出。10:15-10:35及13:45-14:00期间沿途主干道人流极度密集。"""


# =========================================
# 1. 语义化数据加载
# =========================================
def load_excel_semantic():
    """将Excel的每一行转化为结构化的自然语言文本，并采用绝对白名单+黑名单双保险机制过滤脏数据"""
    chunks = []
    try:
        df = pd.read_excel(EXCEL_PATH).fillna("")

        WHITE_LIST = ["灵山", "大佛", "梵宫", "九龙", "胜境", "祥符", "坛城", "拈花", "波罗蜜多", "香月花街", "鹿鸣谷"]
        BLACK_LIST = ["hello kitty", "凯蒂猫", "上海", "陆家嘴", "迪士尼", "乌镇", "西湖", "千岛湖", "周庄", "东方明珠"]

        for _, row in df.iterrows():
            items = [f"{col}为{val}" for col, val in row.items() if str(val).strip()]
            row_text = "，".join(items)
            row_text_lower = row_text.lower()

            is_valid_scenic = any(w in row_text_lower for w in WHITE_LIST)
            is_contaminated = any(b in row_text_lower for b in BLACK_LIST)

            if not is_valid_scenic or is_contaminated:
                continue

            chunks.append(f"【景区运营与设施数据】{row_text}。")

        print(f"Excel数据过滤完毕，成功保留灵山有效运营数据: {len(chunks)} 条")
        return chunks
    except Exception as e:
        print(f"Excel加载失败: {e}")
        return []


def load_docx_lines(path):
    """读取Word，按段落和句子初步拆分"""
    lines = []
    if Document is None:
        print("Docx加载跳过: 未安装 python-docx")
        return lines
    try:
        doc = Document(path)
        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            sub_lines = re.split(r"([。！？；])", text)
            for i in range(0, len(sub_lines) - 1, 2):
                sentence = sub_lines[i] + sub_lines[i + 1]
                if sentence.strip():
                    lines.append(sentence.strip())
            if len(sub_lines) % 2 == 1 and sub_lines[-1].strip():
                lines.append(sub_lines[-1].strip())
    except Exception as e:
        print(f"Docx加载失败: {path}, {e}")
    return lines


# =========================================
# 2. 智能滑动窗口切片
# =========================================
def make_chunks_with_overlap(lines, max_len=350, overlap_sentences=2):
    """基于句子级别的滑动窗口切片，确保数字不丢失语境"""
    chunks = []
    current_chunk = []
    current_len = 0

    for line in lines:
        line_len = len(line)
        if current_len + line_len <= max_len:
            current_chunk.append(line)
            current_len += line_len
        else:
            if current_chunk:
                chunks.append("".join(current_chunk))
            current_chunk = current_chunk[-overlap_sentences:] if len(
                current_chunk) > overlap_sentences else current_chunk
            current_chunk.append(line)
            current_len = sum(len(s) for s in current_chunk)

    if current_chunk:
        chunks.append("".join(current_chunk))
    return chunks


# =========================================
# 3. 增强型知识库
# =========================================
class KnowledgeBase:
    def __init__(self):
        print("正在深度构建智能化知识库...")

        docx_lines = load_docx_lines(DOCX_PATH_1) + load_docx_lines(DOCX_PATH_2)
        self.chunks = make_chunks_with_overlap(docx_lines, max_len=350, overlap_sentences=2)

        excel_chunks = load_excel_semantic()
        self.chunks.extend(excel_chunks)

        self.chunks.append(CROWD_AND_TIME_ANALYSIS_CHUNK.strip())
        self.chunks = [c.strip() for c in self.chunks if len(c) > 8]
        print(f"知识库构建完成，当前纯净知识片段(Chunk)总量: {len(self.chunks)}")

    def extract_search_terms(self, q):
        """增强版中文意图与同义词映射机制"""
        q = normalize_search_text(q)
        terms = set()

        mapping = {
            "大佛": ["灵山大佛", "佛体", "释迦牟尼", "立像", "青铜", "高度", "铜量", "抱佛脚", "登顶"],
            "多高": ["88米", "通高", "高", "高度", "尺寸", "雄伟"],
            "高度": ["88米", "通高", "高", "高度", "尺寸"],
            "亲子": ["互动", "体验", "儿童", "孩子", "家庭", "童趣", "弥勒", "九龙灌浴", "百子戏弥勒"],
            "路线": ["路线", "游览", "行程", "顺序", "怎么走", "一日游", "推荐", "半天"],
            "老人": ["老年", "轻松", "舒适", "平缓", "素斋", "休息", "无障碍"],
            "休息": ["休息", "座椅", "茶室", "服务中心", "长廊", "设施", "憩", "杏坛广场"],
            "演出": ["演出", "表演", "时间", "时刻表", "几点", "九龙灌浴", "吉祥颂", "演艺", "大秀", "场次", "剧场"],
            "时间": ["时间", "时刻表", "几点", "开放", "运行", "时段", "场次", "开演"],
            "梵宫": ["梵宫", "建筑", "艺术", "卢浮宫", "珍品", "壁画", "吉祥颂", "穹顶", "木雕", "圣坛"],
            "历史": ["历史", "背景", "建造", "年份", "开放", "建成", "筹建", "渊源", "宋代", "玄奘"],
            "吃饭": ["吃饭", "就餐", "餐饮", "素面", "素斋", "素宴", "用餐", "餐厅", "美食"],
            "人少": ["避峰", "错峰", "空窗期", "清幽", "拥堵", "人流量", "排队", "高峰", "静默", "清静", "人流",
                     "人多"],
            "人多": ["避峰", "错峰", "空窗期", "清幽", "拥堵", "人流量", "排队", "高峰", "静默", "清静", "人流",
                     "人少"],
            "排队": ["避峰", "错峰", "空窗期", "清幽", "拥堵", "人流量", "排队", "高峰", "拥挤", "人流"]
        }

        for key, value in mapping.items():
            if key in q:
                terms.update(value)

        terms.update(numeric_variants(q))

        # 🌟 优化：建立高频无意义词库，精准拦截虚假繁荣的滑窗词
        STOP_WORDS = {"什么", "哪个", "哪里", "哪些", "可以", "推荐", "一条", "适合", "有些", "一个", "怎么", "如何",
                      "内有", "项目", "有没有"}

        for length in [2, 3, 4, 5, 6]:
            for i in range(len(q) - length + 1):
                sub_word = q[i:i + length]
                if sub_word in STOP_WORDS:
                    continue
                # 单字过滤兜底
                if not re.match(r"^[的是在了和一个吗啥谁哪个去到有没个条首块区内]$", sub_word):
                    terms.add(sub_word)

        return list(terms)

    def search(self, query, top_k=4):
        # 🌟 修复核心：显式将返回的 list 包装成 set 集合类型，确保完美兼容 .update()
        normalized_query = normalize_search_text(query)
        terms = set(self.extract_search_terms(normalized_query))
        expanded_terms = set()
        for term in terms:
            normalized_term = normalize_search_text(term)
            expanded_terms.add(normalized_term)
            expanded_terms.update(numeric_variants(normalized_term))
        terms = {t for t in expanded_terms if t}
        fact_intents = detect_fact_intents(normalized_query)
        subject_terms = extract_subject_terms(normalized_query)
        scored = []

        CORE_DOMAINS = ["灵山", "大佛", "梵宫", "九龙", "胜境", "祥符", "坛城", "拈花"]

        # 隐式语义锚定
        if not any(d in normalized_query for d in CORE_DOMAINS):
            # 🌟 这里的 terms 现在是 set 类型了，调用 update 绝对不会再报错！
            terms.update(CORE_DOMAINS)

        for chunk in self.chunks:
            chunk_lower = normalize_search_text(chunk)
            score = 0
            is_admin_chunk = chunk.startswith("【后台知识】")

            for t in terms:
                if t in chunk_lower:
                    score += 5 if len(t) > 2 else 2

            if score == 0:
                continue

            if is_admin_chunk:
                score += 40

            domain_hit = sum(3 for d in CORE_DOMAINS if d in chunk_lower)
            score += domain_hit

            if any(w in normalized_query for w in ["时间", "多高", "几点", "多长", "哪里", "人少", "错峰", "排队"]):
                if re.search(r"\d+|时|分|处|设|避|空窗|潮汐", chunk_lower):
                    score += 6
            if any(w in normalized_query for w in FACT_WORDS):
                if re.search(r"\d+|一|二|三|四|五|六|七|八|九|十|百|千|万|米|元|时|分", chunk_lower):
                    score += 18
                if re.search(r"\d+(?:\.\d+)?\s*(?:米|元|年|月|日|时|分|公里|万|%|％)", chunk_lower):
                    score += 18

            if fact_intents:
                subject_hit = not subject_terms or any(subject in chunk_lower for subject in subject_terms)
                if subject_terms and not subject_hit:
                    continue
                if subject_hit:
                    score += 25
                else:
                    score -= 25

                for intent in fact_intents:
                    spec = FACT_INTENTS[intent]
                    field_hit = any(field in chunk_lower for field in spec["fields"])
                    unit_hit = any(unit in chunk_lower for unit in spec["units"])
                    numeric_hit = bool(re.search(r"\d+(?:\.\d+)?|[一二三四五六七八九十百千万]+", chunk_lower))
                    if subject_hit and field_hit and numeric_hit:
                        score += 120
                    if subject_hit and unit_hit and numeric_hit:
                        score += 35
                    if field_hit and unit_hit and numeric_hit:
                        score += 70
                    if subject_hit and not numeric_hit:
                        score -= 15

            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)

        seen = set()
        result = []
        for _, c in scored:
            if c not in seen:
                seen.add(c)
                result.append(c)
            if len(result) == top_k:
                break

        return result
