# UniquePaperFromGoogleScholarAlter

从 Gmail 的 Google Scholar Alert 邮件中提取去重论文，并通过 GitHub Actions 自动更新 GitHub Pages 文献库。

## 工作方式

- 每天北京时间 06:00 运行，也可以在 Actions 页面手动运行。
- 推送代码或数据到 `main` 后也会自动重新部署页面；这种推送触发只发布现有数据，不读取 Gmail。
- 工作流从 Gmail 读取未读 Scholar Alert 邮件，提取标题、作者、摘要和论文链接。
- 运行结果写入 `data/days/`，`build_site.py` 再生成 `data/catalog.json`，页面通过这个目录展示数据。
- Actions 在数据成功推送到仓库后才移除 `UNREAD` 标签；解析、构建或推送失败时保留未读状态。没有新邮件时不会生成空记录。
- 手动运行时可填写 `recover_date`（如 `2026-10-07`），按北京时间补抓该日已读及未读邮件；通常留空。
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

## OAuth 客户端被删除后的修复

如果 Actions 报错：

```text
deleted_client: The OAuth client was deleted.
```

说明 `credentials.json` 对应的 Google Cloud OAuth 客户端已经失效。旧的 `token.json` 也不能继续刷新，必须重新创建客户端并重新授权：

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)，选择原项目或创建一个专用项目。
2. 在 **APIs & Services → Library** 中启用 **Gmail API**。
3. 在 **APIs & Services → OAuth consent screen** 中配置应用。若应用处于 Testing 状态，把自己的 Gmail 地址加入 **Test users**。
4. 在 **APIs & Services → Credentials → Create credentials → OAuth client ID** 中选择 **Desktop app**，下载新的 JSON 文件并保存为本地 `credentials.json`。
5. 删除旧的本地 `token.json`，安装依赖后只运行授权工具：

```text
python -m pip install -r requirements.txt
python authorize_gmail.py
```

浏览器会打开 Google 授权页面。使用接收 Scholar Alert 的 Gmail 账号登录并允许 Gmail 读取和修改权限。授权工具只生成 `token.json`，不会处理或标记邮件。

6. 在 GitHub 仓库的 **Settings → Secrets and variables → Actions → Secrets** 中覆盖：

   - `GMAIL_CREDENTIALS_JSON`：新的 `credentials.json` 完整内容
   - `GMAIL_TOKEN_JSON`：刚刚生成的 `token.json` 完整内容

   两个值都必须放在 **Repository secrets**，不要放到 Variables，也不要提交到仓库。

7. 在 Actions 页面手动运行工作流。需要补抓某个北京时间日期时，在 `recover_date` 输入框填入例如 `2026-10-07`；普通运行留空。

如果授权页面提示应用未验证，在确认 Google Cloud 项目和 Gmail 账号都是自己的前提下，可以通过 **Advanced → Go to app** 继续。若看不到授权按钮，通常是 Gmail 地址没有加入 OAuth consent screen 的 Test users。
