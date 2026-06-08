const CITY_ALIASES = [
  "哈尔滨阿城", "长白山", "哈尔滨", "齐齐哈尔", "牡丹江", "佳木斯", "大庆", "伊春",
  "天津", "北京", "上海", "重庆", "广州", "深圳", "佛山", "东莞", "珠海", "中山",
  "杭州", "宁波", "温州", "绍兴", "南京", "苏州", "无锡", "常州", "扬州", "徐州",
  "济南", "青岛", "烟台", "威海", "临沂", "郑州", "洛阳", "武汉", "长沙", "南昌",
  "成都", "绵阳", "乐山", "贵阳", "昆明", "西安", "兰州", "银川", "西宁", "乌鲁木齐",
  "沈阳", "大连", "长春", "延吉", "吉林", "石家庄", "太原", "呼和浩特", "海口", "三亚",
  "福州", "厦门", "泉州", "南宁", "桂林", "合肥", "香港", "澳门", "台北",
].sort((a, b) => b.length - a.length);

const PROVINCE_PREFIXES = [
  "黑龙江省", "黑龙江", "吉林省", "吉林", "辽宁省", "辽宁", "河北省", "河北",
  "山东省", "山东", "河南省", "河南", "山西省", "山西", "陕西省", "陕西",
  "甘肃省", "甘肃", "青海省", "青海", "四川省", "四川", "云南省", "云南",
  "贵州省", "贵州", "湖北省", "湖北", "湖南省", "湖南", "江西省", "江西",
  "安徽省", "安徽", "江苏省", "江苏", "浙江省", "浙江", "福建省", "福建",
  "广东省", "广东", "海南省", "海南", "台湾省", "台湾", "内蒙古自治区", "内蒙古",
  "广西壮族自治区", "广西", "西藏自治区", "西藏", "宁夏回族自治区", "宁夏",
  "新疆维吾尔自治区", "新疆", "北京市", "天津市", "上海市", "重庆市",
].sort((a, b) => b.length - a.length);

function findLocationStart(text) {
  const candidates = [];
  const lastCloseParen = Math.max(text.lastIndexOf(")"), text.lastIndexOf("）"));
  [...CITY_ALIASES, ...PROVINCE_PREFIXES].forEach((alias) => {
    let from = 0;
    while (from < text.length) {
      const index = text.indexOf(alias, from);
      if (index < 0) break;
      const followsWhitespace = /\s/.test(text[index - 1] || "");
      const followsStoreSuffix = lastCloseParen >= 0 && index === lastCloseParen + 1;
      if (index > lastCloseParen && (followsWhitespace || followsStoreSuffix)) candidates.push(index);
      from = index + alias.length;
    }
  });
  return candidates.length ? Math.min(...candidates) : -1;
}

function inferCity(locationText) {
  const normalized = String(locationText || "").replaceAll("市", "");
  const alias = CITY_ALIASES.find((city) => normalized.includes(city.replaceAll("市", "")));
  if (!alias) return "";
  if (alias.includes("哈尔滨")) return "哈尔滨";
  return alias;
}

function looksLikeAddress(text) {
  return /(?:省|市|区|县|旗|街|路|道|巷|号|镇|乡|村|广场|商场|中心|大厦)/.test(text);
}

function stripTrailingCity(text, city) {
  if (!city) return String(text || "").trim();
  return String(text || "")
    .replace(new RegExp(`\\s*(?:哈尔滨阿城|${city}市?)\\s*$`), "")
    .trim();
}

function stripLocationPrefix(text, city) {
  let value = String(text || "").trim();
  const province = PROVINCE_PREFIXES.find((prefix) => value.startsWith(prefix));
  if (province) value = value.slice(province.length).trim();
  if (city) value = value.replace(new RegExp(`^(?:哈尔滨阿城|${city}市?)\\s*`), "").trim();
  return value;
}

export function recommendationForRating(rating) {
  return Number(rating) >= 8 ? "推荐" : "一般";
}

