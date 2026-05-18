#!/usr/bin/env python3
"""
BOSS直聘 AI Agent 岗位采集器 — 基于 Playwright + Firefox

绕过 BOSS 直聘反爬的关键：
  1. 使用 Firefox 浏览器（Chromium 会被检测）
  2. 注入反检测脚本隐藏 webdriver 特征
  3. 解码 BOSS 的 U+E030 数字加密

用法:
  python3 boss_firefox.py                          # 采集并生成日报
  python3 boss_firefox.py --login                  # 首次扫码登录
  python3 boss_firefox.py --headless               # 无头模式（登录后）
  python3 boss_firefox.py --keywords "AI,Agent"    # 自定义关键词
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

# ============================================================
# 配置
# ============================================================
TODAY = date.today().isoformat()
DATE_STR = date.today().strftime("%Y-%m-%d")

DEFAULT_KEYWORDS = [
    "AI Agent开发",
    "AI Agent",
    "Agent工程师",
    "智能体开发",
    "大模型应用开发",
    "LLM应用开发",
    "LLM开发",
    "RAG工程师",
    "LangChain开发",
]

SALARY_MIN = 15   # 最低薪资 (K)
SALARY_MAX = 35   # 最高薪资 (K)
CITY_CODE = "100010000"  # 全国
OUTPUT_DIR = Path.home() / "AI" / "岗位日报"
STATE_FILE = Path(__file__).parent / ".boss_profile" / "firefox_state.json"

# ============================================================
# BOSS 直聘字符解码
# ============================================================
def decode_boss_salary(text: str) -> str:
    """
    BOSS 直聘用 U+E030-E039 替代 0-9 来加密薪资数字。
    例如: U+E036-U+E032U+E031K → 6-21K
    """
    result = []
    for c in text:
        cp = ord(c)
        if 0xE030 <= cp <= 0xE039:
            result.append(str(cp - 0xE030))
        else:
            result.append(c)
    return "".join(result)


def salary_ok(text: str) -> bool:
    """检查薪资是否在范围内"""
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
        return low <= SALARY_MAX and high >= SALARY_MIN
    return False


def exp_ok(text: str) -> bool:
    if not text:
        return False
    if "经验不限" in text or "应届" in text:
        return True
    nums = re.findall(r"(\d+)", text)
    if len(nums) >= 2:
        lv, hv = int(nums[0]), int(nums[1])
        return lv <= 5 and hv >= 1
    return False


# ============================================================
# 技能分类
# ============================================================
CATEGORIES = {
    "编程语言": ["python", "java", "go", "golang", "rust", "c++", "typescript", "javascript", "js", "ts"],
    "AI/ML框架": ["langchain", "llamaindex", "pytorch", "tensorflow", "transformers", "vllm", "onnx", "huggingface", "langgraph", "autogen", "crewai"],
    "大模型技术": ["大模型", "llm", "gpt", "rag", "agent", "prompt", "微调", "finetune", "embedding", "mcp", "function calling", "tool calling"],
    "数据库": ["mysql", "redis", "mongodb", "elasticsearch", "milvus", "pinecone", "kafka", "faiss", "qdrant", "chroma"],
    "部署运维": ["docker", "kubernetes", "k8s", "gpu", "cuda", "serving", "devops", "ci/cd", "linux", "fastapi"],
    "架构设计": ["架构", "微服务", "高并发", "分布式", "系统设计", "工作流", "多智能体", "multi-agent"],
}


def classify(text: str) -> dict:
    tl = text.lower()
    result = {}
    for cat, kws in CATEGORIES.items():
        found = [kw for kw in kws if kw.lower() in tl]
        if found:
            result[cat] = found
    return result


# ============================================================
# 浏览器管理
# ============================================================
ANTI_DETECT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
"""


