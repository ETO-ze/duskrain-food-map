const CATEGORY_SPLIT_RE = /\s*(?:[,，、|;；]|\s+\/\s+)\s*/;

export function normalizeCategories(values = [], legacyValue = "") {
  const source = Array.isArray(values) && values.length ? values : [legacyValue];
  const result = [];
  const seen = new Set();
  source.forEach((value) => {
    String(value || "")
      .split(CATEGORY_SPLIT_RE)
      .map((item) => item.trim().slice(0, 40))
      .filter(Boolean)
      .forEach((category) => {
        const key = category.toLocaleLowerCase();
        if (seen.has(key) || result.length >= 12) return;
        seen.add(key);
        result.push(category);
      });
  });
  return result;
}

export function placeCategories(place) {
  return normalizeCategories(place?.my_categories, place?.my_category || "");
}

export function categoryText(place, separator = " · ") {
  return placeCategories(place).join(separator);
}

export function categoryPayload(values, legacyValue = "") {
  const myCategories = normalizeCategories(values, legacyValue);
  return {
    my_category: myCategories[0] || "",
    my_categories: myCategories,
  };
}
