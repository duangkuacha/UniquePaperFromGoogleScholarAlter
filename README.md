# UniquePaperFromGoogleScholarAlter

从 Gmail 的 Google Scholar Alert 邮件中提取去重论文，并通过 GitHub Actions 自动更新 GitHub Pages 文献库。

## 工作方式

- 每天北京时间 06:00 运行，也可以在 Actions 页面手动运行。
- 工作流从 Gmail 读取未读 Scholar Alert 邮件，提取标题、作者、摘要和论文链接。
- 运行结果写入 `data/days/`，`build_site.py` 再生成 `data/catalog.json`，页面通过这个目录展示数据。
- 邮件处理成功后会移除 `UNREAD` 标签；没有新邮件时不会生成空记录。
- 页面只发布论文元数据。Google Scholar 跟踪参数、邮箱地址和 OAuth 内容不会写入公开数据。

## 一次性配置 GitHub

### Repository secrets

在仓库的 **Settings → Secrets and variables → Actions → New repository secret** 中添加：

| Secret | 内容 |
| --- | --- |
| `GMAIL_CREDENTIALS_JSON` | Google Cloud OAuth 客户端 JSON 的完整内容 |
| `GMAIL_TOKEN_JSON` | 本地授权后生成的 `token.json` 完整内容 |

这两个值只在 Actions 运行时写入 runner 的临时目录，工作流结束后会删除。不要把它们写进代码、Markdown、Issue 或页面。

### Repository variables（可选）

在 **Settings → Secrets and variables → Actions → Variables** 中可以添加：

| Variable | 作用 |
| --- | --- |
| `SCHOLAR_QUERY` | 覆盖默认 Gmail 查询；默认值为 `is:unread from:scholaralerts-noreply@google.com` |
| `MAX_MESSAGES` | 限制单次最多处理的邮件数，留空表示不限制 |
| `TIMEZONE` | 工作流日期显示时区，默认 `Asia/Shanghai` |

### GitHub Pages

在 **Settings → Pages** 中将发布来源设为 **GitHub Actions**。首次运行工作流后，页面地址通常是：

`https://<用户名>.github.io/<仓库名>/`

## 本地运行

本地调试时保留 `credentials.json` 和 `token.json` 即可，它们已被 `.gitignore` 忽略：

```text
python -m pip install -r requirements.txt
python UniquePaper.py
python build_site.py
```

首次授权需要在本地浏览器完成 OAuth。历史数据已经转换为 `data/days/*.json` 并纳入页面目录；原始邮件文件不会被上传。