class BossFirefoxScraper:
    """BOSS直聘 Firefox 爬虫"""

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
            print(f"📂 加载已保存的登录状态")

        self.context = self.browser.new_context(**ctx_kwargs)
        self.page = self.context.new_page()
        self.page.set_default_timeout(30000)
        self.page.add_init_script(ANTI_DETECT_SCRIPT)

    def login(self):
        """首次扫码登录，保存状态"""
        self.page.goto("https://www.zhipin.com/web/user/?ka=header-login")
        time.sleep(3)
        self.page.bring_to_front()

        print("\n🔓 浏览器已打开 BOSS 直聘登录页")
        print("请用微信扫码登录，等待检测...")

        last_url = self.page.url
        for i in range(600):
            time.sleep(1)
            try:
                url = self.page.evaluate("window.location.href")
            except Exception:
                continue
            if url != last_url:
                print(f"  URL 变化: {url[:60]}...")
                last_url = url
                if any(p in url for p in ["/web/geek", "/web/chat", "/web/expect", "/web/message"]):
                    print("✅ 登录成功!")
                    break
            if i > 0 and i % 30 == 0:
                print(f"  ⏳ {i}s...")

        # 保存状态
        state = self.context.storage_state()
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        print(f"✅ 登录状态已保存 ({len(state.get('cookies', []))} cookies)")

    def search_keyword(self, keyword: str) -> list[dict]:
        """搜索单个关键词，返回岗位列表"""
        encoded = keyword.replace(" ", "+")
        url = f"https://www.zhipin.com/web/geek/job?query={encoded}&city={CITY_CODE}"

        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)

        # 滚动触发懒加载
        for _ in range(3):
            try:
                self.page.evaluate("window.scrollBy(0, 500)")
                time.sleep(1)
            except Exception:
                break

        body = self.page.inner_text("body")
        lines = [l.strip() for l in body.split("\n") if l.strip()]

        jobs = []
        for i, line in enumerate(lines):
            decoded = decode_boss_salary(line)
            if re.search(r"\d+[-~]\d+K", decoded, re.I):
                if i > 0 and lines[i - 1] and 2 < len(lines[i - 1]) < 60:
                    title = lines[i - 1]
                    salary_decoded = decoded

                    # 找公司名（后面的非经验/学历行）
                    company = ""
                    for j in range(i + 1, min(i + 4, len(lines))):
                        ln = lines[j]
                        if len(ln) > 2 and len(ln) < 50 and not re.search(r"年|学历|大专|本科|硕士|博士|不限|应届", ln):
                            company = ln
                            break

                    # 找经验/学历（在薪资和公司之间）
                    exp_text = ""
                    edu_text = ""
                    for j in range(i + 1, min(i + 4, len(lines))):
                        ln = lines[j]
                        if "经验" in ln or "应届" in ln:
                            exp_text = ln
                        if "本科" in ln or "硕士" in ln or "博士" in ln or "大专" in ln or "学历" in ln:
                            edu_text = ln

                    jobs.append({
                        "title": title,
                        "salary": salary_decoded,
                        "company": company,
                        "experience": exp_text,
                        "education": edu_text,
                        "keyword": keyword,
                    })

        return jobs

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


# ============================================================
# 日报生成
# ============================================================
def render_daily_report(jobs: list[dict]) -> str:
    lines = [f"# 招聘日报 · {DATE_STR}\n"]
    lines.append(
        f"> 来源：**BOSS直聘** · "
        f"关键词 **AI Agent / 大模型 / LLM / RAG / Agent** · "
        f"薪资 **{SALARY_MIN}K-{SALARY_MAX}K** · "
        f"共 {len(jobs)} 条\n---\n"
    )

    # 技能分类统计
    cc = {}
    for j in jobs:
        for cat in classify(j["title"] + " " + j.get("experience", "") + " " + j.get("education", "")):
            cc[cat] = cc.get(cat, 0) + 1
    if cc:
        lines.append("### 技能要求分布\n")
        for c, n in sorted(cc.items(), key=lambda x: -x[1]):
            bar = "■" * min(n, 20)
            lines.append(f"- {c}: {bar} ({n}条)")
        lines.append("\n---\n")

    lines.append("## 岗位列表\n")
    for i, j in enumerate(jobs, 1):
        lines.append(f"### {i}. {j['title']}")
        lines.append(f"- 公司: {j.get('company', '未显示')}")
        lines.append(f"- 薪资: {j['salary']}")
        if j.get("experience"):
            lines.append(f"- 经验: {j['experience']}")
        if j.get("education"):
            lines.append(f"- 学历: {j['education']}")
        lines.append(f"- 关键词: {j['keyword']}")

        cl = classify(j["title"] + " " + j.get("experience", "") + " " + j.get("education", ""))
        if cl:
            lines.append("  " + " ".join(f"`{c}`" for c in cl))
        lines.append("\n---\n")

    lines.append(f"\n---\n*数据采集于 {DATE_STR}，BOSS直聘 - Firefox + Playwright*\n")
    return "\n".join(lines)


