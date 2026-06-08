# Google Maps 国外模式项目笔记

更新日期：2026-06-07

## 官方文档

- [Maps JavaScript API 加载](https://developers.google.com/maps/documentation/javascript/load-maps-js-api)
- [Place 类与文本搜索](https://developers.google.com/maps/documentation/javascript/place-search)
- [Place Autocomplete Element](https://developers.google.com/maps/documentation/javascript/place-autocomplete-new)
- [地图 POI 点击事件](https://developers.google.com/maps/documentation/javascript/poi-click-events)
- [Place 类字段与 fetchFields](https://developers.google.com/maps/documentation/javascript/place-class-data-fields)
- [反向地理编码](https://developers.google.com/maps/documentation/javascript/examples/geocoding-reverse)
- [Advanced Markers](https://developers.google.com/maps/documentation/javascript/advanced-markers/overview)
- [Places 内容与归属政策](https://developers.google.com/maps/documentation/places/web-service/policies)
- [API 安全最佳实践](https://developers.google.com/maps/api-security-best-practices)
- [Maps Platform 计费](https://developers.google.com/maps/billing-and-pricing/pricing)

## 当前实现

- 国内入口 `/food-map/` 使用高德与 GCJ-02。
- 国外入口 `/food-map/global/` 使用 Google Maps 与 WGS84。
- 管理端搜索导入支持高德与 Google Places 两种提供商。
- Google 管理端提供双语国家下拉列表；国家名称会加入文本查询，减少跨国家同名店误匹配。
- Google 地图上的官方 POI 可直接点击，通过 `placeId` 和 `fetchFields()` 补全商家信息。
- 点击非 POI 区域时使用 Geocoder 反向解析地址、国家、城市和行政区。
- Google Places 只请求名称、地址、坐标、类型、电话、营业时间、Google Maps 链接和地址组件。
- 数据库长期保存 Google `place_id`、用户自己的评分、评论和图片；不缓存 Google 图片。
- Google 单店使用 `AdvancedMarkerElement`，地图使用 `DEMO_MAP_ID`。正式自定义 Google 地图样式时应换成自有 Map ID。
- 海外地图可选择同步显示国内高德店家。同步时只转换并显示本站已有店铺数据，不抓取高德底图；GCJ-02 坐标先转换为 WGS84。
- 海外地图分类筛选直接读取 Google Places 返回的 `primaryTypeDisplayName`，存入 `provider_category`。
- Google 店家标记由评分圆点和店家名组成，点击后使用本站统一 `infoHtml()` 信息卡。
- 日夜切换使用 Google `LIGHT` / `DARK` 色系。由于 `colorScheme` 只能在地图初始化时设置，切换时保存中心和缩放级别后重建地图实例；使用字符串值避免 weekly 构建未导出 `ColorScheme` 枚举时初始化失败。

## 优化结论

- 当前店铺规模不需要额外接入 Google Places Web Service 后端代理，浏览器端 Places Library 足够，结构更简单。
- 搜索结果必须由用户点击确认后才进入编辑表单，避免文本搜索第一条误选。
- 国家筛选先作为查询上下文而不是强制边界。跨境城市和边界地区不会因此被错误排除。
- 国内点同步默认关闭，用户需要时手动开启，避免海外地图首次进入时在中国区域堆叠大量点位。
- 不尝试缓存 Google 地图瓦片或 Places 原始内容；本站只缓存自己的评分、评论、图片和店铺关联字段。

## 数据字段

- `map_provider`: `amap` 或 `google`
- `country_code`: ISO 两位国家代码
- `coordinate_system`: `gcj02` 或 `wgs84`
- `provider_poi_id`: 高德 POI ID 或 Google Place ID
- `provider_detail_url`: 对应地图提供商详情页

## 安全要求

- Google Key 必须设置网站来源限制，只允许 `https://duskrain.cn/*`。
- API 限制至少只允许 Maps JavaScript API 和 Places API。
- 开启预算提醒和配额限制，防止公开浏览器 Key 被滥用产生超额费用。
