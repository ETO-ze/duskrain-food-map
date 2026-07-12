import { getConfig } from "./api";
import { categoryText } from "./categories";

let amapPromise;
const TRANSPARENT_IMAGE = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

export async function loadAmap() {
  if (window.AMap) return window.AMap;
  if (amapPromise) return amapPromise;

  amapPromise = getConfig().then((config) => new Promise((resolve, reject) => {
    window._AMapSecurityConfig = {
      securityJsCode: config.amapSecurityCode,
    };
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(config.amapJsKey)}&plugin=AMap.Scale,AMap.MarkerCluster`;
    script.async = true;
    script.onload = () => resolve(window.AMap);
    script.onerror = () => reject(new Error("高德地图脚本加载失败"));
    document.head.appendChild(script);
  }));

  return amapPromise;
}

export function loadAmapPlugin(AMap, plugins) {
  return new Promise((resolve) => {
    AMap.plugin(plugins, resolve);
  });
}

export function markerClass(place) {
  const rec = (place.recommend_level || "").toLowerCase();
  if (rec.includes("必") || rec.includes("must")) return "must";
  if (rec.includes("避") || rec.includes("差") || rec.includes("avoid")) return "avoid";
  if (rec.includes("推") || rec.includes("good")) return "good";
  return "";
}

export function markerHtml(place) {
  const rating = place.rating == null ? "" : String(Math.round(Number(place.rating)));
  return `<div class="marker ${markerClass(place)}">${rating || "食"}</div>`;
}

export function storeMarkerHtml(place) {
  return `
    <div class="store-marker">
      ${markerHtml(place)}
      <span class="store-marker-name">${escapeHtml(place.name || "未命名店家")}</span>
    </div>
  `;
}

export function cityClusterHtml(city, count, options = {}) {
  const safeCount = Number(count) || 0;
  const hiddenClass = options.showLabel === false ? " is-label-hidden" : "";
  return `
    <div class="city-cluster${hiddenClass}">
      <span class="city-cluster-dot">${escapeHtml(safeCount)}</span>
      <span class="city-cluster-label">${escapeHtml(city)} · ${escapeHtml(safeCount)}家</span>
    </div>
  `;
}

export function clusterCountHtml(count) {
  return `<div class="cluster-count">${escapeHtml(Number(count) || 0)}</div>`;
}

function markerFill(place) {
  const variant = markerClass(place);
  if (variant === "must") return "#6ef2b0";
  if (variant === "avoid") return "#ff6b7a";
  if (variant === "good") return "#ffd166";
  return "#6be6ff";
}

function markerIconDataUrl(place) {
  const rating = place.rating == null ? "食" : String(Math.round(Number(place.rating)));
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">
      <circle cx="14" cy="14" r="12.5" fill="${markerFill(place)}" stroke="rgba(255,255,255,0.9)" stroke-width="2"/>
      <circle cx="14" cy="14" r="13.5" fill="none" stroke="rgba(16,32,51,0.2)" stroke-width="1"/>
      <text x="14" y="18.5" text-anchor="middle" font-family="Arial, sans-serif" font-size="12.5" font-weight="900" fill="#06101d">${escapeHtml(rating)}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function clusterIconDataUrl(cluster) {
  const count = String(cluster.count || 0);
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
      <circle cx="16" cy="16" r="14.5" fill="#6be6ff" stroke="rgba(255,255,255,0.92)" stroke-width="2"/>
      <circle cx="16" cy="16" r="15.5" fill="none" stroke="rgba(16,32,51,0.22)" stroke-width="1"/>
      <text x="16" y="21" text-anchor="middle" font-family="Arial, sans-serif" font-size="${count.length > 2 ? 11 : 13}" font-weight="900" fill="#06101d">${escapeHtml(count)}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export function labelMarkerText(place, visible = true) {
  return {
    content: visible ? place.name : "",
    direction: "right",
    offset: [8, 0],
    style: {
      fontSize: 12,
      fontWeight: "800",
      fillColor: "#102033",
      strokeColor: "#ffffff",
      strokeWidth: 3,
      padding: [4, 8, 4, 8],
      backgroundColor: "rgba(255,255,255,0.94)",
      borderColor: "rgba(0,122,157,0.22)",
      borderWidth: 1,
    },
  };
}

export function clusterMarkerText(cluster, visible = true) {
  return {
    content: visible ? `${cluster.city} · ${cluster.count}` : "",
    direction: "right",
    offset: [7, 0],
    style: {
      fontSize: 12,
      fontWeight: "900",
      fillColor: "#102033",
      strokeColor: "#ffffff",
      strokeWidth: 3,
      padding: [4, 8, 4, 8],
      backgroundColor: "rgba(255,255,255,0.94)",
      borderColor: "rgba(0,122,157,0.22)",
      borderWidth: 1,
    },
  };
}

export function placeLabelMarker(AMap, place, showText = false) {
  return new AMap.LabelMarker({
    name: place.name,
    position: [Number(place.lng), Number(place.lat)],
    rank: 1,
    zIndex: 130,
    icon: {
      type: "image",
      image: markerIconDataUrl(place),
      size: [28, 28],
      anchor: "center",
    },
    text: labelMarkerText(place, showText),
    extData: { placeId: place.id },
  });
}

export function placeNameLabelMarker(AMap, place, showText = false) {
  return new AMap.LabelMarker({
    name: place.name,
    position: [Number(place.lng), Number(place.lat)],
    rank: 1,
    zIndex: 130,
    icon: {
      type: "image",
      image: TRANSPARENT_IMAGE,
      size: [1, 1],
      anchor: "center",
    },
    text: labelMarkerText(place, showText),
    extData: { placeId: place.id },
  });
}

export function placeDotMarker(AMap, place) {
  return new AMap.Marker({
    position: [Number(place.lng), Number(place.lat)],
    content: markerHtml(place),
    offset: new AMap.Pixel(-14, -14),
    zIndex: 180,
    extData: { placeId: place.id },
  });
}

export function setLabelMarkerText(marker, place, visible) {
  marker.setText(labelMarkerText(place, visible));
}

export function cityClusterLabelMarker(AMap, cluster, showText = true) {
  return new AMap.LabelMarker({
    name: cluster.city,
    position: [Number(cluster.lng), Number(cluster.lat)],
    rank: 1,
    zIndex: 125,
    icon: {
      type: "image",
      image: clusterIconDataUrl(cluster),
      size: [32, 32],
      anchor: "center",
    },
    text: clusterMarkerText(cluster, showText),
    extData: { city: cluster.city, count: cluster.count },
  });
}

export function setClusterMarkerText(marker, cluster, visible) {
  marker.setText(clusterMarkerText(cluster, visible));
}

export function placeLabel(AMap, place) {
  return new AMap.Text({
    text: place.name,
    position: [Number(place.lng), Number(place.lat)],
    anchor: "middle-left",
    offset: new AMap.Pixel(22, 0),
    zIndex: 130,
    style: {
      "padding": "5px 9px",
      "border": "1px solid rgba(0, 122, 157, 0.24)",
      "border-radius": "8px",
      "background": "rgba(255, 255, 255, 0.92)",
      "color": "#102033",
      "font-size": "12px",
      "font-weight": "800",
      "line-height": "1.2",
      "white-space": "nowrap",
      "box-shadow": "0 2px 8px rgba(0, 0, 0, 0.14)",
    },
  });
}

export const DEFAULT_MAP_CENTER = [116.397428, 39.90923];
export const DEFAULT_MAP_ZOOM = 11;
export const BASE_MAP_FEATURES = ["bg", "road", "building", "point"];
export const MOVING_MAP_FEATURES = ["bg", "road"];

export function mapOptions(overrides = {}) {
  return {
    zoom: DEFAULT_MAP_ZOOM,
    center: DEFAULT_MAP_CENTER,
    mapStyle: "amap://styles/normal",
    viewMode: "2D",
    animateEnable: true,
    showLabel: true,
    labelzIndex: 480,
    lang: "zh_cn",
    features: BASE_MAP_FEATURES,
    ...overrides,
  };
}

export function applyMapLabels(map, AMap, theme = "day") {
  if (typeof map.setStatus === "function") {
    try {
      map.setStatus({ showLabel: true });
    } catch {
      // Older AMap builds ignore unsupported status keys.
    }
  }
  if (typeof map.setFeatures === "function") {
    map.setFeatures(BASE_MAP_FEATURES);
  }
  if (typeof map.setLabelzIndex === "function") {
    map.setLabelzIndex(480);
  }
}

export function applyMovingMapFeatures(map) {
  if (typeof map.setFeatures === "function") {
    map.setFeatures(MOVING_MAP_FEATURES);
  }
}

export function imageList(place) {
  const urls = []
    .concat((place.cover_image || "").trim())
    .concat((place.image_urls || "").split(/\n+/))
    .map((url) => normalizeImageUrl(url.trim()))
    .filter(Boolean);
  return [...new Set(urls)];
}

function normalizeImageUrl(url) {
  if (/^http:\/\//i.test(url)) {
    return url.replace(/^http:/i, "https:");
  }
  return url;
}

export function formatAddress(place) {
  return [place.city, place.district, place.address].filter(Boolean).join(" ");
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function safeLink(value) {
  const url = String(value ?? "").trim();
  if (!/^(https?:\/\/|\/)/i.test(url)) return "";
  return escapeHtml(url);
}

export function imageStripHtml(place, options = {}) {
  if (place.hide_images) return "";
  const images = imageList(place).slice(0, 2);
  if (!images.length) return "";
  return `<div class="image-strip">${images.map((url) => {
    const escapedUrl = escapeHtml(url);
    const imageSource = options.deferImages ? `src="${TRANSPARENT_IMAGE}" data-src="${escapedUrl}"` : `src="${escapedUrl}"`;
    return `<img ${imageSource} alt="${escapeHtml(place.name)}" loading="lazy" decoding="async" fetchpriority="low">`;
  }).join("")}</div>`;
}

export function hydrateDeferredImages(root = document) {
  const loadImages = () => {
    root.querySelectorAll("img[data-src]").forEach((image) => {
      image.src = image.dataset.src;
      image.removeAttribute("data-src");
    });
  };
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(loadImages, { timeout: 700 });
    return;
  }
  window.setTimeout(loadImages, 180);
}

export function infoHtml(place, options = {}) {
  const reviewPageUrl = place.id ? safeLink(`/food-map/review/${place.id}`) : "";
  const providerUrl = safeLink(place.provider_detail_url || place.amap_detail_url);
  const providerLabel = place.map_provider === "google" ? "打开 Google Maps" : "打开高德详情";
  const ratingAuthor = place.rating_author || "吕俊泽";
  const categoryLabel = categoryText(place) || place.provider_category || "";
  const tags = (place.tags || "")
    .split(/[，,]/)
    .map((tag) => tag.trim())
    .filter(Boolean)
    .map((tag) => `<span class="pill">${escapeHtml(tag)}</span>`)
    .join("");
  return `
    <div class="info">
      <h3>${escapeHtml(place.name)}</h3>
      ${imageStripHtml(place, options)}
      <p class="info-address">${escapeHtml(place.address || "")}</p>
      <div class="info-score">
        <strong>${place.rating ?? "-"} / 10</strong>
        <span>${escapeHtml(ratingAuthor)}</span>
        ${place.recommend_level ? `<span>${escapeHtml(place.recommend_level)}</span>` : ""}
      </div>
      ${categoryLabel ? `<p class="info-category">${escapeHtml(categoryLabel)}</p>` : ""}
      ${place.phone ? `<p>电话：${escapeHtml(place.phone)}</p>` : ""}
      ${place.business_hours ? `<p>营业：${escapeHtml(place.business_hours)}</p>` : ""}
      ${reviewPageUrl || providerUrl ? `
        <div class="info-actions">
          ${reviewPageUrl ? `<a class="info-link primary" href="${reviewPageUrl}">美食评价</a>` : ""}
          ${providerUrl ? `<a class="info-link" href="${providerUrl}" target="_blank" rel="noopener noreferrer">${providerLabel}</a>` : ""}
        </div>
      ` : ""}
      ${place.note ? `<p class="info-note">${escapeHtml(place.note)}</p>` : ""}
      ${tags ? `<div class="pill-row">${tags}</div>` : ""}
    </div>
  `;
}