# ============================================================
# MySQL 存储
# ============================================================
def save_to_mysql(jobs: list[dict]):
    """存到 MySQL 数据库"""
    db_password = os.environ.get("DB_PASSWORD", "") or os.environ.get("MYSQL_PWD", "")
    if not db_password:
        # 尝试找 config.yaml
        cfg_path = Path(__file__).parent / "config.yaml"
        if cfg_path.exists():
            try:
                import yaml
                with open(cfg_path) as f:
                    cfg = yaml.safe_load(f)
                db_cfg = cfg.get("database", {})
                db_password = db_cfg.get("password", "")
                host = db_cfg.get("host", "127.0.0.1")
                user = db_cfg.get("user", "root")
                database = db_cfg.get("database", "ai_jobs_db")
            except Exception:
                pass
        else:
            host, user, database = "127.0.0.1", "root", "ai_jobs_db"

    if not db_password:
        print("💾 MySQL 跳过（未配置密码，设置 DB_PASSWORD 环境变量）")
        return

    count = 0
    for j in jobs:
        cls = classify(j["title"] + " " + j.get("experience", "") + " " + j.get("education", ""))
        for cat, kws in cls.items():
            kw_str = ",".join(kws)
            title = j["title"].replace("'", "\\'")
            company = (j.get("company") or "").replace("'", "\\'")
            salary = j["salary"].replace("'", "\\'")
            exp = (j.get("experience") or "").replace("'", "\\'")
            edu = (j.get("education") or "").replace("'", "\\'")
            cat_safe = cat.replace("'", "\\'")

            sql = f"""INSERT IGNORE INTO job_requirements 
(collected_date,title,company,salary,experience,education,requirement_category,requirement_text)
VALUES ('{TODAY}','{title}','{company}','{salary}',
'{exp}','{edu}','{cat_safe}','{kw_str}');"""
            os.system(
                f'mysql -h {host} -u {user} -p\'{db_password}\' {database} -e "{sql}" 2>/dev/null'
            )
            count += 1

    print(f"💾 已存 MySQL: {count} 条")


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="BOSS直聘 AI Agent 岗位采集器 (Firefox)")
    parser.add_argument("--login", action="store_true", help="首次扫码登录并保存状态")
    parser.add_argument("--headless", action="store_true", default=False, help="无头模式（登录后可用）")
    parser.add_argument("--keywords", help="关键词用逗号分隔，默认使用 AI Agent 关键词集")
    parser.add_argument("--salary-min", type=int, default=SALARY_MIN)
    parser.add_argument("--salary-max", type=int, default=SALARY_MAX)
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="日报输出目录")
    parser.add_argument("--no-db", action="store_true", help="不存 MySQL")
    args = parser.parse_args()

    global SALARY_MIN, SALARY_MAX
    SALARY_MIN = args.salary_min
    SALARY_MAX = args.salary_max

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else DEFAULT_KEYWORDS
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    scraper = BossFirefoxScraper(headless=args.headless)
    scraper.start()

    try:
        if args.login:
            scraper.login()
            print("✅ 登录完成，下次运行不需要 --login 参数")
            return

        if not STATE_FILE.exists():
            print("⚠️ 未检测到登录状态，请先运行: python3 boss_firefox.py --login")
            return

        all_jobs = []
        seen = set()

        for kw in keywords:
            print(f"\n📌 搜索: 「{kw}」")
            try:
                jobs = scraper.search_keyword(kw)
            except Exception as e:
                print(f"  ⚠️ 失败: {e}")
                continue

            # 去重 + 过滤
            new_count = 0
            for j in jobs:
                key = j["title"] + j["salary"]
                if key not in seen:
                    seen.add(key)
                    if salary_ok(j["salary"]):
                        all_jobs.append(j)
                        new_count += 1

            print(f"  📋 提取 {len(jobs)} 条，过滤后新增 {new_count} 条（累计 {len(all_jobs)}）")
            time.sleep(3)

        print(f"\n📊 共采集 {len(all_jobs)} 条")

        if not all_jobs:
            print("❌ 一条符合条件的都没找到")
            return

        # 生成日报
        md = render_daily_report(all_jobs)
        md_path = out_dir / f"招聘日报_{DATE_STR}.md"
        with open(md_path, "w") as f:
            f.write(md)
        print(f"📄 日报: {md_path}")

        # JSONL
        jsonl_path = out_dir / f"招聘日报_{DATE_STR}.jsonl"
        with open(jsonl_path, "w") as f:
            for j in all_jobs:
                f.write(json.dumps(j, ensure_ascii=False) + "\n")
        print(f"📄 JSONL: {jsonl_path}")

        # MySQL
        if not args.no_db:
            save_to_mysql(all_jobs)

        # 输出摘要
        print(f"\n{'─' * 60}")
        print(f"  {'岗位名称':25s} | {'薪资':12s} | {'公司':15s}")
        print(f"{'─' * 60}")
        for j in all_jobs[:20]:
            print(f"  {j['title'][:25]:25s} | {j['salary'][:12]:12s} | {j.get('company', '')[:15]:15s}")
        if len(all_jobs) > 20:
            print(f"  ... 还有 {len(all_jobs) - 20} 条")
        print(f"{'─' * 60}")

        print(f"\n✅ 完成！共 {len(all_jobs)} 条岗位信息")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
