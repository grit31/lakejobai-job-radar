<div align="center">

# lakejobai-job-radar

**AI 驱动的 BOSS 直聘智能求职助手 · Web 控制台版**

> 自动搜索 · 批量投递 · AI 聊天 · 微信/简历/手机号交换 · 多模型支持

[![Python](https://img.shields.io/badge/Python-≥3.10-3776AB?logo=python&logoColor=white&style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](https://github.com/longnull-ck/lakejobai-job-radar/pulls)

[快速开始](#-快速开始) · [安装](#-安装) · [核心能力](#-核心能力) · [AI 模型配置](#-ai-模型配置) · [命令参考](#-api-端点参考) · [架构](#-技术架构) · [免责声明](#️-免责声明)

</div>

> AI-driven job hunting assistant for BOSS Zhipin with web dashboard. Auto search, batch apply, AI chat replies, WeChat/resume/phone exchange. Supports DeepSeek, OpenRouter, MiMo and OpenAI-compatible APIs.

---

## 📑 导航目录

- [为什么用 lakejobai-job-radar](#-为什么用-lakejobai-job-radar)
- [核心能力](#-核心能力)
- [安装](#-安装)
- [快速开始](#-快速开始)
- [AI 模型配置](#-ai-模型配置)
- [项目结构](#-项目结构)
- [API 端点参考](#-api-端点参考)
- [技术架构](#-技术架构)
- [配置](#-配置)
- [免责声明](#️-免责声明)

---

## 💡 为什么用 lakejobai-job-radar

传统 BOSS 直聘求职流程：打开网页 → 逐个搜索关键词 → 翻几十页 → 手动点"立即沟通" → 记不清跟谁聊了什么 → 反复切换 App 查看回复。

**lakejobai-job-radar 帮你自动化这一切：**

1. **搜索** — 选择城市和关键词，一键搜索 AI/技术相关岗位
2. **投递** — 搜索完成后一键批量投递，带进度条和取消按钮
3. **AI 聊天** — 投递后 HR 的消息由 AI 自动接管回复，你只需查看结果
4. **自动交换** — HR 要简历、微信、手机号时，系统自动通过 BOSS 官方按钮发送

所有操作通过 Web 控制台完成，浏览器和手机都能用。

---

## 🌟 核心能力

| 功能 | 说明 | 入口 |
|------|------|------|
| 🔍 岗位搜索 | 60+ 城市、多关键词搜索 AI 技术岗位 | 搜索 Tab → 选城市 → 关键词 → 搜索 |
| 🚀 一键投递 | 搜索后一次性投递所有待投递岗位，实时进度条 | 搜索 Tab → 一键投递待投递 |
| 📋 投递记录 | 补投漏掉的岗位，按状态筛选 | 投递记录 Tab → 一键投递待投递 |
| 🤖 AI 自动回复 | DeepSeek / OpenRouter / 小米MiMo 等多模型驱动 | 设置 Tab → AI模型配置 |
| 📱 智能交换 | HR 要简历/微信/手机号时自动通过 BOSS 发送 | 自动触发，无需手动操作 |
| 🎛️ Web 控制台 | FastAPI 后端 + 现代黑暗风 UI，实时状态推送 | 浏览器打开 http://127.0.0.1:8010 |

### 投递流程

```bash
# 1. 设置页 → 启动浏览器 → 扫码登录 BOSS 直聘
# 2. 搜索页 → 选城市 "广州" → 输入关键词 "AI Agent" → 点击搜索
# 3. 搜索页 → 点击"一键投递待投递" → 确认 → 看进度条
# 4. HR 回复后，AI 自动接管聊天
```

### AI 回复示例

```
HR: 你好，看到你投了我们公司的AI岗位，能简单介绍下吗？
AI: 您好！我是求职者开发的AI助手，擅长LangChain/RAG/Agent开发，有多个企业级AI项目经验。具体细节可以让本人跟您详聊～
```

---

## 📦 安装

```bash
# 克隆仓库
git clone https://github.com/longnull-ck/lakejobai-job-radar.git
cd lakejobai-job-radar

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install firefox
```

<details>
<summary>📋 requirements.txt 内容</summary>

```
playwright
beautifulsoup4
lxml
pyyaml
fastapi
uvicorn
python-multipart
```
</details>

---

## 🚀 快速开始

```bash
# 1. 启动服务
python boss_app.py --port 8010

# 2. 浏览器打开
#    http://127.0.0.1:8010

# 3. 设置页操作
#    → 点击「启动浏览器」
#    → 点击「重新扫码登录」
#    → 手机 BOSS 直聘 App 扫码

# 4. AI 配置
#    → 设置页 → AI模型配置
#    → 选择平台（DeepSeek / OpenRouter / MiMo）
#    → 填入 API Key
#    → 选择模型
#    → 保存设置

# 5. 搜索 & 投递
#    → 搜索页 → 选城市 → 输入关键词 → 搜索
#    → 点击"一键投递待投递"
```

---

## 🤖 AI 模型配置

Web 控制台设置页中选择平台后自动填充 Base URL 和可选模型。

| 平台 | Base URL | 自动填充 |
|------|----------|:------:|
| DeepSeek | `https://api.deepseek.com/v1` | ✅ |
| OpenRouter | `https://openrouter.ai/api/v1` | ✅ |
| 小米MiMo | `https://token-plan-sgp.xiaomimimo.com/v1` | ✅ |
| 自定义 | 手动输入 | — |

### 推荐模型

| 平台 | 模型 ID | 说明 |
|------|---------|------|
| DeepSeek | `deepseek-chat` | 通用对话 |
| DeepSeek | `deepseek-reasoner` | 深度推理 |
| OpenRouter | `openrouter/auto` | 自动路由最优模型 |
| OpenRouter | `anthropic/claude-sonnet-4` | Claude Sonnet 4 |
| OpenRouter | `google/gemini-2.5-flash` | Gemini 2.5 Flash |
| MiMo | `mi-undefined` | 默认模型 |

---

## 📁 项目结构

```
lakejobai-job-radar/
├── boss_app.py              # FastAPI Web 后端（923行）
├── boss_automation.py       # 自动化投递 & 聊天交互（1256行）
├── boss_firefox.py          # BOSS 直聘搜索采集（748行）
├── boss_replier.py          # AI 回复生成 & DeepSeek/OpenAI API
├── boss_state.py            # SQLite 数据持久化
├── boss_daily.py            # 日报生成
├── scraper.py               # 智联招聘爬虫
├── config.yaml              # 本地配置（浏览器/登录）
├── requirements.txt         # Python 依赖
├── setup.sh                 # 安装脚本
├── static/
│   └── dashboard.html       # Web 控制台前端（单文件 SPA）
├── reports/                 # 搜索日报输出目录
├── interview/               # 面试问答 Agent 子模块
│   ├── main.py              # 独立 FastAPI 服务
│   ├── engine.py            # 面试引擎
│   ├── fast_qa.py           # 快速检索
│   ├── llm_client.py        # LLM API 客户端
│   ├── db.py                # MySQL 数据库层
│   └── static/              # 面试页面前端
└── .boss_profile/           # Firefox 浏览器 Profile（不提交 Git）
```

---

## 🔌 API 端点参考

### 系统

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/status` | 浏览器状态、今日统计 |
| `POST` | `/api/system/start` | 启动浏览器 |
| `POST` | `/api/system/stop` | 停止浏览器 |
| `POST` | `/api/system/relogin` | 重新扫码登录 |
| `POST` | `/api/system/heartbeat` | 心跳保活 |
| `WS` | `/ws` | 实时状态推送 |

### 岗位

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/jobs/search` | 搜索岗位 `{keyword, city}` |
| `GET` | `/api/jobs?status=pending&limit=100` | 岗位列表 |
| `POST` | `/api/jobs/apply` | 投递单个 `{job_url, greeting?}` |
| `POST` | `/api/jobs/apply-batch` | 批量投递 `{job_urls[], greeting?}` |

### 会话 & 聊天

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/conversations` | 会话列表 |
| `GET` | `/api/conversations/{id}/messages` | 消息记录 |
| `POST` | `/api/conversations/{id}/send` | 手动发送消息 |
| `POST` | `/api/conversations/sync` | 同步BOSS聊天页数据 |

### 设置

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/settings` | 读取所有设置 |
| `PUT` | `/api/settings` | 更新设置 |

---

## 🏗️ 技术架构

```
Web 浏览器                  FastAPI 后端                    BOSS 直聘
┌──────────┐  WebSocket   ┌──────────────┐   Playwright   ┌──────────────┐
│dashboard │◄────────────►│  boss_app.py  │◄─────────────►│  zhipin.com   │
│  .html   │  HTTP/REST   │               │   Firefox     │               │
└──────────┘              │  ┌─────────┐  │               └──────────────┘
                          │  │automation│  │
                          │  ├─────────┤  │               DeepSeek/OpenAI
                          │  │replier   │──┤◄─────────────►│ 兼容 API      │
                          │  ├─────────┤  │   httpx       │               │
                          │  │state     │──┤               └──────────────┘
                          │  └─────────┘  │  SQLite
                          └──────────────┘  ┌──────────────┐
                                            │ boss_state.db │
                                            └──────────────┘
```

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端 | Python >= 3.10 + FastAPI | 异步 Web 框架 |
| 浏览器 | Playwright + Firefox | 持久化 Profile 避免重复登录 |
| 自动化 | Playwright Sync API | 线程池隔离，避免 asyncio 冲突 |
| 数据库 | SQLite (WAL) | 本地轻量存储 |
| 前端 | 单文件 HTML + Vanilla JS | WebSocket 实时推送 |
| AI | OpenAI Chat Completions 兼容 API | 多平台模型支持 |
| 搜索 | 正则 + DOM 提取 | BOSS 直聘搜索页解析 |

---

## ⚙️ 配置

### config.yaml

```yaml
browser:
  headless: false
  profile_dir: ./.boss_profile/firefox_user_data

login:
  account_type: boss
```

### Web 控制台设置项

| 设置项 | 说明 | 默认值 |
|--------|------|--------|
| 招呼语模板 | 投递时自动发送 | `您好，我对贵公司的{job_title}岗位很感兴趣` |
| AI 回复风格 | professional / casual / enthusiastic | professional |
| 每日投递上限 | 1-30 | 15 |
| 回复间隔 | 最小/最大秒数 | 30-120 |
| 搜索关键词 | 一行一个 | AI Agent, 大模型开发, RAG |
| 微信号 | AI 引导 HR 添加时用 | — |
| 简历摘要 | AI 生成回复的素材 | — |
| AI 平台 | DeepSeek / OpenRouter / MiMo / 自定义 | — |
| AI API Key | 模型 API Key | — |
| AI Base URL | API 地址 | 自动填充 |
| AI 模型 | 模型名称 | 下拉选择 |

---

## ⚠️ 免责声明

本项目仅供学习交流和个人求职辅助，请遵守：

- ✅ 仅用于个人账号的求职辅助
- ✅ 遵守 BOSS 直聘用户协议和隐私政策
- ❌ 不得用于批量注册、商业采集等违规行为
- ❌ 不得规避平台风控机制

因不当使用产生的一切后果由使用者自行承担，与本项目作者无关。

---

## 📑 许可证

[MIT](LICENSE)

## 🙏 致谢

- [can4hou6joeng4/boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli) — AI Agent 友好的 BOSS 直聘 CLI 工具，本项目 Web 控制台版的设计灵感来源
- [Playwright](https://playwright.dev/) — 跨浏览器自动化框架
- [FastAPI](https://fastapi.tiangolo.com/) — 高性能 Python Web 框架
