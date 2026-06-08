# DuskRain 美食地图项目记忆

更新日期：2026-06-08

## 项目定位

- 网站名称：DuskRain 吕其林美食指南。
- 国内入口使用高德地图，海外入口使用 Google Maps。
- 项目只保存用户自己的评分、评论、图片和店家关联信息。
- 管理端负责搜索导入、编辑、删除和评价编写，不负责自动量化交易。
- 管理端“批量新建”支持每行一个商家，格式为“编号 店名 城市或地址 评分 推荐等级 作者 菜系”。
- 推荐等级支持“必去 / 推荐 / 一般 / 避雷”；未填写时 `rating >= 8.0` 默认为“推荐”，否则默认为“一般”；作者未填写时默认为吕俊泽，菜系保存到 `my_category`。
- 批量新建逐条调用高德搜索和详情接口。信息不完整时使用模糊匹配并采用评分最高的第一个候选。
- 店家去重键包含评分作者：同一 POI 的不同作者允许分别保存；同作者重复导入时合并非空字段，只有信息增加时更新已有记录。

## 当前架构

- 前端：Vite 5 + Vue 3。
- 后端：FastAPI。
- 数据库：SQLite，Docker volume 持久化。
- 部署：Docker Compose，通过网站反向代理暴露 `/food-map/`。
- 国内坐标：GCJ-02。
- 海外坐标：WGS84。

## 管理权限

- `/food-map/admin/` 是超级管理员后台，继续由 Authelia + Google TOTP 保护。
- `/food-map/developer/` 是独立作者工作台，使用应用内账号与 HttpOnly 会话 Cookie。
- 六个初始作者账号：`adminljz`、`adminlxy`、`admingjdtddd`、`adminwyz`、`adminczk`、`adminly`。
- 初始账号首次登录必须修改临时密码，之后才能访问店家接口。
- 普通作者只能读取、创建、修改和删除 `rating_author` 等于本人作者名的记录；后端强制覆盖提交的作者字段。
- 超级管理员可以创建、停用、重命名、重置作者账号；重命名时同步迁移已有店家归属。
- 同一 POI 不同作者允许并存，同一作者同店家仍执行去重。
- 密码使用 PBKDF2-HMAC-SHA256，令牌仅以 SHA-256 哈希保存；连续登录失败有限流。

## 地图实现

### 国内高德

- 使用高德 JavaScript API 2.0。
- 已保存店家使用 LabelMarker、MarkerCluster 和信息窗体。
- 管理端可搜索高德 POI、读取详情，也可点击地图热点或空白位置添加。
- 城市聚合只在低缩放级别出现，进入城市后展示单店点和店名。
- 地图移动时可降低道路特征复杂度，停止后恢复完整街道与地名。

### 海外 Google

- 使用 Maps JavaScript API、Places Library、Geocoder 和 AdvancedMarkerElement。
- 管理端文本搜索返回候选列表，必须点击候选项后才写入表单。
- 支持 249 个国家和地区的中英文国家下拉列表。
- 点击 Google 官方 POI 时用 Place ID 补全商家字段。
- 点击非 POI 区域时用 Geocoder 反向解析地址。
- 海外筛选分类来自 Google `provider_category`，不是用户自定义分类。
- 店家点显示评分圆点和完整店名，点击后打开本站统一信息卡。
- 海外筛选、列表和地图点共用 `availablePlaces` 数据集合。国内同步开启时纳入高德店家及其 `my_category`，关闭时自动移除对应菜系、城市和作者选项。
- Google Advanced Marker 同时绑定 `click`、`gmp-click` 和自定义标记 DOM 点击，信息窗体锚定 Marker 打开，避免圆点点击无响应。
- 日夜切换通过保留视野并重建 Google Map 完成，因为 `colorScheme` 只能在初始化时设置。为兼容 weekly 构建，传入稳定字符串值 `LIGHT` / `DARK`。
- 可选同步显示国内店家；坐标先从 GCJ-02 转换为 WGS84。

## 数据字段约定

- `map_provider`: `amap` 或 `google`。
- `country_code`: ISO 3166-1 alpha-2。
- `coordinate_system`: `gcj02` 或 `wgs84`。
- `provider_poi_id`: 地图平台 POI ID。
- `provider_category`: 地图平台分类。
- `my_category`: 用户自己的美食分类。
- `provider_detail_url`: 对应地图平台详情链接。
- `rating_author`: 默认作者吕俊泽。
- `review_text`: Markdown 风格长篇评价。

## 性能约束

- 不缓存地图瓦片，不把中国地图完整下载到服务器。
- 缓存本站自己的店铺数据、图片地址、评分和评论。
- 地图标记数量增大时优先使用地图官方聚合和 Canvas/WebGL 能力。
- 地图组件卸载时必须清理标记、事件监听、信息窗体和地图引用。
- 移动端默认优先保证拖动和缩放流畅，不增加重型阴影或重复 DOM 标记。

## 隐私与发布

- `.env`、数据库、服务器凭据、备份、构建产物和日志禁止进入 GitHub。
- GitHub 发布采用路径白名单和密钥正则扫描。
- 公开仓库只包含源代码、模板环境变量、README 和技术文档。
- 浏览器 API Key 即使会在网络请求中出现，也必须配置 HTTP Referrer 和 API 范围限制。

## 后续优化方向

- 为 Google 地图配置正式 Cloud Map ID，而不是长期使用 `DEMO_MAP_ID`。
- 当海外店家数量明显增加后，再接入 Google 官方 MarkerClusterer。
- 为平台分类增加稳定的中文别名映射，避免 Google 本地化名称变化造成筛选分裂。
- 为 README 补充不含隐私信息的桌面端和移动端截图。
