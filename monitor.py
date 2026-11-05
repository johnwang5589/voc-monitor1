#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOC 中控台看板 - 省钱版 monitor.py
=====================================
架构: Python脚本 -> GitHub Actions -> GitHub Pages
数据源: Serper.dev (Google搜索) + PRAW (Reddit) + youtube-search-python (YouTube) + Google News RSS
AI分析: 可选 DeepSeek/Kimi/Ollama 本地模型
产出: index.html 静态看板 + JSON 原始数据

成本估算:
  - Serper.dev: 免费层 2500 次/月, 超出后 $3/1000次
  - PRAW (Reddit): 完全免费
  - youtube-search-python: 完全免费(模拟网页请求)
  - AI分析: 可用 Kimi/Moonshot 免费额度或本地 Ollama
  - 部署: GitHub Actions 免费额度(2000分钟/月) + GitHub Pages 免费托管
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

# ============================================================
# 1. 配置区 (建议通过环境变量注入, 便于 GitHub Secrets 管理)
# ============================================================

# 数据源配置
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "VOCMonitor/1.0")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
GOOGLE_NEWS_RSS = os.getenv("GOOGLE_NEWS_RSS", "")

# AI 分析配置 (三选一)
AI_PROVIDER = os.getenv("AI_PROVIDER", "kimi")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# 监控关键词配置
MONITOR_KEYWORDS = os.getenv(
    "MONITOR_KEYWORDS",
    "your_brand,competitor_brand,industry_keywords"
).split(",")

# Reddit 监控配置
REDDIT_SUBREDDITS = os.getenv(
    "REDDIT_SUBREDDITS",
    "your_niche,competitor_name,industry_topic"
).split(",")

# 输出路径
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))
DATA_DIR = OUTPUT_DIR / "data"
HTML_DIR = OUTPUT_DIR / "html"


# ============================================================
# 2. 日志配置
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUTPUT_DIR / "monitor.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("VOCMonitor")


# ============================================================
# 3. 数据源采集器
# ============================================================

