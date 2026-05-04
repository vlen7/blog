#!/usr/bin/env python3
"""博客发布脚本：扫描 ~/ai/blog/posts/*.md → 生成 HTML → 部署到 hehan.tech"""

import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

PROJECT = os.path.expanduser("~/ai/blog")
POSTS_DIR = os.path.join(PROJECT, "posts")        # 你的 .md 放这里
OUTPUT_DIR = os.path.join(PROJECT, "output")       # 生成的 HTML
TEMPLATE = os.path.join(PROJECT, "templates", "post.html")

REMOTE_HOST = "root@100.121.221.104"
REMOTE_ROOT = "/var/www/hehan.tech"

# ── helpers ──────────────────────────────────────────────

def parse_frontmatter(md_path):
    """从 markdown 文件顶部提取 YAML-like frontmatter: date, title, description"""
    defaults = {
        "date": "",
        "title": "",
        "description": "",
    }
    with open(md_path) as f:
        text = f.read()
    # 查找 frontmatter 块 (--- ... ---)
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if not m:
        # 没有 frontmatter: 用文件名当标题
        basename = os.path.splitext(os.path.basename(md_path))[0]
        defaults["title"] = basename.replace("-", " ")
        defaults["raw_content"] = text
        return defaults

    fm_text = m.group(1)
    defaults["raw_content"] = text[m.end():]
    for line in fm_text.strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            defaults[key.strip()] = val.strip().strip('"').strip("'")
    return defaults


def md_to_html(md_text):
    """Markdown → HTML（纯 body 内容）"""
    import markdown
    return markdown.markdown(
        md_text,
        extensions=["fenced_code", "codehilite", "tables", "nl2br"]
    )


def generate_post(md_path):
    """读取一篇 .md → 生成 .html"""
    slug = os.path.splitext(os.path.basename(md_path))[0]
    meta = parse_frontmatter(md_path)

    # 日期：优先 frontmatter，否则用文件修改时间
    if meta["date"]:
        try:
            dt = datetime.strptime(meta["date"], "%Y-%m-%d")
        except ValueError:
            dt = datetime.fromtimestamp(os.path.getmtime(md_path))
    else:
        dt = datetime.fromtimestamp(os.path.getmtime(md_path))
    date_str = dt.strftime("%Y-%m-%d")
    date_display = f"{dt.year}年{dt.month}月{dt.day}日"

    # 转换内容
    html_body = md_to_html(meta["raw_content"])

    # 没有 frontmatter title? 从第一个 h1 提取
    title = meta["title"]
    if not title:
        h1_match = re.search(r'<h1>(.+?)</h1>', html_body)
        title = h1_match.group(1) if h1_match else slug.replace("-", " ")

    description = meta["description"]
    if not description:
        # 取前 150 字纯文本作为描述
        clean = re.sub(r'<[^>]+>', '', html_body)
        description = clean[:150].strip()

    # 套模板
    with open(TEMPLATE) as f:
        tmpl = f.read()

    html = (
        tmpl
        .replace("{{title}}", title)
        .replace("{{date}}", date_display)
        .replace("{{description}}", description)
        .replace("{{content}}", html_body)
    )

    out_path = os.path.join(OUTPUT_DIR, "posts", f"{slug}.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)

    return {
        "slug": slug,
        "title": title,
        "date": date_str,
        "output": out_path,
    }


def build_index(posts):
    """根据文章列表重新生成首页"""
    items_html = ""
    for p in sorted(posts, key=lambda x: x["date"], reverse=True):
        items_html += (
            f'    <li class="post-item">\n'
            f'      <span class="post-date">{p["date"]}</span>\n'
            f'      <a href="/posts/{p["slug"]}.html" class="post-link">{p["title"]}</a>\n'
            f'    </li>\n'
        )

    index_tmpl = os.path.join(PROJECT, "templates", "index.html")
    with open(index_tmpl) as f:
        index = f.read()
    index = index.replace("{{posts}}", items_html.strip())

    index_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(index_path, "w") as f:
        f.write(index)


def build_rss(posts):
    """生成 RSS feed"""
    items_xml = ""
    for p in sorted(posts, key=lambda x: x["date"], reverse=True):
        pub_date = ""
        if p["date"]:
            try:
                from datetime import datetime
                dt = datetime.strptime(p["date"], "%Y-%m-%d")
                pub_date = dt.strftime("%a, %d %b %Y 00:00:00 +0800")
            except ValueError:
                pass
        items_xml += (
            f'  <item>\n'
            f'    <title>{p["title"]}</title>\n'
            f'    <link>https://hehan.tech/posts/{p["slug"]}.html</link>\n'
            f'    <guid>https://hehan.tech/posts/{p["slug"]}.html</guid>\n'
            f'    <pubDate>{pub_date}</pubDate>\n'
            f'  </item>\n'
        )

    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '<channel>\n'
        '  <title>微冷</title>\n'
        '  <link>https://hehan.tech</link>\n'
        '  <description>技术 · 思考 · 日常</description>\n'
        '  <language>zh-CN</language>\n'
        '  <atom:link href="https://hehan.tech/rss.xml" rel="self" type="application/rss+xml"/>\n'
        f'{items_xml}'
        '</channel>\n'
        '</rss>\n'
    )

    rss_path = os.path.join(OUTPUT_DIR, "rss.xml")
    with open(rss_path, "w") as f:
        f.write(rss)


def deploy():
    """部署到远程服务器"""
    cmds = [
        f"scp {OUTPUT_DIR}/index.html {REMOTE_HOST}:{REMOTE_ROOT}/index.html",
        f"scp {OUTPUT_DIR}/rss.xml {REMOTE_HOST}:{REMOTE_ROOT}/rss.xml",
        # 确保远程 posts 目录存在
        f"ssh {REMOTE_HOST} 'mkdir -p {REMOTE_ROOT}/posts'",
        # 上传所有生成的 post HTML
        f"scp {OUTPUT_DIR}/posts/*.html {REMOTE_HOST}:{REMOTE_ROOT}/posts/",
    ]

    # 同步图片目录（如果有）
    images_dir = os.path.join(POSTS_DIR, "images")
    if os.path.isdir(images_dir) and os.listdir(images_dir):
        cmds.extend([
            f"ssh {REMOTE_HOST} 'mkdir -p {REMOTE_ROOT}/posts/images'",
            f"scp -r {images_dir}/* {REMOTE_HOST}:{REMOTE_ROOT}/posts/images/",
        ])

    for cmd in cmds:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"❌ 部署失败: {cmd}\n{r.stderr}", file=sys.stderr)
            return False
    return True


# ── main ─────────────────────────────────────────────────

def main():
    md_files = sorted(
        [f for f in os.listdir(POSTS_DIR) if f.endswith(".md")],
        key=lambda f: os.path.getmtime(os.path.join(POSTS_DIR, f)),
        reverse=True,
    )

    if not md_files:
        print("📝 没有找到 .md 文件。请把 markdown 放到 posts/ 目录。")
        return

    posts = []
    for f in md_files:
        path = os.path.join(POSTS_DIR, f)
        print(f"  📄 {f} → HTML...")
        posts.append(generate_post(path))

    print(f"\n✅ 共生成 {len(posts)} 篇文章")
    print("🏠 更新首页...")
    build_index(posts)
    print("📡 更新 RSS...")
    build_rss(posts)

    print("🚀 部署到 hehan.tech...")
    if deploy():
        print(f"\n✨ 完成！https://hehan.tech")
    else:
        print("\n⚠️ 部署出错，请检查网络连接。")


if __name__ == "__main__":
    main()
