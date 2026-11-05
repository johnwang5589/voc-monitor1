# VOC 中控台看板 - 省钱版

## 项目简介

这是一个基于 **Python + GitHub Actions** 的自动化 VOC (Voice of Customer) 监控系统,
专为海外品牌营销设计。通过聚合 Google 搜索、Reddit 社区、YouTube 视频和新闻资讯等多渠道数据,
结合 AI 分析, 自动生成可执行的营销行动建议。

### 省钱设计亮点

| 模块 | 原方案 (贵) | 本方案 (省) | 预计节省 |
|------|------------|------------|---------|
| Google搜索 | SerpAPI | **Serper.dev** (便宜) 或 Google Custom Search (免费100次/天) | 90% |
| Reddit监控 | Apify | **PRAW** (直接调官方免费接口) | 100% |
| YouTube监控 | YouTube Data API | **youtube-search-python** (爬虫库, 不耗配额) | 100% |
| AI分析 | DeepSeek API | **Kimi/Moonshot** (免费额度) 或本地 Ollama | 80% |
| 部署 | Cloudflare Pages | **GitHub Pages** (完全免费) | 100% |

## 快速开始

### 1. 克隆仓库

```
git clone <your-repo-url>
cd voc-monitor
```

### 2. 安装依赖

```
pip install -r requirements.txt
```

### 3. 配置环境变量

```
cp .env.example .env
# 编辑 .env 文件, 填入你的 API Key
```

### 4. 本地运行

```
python monitor.py
```

### 5. GitHub Actions 自动运行

1. 在 GitHub 仓库 Settings > Secrets 中添加以下密钥:
   - `SERPER_API_KEY` - Serper.dev API Key
   - `REDDIT_CLIENT_ID` - Reddit App Client ID
   - `REDDIT_CLIENT_SECRET` - Reddit App Client Secret
   - `KIMI_API_KEY` - Kimi/Moonshot API Key (或其他 AI 提供商)
   - `MONITOR_KEYWORDS` - 监控关键词(逗号分隔)
   - `REDDIT_SUBREDDITS` - Reddit subreddit(逗号分隔)

2. 工作流会自动每周一运行, 生成看板并部署到 GitHub Pages

## 文件结构

```
├── monitor.py              # 主脚本: 数据采集 + 分析 + 看板生成
├── requirements.txt        # Python 依赖
├── .env.example           # 环境变量模板
├── .github/
│   └── workflows/
│       └── voc-monitor.yml # GitHub Actions 工作流
└── output/
    ├── html/
    │   └── index.html      # 生成的看板
    └── data/
        └── voc_data_*.json # 原始数据快照
```

## 成本估算

- **Serper.dev**: 免费层 2500 次/月, 超出后 $3/1000次
- **PRAW (Reddit)**: 完全免费
- **youtube-search-python**: 完全免费
- **Kimi/Moonshot**: 免费额度充足
- **GitHub Actions**: 免费 2000分钟/月
- **GitHub Pages**: 完全免费

**月均成本: $0 ~ $2** (取决于关键词数量和请求频率)

## 注意事项

1. Reddit API 有速率限制, 建议不要设置过短的 cron 间隔
2. youtube-search-python 是逆向接口, 如失效可切换回官方 API
3. 生产环境建议使用 GitHub Secrets 管理密钥, 不要提交 .env 文件
4. AI 分析步骤可能较慢, GitHub Actions 超时时间已设置为 30 分钟
