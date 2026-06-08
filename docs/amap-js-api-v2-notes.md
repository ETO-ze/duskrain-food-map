# 高德地图 JavaScript API 2.0 项目笔记

更新日期：2026-06-07

这份文档记录 `food-map` 对高德地图 JavaScript API 2.0 的使用约束、当前实现和后续优化依据。它是项目内的长期技术记忆，修改地图逻辑前应先核对这里和官方文档。

## 官方文档范围

- [API 概述](https://lbs.amap.com/api/javascript-api-v2/summary)
- [地图生命周期](https://lbs.amap.com/api/javascript-api-v2/guide/map/lifecycle)
- [地图状态](https://lbs.amap.com/api/javascript-api-v2/guide/map/state)
- [地图交互与事件](https://lbs.amap.com/api/javascript-api-v2/guide/map/map-bind)
- [覆盖物与图层管理](https://lbs.amap.com/api/javascript-api-v2/guide/map/map-layer)
- [地图样式](https://lbs.amap.com/api/javascript-api-v2/guide/map/map-style)
- [地图和覆盖物事件](https://lbs.amap.com/api/javascript-api-v2/guide/events/map_overlay)
- [Marker](https://lbs.amap.com/api/javascript-api-v2/guide/amap-marker/default-marker)
- [LabelMarker / LabelsLayer](https://lbs.amap.com/api/javascript-api-v2/guide/amap-massmarker/label-marker)
- [MarkerCluster](https://lbs.amap.com/api/javascript-api-v2/guide/amap-massmarker/marker-cluster)
- [InfoWindow](https://lbs.amap.com/api/javascript-api-v2/guide/overlays/info-window)
- [地图控件](https://lbs.amap.com/api/javascript-api-v2/guide/overlays/toolbar)
- [POI 搜索](https://lbs.amap.com/api/javascript-api-v2/guide/services/autocomplete)
- [地理编码与逆地理编码](https://lbs.amap.com/api/javascript-api-v2/guide/services/geocoder)

## 核心使用规则

1. 地图实例只创建一次。`complete` 后再执行依赖底图完成的操作；组件卸载时解绑事件并调用 `map.destroy()`。
2. 使用 `setCenter`、`setZoom`、`setZoomAndCenter` 和 `setFitView` 管理视野，不通过 DOM 位移模拟地图定位。
3. 拖动和缩放过程中避免反复创建、移除覆盖物。实时反馈只做轻量更新，完整计算放在 `moveend`、`dragend`、`zoomend`。
4. 普通少量交互点可使用 `Marker`；海量文字使用 `LabelsLayer + LabelMarker`；低缩放级别的大量点优先使用 `MarkerCluster`。
5. `LabelsLayer` 的碰撞、避让、层级和文字显隐应由稳定的缩放规则控制，不能在一次缩放过程中出现互相冲突的 show/hide。
6. 覆盖物应批量 `add/remove`，避免逐个跨边界调用。只更新变化的数据，不在视野变化时重建全部店铺对象。
7. 地图样式使用 `mapStyle` 初始化或 `setMapStyle()` 动态切换。业务面板主题由网站 CSS 管理，不依赖底图颜色。
8. 地图内置 POI 点击优先使用热点事件和 POI ID，再调用详情查询；普通空白位置点击才使用逆地理编码和附近 POI。
9. POI 搜索需要区分关键字搜索、周边搜索、范围搜索和 POI ID 详情。选择地图上的具体店铺时，POI ID 详情比逆地理结果第一项可靠。
10. Web Service Key 只保存在后端环境变量中。前端仅使用受域名和安全密钥约束的 JS API Key。
11. 默认 `InfoWindow` 适合简单内容；需要完全统一日夜主题时应改成自定义内容和样式，并控制 `anchor`、`offset`、`autoMove`。
12. 官方控件可以通过插件加载；网站自己的视图和主题按钮应作为地图容器上的独立 UI，不要伪装成高德原生控件。

## 当前项目映射

- 地图创建与公共配置：`frontend/src/utils/map.js`
- 首页地图、标注、城市聚合：`frontend/src/components/PublicMap.vue`
- 管理端热点选店和逆地理兜底：`frontend/src/components/AdminDashboard.vue`
- 后端高德 Web Service：`app.py`
- 前端主题和地图浮层：`frontend/src/styles.css`

## 当前实现决策

- 默认日间底图为 `amap://styles/normal`。
- 夜间底图为较低对比度的 `amap://styles/dark`。
- 店铺评分圆点使用 `Marker` 保证常显和点击稳定。
- 店铺名称使用 `LabelsLayer + LabelMarker`。
- 评分圆点由按城市拆分的官方 `MarkerCluster` 管理，店名标签继续由 `LabelsLayer` 独立管理。
- 不给 `MarkerCluster` 设置分数型 `maxZoom` 临界值。让插件按网格自然拆分，避免缩放结束重算时清空聚合点却不补回单店圆点。
- 全国视角的聚合点显示“城市名 · 店铺数”，进入城市后同一城市可自然拆成多个局部聚合点和单店圆点。
- 城市级及更高缩放层级的聚合点只显示数量，不重复显示城市名。
- 单店名称与评分圆点使用同一个 `Marker` 内容，避免独立 `LabelsLayer` 与 `MarkerCluster` 在 `zoomend` 后状态不同步。
- 管理端不渲染全部已保存店铺，只保留地图选点，减少添加店铺时的开销。
- 管理端点击地图内置 POI 时优先走热点 POI ID 详情；空白处点击使用逆地理和餐饮优先排序。

## 优化优先级

### 已完成

- Vue 组件已补齐 `onUnmounted`：解绑窗口和地图事件、清除定时器、关闭信息窗体、移除覆盖物并销毁地图。
- 已使用官方 `MarkerCluster` 替换手写城市中心聚合。
- 已将聚合实例按城市拆分，并移除导致缩放停止后标记消失的 `maxZoom` 临界值。
- 已将店名绑定到单店 Marker，解决缩放停止后店名消失。
- 首页列表和信息窗体已统一日夜主题变量。

### P1

- 移动中停止不必要的底图 feature 重设和标签重算，只在稳定事件后刷新。
- 将文字标签选择改为空间网格索引，减少每次视野变化的全量排序。

### P2

- 对 POI 搜索增加地图中心点、城市和类型联合排序。
- 对店铺图片建立缩略图和响应式尺寸，减少移动端列表解码开销。
- 增加地图性能指标：首屏完成时间、拖动帧率、覆盖物数量、标签刷新耗时。
