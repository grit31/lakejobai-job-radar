#!/usr/bin/env python3
"""
BOSS直聘 AI Agent 岗位采集 + 技能分析工具

功能:
  1. 采集 BOSS 直聘 AI Agent 相关岗位
  2. 爬取每个岗位的详细 JD（技能要求）
  3. 分析个人技能差距，生成查漏补缺报告

原理:
  - Firefox + Playwright 绕过反爬
  - 注入反检测脚本隐藏 webdriver
  - 模拟人类行为（随机延迟/滚动/鼠标移动）
  - 解码 BOSS 的 U+E030 数字加密

用法:
  python3 boss_firefox.py                 # 完整采集 + 技能分析
  python3 boss_firefox.py --login         # 首次扫码登录
  python3 boss_firefox.py --headless      # 无头模式
  python3 boss_firefox.py --keywords "AI,Agent"
  python3 boss_firefox.py --quick         # 仅列表页（不爬详情）
  python3 boss_firefox.py --max-jobs 30   # 限制采集数量
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

# ============================================================
# 配置
# ============================================================
TODAY = date.today().isoformat()
DATE_STR = date.today().strftime("%Y-%m-%d")

DEFAULT_KEYWORDS = [
    "AI Agent开发", "AI Agent", "Agent工程师", "智能体开发",
    "大模型应用开发", "LLM应用开发", "LLM开发", "RAG工程师", "LangChain开发",
    "MCP开发", "AIGC开发", "AI应用开发", "大模型工程师", "Prompt工程师",
]

SALARY_MIN = 15
SALARY_MAX = 35
CITY_CODE = "100010000"  # 全国
OUTPUT_DIR = Path.home() / "AI" / "岗位日报"
STATE_FILE = Path(__file__).parent / ".boss_profile" / "firefox_state.json"

# ============================================================
# 你的技能清单 — 用于对比分析
# ============================================================
MY_SKILLS = {
    "编程语言": {"Python", "TypeScript", "JavaScript"},
    "AI框架/工具": {"LangChain", "LangGraph", "AutoGen", "CrewAI", "Dify", "Coze"},
    "大模型技术": {"LLM", "AI Agent", "RAG", "微调(Finetune)", "MCP", "Prompt Engineering", "Function Calling", "Tool Calling", "Embedding"},
    "数据库/向量库": {"MySQL", "Milvus", "FAISS", "Chroma", "Qdrant"},
    "部署/运维": {"Docker", "FastAPI", "Kubernetes"},
    "AI平台/模型": {"Claude", "OpenAI", "GPT"},
}

# 所有技能关键词（扁平化，用于匹配 JD）
MY_SKILL_KEYWORDS = set()
for items in MY_SKILLS.values():
    MY_SKILL_KEYWORDS.update(items)

# JD 通用技能词库（用于识别岗位要求的所有技能）
ALL_SKILL_KEYWORDS = MY_SKILL_KEYWORDS | {
    # 编程语言
    "Python", "Java", "Go", "Golang", "Rust", "C++", "C#", "C", "PHP", "Ruby", "Swift", "Kotlin", "Scala",
    "TypeScript", "JavaScript", "Node.js", "Deno",
    # 前端
    "React", "Vue", "Angular", "Next.js", "Nuxt", "HTML", "CSS", "Tailwind", "Webpack",
    # AI/ML
    "PyTorch", "TensorFlow", "Transformers", "vLLM", "ONNX", "HuggingFace", "GGUF",
    "LangChain", "LangGraph", "LlamaIndex", "AutoGen", "CrewAI", "Dify", "Coze", "MCP",
    "RAG", "Fine-tuning", "Finetune", "微调", "SFT", "RLHF", "LoRA", "QLoRA",
    "Prompt", "Function Calling", "Tool Calling", "Agent", "Multi-Agent", "Embedding",
    "Stable Diffusion", "AIGC", "Diffusion", "Vision", "Multimodal",
    # 数据库
    "MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch",
    "Milvus", "FAISS", "Chroma", "Qdrant", "Pinecone", "Weaviate",
    "Kafka", "RabbitMQ", "MQTT",
    # 架构/中间件
    "Docker", "Kubernetes", "K8s", "FastAPI", "Flask", "Django", "Spring", "Spring Boot",
    "Nginx", "gRPC", "GraphQL", "WebSocket", "REST", "RESTful",
    "CI/CD", "GitHub Actions", "GitLab CI", "Jenkins", "ArgoCD",
    # 云/部署
    "AWS", "GCP", "Azure", "阿里云", "腾讯云", "GPU", "CUDA", "Linux",
    # 经典计算机
    "数据结构", "算法", "系统设计", "架构", "微服务", "高并发", "分布式",
    "设计模式", "OOP", "TDD", "单元测试", "测试",
}


def decode_boss_salary(text: str) -> str:
    """解码 BOSS U+E030-E039 加密数字"""
    result = []
    for c in text:
        cp = ord(c)
        if 0xE030 <= cp <= 0xE039:
            result.append(str(cp - 0xE030))
        else:
            result.append(c)
    return "".join(result)


def salary_ok(text: str) -> bool:
    if not text:
        return False
    s = text.replace("~", "-").replace("—", "-").replace("K", "").replace("k", "")
    s = re.sub(r"[^\d-]", "", s)
    nums = re.findall(r"(\d+)", s)
    if len(nums) >= 2:
        low, high = int(nums[0]), int(nums[1])
        if low < 5 and high < 20:
            low *= 10
            high *= 10
        return low >= 15 and high <= 35
    return False


def human_delay(min_s=1.0, max_s=3.0):
    """模拟人类操作的随机延迟"""
    time.sleep(random.uniform(min_s, max_s))


def parse_jd_skills(text: str) -> dict:
    """从 JD 描述中提取技能，分类统计"""
    tl = text.lower()
    found = defaultdict(list)

    for skill in ALL_SKILL_KEYWORDS:
        if skill.lower() in tl:
            # 分类
            if skill in {"Python", "Java", "Go", "Golang", "Rust", "C++", "C#", 
                         "PHP", "Ruby", "Swift", "Kotlin", "Scala", "TypeScript",
                         "JavaScript", "Node.js"}:
                found["编程语言"].append(skill)
            elif skill in {"React", "Vue", "Angular", "Next.js", "HTML", "CSS", "Tailwind"}:
                found["前端"].append(skill)
            elif skill in {"PyTorch", "TensorFlow", "Transformers", "vLLM", "ONNX", 
                          "HuggingFace", "Stable Diffusion", "Diffusion", "Vision", "Multimodal"}:
                found["AI/ML框架"].append(skill)
            elif skill in {"LangChain", "LangGraph", "LlamaIndex", "AutoGen", "CrewAI", "Dify", "Coze", "MCP"}:
                found["AI框架/工具"].append(skill)
            elif skill in {"RAG", "Fine-tuning", "Finetune", "微调", "SFT", "RLHF", "LoRA", "QLoRA",
                          "Prompt", "Function Calling", "Tool Calling", "Agent", "Multi-Agent",
                          "Embedding", "LLM"}:
                found["大模型技术"].append(skill)
            elif skill in {"MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch",
                          "Milvus", "FAISS", "Chroma", "Qdrant", "Pinecone", "Weaviate",
                          "Kafka", "RabbitMQ"}:
                found["数据库/中间件"].append(skill)
            elif skill in {"Docker", "Kubernetes", "K8s", "FastAPI", "Flask", "Django", "Spring",
                          "Nginx", "gRPC", "GraphQL", "WebSocket", "CI/CD", "GitHub Actions",
                          "Linux", "GPU", "CUDA"}:
                found["部署/架构"].append(skill)
            elif skill in {"AWS", "GCP", "Azure", "阿里云", "腾讯云"}:
                found["云平台"].append(skill)
            else:
                found["其他"].append(skill)

    return dict(found)


def analyze_skill_gap(all_jobs: list) -> dict:
    """分析技能差距：岗位要求 vs 个人技能"""
    skill_counter = Counter()
    skill_jd_examples = defaultdict(list)

    for job in all_jobs:
        # 从 JD 描述 + 岗位标题 中分析技能
        jd_text = (job.get("description", "") or "") + " " + (job.get("title", "") or "")
        jd_skills = parse_jd_skills(jd_text)

        # 统计每个技能的出现次数
        seen_in_job = set()
        for cat, skills in jd_skills.items():
            for s in skills:
                s_lower = s.lower()
                if s_lower not in seen_in_job:
                    seen_in_job.add(s_lower)
                    skill_counter[s] += 1

        # 记录示例（每个技能取前3个 JD）
        for cat, skills in jd_skills.items():
            for s in skills:
                if len(skill_jd_examples[s]) < 3:
                    skill_jd_examples[s].append({
                        "title": job["title"],
                        "company": job.get("company", ""),
                        "salary": job["salary"],
                    })

    # 分类
    my_skills_set = {s.lower() for s in MY_SKILL_KEYWORDS}

    have = []
    missing = []

    for skill, count in skill_counter.most_common():
        examples = skill_jd_examples.get(skill, [])
        entry = {"skill": skill, "count": count, "examples": examples}
        if skill.lower() in my_skills_set:
            have.append(entry)
        else:
            missing.append(entry)

    return {"have": have, "missing": missing, "total_jobs": len(all_jobs)}


# ============================================================
# 反检测脚本
# ============================================================
ANTI_DETECT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
// 添加更多插件
Object.defineProperty(navigator, 'plugins', {get: () => [
    {name: 'Chrome PDF Plugin'},
    {name: 'Chrome PDF Viewer'},
    {name: 'Native Client'}
]});
// 覆盖权限查询
if (window.Permissions) {
    const orig = window.Permissions.prototype.query;
    window.Permissions.prototype.query = function(d) {
        if (d.name === 'notifications') return Promise.resolve({state: 'prompt'});
        return orig.call(this, d);
    };
}
"""


