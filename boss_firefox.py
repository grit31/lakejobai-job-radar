#!/usr/bin/env python3
"""
BOSS直聘 AI Agent 岗位采集工具

流程:
  1. 搜索列表页 → 提取基本信息（标题、薪资、公司、城市、经验、学历、链接）
  2. 逐个访问详情页 → 提取"岗位技能"原文输出

用法:
  python3 boss_firefox.py                     # 采集+分析
  python3 boss_firefox.py --login             # 首次扫码登录
  python3 boss_firefox.py --headless          # 无头模式
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

KEYWORDS = [
    "AI Agent开发", "AI Agent", "Agent工程师", "智能体开发",
    "大模型应用开发", "LLM应用开发", "LLM开发", "RAG工程师", "LangChain开发",
    "MCP开发", "AIGC开发", "AI应用开发", "大模型工程师", "Prompt工程师",
]

OUTPUT_DIR = Path.home() / "AI" / "岗位日报"
STATE_FILE = Path(__file__).parent / ".boss_profile" / "firefox_state.json"

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

# ── 技能词库（仅分析用）──
SKILL_MAP = {
    "编程语言": {"Python","Java","Go","Golang","Rust","C++","C#","C","PHP","Ruby","Swift","Kotlin","Scala","TypeScript","JavaScript","Node.js"},
    "前端": {"React","Vue","Angular","Next.js","HTML","CSS","Tailwind"},
    "AI/ML框架": {"PyTorch","TensorFlow","Transformers","vLLM","ONNX","HuggingFace","GGUF","Stable Diffusion","Diffusion","Vision","Multimodal"},
    "AI框架/工具": {"LangChain","LangGraph","LlamaIndex","AutoGen","CrewAI","Dify","Coze","MCP"},
    "大模型技术": {"RAG","Fine-tuning","Finetune","微调","SFT","RLHF","LoRA","QLoRA","Prompt","Function Calling","Tool Calling","Agent","Multi-Agent","Embedding","LLM","AI Agent","AIGC"},
    "数据库/中间件": {"MySQL","PostgreSQL","Redis","MongoDB","Elasticsearch","Milvus","FAISS","Chroma","Qdrant","Pinecone","Weaviate","Kafka","RabbitMQ"},
    "部署/架构": {"Docker","Kubernetes","K8s","FastAPI","Flask","Django","Spring","Nginx","gRPC","GraphQL","WebSocket","REST","RESTful","CI/CD","GitHub Actions","Linux","GPU","CUDA"},
    "云平台": {"AWS","GCP","Azure","阿里云","腾讯云"},
    "其他": {"数据结构","算法","系统设计","架构","微服务","高并发","分布式","设计模式","OOP","TDD","单元测试","测试"},
}
ALL_SKILLS = {s for v in SKILL_MAP.values() for s in v}
MY_SKILLS = {s.lower() for v in {"编程语言": {"Python","TypeScript","JavaScript"},"AI框架/工具": {"LangChain","LangGraph","AutoGen","CrewAI","Dify","Coze"},"大模型技术": {"LLM","AI Agent","RAG","微调","MCP","Prompt Engineering","Function Calling","Tool Calling","Embedding"},"数据库/向量库": {"MySQL","Milvus","FAISS","Chroma","Qdrant"},"部署/运维": {"Docker","FastAPI","Kubernetes"},"AI平台/模型": {"Claude","OpenAI","GPT"}}.values() for s in v}


def decode_salary(text):
    return "".join(str(ord(c)-0xE030) if 0xE030<=ord(c)<=0xE039 else c for c in text)


def salary_ok(text):
    if not text: return False
    nums = re.findall(r"(\d+)", re.sub(r"[^\d-]", "", text.replace("~","-").replace("K","").replace("k","")))
    if len(nums) < 2: return False
    l, h = int(nums[0]), int(nums[1])
    if l < 5 and h < 20: l *= 10; h *= 10
    return 15 <= l and h <= 35


def pause(a=1.0, b=3.0):
    time.sleep(random.uniform(a, b))


def parse_skills(text):
    tl = text.lower()
    r = defaultdict(list)
    for cat, skills in SKILL_MAP.items():
        for s in skills:
            if s.lower() in tl:
                r[cat].append(s)
    return dict(r)


# ══════════════════════════════════════
#  浏览器
# ══════════════════════════════════════

class BossScraper:
    def __init__(self, headless=False):
        self.headless = headless
        self._pw = self._br = self._ctx = None
        self.page = None

    def start(self):
        self._pw = sync_playwright().start()
        self._br = self._pw.firefox.launch(headless=self.headless)
        kw = {"viewport": {"width": 1280, "height": 800}, "locale": "zh-CN"}
        if STATE_FILE.exists():
            kw["storage_state"] = str(STATE_FILE)
        self._ctx = self._br.new_context(**kw)
        self.page = self._ctx.new_page()
        self.page.set_default_timeout(30000)
        self.page.add_init_script(ANTI_DETECT)

    def close(self):
        if self._br: self._br.close()
        if self._pw: self._pw.stop()

    def login(self):
        self.page.goto("https://www.zhipin.com/web/user/?ka=header-login")
        pause(2, 4)
        self.page.bring_to_front()
        print("\n🔓 浏览器已打开，请扫码登录")
        last = self.page.url
        for i in range(600):
            time.sleep(1)
            try:
                url = self.page.evaluate("window.location.href")
            except:
                continue
            if url != last and any(p in url for p in ["/web/geek","/web/chat"]):
                print("✅ 登录成功")
                break
            last = url
            if i > 0 and i % 30 == 0: print("  ⏳ %ds" % i)
        state = self._ctx.storage_state()
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        print("✅ 登录状态已保存")

    # ── 搜索列表页 ──

    def search(self, keyword):
        """搜索关键词，返回岗位列表"""
        url = "https://www.zhipin.com/web/geek/job?query=%s&city=100010000" % keyword.replace(" ","+")
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        pause(3, 5)
        self._scroll_all()

        lines = [l.strip() for l in self.page.inner_text("body").split("\n") if l.strip()]

        # 薪资行定位
        sal_idx = [i for i,l in enumerate(lines) if re.search(r"\d+[-~]\d+K", decode_salary(l), re.I)]

        jobs = []
        for n, si in enumerate(sal_idx):
            if n > 0 and si - sal_idx[n-1] < 3: continue
            if si == 0: continue
            title = lines[si-1]
            if not (2 < len(title) < 60): continue

            salary = decode_salary(lines[si])
            company = exp = edu = city = ""
            end = sal_idx[n+1] if n+1 < len(sal_idx) else min(si+10, len(lines))
            for j in range(si+1, min(end, len(lines))):
                ln = lines[j]
                if "经验" in ln or "应届" in ln: exp = ln
                elif re.search(r"本科|硕士|博士|大专|学历不限", ln): edu = ln
                elif "·" in ln and len(ln) < 30: city = ln
                elif not company and len(ln) > 2 and len(ln) < 40 and not re.search(r"年|学历|大专|本科|硕士|博士|不限|应届|·", ln):
                    company = ln

            jobs.append({"title":title,"salary":salary,"company":company,"experience":exp,"education":edu,"city":city,"url":"","description":""})

        # 合并链接
        links = self._extract_links()
        if links:
            lm = {l["title"][:12]: l["href"] for l in links if l["title"][:12]}
            for j in jobs:
                if not j["url"] and j["title"][:12] in lm:
                    j["url"] = lm[j["title"][:12]]
        return jobs

    def _scroll_all(self):
        try:
            h = self.page.evaluate("document.body.scrollHeight")
            for p in range(0, int(h)+400, 400):
                self.page.evaluate("window.scrollTo(0,%d)" % p)
                time.sleep(random.uniform(0.3, 0.6))
        except: pass

    def _extract_links(self):
        try:
            return self.page.evaluate("""()=>{
                const r=[];const s=new Set();
                document.querySelectorAll('a[href*="/job_detail/"]').forEach(a=>{
                    const h=a.href,t=(a.innerText||'').trim();
                    if(h&&t&&!s.has(h)&&t.length<60){s.add(h);r.push({href:h,title:t.substring(0,60)});}
                });return r;
            }""")
        except: return []

    # ── 详情页 ──

    def fetch_skills(self, url):
        """访问详情页，提取岗位技能原文（岗位职责/职位描述部分）"""
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            pause(2, 4)
            body = self.page.inner_text("body")
            lines = [l.strip() for l in body.split("\n") if l.strip()]

            # 找到"职位描述"或"岗位职责"段落
            skill_lines = []
            capture = False
            for l in lines:
                if "职位描述" in l or "岗位职责" in l:
                    capture = True
                    continue
                if capture:
                    # 遇到公司介绍/工商信息等结束标志就停
                    if any(stop in l for stop in ["公司介绍","工商信息","BOSS 安全提示","竞争力分析"]):
                        break
                    skill_lines.append(l)
            return "\n".join(skill_lines) if skill_lines else ""
        except Exception as e:
            return ""


# ══════════════════════════════════════
#  分析
# ══════════════════════════════════════

def skill_gap(jobs):
    c = Counter()
    for j in jobs:
        text = (j.get("description") or "") + " " + (j.get("title") or "")
        seen = set()
        for cat, skills in parse_skills(text).items():
            for s in skills:
                if s.lower() not in seen:
                    seen.add(s.lower())
                    c[s] += 1
    have, miss = [], []
    for s, n in c.most_common():
        (have if s.lower() in MY_SKILLS else miss).append({"skill":s,"count":n})
    return {"have":have,"missing":miss,"total":len(jobs)}


# ══════════════════════════════════════
#  输出
# ══════════════════════════════════════

def output_report(jobs):
    lines = ["# 招聘日报 · %s\n" % DATE_STR]
    lines.append("> 来源：**BOSS直聘** · 薪资 **15K-35K** · 共 %d 条\n---\n" % len(jobs))

    for i, j in enumerate(jobs, 1):
        lines.append("### %d. %s %s" % (i, j["title"], j["salary"]))
        lines.append("- 公司: %s" % (j.get("company") or "未显示"))
        if j.get("city"): lines.append("- 城市: %s" % j["city"])
        if j.get("experience"): lines.append("- 经验: %s" % j["experience"])
        if j.get("education"): lines.append("- 学历: %s" % j["education"])
        if j.get("url"): lines.append("- 链接: %s" % j["url"])
        desc = j.get("description", "")
        if desc:
            lines.append("- 岗位技能：%s" % desc[:600])
        lines.append("---\n")
    lines.append("\n*数据采集于 %s，BOSS直聘*\n" % DATE_STR)
    return "\n".join(lines)


def skill_report(gap):
    lines = ["# AI Agent 技能差距分析报告 · %s\n" % DATE_STR]
    lines.append("> 基于 BOSS 直聘 %d 个岗位\n---\n" % gap["total"])
    lines.append("## 一、✅ 你已拥有的技能\n")
    for item in gap["have"]:
        lines.append("- **%s**: %d个岗位" % (item["skill"], item["count"]))
    lines.append("\n## 二、🔍 需要查漏补缺\n")
    for item in gap["missing"][:30]:
        p = "🔴" if item["count"]>=10 else "🟡" if item["count"]>=5 else "🟢"
        lines.append("- %s **%s**: %d个岗位" % (p, item["skill"], item["count"]))
    return "\n".join(lines)


# ══════════════════════════════════════
#  主流程
# ══════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--headless", action="store_true", default=False)
    ap.add_argument("--keywords")
    ap.add_argument("--output", default=str(OUTPUT_DIR))
    ap.add_argument("--max-jobs", type=int, default=64)
    args = ap.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else KEYWORDS

    if not STATE_FILE.exists() and not args.login:
        print("⚠️ 请先运行: python3 boss_firefox.py --login")
        sys.exit(1)

    sc = BossScraper(headless=args.headless)
    sc.start()
    try:
        if args.login:
            sc.login()
            return

        # Phase 1: 搜索列表
        all_jobs = []
        seen = set()
        for kw in keywords:
            print("\n📌 搜索: 「%s」" % kw)
            try:
                jobs = sc.search(kw)
            except Exception as e:
                print("  ⚠️ 失败: %s" % e)
                continue
            ok = []
            for j in jobs:
                if not salary_ok(j["salary"]): continue
                key = j["title"]+j["salary"]
                if key not in seen:
                    seen.add(key)
                    ok.append(j)
            print("  %d条, 过滤后%d条(累计%d)" % (len(jobs), len(ok), len(all_jobs)))
            all_jobs.extend(ok)
            if len(all_jobs) >= args.max_jobs:
                print("  📊 已达上限%d条" % args.max_jobs)
                break
            pause(2, 4)

        print("\n📊 共%d条" % len(all_jobs))
        if not all_jobs:
            return

        # Phase 2: 逐个访问详情页，提取岗位技能
        print("\n🔍 开始采集岗位技能（共%d条）..." % len(all_jobs))
        success = 0
        for i, j in enumerate(all_jobs):
            if not j.get("url"):
                continue
            print("  [%d/%d] %s" % (i+1, len(all_jobs), j["title"][:25]), end=" ", flush=True)
            desc = sc.fetch_skills(j["url"])
            if desc:
                j["description"] = desc
                success += 1
                print("✅ %d字" % len(desc))
            else:
                print("⚠️ 无技能描述")
            time.sleep(random.uniform(1.5, 3.0))

        print("📊 技能采集: %d/%d条成功" % (success, len(all_jobs)))

        # 分析输出到终端即可
        gap = skill_gap(all_jobs)
        print("\n" + "="*60)
        print("📊 技能差距分析")
        print("="*60)
        for item in gap["have"][:10]:
            print("  ✅ %s: %d个岗位" % (item["skill"], item["count"]))
        for item in gap["missing"][:15]:
            p = "🔴" if item["count"]>=10 else "🟡" if item["count"]>=5 else "🟢"
            print("  %s %s: %d个岗位" % (p, item["skill"], item["count"]))

        # 输出——只保留招聘日报
        with open(out_dir / ("招聘日报_%s.md" % DATE_STR), "w") as f:
            f.write(output_report(all_jobs))
        print("📄 日报: %s/招聘日报_%s.md" % (out_dir, DATE_STR))
        print("\n✅ 完成！")

    finally:
        sc.close()

if __name__ == "__main__":
    main()