class SearchMonitor:
    """Google 搜索监控 - 使用 Serper.dev 替代 SerpAPI"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://google.serper.dev/search"
        self.headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }

    def search(self, keyword: str, num_results: int = 10) -> Dict[str, Any]:
        """执行 Google 搜索并返回排名结果"""
        import requests
        payload = {
            "q": keyword,
            "num": num_results,
            "gl": "us",
            "hl": "en",
        }
        try:
            resp = requests.post(
                self.base_url, headers=self.headers, json=payload, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "keyword": keyword,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "organic_results": data.get("organic", []),
                "paa_results": data.get("peopleAlsoAsk", []),
                "total_results": data.get("searchInformation", {}).get("totalResults", 0),
            }
        except Exception as e:
            logger.error(f"SearchMonitor search failed for '{keyword}': {e}")
            return {"keyword": keyword, "error": str(e), "timestamp": datetime.datetime.utcnow().isoformat()}

    def monitor_keywords(self, keywords: List[str]) -> List[Dict]:
        """批量监控关键词"""
        results = []
        for kw in keywords:
            logger.info(f"SearchMonitor: searching '{kw}'")
            result = self.search(kw)
            results.append(result)
            time.sleep(1)
        return results


class RedditMonitor:
    """Reddit 社区监控 - 使用 PRAW 替代 Apify"""

    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        try:
            import praw
        except ImportError:
            raise ImportError("请安装 praw: pip install praw")
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        logger.info("RedditMonitor: PRAW client initialized")

    def search_subreddits(
        self, subreddits: List[str], limit: int = 25, time_filter: str = "week"
    ) -> List[Dict]:
        """搜索指定 subreddit 的热门帖子"""
        results = []
        for sub_name in subreddits:
            sub_name = sub_name.strip()
            try:
                subreddit = self.reddit.subreddit(sub_name)
                if time_filter == "week":
                    posts = list(subreddit.new(limit=limit))
                elif time_filter == "month":
                    posts = list(subreddit.top(time_filter="month", limit=limit))
                else:
                    posts = list(subreddit.hot(limit=limit))

                for post in posts:
                    results.append({
                        "subreddit": sub_name,
                        "title": post.title,
                        "url": post.url,
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "created_utc": datetime.datetime.utcfromtimestamp(post.created_utc).isoformat(),
                        "selftext": post.selftext[:500] if post.selftext else "",
                        "flair": post.link_flair_text or "",
                    })
                logger.info(f"RedditMonitor: fetched {len(posts)} posts from r/{sub_name}")
            except Exception as e:
                logger.error(f"RedditMonitor: failed for r/{sub_name}: {e}")
        return results


class YouTubeMonitor:
    """YouTube 视频监控 - 使用 youtube-search-python 替代官方 Data API"""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.use_official = bool(api_key)

    def search_videos(self, keyword: str, max_results: int = 10) -> List[Dict]:
        """搜索 YouTube 视频"""
        if self.use_official:
            return self._search_official(keyword, max_results)
        else:
            return self._search_opensource(keyword, max_results)

    def _search_opensource(self, keyword: str, max_results: int = 10) -> List[Dict]:
        """使用 youtube-search-python (免费爬虫方式)"""
        try:
            from youtube_search import YoutubeSearch
        except ImportError:
            raise ImportError("请安装 youtube-search-python: pip install youtube-search-python")

        results = []
        try:
            search_results = YoutubeSearch(keyword, max_results=max_results).to_dict()
            for video in search_results:
                results.append({
                    "title": video.get("title", ""),
                    "video_id": video.get("id", ""),
                    "url": f"https://www.youtube.com/watch?v={video.get('id', '')}",
                    "channel": video.get("channel", ""),
                    "views": video.get("views", ""),
                    "duration": video.get("duration", ""),
                    "published": video.get("published", ""),
                    "description": video.get("description", "")[:300],
                })
            logger.info(f"YouTubeMonitor: found {len(results)} videos for '{keyword}'")
        except Exception as e:
            logger.error(f"YouTubeMonitor: opensource search failed for '{keyword}': {e}")
        return results

    def _search_official(self, keyword: str, max_results: int = 10) -> List[Dict]:
        """使用 YouTube Data API v3 (备用方案)"""
        try:
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError("请安装 google-api-python-client: pip install google-api-python-client")

        results = []
        try:
            youtube = build("youtube", "v3", developerKey=self.api_key)
            request = youtube.search().list(
                q=keyword,
                part="snippet",
                type="video",
                maxResults=max_results,
            )
            response = request.execute()
            for item in response.get("items", []):
                snippet = item["snippet"]
                results.append({
                    "title": snippet.get("title", ""),
                    "video_id": item["id"]["videoId"],
                    "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                    "channel": snippet.get("channelTitle", ""),
                    "published": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", "")[:300],
                })
            logger.info(f"YouTubeMonitor: official API found {len(results)} videos for '{keyword}'")
        except Exception as e:
            logger.error(f"YouTubeMonitor: official API failed for '{keyword}': {e}")
        return results


class GoogleNewsMonitor:
    """Google News 监控 - 使用 RSS Feed (完全免费)"""

    def search_news(self, keyword: str, max_results: int = 15) -> List[Dict]:
        """通过 RSS 搜索新闻"""
        import feedparser
        rss_url = f"https://news.google.com/rss/search?q={keyword}&hl=en&gl=US&max={max_results}"
        results = []
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                results.append({
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "source": entry.get("source", {}).get("title", "Google News"),
                    "summary": entry.get("summary", "")[:300],
                })
            logger.info(f"GoogleNewsMonitor: found {len(results)} news items for '{keyword}'")
        except Exception as e:
            logger.error(f"GoogleNewsMonitor: failed for '{keyword}': {e}")
        return results


# ============================================================
# 4. AI 分析模块 (支持多提供商切换)
# ============================================================

class AIAnalyzer:
    """AI 分析器 - 支持 DeepSeek / Kimi / Ollama 本地模型"""

    def __init__(self, provider: str = "kimi"):
        self.provider = provider
        logger.info(f"AIAnalyzer: initialized with provider='{provider}'")

    def analyze_voc(self, raw_data: Dict[str, Any], keywords: List[str]) -> Dict[str, Any]:
        """对采集的原始 VOC 数据进行分析, 输出行动建议"""
        prompt = self._build_prompt(raw_data, keywords)
        response = self._call_model(prompt)
        return self._parse_response(response)

    def _build_prompt(self, raw_data: Dict, keywords: List[str]) -> str:
        """构建 AI 分析提示词"""
        return textwrap.dedent(f"""\
            你是一位海外市场情报分析师。请根据以下 VOC (Voice of Customer) 监控数据,
            分析品牌在以下渠道的表现并给出行动建议:

            监控关键词: {", ".join(keywords)}

            数据概要:
            - Google搜索排名数据: {len(raw_data.get("search_results", []))} 个关键词
            - Reddit社区讨论: {len(raw_data.get("reddit_posts", []))} 条帖子
            - YouTube视频: {len(raw_data.get("youtube_videos", []))} 个视频
            - 新闻资讯: {len(raw_data.get("news_items", []))} 条新闻

            请输出:
            1. 品牌在各渠道的排名/曝光概况
            2. 用户关注的热点话题和痛点
            3. 竞品动态与机会缺口
            4. 本周优先行动建议 (最多5条, 具体可执行)

            用中文回答, 简洁明了。
        """)

    def _call_model(self, prompt: str) -> str:
        """调用 AI 模型"""
        if self.provider == "deepseek":
            return self._call_deepseek(prompt)
        elif self.provider == "kimi":
            return self._call_kimi(prompt)
        elif self.provider == "ollama":
            return self._call_ollama(prompt)
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")

    def _call_deepseek(self, prompt: str) -> str:
        """调用 DeepSeek API"""
        import requests
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_kimi(self, prompt: str) -> str:
        """调用 Kimi (Moonshot) API"""
        import requests
        resp = requests.post(
            "https://api.moonshot.cn/v1/chat/completions",
            headers={"Authorization": f"Bearer {KIMI_API_KEY}"},
            json={
                "model": "moonshot-v1-8k",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_ollama(self, prompt: str) -> str:
        """调用本地 Ollama 模型 (如 Qwen2.5-7B)"""
        import requests
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": "qwen2.5:7b",
                "prompt": prompt,
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析 AI 分析结果"""
        return {
            "analysis": response,
            "provider": self.provider,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }


