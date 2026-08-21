# EVEngine Blog

EVEngine 官方开发博客：开发日志与技术笔记。

- 文章源文件：`posts/*.md`（Markdown，带简单 front matter）
- 站点生成：`python build.py`（纯标准库，零依赖）
- 发布地址：<https://evengine.github.io/Blog/>
- 自动部署：推送到 `main` 后由 GitHub Actions 构建并发布到 GitHub Pages

## 添加一篇新文章

1. 在 `posts/` 下新建 Markdown 文件，文件名建议以日期开头：
   `2026-08-22-devlog-v0.1.0.md`
2. 文件头部写 front matter：

   ```markdown
   ---
   title: 文章标题
   date: 2026-08-22
   tags: [开发日志, EVEngine]
   summary: 一句话摘要（显示在首页列表和 <meta description> 中）
   ---
   ```

3. 正文按普通 Markdown 写即可。支持：标题、列表（含嵌套）、引用、
   代码块（带语言标注）、行内代码、表格、链接、图片、加粗/斜体。
4. 本地预览：

   ```bash
   python build.py
   python -m http.server 8000 -d site
   # 浏览器打开 http://localhost:8000/
   ```

5. 推送到 `main`，Actions 会自动构建并部署到 GitHub Pages。

## 项目结构

```text
Blog/
├── build.py                  # 站点生成器（纯 Python 标准库）
├── assets/style.css          # 主题样式
├── posts/*.md                # 博客文章源文件
├── site/                     # 构建输出（git 忽略，由 Actions 生成）
└── .github/workflows/blog.yml # 自动构建 + 部署到 Pages
```
