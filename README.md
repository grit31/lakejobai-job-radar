# 招聘网站爬虫 (ai-job-radar)

每天自动扫 BOSS直聘 和 智联招聘，按条件筛 AI 相关岗位，生成日报。

**亲测可用：绕过 BOSS 直聘反爬，能正常采集数据。**

## 它能干啥

- ✅ **BOSS直聘** — 用 Playwright + Firefox 绕过反爬，每日自动采集
- ✅ **智联招聘** — Playwright 无头浏览器采集（稳定运行中）
- ✅ 9个 AI Agent 关键词自动搜索：AI Agent、LLM、RAG、LangChain 等
- ✅ 薪资/经验自动过滤（默认 15-35K，可调）
- ✅ 技能自动分类（编程语言、AI框架、数据库、部署运维……）
- ✅ 生成 Markdown 日报 + JSONL 数据文件
- ✅ 支持 MySQL 存储（历史数据可查）
- ✅ 可设置定时任务，每天自动跑

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install firefox

# 2. 首次运行：扫码登录 BOSS 直聘
python boss_firefox.py --login

# 3. 采集数据
python boss_firefox.py               # 有头模式（能看到浏览器）
python boss_firefox.py --headless    # 无头模式（后台静默运行）
```

> **注意**：首次需要 --login 扫码登录一次，登录状态会保存，以后不用再扫码。

## 智联招聘

```bash
# 智联招聘不需要登录，直接跑
python scraper.py

# 自定义关键词
python scraper.py --keywords "Java,Go,Python"

# 改薪资范围
python scraper.py --salary-min 20 --salary-max 35
```

## BOSS直聘详细使用

### 命令行参数

```bash
python boss_firefox.py --help

选项:
  --login           首次扫码登录并保存状态
  --headless        无头模式（登录后可用）
  --keywords        关键词用逗号分隔，默认 9个AI关键词
  --salary-min      最低薪资，默认 15K
  --salary-max      最高薪资，默认 35K
  --output          日报输出目录
  --no-db           不存 MySQL
```

### 自定义关键词示例

```bash
python boss_firefox.py --keywords "AI开发,大模型,机器学习"
```

### 定时任务

每天早上 9:30 自动采集：

```bash
crontab -e
30 9 * * * cd /path/to/ai-job-radar && python boss_firefox.py --headless
```

## 输出示例

跑完会在指定目录下生成：

- `招聘日报_2026-05-18.md` — 完整的 Markdown 日报
- `招聘日报_2026-05-18.jsonl` — JSONL 格式数据

日报包含：岗位名称、公司、薪资、经验要求、技能标签分类统计。

## 技术原理

### BOSS直聘反爬绕过（亲测有效）

BOSS 直聘的反爬主要靠以下手段：
1. **WebDriver 检测** — 检查 `navigator.webdriver` 属性
2. **浏览器指纹识别** — 检测 Chromium 的自动化特征
3. **薪资数字加密** — 用 Unicode U+E030-E039 替代 0-9

绕过方案：
1. **使用 Firefox 浏览器**（Playwright 内置），Chromium 会被更严格地检测
2. **注入反检测脚本**，隐藏 webdriver 特征
3. **解码薪资数字**，还原真实薪资

```python
# 核心反检测代码
page.add_init_script('''
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
    Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
''')
```

### 智联招聘

智联的反爬相对宽松，直接用 Playwright Chromium 无头浏览器即可。

## 配置

也可以写 `config.yaml`：

```yaml
output_dir: ./reports
keywords:
  - AI Agent开发
  - 大模型应用开发
filters:
  salary_min: 15
  salary_max: 35
database:
  host: 127.0.0.1
  user: root
  password: ${DB_PASSWORD}
```

数据库密码用环境变量 `DB_PASSWORD` 或 `MYSQL_PWD`，别写死在文件里。

## 注意事项

- 别爬太狠，BOSS 直聘也不容易
- 只供个人求职参考，别拿来干别的
- 如果登录失效，重新跑一次 `--login`
- 网站改版可能导致解析失效，提 issue 就行