# ============================================================
# 5. HTML 看板生成器
# ============================================================

class DashboardGenerator:
    """生成静态 HTML 看板"""

    def __init__(self, output_dir: Path = HTML_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, data: Dict[str, Any], ai_analysis: Dict[str, Any]) -> str:
        """生成 index.html"""
        html_content = self._build_html(data, ai_analysis)
        output_path = self.output_dir / "index.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info(f"DashboardGenerator: saved to {output_path}")
        return str(output_path)

    def _build_html(self, data: Dict, ai_analysis: Dict) -> str:
        """构建 HTML 内容"""
        search_count = len(data.get("search_results", []))
        reddit_count = len(data.get("reddit_posts", []))
        youtube_count = len(data.get("youtube_videos", []))
        news_count = len(data.get("news_items", []))

        # 渲染各板块
        reddit_html = self._render_reddit_posts(data.get("reddit_posts", []))
        youtube_html = self._render_youtube_videos(data.get("youtube_videos", []))
        search_html = self._render_search_results(data.get("search_results", []))

        data_json = json.dumps(data, ensure_ascii=False, indent=2)
        analysis_text = ai_analysis.get("analysis", "暂无分析结果")

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VOC 中控台看板</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        header {{ text-align: center; padding: 30px 0; border-bottom: 1px solid #334155; margin-bottom: 30px; }}
        header h1 {{ font-size: 2rem; color: #38bdf8; margin-bottom: 8px; }}
        header p {{ color: #94a3b8; font-size: 0.95rem; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }}
        .stat-card {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }}
        .stat-card h3 {{ font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }}
        .stat-card .value {{ font-size: 2rem; font-weight: 700; color: #38bdf8; }}
        .section {{ background: #1e293b; border-radius: 12px; padding: 24px; margin-bottom: 20px; border: 1px solid #334155; }}
        .section h2 {{ font-size: 1.25rem; color: #38bdf8; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #334155; }}
        .item {{ background: #0f172a; border-radius: 8px; padding: 16px; margin-bottom: 12px; border-left: 3px solid #38bdf8; }}
        .item h4 {{ color: #f1f5f9; margin-bottom: 6px; }}
        .item p {{ color: #94a3b8; font-size: 0.9rem; line-height: 1.6; }}
        .item a {{ color: #38bdf8; text-decoration: none; }}
        .item a:hover {{ text-decoration: underline; }}
        .meta {{ font-size: 0.8rem; color: #64748b; margin-top: 6px; }}
        .tag {{ display: inline-block; background: #334155; color: #cbd5e1; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; margin-right: 6px; }}
        .action-item {{ border-left-color: #f59e0b; }}
        .action-item h4 {{ color: #f59e0b; }}
        .raw-data {{ background: #0f172a; padding: 16px; border-radius: 8px; overflow-x: auto; }}
        .raw-data pre {{ color: #a5f3fc; font-size: 0.85rem; }}
        .timestamp {{ text-align: center; color: #64748b; font-size: 0.85rem; padding: 20px 0; border-top: 1px solid #334155; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>VOC 中控台看板</h1>
            <p>自动化客户之声监控系统 | 省钱版架构</p>
        </header>

        <div class="stats">
            <div class="stat-card">
                <h3>Google 搜索监控</h3>
                <div class="value">{search_count}</div>
                <p style="color:#64748b;font-size:0.85rem;">关键词已追踪</p>
            </div>
            <div class="stat-card">
                <h3>Reddit 社区讨论</h3>
                <div class="value">{reddit_count}</div>
                <p style="color:#64748b;font-size:0.85rem;">帖子已采集</p>
            </div>
            <div class="stat-card">
                <h3>YouTube 视频监控</h3>
                <div class="value">{youtube_count}</div>
                <p style="color:#64748b;font-size:0.85rem;">视频已追踪</p>
            </div>
            <div class="stat-card">
                <h3>新闻资讯监控</h3>
                <div class="value">{news_count}</div>
                <p style="color:#64748b;font-size:0.85rem;">新闻已采集</p>
            </div>
        </div>

        <!-- AI 分析建议 -->
        <div class="section">
            <h2>AI 分析行动建议</h2>
            <div class="item action-item">
                <h4>分析报告</h4>
                <pre style="color:#cbd5e1;font-size:0.9rem;line-height:1.8;white-space:pre-wrap;">{analysis_text}</pre>
            </div>
        </div>

        <!-- 搜索排名 -->
        <div class="section">
            <h2>Google 搜索排名</h2>
            {search_html if search_html else '<p style="color:#64748b;">暂无数据</p>'}
        </div>

        <!-- Reddit 帖子 -->
        <div class="section">
            <h2>Reddit 社区热帖</h2>
            {reddit_html if reddit_html else '<p style="color:#64748b;">暂无数据</p>'}
        </div>

        <!-- YouTube 视频 -->
        <div class="section">
            <h2>YouTube 相关视频</h2>
            {youtube_html if youtube_html else '<p style="color:#64748b;">暂无数据</p>'}
        </div>

        <!-- 原始数据 -->
        <div class="section">
            <h2>原始数据 (JSON)</h2>
            <div class="raw-data">
                <pre>{data_json}</pre>
            </div>
        </div>

        <div class="timestamp">
            最后更新: {datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")} |
            运行环境: GitHub Actions + Python 3
        </div>
    </div>
</body>
</html>"""

    def _render_search_results(self, results: List[Dict]) -> str:
        """渲染搜索排名 HTML"""
        if not results:
            return ""
        items = []
        for r in results:
            kw = r.get("keyword", "")
            total = r.get("total_results", "")
            paa = r.get("paa_results", [])
            paa_html = ""
            if paa:
                paa_items = [f"<li>{item.get('question', item.get('title', ''))}</li>" for item in paa[:5]]
                paa_html = f"<h5 style='color:#38bdf8;margin:8px 0;'>People Also Ask:</h5><ul>{''.join(paa_items)}</ul>"
            items.append(f"""
            <div class="item">
                <h4>关键词: {kw}</h4>
                <p>总结果数: {total}</p>
                {paa_html}
            </div>
            """)
        return "\n".join(items)

    def _render_reddit_posts(self, posts: List[Dict]) -> str:
        """渲染 Reddit 帖子 HTML"""
        if not posts:
            return ""
        items = []
        for post in posts[:20]:
            items.append(f"""
            <div class="item">
                <h4><a href="{post.get('url', '#')}" target="_blank">{post.get('title', '无标题')}</a></h4>
                <p>{post.get('selftext', '')[:200]}</p>
                <div class="meta">
                    <span class="tag">r/{post.get('subreddit', '')}</span>
                    <span>▲ {post.get('score', 0)}</span>
                    <span>💬 {post.get('num_comments', 0)}</span>
                    <span>{post.get('created_utc', '')[:10]}</span>
                </div>
            </div>
            """)
        return "\n".join(items)

    def _render_youtube_videos(self, videos: List[Dict]) -> str:
        """渲染 YouTube 视频 HTML"""
        if not videos:
            return ""
        items = []
        for video in videos[:15]:
            items.append(f"""
            <div class="item">
                <h4><a href="{video.get('url', '#')}" target="_blank">{video.get('title', '无标题')}</a></h4>
                <p>频道: {video.get('channel', '')} | 时长: {video.get('duration', '')}</p>
                <div class="meta">
                    <span>👁 {video.get('views', '')}</span>
                    <span>{video.get('published', '')}</span>
                </div>
            </div>
            """)
        return "\n".join(items)


# ============================================================
# 6. 通知推送模块
# ============================================================

class NotificationSender:
    """报告推送 - 支持邮件和 Webhook"""

    def send_email(self, to_emails: List[str], subject: str, body: str, html_path: str = ""):
        """发送 HTML 报告邮件"""
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["To"] = ", ".join(to_emails)
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html_path and os.path.exists(html_path):
            with open(html_path, "r", encoding="utf-8") as f:
                msg.attach(MIMEText(f.read(), "html", "utf-8"))

        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")

        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_emails, msg.as_string())
            server.quit()
            logger.info(f"NotificationSender: email sent to {to_emails}")
        except Exception as e:
            logger.error(f"NotificationSender: email failed: {e}")

    def send_webhook(self, webhook_url: str, message: str):
        """发送 Webhook 消息 (飞书/钉钉/Slack)"""
        import requests
        payload = {"text": message}
        try:
            resp = requests.post(webhook_url, json=payload, timeout=30)
            resp.raise_for_status()
            logger.info("NotificationSender: webhook sent successfully")
        except Exception as e:
            logger.error(f"NotificationSender: webhook failed: {e}")


# ============================================================
# 7. 主流程编排
# ============================================================

def save_json(data: Dict, filename: str) -> Path:
    """保存 JSON 数据到文件"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DATA_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Data saved: {output_path}")
    return output_path


def main():
    """主执行流程"""
    logger.info("=" * 60)
    logger.info("VOC Monitor 启动")
    logger.info(f"监控关键词: {MONITOR_KEYWORDS}")
    logger.info(f"AI提供商: {AI_PROVIDER}")
    logger.info("=" * 60)

    all_data = {
        "run_id": datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
        "keywords": MONITOR_KEYWORDS,
        "search_results": [],
        "reddit_posts": [],
        "youtube_videos": [],
        "news_items": [],
    }

    # 1. Google 搜索监控 (Serper.dev)
    if SERPER_API_KEY:
        logger.info(">>> 开始 Google 搜索监控 (Serper.dev)")
        search_monitor = SearchMonitor(SERPER_API_KEY)
        all_data["search_results"] = search_monitor.monitor_keywords(MONITOR_KEYWORDS)
    else:
        logger.warning("SERPER_API_KEY 未配置, 跳过 Google 搜索监控")

    # 2. Reddit 社区监控 (PRAW)
    if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
        logger.info(">>> 开始 Reddit 社区监控 (PRAW)")
        reddit_monitor = RedditMonitor(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT)
        all_data["reddit_posts"] = reddit_monitor.search_subreddits(REDDIT_SUBREDDITS)
    else:
        logger.warning("Reddit 凭据未配置, 跳过 Reddit 监控")

    # 3. YouTube 视频监控
    logger.info(">>> 开始 YouTube 视频监控")
    yt_monitor = YouTubeMonitor(YOUTUBE_API_KEY)
    for kw in MONITOR_KEYWORDS[:3]:
        all_data["youtube_videos"].extend(yt_monitor.search_videos(kw))
    if not all_data["youtube_videos"]:
        logger.warning("YouTube 监控未返回数据, 请检查配置")

    # 4. Google News 监控 (RSS)
    logger.info(">>> 开始 Google News 监控 (RSS)")
    news_monitor = GoogleNewsMonitor()
    for kw in MONITOR_KEYWORDS[:3]:
        all_data["news_items"].extend(news_monitor.search_news(kw))

    # 5. AI 分析
    ai_analysis = {"analysis": "AI分析未配置或失败, 请检查 AI_PROVIDER 和相关 API Key", "provider": "none"}
    if AI_PROVIDER != "none" and any(all_data.values()):
        logger.info(">>> 开始 AI 分析")
        try:
            analyzer = AIAnalyzer(AI_PROVIDER)
            ai_analysis = analyzer.analyze_voc(all_data, MONITOR_KEYWORDS)
        except Exception as e:
            logger.error(f"AI分析失败: {e}")
            ai_analysis = {"analysis": f"AI分析失败: {str(e)}", "provider": AI_PROVIDER}

    # 6. 保存数据
    save_json(all_data, f"voc_data_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")

    # 7. 生成 HTML 看板
    dashboard = DashboardGenerator()
    html_path = dashboard.generate(all_data, ai_analysis)

    # 8. 推送通知 (可选)
    webhook_url = os.getenv("WEBHOOK_URL", "")
    if webhook_url:
        notifier = NotificationSender()
        summary = (
            f"VOC监控报告已生成\n"
            f"搜索监控: {len(all_data['search_results'])} 个关键词\n"
            f"Reddit帖子: {len(all_data['reddit_posts'])} 条\n"
            f"YouTube视频: {len(all_data['youtube_videos'])} 个\n"
            f"新闻资讯: {len(all_data['news_items'])} 条"
        )
        notifier.send_webhook(webhook_url, summary)

    logger.info("=" * 60)
    logger.info("VOC Monitor 运行完成")
    logger.info(f"看板文件: {html_path}")
    logger.info("=" * 60)

    return all_data


if __name__ == "__main__":
    main()
