# 换机与离线迁移

## GitHub 中保存的内容

GitHub 仅保存经过白名单和密钥扫描的源码、Docker 配置、前端资源、测试与文档。数据库、`.env`、API Key、服务器认证配置和 Codex 会话不会提交到仓库。

## 从 GitHub 启动

1. 安装 Docker Desktop。
2. 克隆仓库并将 `.env.example` 复制为 `.env`，填写自己的地图 API 配置。
3. 双击 `Start Food Map.cmd`。

脚本会启动 Docker Desktop、构建容器、检查 `/api/health`，然后打开 `http://127.0.0.1:8091/`。

## 完整私密迁移

完整迁移包应额外包含加密的 `.env`、SQLite 数据库、服务器部署配置和 Codex 原始会话。私密归档密码不得放入 GitHub 或和 U 盘存放在一起。

Codex 会话可以用以下命令导出：

```powershell
py -3.14 .\scripts\export-codex-conversation.py <rollout.jsonl> <output-directory>
```

导出的 JSONL 是完整原始记录，Markdown 是便于浏览的用户/助手消息版本。
