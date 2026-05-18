#!/usr/bin/env python3
"""
BOSS直聘 AI Agent 岗位采集 + 技能分析工具

用法:
  python3 boss_firefox.py                     # 采集+分析
  python3 boss_firefox.py --login             # 首次扫码登录
  python3 boss_firefox.py --headless          # 无头模式
  python3 boss_firefox.py --keywords "AI,Agent"
"""

import argparse
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

# ── 配置 ──
TODAY = date.today().isoformat()
DATE_STR = date.today().strftime("%Y-%m-%d")

DEFAULT_KEYWORDS = [
    "AI Agent开发", "AI Agent", "Agent工程师", "智能体开发",
    "大模型应用开发", "LLM应用开发", "LLM开发", "RAG工程师", "LangChain开发",
    "MCP开发", "AIGC开发", "AI应用开发", "大模型工程师", "Prompt工程师",
]

CITY_CODE = "100010000"
OUTPUT_DIR = Path.home() / "AI" / "岗位日报"
STATE_FILE = Path(__file__).parent / ".boss_profile" / "firefox_state.json"
SALARY_MIN = 15
SALARY_MAX = 35

# ── 反检测脚本 ──
ANTI_DETECT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
Object.defineProperty(navigator, 'plugins', {get: () => [
    {name: 'Chrome PDF Plugin'}, {name: 'Chrome PDF Viewer'}, {name: 'Native Client'}
]});
if (window.Permissions) {
    const orig = window.Permissions.prototype.query;
    window.Permissions.prototype.query = function(d) {
        if (d.name === 'notifications') return Promise.resolve({state: 'prompt'});
        return orig.call(this, d);
    };
}
"""

# ── 技能词库 ──
SKILL_KEYWORDS = {
    "编程语言": {"Python", "Java", "Go", "Golang", "Rust", "C++", "C#", "C", "PHP",
                  "Ruby", "Swift", "Kotlin", "Scala", "TypeScript", "JavaScript", "Node.js"},
    "前端": {"React", "Vue", "Angular", "Next.js", "HTML", "CSS", "Tailwind"},
    "AI/ML框架": {"PyTorch", "TensorFlow", "Transformers", "vLLM", "ONNX", "HuggingFace", "GGUF",
                   "Stable Diffusion", "Diffusion", "Vision", "Multimodal"},
    "AI框架/工具": {"LangChain", "LangGraph", "LlamaIndex", "AutoGen", "CrewAI", "Dify", "Coze", "MCP"},
    "大模型技术": {"RAG", "Fine-tuning", "Finetune", "微调", "SFT", "RLHF", "LoRA", "QLoRA",
                   "Prompt", "Function Calling", "Tool Calling", "Agent", "Multi-Agent",
                   "Embedding", "LLM", "AI Agent", "AIGC"},
    "数据库/中间件": {"MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch",
                      "Milvus", "FAISS", "Chroma", "Qdrant", "Pinecone", "Weaviate",
                      "Kafka", "RabbitMQ"},
    "部署/架构": {"Docker", "Kubernetes", "K8s", "FastAPI", "Flask", "Django", "Spring",
                  "Nginx", "gRPC", "GraphQL", "WebSocket", "REST", "RESTful",
                  "CI/CD", "GitHub Actions", "Linux", "GPU", "CUDA"},
    "云平台": {"AWS", "GCP", "Azure", "阿里云", "腾讯云"},
    "其他": {"数据结构", "算法", "系统设计", "架构", "微服务", "高并发", "分布式",
              "设计模式", "OOP", "TDD", "单元测试", "测试"},
}
ALL_SKILLS = {s for cat in SKILL_KEYWORDS.values() for s in cat}

# 你的技能（用于对比分析）
MY_SKILLS = {
    "编程语言": {"Python", "TypeScript", "JavaScript"},
    "AI框架/工具": {"LangChain", "LangGraph", "AutoGen", "CrewAI", "Dify", "Coze"},
    "大模型技术": {"LLM", "AI Agent", "RAG", "微调(Finetune)", "MCP", "Prompt Engineering",
                   "Function Calling", "Tool Calling", "Embedding"},
    "数据库/向量库": {"MySQL", "Milvus", "FAISS", "Chroma", "Qdrant"},
    "部署/运维": {"Docker", "FastAPI", "Kubernetes"},
    "AI平台/模型": {"Claude", "OpenAI", "GPT"},
}
MY_SKILL_FLAT = {s.lower() for cat in MY_SKILLS.values() for s in cat}


# ══════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════

def decode_salary(text: str) -> str:
    """解码 BOSS U+E030-E039 加密薪资数字"""
    return "".join(str(ord(c) - 0xE030) if 0xE030 <= ord(c) <= 0xE039 else c for c in text)


def salary_in_range(text: str) -> bool:
    """15K <= 薪资 <= 35K"""
    if not text:
        return False
    nums = re.findall(r"(\d+)", re.sub(r"[^\d-]", "", text.replace("~", "-").replace("K", "").replace("k", "")))
    if len(nums) < 2:
        return False
    low, high = int(nums[0]), int(nums[1])
    if low < 5 and high < 20:
        low *= 10
        high *= 10
    return 15 <= low and high <= 35


def human_pause(a=1.0, b=3.0):
    time.sleep(random.uniform(a, b))


def parse_skills(text: str) -> dict:
    """从文本中提取技能，按分类返回"""
    tl = text.lower()
    result = defaultdict(list)
    for cat, skills in SKILL_KEYWORDS.items():
        for s in skills:
            if s.lower() in tl:
                result[cat].append(s)
    return dict(result)


# ══════════════════════════════════════════════
#  浏览器控制
# ══════════════════════════════════════════════

class BossScraper:
    def __init__(self, headless=False):
        self.headless = headless
        self._pw = None
        self._browser = None
        self._ctx = None
        self.page = None

    def start(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.firefox.launch(headless=self.headless)
        ctx_kw = {"viewport": {"width": 1280, "height": 800}, "locale": "zh-CN"}
        if STATE_FILE.exists():
            ctx_kw["storage_state"] = str(STATE_FILE)
        self._ctx = self._browser.new_context(**ctx_kw)
        self.page = self._ctx.new_page()
        self.page.set_default_timeout(30000)
        self.page.add_init_script(ANTI_DETECT)

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def login(self):
        """扫码登录并保存状态"""
        self.page.goto("https://www.zhipin.com/web/user/?ka=header-login")
        human_pause(2, 4)
        self.page.bring_to_front()
        print("\n🔓 浏览器已打开，请扫码登录")

        last_url = self.page.url
        for i in range(600):
            time.sleep(1)
            try:
                url = self.page.evaluate("window.location.href")
            except Exception:
                continue
            if url != last_url and any(p in url for p in ["/web/geek", "/web/chat"]):
                print("✅ 登录成功")
                break
            last_url = url
            if i > 0 and i % 30 == 0:
                print(f"  ⏳ {i}s")

        state = self._ctx.storage_state()
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        print("✅ 状态已保存")

    def _scroll_all(self):
        """滚动到底部再回顶再到底，触发懒加载"""
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            human_pause(2, 3)
            self.page.evaluate("window.scrollTo(0, 0)")
            human_pause(1, 2)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            human_pause(2, 3)
        except Exception:
            pass

    def _extract_links(self) -> list[dict]:
        """提取当前页面上的详情页链接"""
        try:
            return self.page.evaluate("""() => {
                const items = [], seen = new Set();
                document.querySelectorAll('a[href*="/job_detail/"]').forEach(a => {
                    const href = a.href, text = (a.innerText || '').trim();
                    if (href && text && !seen.has(href) && text.length < 60) {
                        seen.add(href);
                        items.push({href, title: text.substring(0, 60)});
                    }
                });
                return items;
            }""")
        except Exception:
            return []

    def search(self, keyword: str) -> list[dict]:
        """搜一个关键词，返回岗位列表（含描述原文）"""
        url = "https://www.zhipin.com/web/geek/job?query=%s&city=%s" % (
            keyword.replace(" ", "+"), CITY_CODE)
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        human_pause(3, 5)
        self._scroll_all()

        body = self.page.inner_text("body")
        lines = [l.strip() for l in body.split("\n") if l.strip()]

        # 1) 定位薪资行
        sal_idx = []
        for i, l in enumerate(lines):
            if re.search(r"\d+[-~]\d+K", decode_salary(l), re.I):
                sal_idx.append(i)

        # 2) 提取基本信息
        jobs = []
        for n, si in enumerate(sal_idx):
            if n > 0 and si - sal_idx[n - 1] < 3:
                continue
            if si == 0:
                continue
            title = lines[si - 1]
            if not (2 < len(title) < 60):
                continue

            salary = decode_salary(lines[si])
            company = exp = edu = city = ""
            end = sal_idx[n + 1] if n + 1 < len(sal_idx) else min(si + 10, len(lines))
            for j in range(si + 1, min(end, len(lines))):
                ln = lines[j]
                if "经验" in ln or "应届" in ln:
                    exp = ln
                elif re.search(r"本科|硕士|博士|大专|学历不限", ln):
                    edu = ln
                elif "·" in ln and len(ln) < 30:
                    city = ln
                elif not company and len(ln) > 2 and len(ln) < 40 \
                        and not re.search(r"年|学历|大专|本科|硕士|博士|不限|应届|·", ln):
                    company = ln

            jobs.append({"title": title, "salary": salary, "company": company,
                         "experience": exp, "education": edu, "city": city,
                         "description": "", "href": ""})

        # 3) 页面底部有"职位描述"段落，关联到最近的上一个岗位
        desc_rows = {i for i, l in enumerate(lines) if "职位描述" in l or "岗位职责" in l}
        for dr in desc_rows:
            # 往前找最近薪资行
            prev_si = max([si for si in sal_idx if si < dr] or [-1])
            if prev_si < 0:
                continue
            # 匹配到对应岗位
            target = None
            for j in jobs:
                if decode_salary(lines[prev_si]) == j["salary"] and lines[prev_si - 1] == j["title"]:
                    target = j
                    break
            if target is None:
                continue
            # 收集描述文本
            seg = []
            for k in range(dr, min(dr + 60, len(lines))):
                if k != dr and ("职位描述" in lines[k] or "岗位职责" in lines[k]):
                    break
                seg.append(lines[k])
            target["description"] = "\n".join(seg)

        # 4) 合并详情页链接（按标题前10字匹配）
        links = self._extract_links()
        if links:
            lmap = {l["title"][:10]: l["href"] for l in links if l["title"][:10]}
            for j in jobs:
                if not j["href"] and j["title"][:10] in lmap:
                    j["href"] = lmap[j["title"][:10]]

        return jobs


# ══════════════════════════════════════════════
#  分析
# ══════════════════════════════════════════════

def skill_gap(jobs: list) -> dict:
    c = Counter()
    ex = defaultdict(list)
    for j in jobs:
        text = (j.get("description") or "") + " " + (j.get("title") or "")
        seen = set()
        for cat, skills in parse_skills(text).items():
            for s in skills:
                if s.lower() not in seen:
                    seen.add(s.lower())
                    c[s] += 1
                    if len(ex[s]) < 3:
                        ex[s].append({"title": j["title"], "company": j.get("company", ""), "salary": j["salary"]})
    have, miss = [], []
    for s, cnt in c.most_common():
        entry = {"skill": s, "count": cnt, "examples": ex.get(s, [])}
        (have if s.lower() in MY_SKILL_FLAT else miss).append(entry)
    return {"have": have, "missing": miss, "total": len(jobs)}


# ══════════════════════════════════════════════
#  输出
# ══════════════════════════════════════════════

def daily_report(jobs: list) -> str:
    lines = ["# 招聘日报 · %s\n" % DATE_STR]
    lines.append("> 来源：**BOSS直聘** · 薪资 **15K-35K** · 共 %d 条\n---\n" % len(jobs))

    # 分类统计
    cc = Counter()
    for j in jobs:
        text = (j.get("description") or "") + " " + (j.get("title") or "")
        seen = set()
        for cat in parse_skills(text):
            if cat not in seen:
                seen.add(cat)
                cc[cat] += 1
    if cc:
        lines.append("### 技能要求分布\n")
        for cat, n in cc.most_common():
            bar = "█" * min(int(n / len(jobs) * 100 / 3), 30)
            lines.append("- %s: %s (%d个岗位, %d%%)" % (cat, bar, n, n * 100 // len(jobs)))
        lines.append("\n---\n")

    for i, j in enumerate(jobs, 1):
        lines.append("### %d. %s %s" % (i, j["title"], j["salary"]))
        lines.append("- 公司: %s" % (j.get("company") or "未显示"))
        if j.get("city"):
            lines.append("- 城市: %s" % j["city"])
        if j.get("experience"):
            lines.append("- 经验: %s" % j["experience"])
        if j.get("education"):
            lines.append("- 学历: %s" % j["education"])
        if j.get("href"):
            lines.append("- 链接: %s" % j["href"])
        desc = j.get("description", "")
        if desc:
            lines.append("")
            lines.append(desc[:1200])
            lines.append("")
        lines.append("---\n")
    lines.append("\n*数据采集于 %s，BOSS直聘*\n" % DATE_STR)
    return "\n".join(lines)


def skill_report(gap: dict, jobs: list) -> str:
    lines = ["# AI Agent 技能差距分析报告 · %s\n" % DATE_STR]
    lines.append("> 基于 BOSS 直聘 %d 个岗位 JD 分析\n---\n" % gap["total"])

    lines.append("## 一、✅ 你已拥有的技能\n")
    for item in gap["have"]:
        bar = "■" * min(item["count"] // 2 + 1, 20)
        lines.append("- **%s**: %s (%d个岗位要求)" % (item["skill"], bar, item["count"]))
    lines.append("")

    lines.append("## 二、🔍 需要查漏补缺\n")
    for item in gap["missing"][:30]:
        bar = "■" * min(item["count"] // 2 + 1, 20)
        p = "🔴" if item["count"] >= 10 else "🟡" if item["count"] >= 5 else "🟢"
        lines.append("- %s **%s**: %s (%d个岗位要求)" % (p, item["skill"], bar, item["count"]))
        if item["examples"]:
            e = item["examples"][0]
            lines.append("  - 例如: %s @ %s (%s)" % (e["title"], e["company"], e["salary"]))
    lines.append("")

    lines.append("## 三、📊 技能分类统计\n")
    cc = Counter()
    for j in jobs:
        text = (j.get("description") or "") + " " + (j.get("title") or "")
        seen = set()
        for cat in parse_skills(text):
            if cat not in seen:
                seen.add(cat)
                cc[cat] += 1
    for cat, n in cc.most_common():
        pct = n * 100 // len(jobs)
        lines.append("- %s: %s %d/%d (%d%%)" % (cat, "█" * min(pct // 3, 30), n, len(jobs), pct))

    lines.append("\n---\n## 📋 完整岗位列表\n")
    for i, j in enumerate(jobs, 1):
        lines.append("### %d. %s" % (i, j["title"]))
        lines.append("- 公司: %s" % (j.get("company") or "未显示"))
        lines.append("- 薪资: %s" % j["salary"])
        desc = j.get("description", "")
        if desc:
            lines.append("\n**岗位要求：**\n```\n%s\n```" % desc[:500])
        lines.append("\n---\n")
    lines.append("\n*数据采集于 %s*\n" % DATE_STR)
    return "\n".join(lines)


def save_links(jobs: list, path: Path):
    with open(path, "w") as f:
        for j in jobs:
            if j.get("href"):
                f.write("%s | %s | %s\n" % (j["title"], j["salary"], j["href"]))


# ══════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="BOSS直聘 AI Agent 岗位采集")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--headless", action="store_true", default=False)
    ap.add_argument("--keywords")
    ap.add_argument("--output", default=str(OUTPUT_DIR))
    ap.add_argument("--no-db", action="store_true")
    ap.add_argument("--max-jobs", type=int, default=64)
    args = ap.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else DEFAULT_KEYWORDS

    if not STATE_FILE.exists() and not args.login:
        print("⚠️ 请先运行: python3 boss_firefox.py --login")
        sys.exit(1)

    sc = BossScraper(headless=args.headless)
    sc.start()
    try:
        if args.login:
            sc.login()
            return

        all_jobs = []
        seen = set()

        for kw in keywords:
            print("\n📌 搜索: 「%s」" % kw)
            try:
                jobs = sc.search(kw)
            except Exception as e:
                print("  ⚠️ 失败: %s" % e)
                continue

            valid = []
            for j in jobs:
                if not salary_in_range(j["salary"]):
                    continue
                key = j["title"] + j["salary"]
                if key not in seen:
                    seen.add(key)
                    valid.append(j)

            print("  📋 %d条，过滤后%d条（累计%d）" % (len(jobs), len(valid), len(all_jobs)))
            all_jobs.extend(valid)
            if len(all_jobs) >= args.max_jobs:
                print("  📊 已达上限%d条" % args.max_jobs)
                break
            human_pause(2, 4)

        print("\n📊 共%d条" % len(all_jobs))
        if not all_jobs:
            return

        # 链接文件
        links_path = out_dir / "岗位链接_%s.txt" % DATE_STR
        save_links(all_jobs, links_path)
        print("🔗 链接: %s (%d条)" % (links_path, sum(1 for j in all_jobs if j.get("href"))))

        # 分析
        gap = skill_gap(all_jobs)
        print("\n" + "=" * 60)
        print("📊 技能差距分析")
        print("=" * 60)
        print("\n✅ 已有:")
        for item in gap["have"][:10]:
            print("  - %s: %d个岗位" % (item["skill"], item["count"]))
        print("\n🔍 需要补:")
        for item in gap["missing"][:15]:
            p = "🔴" if item["count"] >= 10 else "🟡" if item["count"] >= 5 else "🟢"
            print("  %s %s: %d个岗位" % (p, item["skill"], item["count"]))

        # 输出文件
        with open(out_dir / "技能分析报告_%s.md" % DATE_STR, "w") as f:
            f.write(skill_report(gap, all_jobs))
        with open(out_dir / "招聘日报_%s.md" % DATE_STR, "w") as f:
            f.write(daily_report(all_jobs))
        with open(out_dir / "招聘日报_%s.jsonl" % DATE_STR, "w") as f:
            for j in all_jobs:
                f.write(json.dumps({k: v for k, v in j.items() if not k.startswith("_")},
                                   ensure_ascii=False) + "\n")
        print("📄 日报: %s/招聘日报_%s.md" % (out_dir, DATE_STR))

        # MySQL
        if not args.no_db:
            pw = os.environ.get("DB_PASSWORD") or os.environ.get("MYSQL_PWD", "")
            if pw:
                import yaml
                cfg_path = Path(__file__).parent / "config.yaml"
                if cfg_path.exists():
                    with open(cfg_path) as f:
                        cfg = yaml.safe_load(f)
                    db = cfg.get("database", {})
                    host = db.get("host", "127.0.0.1")
                    user = db.get("user", "root")
                    dbname = db.get("database", "ai_jobs_db")
                    for j in all_jobs:
                        sql = ("INSERT IGNORE INTO job_requirements "
                               "(collected_date,title,company,salary,requirement_text) VALUES "
                               "('%s','%s','%s','%s','%s');" % (
                                   TODAY,
                                   j["title"].replace("'", "\\'"),
                                   (j.get("company") or "").replace("'", "\\'"),
                                   j["salary"].replace("'", "\\'"),
                                   (j.get("description") or "")[:300].replace("'", "\\'")))
                        os.system("mysql -h %s -u %s -p'%s' %s -e \"%s\" 2>/dev/null"
                                  % (host, user, pw, dbname, sql))
                    print("💾 已存 MySQL")

        print("\n✅ 完成！")

    finally:
        sc.close()


if __name__ == "__main__":
    main()
