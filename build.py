#!/usr/bin/env python3
"""EVEngine Blog static site generator (Python stdlib only, zero deps).

Posts live in posts/ as Markdown files named YYYY-MM-DD-slug.md with
optional front matter (title / date / tags / summary). Run `python build.py`
to regenerate the site/ directory.
"""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "posts"
ASSETS_DIR = ROOT / "assets"
OUT_DIR = ROOT / "site"

SITE = {
    "title": "EVEngine 开发博客",
    "subtitle": "EVEngine 的开发日志与技术笔记",
    "author": "EVEngine",
    "github": "https://github.com/EVEngine/EVEngine",
    "blog_repo": "https://github.com/EVEngine/Blog",
    "site_url": "https://evengine.github.io/Blog/",
}

LIST_MARK = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.*)$")
HEADING_MARK = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_MARK = re.compile(r"^(```|~~~)\s*([\w+-]*)\s*$")
HR_MARK = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$")


# --------------------------------------------------------------------------
# Markdown -> HTML
# --------------------------------------------------------------------------

def inline(text: str) -> str:
    """Convert inline markdown (code, links, images, bold/italic, autolinks)."""
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", lambda m: "<code>" + m.group(1) + "</code>", text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img alt="\1" src="\2">', text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)",
        r'<a href="\2">\1</a>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(
        r"(?<![A-Za-z0-9_])_([^_]+)_(?![A-Za-z0-9_])",
        r"<em>\1</em>",
        text,
    )
    text = re.sub(
        r"(?<![\"'>])(https?://[^\s<]+)",
        r'<a href="\1">\1</a>',
        text,
    )
    return text


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def is_sep_row(line: str) -> bool:
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells)


def table_html(rows: list[str]) -> str:
    header = split_row(rows[0])
    body = [split_row(r) for r in rows[2:]]
    ncols = max([len(header)] + [len(r) for r in body], default=0)
    cells = lambda row: "".join(
        f"<td>{inline(c)}</td>" for c in (row + [""] * (ncols - len(row)))[:ncols]
    )
    head = "".join(f"<th>{inline(c)}</th>" for c in header)
    rows_html = "".join(f"<tr>{cells(r)}</tr>" for r in body)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table>"


def collect_list(lines: list[str], i: int) -> tuple[list, int]:
    items: list[tuple[int, bool, list]] = []
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            break
        m = LIST_MARK.match(line)
        if not m:
            break
        indent = len(m.group(1))
        ordered = m.group(2)[0].isdigit()
        content: list = [m.group(3)]
        i += 1
        while i < len(lines) and lines[i].strip():
            m2 = LIST_MARK.match(lines[i])
            if m2 and len(m2.group(1)) > indent:
                sub, i = collect_list(lines, i)
                content.append(sub)
                continue
            if m2:
                break
            if lines[i].startswith((" ", "\t")):
                content.append(lines[i].strip())
                i += 1
            else:
                break
        items.append((indent, ordered, content))
    return items, i


def render_list(items: list) -> str:
    out: list[str] = []
    current_tag: str | None = None
    for _indent, ordered, content in items:
        tag = "ol" if ordered else "ul"
        if tag != current_tag:
            if current_tag:
                out.append(f"</{current_tag}>")
            out.append(f"<{tag}>")
            current_tag = tag
        li = [inline(content[0])] if content[0] else []
        for extra in content[1:]:
            if isinstance(extra, list):
                li.append(render_list(extra))
            elif extra.strip():
                li.append("<p>" + inline(extra) + "</p>")
        out.append("<li>" + "".join(li) + "</li>")
    if current_tag:
        out.append(f"</{current_tag}>")
    return "".join(out)


def is_block_start(line: str) -> bool:
    return bool(
        HEADING_MARK.match(line)
        or FENCE_MARK.match(line)
        or line.startswith(">")
        or line.startswith("|")
        or LIST_MARK.match(line)
        or HR_MARK.match(line)
    )