export function parseBulkPlaceLine(source, lineNumber = 1, options = {}) {
  const original = String(source || "").trim();
  if (!original) return null;
  let text = original
    .replace(/^\s*\d+\s*(?:[.、)）]\s*|\s+)/, "")
    .replace(/\s+/g, " ")
    .trim();
  const fixedAuthor = String(options.fixedAuthor || "").trim();
  const ratingMatch = fixedAuthor
    ? text.match(/(\d+(?:\.\d+)?)\s*(?:(必去|推荐|一般|避雷)(?:\s+(.+))?)?\s*$/)
    : text.match(/(\d+(?:\.\d+)?)\s*(?:(必去|推荐|一般|避雷)(?:\s+(\S+)(?:\s+(.+))?)?)?\s*$/);
  if (!ratingMatch) {
    return { lineNumber, original, enabled: false, error: "末尾缺少评分或推荐等级格式不正确", status: "invalid" };
  }

  const rating = Number(ratingMatch[1]);
  const explicitRecommendation = ratingMatch[2] || "";
  const ratingAuthor = fixedAuthor || String(ratingMatch[3] || "吕俊泽").trim();
  const category = String(fixedAuthor ? ratingMatch[3] || "" : ratingMatch[4] || "").trim();
  text = text.slice(0, ratingMatch.index).trim();
  if (!text || !Number.isFinite(rating) || rating < 0 || rating > 10) {
    return { lineNumber, original, enabled: false, error: "店名为空或评分不在 0-10", status: "invalid" };
  }

  const locationStart = findLocationStart(text);
  const name = (locationStart >= 0 ? text.slice(0, locationStart) : text).trim();
  const locationText = locationStart >= 0 ? text.slice(locationStart).trim() : "";
  const city = inferCity(locationText);
  let address = "";
  let note = "";

  if (locationText) {
    if (looksLikeAddress(locationText) && locationText.length > city.length + 3) {
      address = stripTrailingCity(locationText, city);
    } else {
      const remainder = stripLocationPrefix(locationText, city);
      if (remainder && !PROVINCE_PREFIXES.includes(remainder)) note = remainder;
    }
  }

  return {
    lineNumber,
    original,
    enabled: true,
    name,
    city,
    address,
    note,
    rating,
    rating_author: ratingAuthor,
    my_category: category,
    recommend_level: explicitRecommendation || recommendationForRating(rating),
    recommendation_defaulted: !explicitRecommendation,
    status: "ready",
    message: "",
    matchedName: "",
  };
}

export function parseBulkPlaceText(text, options = {}) {
  return String(text || "")
    .split(/\r?\n/)
    .map((line, index) => parseBulkPlaceLine(line, index + 1, options))
    .filter(Boolean);
}

export function normalizePlaceName(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[·.\-—_（）()【】\[\]\s]/g, "")
    .replace(/(?:旗舰店|总店|分店|店)$/g, "");
}

function characterOverlap(left, right) {
  const a = new Set(normalizePlaceName(left));
  const b = new Set(normalizePlaceName(right));
  if (!a.size || !b.size) return 0;
  let matches = 0;
  a.forEach((char) => {
    if (b.has(char)) matches += 1;
  });
  return matches / Math.max(a.size, b.size);
}

export function scorePoiCandidate(row, candidate) {
  const target = normalizePlaceName(row.name);
  const candidateName = normalizePlaceName(candidate.name);
  let score = 0;
  if (target === candidateName) score += 220;
  else if (target.includes(candidateName) || candidateName.includes(target)) score += 130;
  score += Math.round(characterOverlap(row.name, candidate.name) * 100);
  const candidateLocation = `${candidate.city || ""}${candidate.district || ""}${candidate.address || ""}`;
  if (row.city && candidateLocation.includes(row.city)) score += 45;
  if (row.address) score += Math.round(characterOverlap(row.address, candidate.address) * 45);
  if (/餐饮|美食|烧烤|火锅|咖啡|饭店|小吃|面包|甜品|料理/.test(candidate.provider_category || "")) score += 20;
  return score;
}

export function bestPoiCandidate(row, candidates) {
  const scored = [...(candidates || [])]
    .map((candidate) => ({ candidate, score: scorePoiCandidate(row, candidate) }))
    .sort((a, b) => b.score - a.score);
  return scored[0] || null;
}
