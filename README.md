<h1 align="center">DuskRain 吕其林美食指南</h1>

<p align="center">
  <img src="assets/duskrain-food-map.png" alt="DuskRain 吕其林美食指南" width="180" />
</p>

<p align="center">
  基于高德地图与 Google Maps 的个人美食地图、店铺资料库和评价系统。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Vue-3-42b883?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue 3" />
  <img src="https://img.shields.io/badge/Vite-5-646cff?style=for-the-badge&logo=vite&logoColor=white" alt="Vite 5" />
  <img src="https://img.shields.io/badge/FastAPI-Python-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Docker-Deployment-2496ed?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
</p>

<p align="center">
  <a href="https://duskrain.cn/food-map/">
    <img src="https://img.shields.io/badge/国内地图-高德地图-1677ff?style=for-the-badge" alt="国内地图" />
  </a>
  <a href="https://duskrain.cn/food-map/global/">
    <img src="https://img.shields.io/badge/海外地图-Google%20Maps-34a853?style=for-the-badge&logo=googlemaps&logoColor=white" alt="海外地图" />
  </a>
</p>

## 项目简介

DuskRain 吕其林美食指南是一个自用的跨地图美食资料库。国内店家使用高德 POI 和 GCJ-02 坐标，海外店家使用 Google Places 和 WGS84 坐标；评分、作者、推荐等级、图片和长篇评价由本站独立保存。

项目重点不是抓取第三方点评内容，而是把地图基础信息与个人评价结合起来，形成可以持续维护的个人美食指南。

## 功能亮点

- 国内高德地图和海外 Google Maps 分离展示。
- 管理端支持高德、Google Places 搜索候选店铺并点击加入。
- 管理端支持粘贴“编号 店名 城市或地址 评分 推荐等级 作者 菜系”清单，一键匹配高德 POI、补全资料并批量新建。
- 推荐等级支持“必去 / 推荐 / 一般 / 避雷”；未填写时按评分自动设置，作者未填写时默认为吕俊泽，菜系写入个人分类。
- 城市或地址不完整时使用模糊搜索，并自动采用本站匹配分最高的第一个候选。
- 同一店家允许不同作者分别保存评价；同作者重复导入时自动合并非空字段，保留信息更完整的一条。
- Google 管理端提供 249 个国家和地区的中英文快速选择。
- 支持直接点击地图 POI 导入商家，点击空白位置反向解析地址。
- 自动保存平台 POI ID、地址、电话、营业时间、类型、坐标和平台详情链接。
- 个人评分、评分作者、推荐等级、分类、标签、备注、图片和 Markdown 评价。
- 地图点位显示评分与店家名，点击后打开统一信息卡片。
- 国内地图支持城市聚合、店家标签和日夜模式。
- 海外地图按 Google 店铺分类筛选，并支持日夜底图切换。
- 海外地图可选同步显示国内高德店家，自动进行 GCJ-02 到 WGS84 转换。
- 海外页面的菜系、城市、作者、列表和点位共用同一数据集合：开启国内同步后自动加入国内选项，关闭后自动移除。
- 桌面端侧栏管理，移动端列表和地图快速切换。
- 本地安全 GitHub 发布脚本，默认屏蔽环境变量、数据库、备份和构建文件。

## 页面入口

- 国内地图：[https://duskrain.cn/food-map/](https://duskrain.cn/food-map/)
- 海外地图：[https://duskrain.cn/food-map/global/](https://duskrain.cn/food-map/global/)
- 管理端：`/food-map/admin/`，由网站认证层保护
- 店家评价：`/food-map/review/{店家ID}`

## 架构

```mermaid
flowchart LR
    A["Vue 3 + Vite 前端"] --> B["FastAPI API"]
    B --> C["SQLite 店家资料库"]
    D["高德 Web Service / JS API"] --> A
    E["Google Maps / Places"] --> A
    A --> F["国内高德地图"]
    A --> G["海外 Google 地图"]
    H["Docker Compose"] --> B
```

## 数据原则

- `map_provider`: `amap` 或 `google`
- `coordinate_system`: `gcj02` 或 `wgs84`
- `provider_poi_id`: 高德 POI ID 或 Google Place ID
- `provider_category`: 地图提供商返回的店铺类型
- `my_category`: 用户自己的美食分类
- Google 地图展示国内点时只转换本站保存的坐标，不抓取或缓存高德底图。
- 不把第三方地图瓦片、Google 图片或第三方点评正文保存到仓库。

## 快速开始

1. 复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

2. 在 `.env` 中配置自己的高德和 Google Maps 凭据。

3. 启动容器：

```powershell
docker compose up -d --build
```

4. 本地访问：

```text
http://127.0.0.1:8091/
http://127.0.0.1:8091/global/
http://127.0.0.1:8091/admin/
```

## 前端开发

```powershell
cd frontend
npm install
npm run dev
```

生产构建：

```powershell
npm run build
```

验证批量清单解析：

```powershell
npm run test:bulk-import
```

## 安全发布到 GitHub

首次使用时双击：

```text
Publish to GitHub.cmd
```

脚本会询问空 GitHub 仓库地址。后续再次双击即可检查、提交并推送安全文件。

仅执行隐私检查：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish-github-safe.ps1 -AuditOnly
```

发布白名单包括源码、Docker 配置、依赖清单、README 和技术文档。以下内容不会发布：

- `.env` 和真实 API Key
- SQLite 数据库和店家数据
- 服务器配置、密码与认证信息
- `backups/`、`data/`、日志和报告
- `node_modules/`、`dist/` 和运行时静态构建

## 重要文件

- [app.py](app.py)：FastAPI API、数据库迁移和高德服务端代理。
- [frontend/src/components/PublicMap.vue](frontend/src/components/PublicMap.vue)：国内地图。
- [frontend/src/components/GlobalMap.vue](frontend/src/components/GlobalMap.vue)：海外地图。
- [frontend/src/components/AdminDashboard.vue](frontend/src/components/AdminDashboard.vue)：管理端总控。
- [frontend/src/components/AdminBulkImport.vue](frontend/src/components/AdminBulkImport.vue)：批量解析、匹配、去重和新建。
- [frontend/src/utils/google-map.js](frontend/src/utils/google-map.js)：Google Maps、Places 和坐标转换。
- [docs/PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md)：项目长期技术记忆。
- [docs/google-maps-notes.md](docs/google-maps-notes.md)：Google Maps 接入决策。
- [docs/amap-js-api-v2-notes.md](docs/amap-js-api-v2-notes.md)：高德 JS API 优化记录。

## 安全说明

- 浏览器地图 Key 必须限制为指定网站来源。
- 服务端 Web Service Key 不应出现在前端或 GitHub。
- Google Maps 和 Places API 应设置 API 限制、预算提醒和调用配额。
- 管理端必须继续由反向代理认证保护。
- 本项目是个人美食记录工具，不提供第三方平台评分复制或商业数据采集。