class BossFirefoxScraper:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.firefox.launch(headless=self.headless)

        ctx_kwargs = {
            "viewport": {"width": 1280, "height": 800},
            "locale": "zh-CN",
        }
        if STATE_FILE.exists():
            ctx_kwargs["storage_state"] = str(STATE_FILE)

        self.context = self.browser.new_context(**ctx_kwargs)
        self.page = self.context.new_page()
        self.page.set_default_timeout(30000)
        self.page.add_init_script(ANTI_DETECT)

    def login(self):
        self.page.goto("https://www.zhipin.com/web/user/?ka=header-login")
        human_delay(2, 4)
        self.page.bring_to_front()

        print("\n🔓 浏览器已打开 BOSS 直聘登录页")
        print("请扫码登录，检测到登录后自动保存状态...")

        last_url = self.page.url
        for i in range(600):
            time.sleep(1)
            try:
                url = self.page.evaluate("window.location.href")
            except Exception:
                continue
            if url != last_url:
                if any(p in url for p in ["/web/geek", "/web/chat", "/web/expect", "/web/message"]):
                    print(f"✅ 登录成功!")
                    break
                last_url = url
            if i > 0 and i % 30 == 0:
                print(f"  ⏳ {i}s...")

        state = self.context.storage_state()
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        print(f"✅ 登录状态已保存")

    def human_scroll(self, times=3):
        """模拟人类滚动页面"""
        for _ in range(times):
            try:
                offset = random.randint(300, 700)
                self.page.evaluate(f"window.scrollBy(0, {offset})")
                human_delay(0.8, 2.0)
            except Exception:
                break

    def get_listing_links(self, keyword: str) -> list[dict]:
        """获取搜索结果页的岗位信息（含薪资）"""
        encoded = keyword.replace(" ", "+")
        url = f"https://www.zhipin.com/web/geek/job?query={encoded}&city={CITY_CODE}"

        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        human_delay(3, 5)
        self.human_scroll(3)
        human_delay(1, 2)

        # 从 body 文本中提取岗位信息
        body = self.page.inner_text("body")
        lines = [l.strip() for l in body.split("\n") if l.strip()]

        jobs = []
        for i, line in enumerate(lines):
            decoded = decode_boss_salary(line)
            if re.search(r"\d+[-~]\d+K", decoded, re.I):
                if i > 0 and lines[i - 1] and 2 < len(lines[i - 1]) < 60:
                    title = lines[i - 1]
                    salary = decoded
                    company = ""
                    experience = ""
                    education = ""
                    city = ""
                    for j in range(i + 1, min(i + 5, len(lines))):
                        ln = lines[j]
                        if "经验" in ln or "应届" in ln:
                            experience = ln
                        elif "本科" in ln or "硕士" in ln or "博士" in ln or "大专" in ln or "学历不限" in ln:
                            education = ln
                        elif "·" in ln and len(ln) < 30:
                            city = ln
                        elif len(ln) > 2 and len(ln) < 40 and not re.search(r"年|学历|大专|本科|硕士|博士|不限|应届|·", ln) and not experience and not education:
                            company = ln
                    jobs.append({"title": title, "salary": salary, "company": company,
                                "experience": experience, "education": education, "city": city, "href": ""})

        # 同时提取详情页链接
        links = self._extract_links_from_page(keyword)
        # 把链接合并到 jobs 中（按 title 匹配）
        if links:
            link_map = {}
            for l in links:
                t = l["title"][:10]
                if t:
                    link_map[t] = l["href"]
            for j in jobs:
                t = j["title"][:10]
                if t in link_map and not j["href"]:
                    j["href"] = link_map[t]

        return jobs

    def _extract_links_from_page(self, keyword: str) -> list[dict]:
        """从当前页面提取岗位详情页链接"""
        try:
            js = """
            (() => {
                const items = [];
                const seen = new Set();
                const links = document.querySelectorAll('a[href*="/job_detail/"]');
                for (const a of links) {
                    const href = a.href;
                    const text = (a.innerText || '').trim();
                    if (href && text && !seen.has(href) && text.length > 1 && text.length < 60) {
                        seen.add(href);
                        items.push({href: href, title: text.substring(0, 60)});
                    }
                }
                return items;
            })()
            """
            return self.page.evaluate(js)
        except Exception as e:
            print(f"  ⚠️ 提取链接失败: {e}")
            return []

    def fetch_jd_detail(self, url: str) -> dict:
        """爬取单个岗位的详情 JD"""
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        human_delay(2, 4)

        # 模拟人类阅读
        self.human_scroll(2)

        detail = self.page.evaluate("""() => {
            const get = (selectors) => {
                for (const s of selectors) {
                    const el = document.querySelector(s);
                    if (el) return el.innerText.trim();
                }
                return '';
            };
            return {
                name: get(['.job-name', '.name', 'h1', '.job-title']),
                salary: get(['.salary', '.job-salary', '[class*=salary]']),
                company: get(['.company-name', '.company-info h2', '[class*=company-name]', '[class*=company]']),
                description: get(['.job-sec-text', '.job-detail-section .text', '.job-description',
                                 '[class*=job-sec-text]', '[class*=detail-content]']),
                tags: (() => {
                    const els = document.querySelectorAll('.tag-item, .job-tags span, [class*=tag]');
                    return Array.from(els).map(e => e.innerText.trim()).filter(Boolean).slice(0, 20);
                })(),
            };
        }""")

        # 公司名如果太长则截断
        company = detail.get("company", "")
        if len(company) > 40:
            company = company[:40]

        return {
            "url": url,
            "title": detail.get("name", ""),
            "salary": decode_boss_salary(detail.get("salary", "")),
            "company": company,
            "description": detail.get("description", ""),
            "tags": detail.get("tags", []),
        }

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