def blocks_to_html(lines: list[str]) -> str:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        m = FENCE_MARK.match(line)
        if m:
            fence, lang = m.group(1), m.group(2) or "text"
            buf: list[str] = []
            i += 1
            while i < len(lines) and not re.match(rf"^{fence}\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1
            code = html.escape("\n".join(buf))
            out.append(f'<pre><code class="language-{lang}">{code}</code></pre>')
            continue

        if line.strip().startswith("|") and i + 1 < len(lines) and is_sep_row(lines[i + 1]):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(table_html(rows))
            continue

        m = HEADING_MARK.match(line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue

        if HR_MARK.match(line):
            out.append("<hr>")
            i += 1
            continue

        if line.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i][1:].lstrip())
                i += 1
            out.append("<blockquote>" + inline(" ".join(buf)) + "</blockquote>")
            continue

        m = LIST_MARK.match(line)
        if m:
            items, i = collect_list(lines, i)
            out.append(render_list(items))
            continue

        buf = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not is_block_start(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>" + inline(" ".join(buf)) + "</p>")

    return "\n".join(out)


# --------------------------------------------------------------------------
# Front matter & posts
# --------------------------------------------------------------------------

def parse_front_matter(text: str) -> tuple[dict, str]:
    meta: dict = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            block = text[3:end]
            rest = text[end + 4:].lstrip("\n")
            for line in block.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip('"').strip("'")
            return meta, rest
    return meta, text


def slug_from_name(name: str) -> str:
    stem = Path(name).stem
    m = re.match(r"^\d{4}-\d{2}-\d{2}-(.*)$", stem)
    return m.group(1) if m else stem


def load_posts() -> list[dict]:
    posts = []
    for path in sorted(POSTS_DIR.glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        lines = body.splitlines()
        # Drop a leading H1 from the body when front matter already provides a title.
        while lines and (not lines[0].strip() or HEADING_MARK.match(lines[0])):
            if HEADING_MARK.match(lines[0]) and len(HEADING_MARK.match(lines[0]).group(1)) == 1:
                lines.pop(0)
                continue
            if not lines[0].strip():
                lines.pop(0)
                continue
            break
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-", path.name)
        date_s = meta.get("date") or (m.group(1) if m else "")
        tags = [t.strip() for t in meta.get("tags", "").strip("[]").split(",") if t.strip()]
        posts.append(
            {
                "slug": slug_from_name(path.name),
                "date": date_s,
                "title": meta.get("title") or slug_from_name(path.name).replace("-", " "),
                "summary": meta.get("summary", ""),
                "tags": tags,
                "body_html": blocks_to_html(lines),
            }
        )
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def tags_html(tags: list[str]) -> str:
    return "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags)


def page(title: str, main_html: str, css: str, root: str, summary: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · {html.escape(SITE['title'])}</title>
  <meta name="description" content="{html.escape(summary or SITE['subtitle'])}">
  <link rel="stylesheet" href="{root}{css}">
</head>
<body>
  <header class="site-head wrap">
    <a class="brand" href="{root}index.html">{html.escape(SITE['title'])}</a>
    <span class="tagline">{html.escape(SITE['subtitle'])}</span>
  </header>
  <main class="wrap">
{main_html}
  </main>
  <footer class="site-foot wrap">
    <span>© 2026 {html.escape(SITE['author'])}</span>
    <span><a href="{SITE['github']}">GitHub</a> · <a href="{SITE['blog_repo']}">Blog 仓库</a></span>
  </footer>
</body>
</html>
"""


def build_index(posts: list[dict]) -> str:
    entries = []
    for p in posts:
        summary = (
            f'<p class="summary">{html.escape(p["summary"])}</p>' if p["summary"] else ""
        )
        entries.append(
            '<article class="entry">\n'
            f'<div class="entry-meta">{p["date"]}{tags_html(p["tags"])}</div>\n'
            f'<h2><a href="posts/{p["slug"]}.html">{html.escape(p["title"])}</a></h2>\n'
            f"{summary}\n"
            "</article>"
        )
    main = (
        '<section class="hero">\n'
        f'<p class="hero-sub">{html.escape(SITE["subtitle"])}</p>\n'
        "</section>\n"
        '<section class="entries">\n'
        + "\n".join(entries)
        + "\n</section>"
    )
    return page(SITE["title"], main, "assets/style.css", "", SITE["subtitle"])


def build_post(p: dict) -> str:
    summary_html = (
        f'<p class="lead">{html.escape(p["summary"])}</p>' if p["summary"] else ""
    )
    main = (
        '<article class="post">\n'
        '<header class="post-head">\n'
        f'<div class="post-meta">{p["date"]}{tags_html(p["tags"])}</div>\n'
        f"<h1>{html.escape(p['title'])}</h1>\n"
        f"{summary_html}\n"
        "</header>\n"
        '<div class="post-body">\n'
        f'{p["body_html"]}\n'
        "</div>\n"
        "</article>\n"
        '<p class="back"><a href="../index.html">← 返回博客首页</a></p>'
    )
    return page(
        p["title"], main, "assets/style.css", "../", p["summary"]
    )


def build_feed(posts: list[dict]) -> str:
    entries = []
    for p in posts:
        url = f'{SITE["site_url"]}posts/{p["slug"]}.html'
        entries.append(
            "<entry>\n"
            f"<title>{html.escape(p['title'])}</title>\n"
            f'<link href="{url}"/>\n'
            f'<id>{url}</id>\n'
            f'<updated>{p["date"]}T00:00:00Z</updated>\n'
            f"<summary>{html.escape(p['summary'] or '')}</summary>\n"
            "</entry>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"<title>{html.escape(SITE['title'])}</title>\n"
        f'<link href="{SITE["site_url"]}feed.xml" rel="self"/>\n'
        f'<link href="{SITE["site_url"]}"/>\n'
        f"<updated>{posts[0]['date']}T00:00:00Z</updated>\n"
        + "\n".join(entries)
        + "\n</feed>\n"
    )


def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    (OUT_DIR / "posts").mkdir(parents=True)
    (OUT_DIR / "assets").mkdir(parents=True)
    shutil.copy2(ASSETS_DIR / "style.css", OUT_DIR / "assets" / "style.css")

    posts = load_posts()
    (OUT_DIR / "index.html").write_text(build_index(posts), encoding="utf-8")
    (OUT_DIR / "feed.xml").write_text(build_feed(posts), encoding="utf-8")
    for p in posts:
        (OUT_DIR / "posts" / f'{p["slug"]}.html').write_text(
            build_post(p), encoding="utf-8"
        )

    print(f"Built {len(posts)} post(s) -> {OUT_DIR.relative_to(ROOT)}")
    for p in posts:
        print(f"  {p['date']}  {p['title']}")


if __name__ == "__main__":
    main()
