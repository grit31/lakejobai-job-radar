# 🎯 BOSS Job Radar - AI-Powered Job Hunting Assistant

BOSS直聘岗位雷达 · AI驱动的智能求职助手

## Features 功能

- 🔍 **自动搜索岗位** - 支持60+城市、多关键词搜索AI相关岗位
- 🚀 **一键批量投递** - 带进度条的批量投递，可随时取消
- 🤖 **AI自动聊天** - DeepSeek/OpenRouter/小米MiMo多平台模型驱动，自动回复HR消息
- 📱 **智能交换** - HR要简历/微信/手机号时自动通过BOSS系统发送
- 🎛️ **Web控制台** - 完整的FastAPI前端，实时监控投递和聊天状态

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install firefox

# 2. Start
python boss_app.py --port 8010

# 3. Open http://127.0.0.1:8010
# 4. Settings Tab → 启动浏览器 → 扫码登录BOSS直聘
# 5. Settings Tab → AI模型配置 → 填入API Key
# 6. Search Tab → 搜索岗位 → 一键投递
```

## AI Model Setup

Web控制台 Settings Tab 中配置：

| 平台 | Base URL |
|------|----------|
| DeepSeek | https://api.deepseek.com/v1 |
| OpenRouter | https://openrouter.ai/api/v1 |
| 小米MiMo | https://token-plan-sgp.xiaomimimo.com/v1 |

选平台后自动填充，只需填入API Key即可。

## Tech Stack

- **Python** + FastAPI + Playwright + BeautifulSoup
- **SQLite** 本地数据存储
- **WebSocket** 实时状态推送
- **OpenAI兼容API** 多模型支持

## Note

- 首次使用需扫码登录BOSS直聘
- 每日投递有上限（可在设置中调整）
- 仅用于个人求职，请勿滥用