# ============================================================
# 报告生成
# ============================================================
def render_skill_report(gap: dict, jobs: list) -> str:
    lines = [f"# AI Agent 技能差距分析报告 · {DATE_STR}\n"]
    lines.append(f"> 基于 BOSS 直聘 {gap['total_jobs']} 个 AI Agent 相关岗位 JD 分析\n---\n")

    # 一、你已拥有的技能（市场需求验证）
    lines.append("## 一、✅ 你已拥有的技能")
    lines.append("> 这些技能市场上有需求，你已掌握。\n")

    have_sorted = sorted(gap["have"], key=lambda x: -x["count"])
    for item in have_sorted:
        bar = "■" * min(item["count"] // 2 + 1, 20)
        lines.append(f"- **{item['skill']}**: {bar} ({item['count']}个岗位要求)")
        if item["examples"]:
            ex = item["examples"][0]
            lines.append(f"  - 例如: {ex['title']} @ {ex['company']} ({ex['salary']})")
    lines.append("")

    # 二、查漏补缺 — 市场需要但你不会的技能
    lines.append("## 二、🔍 需要查漏补缺")
    lines.append("> 这些技能市场上有大量需求，建议优先学习。\n")

    missing_sorted = sorted(gap["missing"], key=lambda x: -x["count"])
    for item in missing_sorted[:30]:
        bar = "■" * min(item["count"] // 2 + 1, 20)
        priority = "🔴" if item["count"] >= 10 else "🟡" if item["count"] >= 5 else "🟢"
        lines.append(f"- {priority} **{item['skill']}**: {bar} ({item['count']}个岗位要求)")
        if item["examples"]:
            ex = item["examples"][0]
            lines.append(f"  - 例如: {ex['title']} @ {ex['company']} ({ex['salary']})")
    lines.append("")

    # 三、按岗位技能分类统计
    lines.append("## 三、📊 技能分类统计")
    lines.append("> 岗位要求技能的分布情况\n")

    cat_counter = Counter()
    for job in jobs:
        jd = job.get("description", "") or ""
        title = job.get("title", "") or ""
        text = jd + " " + title
        skills = parse_jd_skills(text)
        seen_cats = set()
        for cat in skills:
            cat_lower = cat.lower()
            if cat_lower not in seen_cats:
                seen_cats.add(cat_lower)
                cat_counter[cat] += 1

    for cat, count in cat_counter.most_common():
        pct = count / len(jobs) * 100 if jobs else 0
        bar = "█" * min(int(pct // 3), 30)
        lines.append(f"- {cat}: {bar} {count}/{len(jobs)} ({pct:.0f}%)")

    lines.append("\n---\n## 📋 完整岗位列表\n")

    for i, j in enumerate(jobs, 1):
        lines.append(f"### {i}. {j['title']}")
        lines.append(f"- 公司: {j.get('company', '未显示')}")
        lines.append(f"- 薪资: {j['salary']}")
        if j.get("experience"):
            lines.append(f"- 经验: {j['experience']}")

        # JD 摘要
        desc = j.get("description", "") or ""
        if desc:
            # 提取关键技能
            skills = parse_jd_skills(desc)
            if skills:
                tags = []
                for cat, items in skills.items():
                    tags.extend(items)
                lines.append(f"- 技能要求: {' '.join(f'`{t}`' for t in tags[:10])}")
            lines.append("\n**岗位要求：**\n```\n" + desc[:500] + "\n```")
        lines.append("\n---\n")

    lines.append(f"\n*数据采集于 {DATE_STR}，BOSS直聘*\n")
    return "\n".join(lines)


def render_daily_report(jobs: list) -> str:
    lines = [f"# 招聘日报 · {DATE_STR}\n"]
    lines.append(f"> 来源：**BOSS直聘** · 薪资 **15K-35K** · 共 {len(jobs)} 条\n---\n")

    # 技能分类统计
    cat_counter = Counter()
    for j in jobs:
        desc = j.get("description", "") or ""
        title = j.get("title", "") or ""
        text = desc + " " + title
        skills = parse_jd_skills(text)
        seen = set()
        for cat in skills:
            if cat not in seen:
                seen.add(cat)
                cat_counter[cat] += 1

    if cat_counter:
        lines.append("### 技能要求分布\n")
        for cat, count in cat_counter.most_common():
            pct = count / len(jobs) * 100 if jobs else 0
            bar = "█" * min(int(pct // 3), 30)
            lines.append(f"- {cat}: {bar} ({count}个岗位, {pct:.0f}%)")
        lines.append("\n---\n")

    for i, j in enumerate(jobs, 1):
        lines.append("### %d. %s %s" % (i, j['title'], j['salary']))
        lines.append("- 公司: %s" % (j.get('company', '未显示')))
        if j.get("city"):
            lines.append("- 城市: %s" % j['city'])
        if j.get("experience"):
            lines.append("- 经验: %s" % j['experience'])
        if j.get("education"):
            lines.append("- 学历: %s" % j['education'])
        if j.get("url"):
            lines.append("- 链接: %s" % j['url'])
        desc = j.get("description", "") or ""
        if desc:
            tags_list = []
            for cat, items in parse_jd_skills(desc).items():
                tags_list.extend(items)
            if tags_list:
                tags_str = " ".join("`%s`" % t for t in tags_list[:12])
                lines.append("- 技能: %s" % tags_str)
            lines.append("")
            lines.append(desc[:1200])
            lines.append("")
        else:
            title = j.get("title", "")
            if title:
                tags_list = []
                for cat, items in parse_jd_skills(title).items():
                    tags_list.extend(items)
                if tags_list:
                    tags_str = " ".join("`%s`" % t for t in tags_list[:5])
                    lines.append("- 技能: %s" % tags_str)
        lines.append("---")
        lines.append("")

    lines.append(f"\n*数据采集于 {DATE_STR}，BOSS直聘*\n")
    return "\n".join(lines)


def save_to_mysql(jobs: list):
    db_password = os.environ.get("DB_PASSWORD", "") or os.environ.get("MYSQL_PWD", "")
    if not db_password:
        cfg_path = Path(__file__).parent / "config.yaml"
        if cfg_path.exists():
            try:
                import yaml
                with open(cfg_path) as f:
                    cfg = yaml.safe_load(f)
                db_cfg = cfg.get("database", {})
                host = db_cfg.get("host", "127.0.0.1")
                user = db_cfg.get("user", "root")
                database = db_cfg.get("database", "ai_jobs_db")
                db_password = db_cfg.get("password", "")
            except Exception:
                return
        else:
            return

    if not db_password:
        return

    for j in jobs:
        title = j["title"].replace("'", "\\'")
        company = (j.get("company") or "").replace("'", "\\'")
        salary = j["salary"].replace("'", "\\'")
        desc = (j.get("description") or "")[:300].replace("'", "\\'")
        sql = f"""INSERT IGNORE INTO job_requirements 
(collected_date,title,company,salary,requirement_text)
VALUES ('{TODAY}','{title}','{company}','{salary}','{desc}');"""
        os.system(
            f'mysql -h {host} -u {user} -p\'{db_password}\' {database} -e "{sql}" 2>/dev/null'
        )
    print(f"💾 已存 MySQL")


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="BOSS直聘 AI Agent 岗位采集 + 技能分析")
    parser.add_argument("--login", action="store_true", help="首次扫码登录")
    parser.add_argument("--headless", action="store_true", default=False)
    parser.add_argument("--keywords", help="关键词逗号分隔")
    parser.add_argument("--salary-min", type=int, default=SALARY_MIN)
    parser.add_argument("--salary-max", type=int, default=SALARY_MAX)
    parser.add_argument("--output", default=str(OUTPUT_DIR))
    parser.add_argument("--no-db", action="store_true")
    parser.add_argument("--quick", action="store_true", help="仅列表页，不爬详情")
    parser.add_argument("--max-jobs", type=int, default=64, help="最多采集岗位数")
    parser.add_argument("--max-detail", type=int, default=0, help="最多爬详情页数（0=不爬详情，默认不爬）")
    args = parser.parse_args()

    salary_min = args.salary_min
    salary_max = args.salary_max

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else DEFAULT_KEYWORDS
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not STATE_FILE.exists() and not args.login:
        print("⚠️ 未检测到登录状态，请先运行: python3 boss_firefox.py --login")
        sys.exit(1)

    scraper = BossFirefoxScraper(headless=args.headless)
    scraper.start()

    try:
        if args.login:
            scraper.login()
            print("✅ 登录完成")
            return

        all_jobs = []
        seen_titles = set()

        # Phase 1: 搜索所有关键词，获取列表
        for kw in keywords:
            print(f"\n📌 搜索: 「{kw}」")
            try:
                links = scraper.get_listing_links(kw)
            except Exception as e:
                print(f"  ⚠️ 失败: {e}")
                continue

            # 过滤薪资
            filtered = []
            for link in links:
                name = link.get("title", "")
                salary_raw = link.get("salary", "")
                salary = decode_boss_salary(salary_raw) if salary_raw else ""
                if not salary or not salary_ok(salary):
                    continue
                key = name + salary
                if key not in seen_titles:
                    seen_titles.add(key)
                    filtered.append(link)

            print(f"  📋 找到 {len(links)} 条，薪资过滤后 {len(filtered)} 条（累计 {len(all_jobs)}）")

            all_jobs.extend([{
                "title": link["title"],
                "salary": link.get("salary", ""),
                "company": link.get("company", ""),
                "experience": link.get("experience", ""),
                "education": link.get("education", ""),
                "city": link.get("city", ""),
                "description": "",
                "tags": [],
                "keyword": kw,
                "url": link.get("href", ""),
            } for link in filtered])

            if len(all_jobs) >= args.max_jobs:
                print(f"  📊 已达上限 {args.max_jobs} 条")
                break

            human_delay(2, 4)

        print(f"\n📊 共获取 {len(all_jobs)} 条岗位")

        if not all_jobs:
            print("❌ 没有符合条件的岗位")
            return

        # Phase 2: 爬取详情页 JD（除非 --quick）
        if not args.quick:
            print("\n🔍 开始爬取岗位详情（模拟人工浏览，每页停留 3-5 秒）...")
            detail_count = 0
            detail_limit = min(args.max_detail, len(all_jobs))

            for i, job in enumerate(all_jobs):
                if detail_count >= detail_limit:
                    break
                if not job.get("url"):
                    continue

                try:
                    print(f"  [{detail_count+1}/{detail_limit}] {job['title'][:25]:25s}", end=" ", flush=True)
                    detail = scraper.fetch_jd_detail(job["url"])
                    
                    # 用详情页薪资重新过滤
                    detail_salary = detail.get("salary", "") or job["salary"]
                    if not salary_ok(detail_salary):
                        print(f"⏭️ 薪资 {detail_salary} 不在范围内")
                        continue
                    
                    job["title"] = detail["title"] or job["title"]
                    job["salary"] = detail_salary
                    job["company"] = detail["company"]
                    job["description"] = detail["description"]
                    job["tags"] = detail.get("tags", [])

                    # 从 description 中提取经验和学历
                    desc = job["description"]
                    if desc:
                        exp_match = re.search(r"(\d+[-~]\d+年|\d+年以上|经验不限|应届)", desc)
                        if exp_match:
                            job["experience"] = exp_match.group(1)
                        edu_match = re.search(r"(本科|硕士|博士|大专|学历不限)", desc)
                        if edu_match:
                            job["education"] = edu_match.group(1)

                    skills = parse_jd_skills(desc)
                    skill_tags = []
                    for cat, items in skills.items():
                        skill_tags.extend(items)
                    print(f"✅ {', '.join(skill_tags[:5])}")
                    detail_count += 1

                except Exception as e:
                    print(f"⚠️ {e}")

                # 每爬3个详情页休息一下（模拟真实浏览）
                if detail_count % 3 == 0:
                    print(f"  💤 休息 {random.uniform(2, 4):.0f} 秒...")
                    human_delay(2, 4)

        # 输出
        print(f"\n{'='*60}")
        print(f"📊 共采集 {len(all_jobs)} 条，其中 {sum(1 for j in all_jobs if j.get('url'))} 条有详情链接")

        # 保存详情页链接
        links_path = out_dir / f"岗位链接_{DATE_STR}.txt"
        with open(links_path, "w") as f:
            for j in all_jobs:
                if j.get("url"):
                    f.write("%s | %s | %s\n" % (j['title'], j['salary'], j['url']))
        print(f"🔗 链接文件: {links_path} ({sum(1 for j in all_jobs if j.get('url'))} 条)")

        # 技能分析
        gap = analyze_skill_gap(all_jobs)

        print(f"\n{'='*60}")
        print("📊 技能差距分析")
        print(f"{'='*60}")
        print(f"\n✅ 你已有的技能（市场需求验证）:")
        for item in sorted(gap["have"], key=lambda x: -x["count"])[:10]:
            print(f"  - {item['skill']}: {item['count']}个岗位要求")

        print(f"\n🔍 需要查漏补缺:")
        for item in sorted(gap["missing"], key=lambda x: -x["count"])[:15]:
            priority = "🔴" if item["count"] >= 10 else "🟡" if item["count"] >= 5 else "🟢"
            print(f"  {priority} {item['skill']}: {item['count']}个岗位要求")

        # 生成报告
        skill_report = render_skill_report(gap, all_jobs)
        skill_path = out_dir / f"技能分析报告_{DATE_STR}.md"
        with open(skill_path, "w") as f:
            f.write(skill_report)
        print(f"\n📄 技能分析报告: {skill_path}")

        # 生成日报
        if not args.quick:
            daily_report = render_daily_report(all_jobs)
            daily_path = out_dir / f"招聘日报_{DATE_STR}.md"
            with open(daily_path, "w") as f:
                f.write(daily_report)
            print(f"📄 招聘日报: {daily_path}")

        # JSONL
        jsonl_path = out_dir / f"招聘日报_{DATE_STR}.jsonl"
        with open(jsonl_path, "w") as f:
            for j in all_jobs:
                clean = {k: v for k, v in j.items() if not k.startswith("_")}
                f.write(json.dumps(clean, ensure_ascii=False) + "\n")
        print(f"📄 JSONL: {jsonl_path}")

        # MySQL
        if not args.no_db:
            save_to_mysql(all_jobs)

        print(f"\n✅ 全部完成！")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
