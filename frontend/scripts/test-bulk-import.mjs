import { bestPoiCandidate, parseBulkPlaceText } from "../src/utils/bulk-import.js";

const sample = `1. 喜家德（凯德广场店）哈尔滨 8.2
2. 羊老赞铜锅涮羊肉·烧烤·宵夜(领世郡店) 天津 8.8
3. 龙四爷.铜锅涮肉(津南旗舰店) 天津 8.5
4. 连兴成(隆泰里店) 天津8.2
5. 西塔老太太泥炉烤肉(天津梅江环宇城店) 天津 9.0
6. 二发烧烤 黑龙江省哈尔滨市香坊区亚麻街副39-1 号 哈尔滨 9.1
7. 碳知味小院烧烤(哈量1区店) 哈尔滨 8.9
8. 探匠烧烤(哈西大街店) 哈尔滨 9.8
9. 老韩杀猪菜(一中店) 哈尔滨阿城 9.1
10. 六泰居(泰山路店) 哈尔滨 9.0
11. MIO·弥欧洋房菜 哈尔滨 9.3
12. 橡果咖啡 黑龙江省哈尔滨市南岗区上夹树街66-2号 7.8
13. 老姑大早点(珊瑚海店) 天津 8.0
14. 老松滨饭店(菜艺街店) 哈尔滨 8.3
15. 富都美食 哈尔滨 量大便宜 8.6
16. 吕氏疙瘩汤·新派鲁菜(河东万达店) 天津 8.8
17. Ranch九号牧场(光屿城店) 天津 8.9
18. 全牛匠·乐山跷脚牛肉(梅江天街店) 8.8
19. 欢喜牛潮汕牛肉火锅(奥城店) 天津 8.5
20. 一九六八伊春饭店 黑龙江伊春 9.3
21. 馋嘴小腰(中北春城2期店) 哈尔滨 7.9
22. 小胖重庆切面 哈尔滨 7.5
23. 李喜旺牛腩饭(和平路店) 哈尔滨 7.1
24. 牛肉传(群力店) 哈尔滨 8.3
25. 马家齐市烤肉(融江路总店) 哈尔滨 8.9
26. 正谈炸鸡(天津和平店) 天津 9.0
27. 朝族高丽火盆(长白山总店) 长白山8.6
28. 远香春豆浆面(恒达嘉苑店) 延吉 8.9
29. 小炭伙泥炉烤肉(延大店) 延吉 8.9
30. 羊小羊炭火羊肉炉(花园街店) 哈尔滨 8.9`;

const rows = parseBulkPlaceText(sample);
const invalid = rows.filter((row) => row.status === "invalid");
const unexpected = rows.filter((row) => !row.name || !Number.isFinite(row.rating));
const generalRatings = rows.filter((row) => row.recommend_level === "一般").map((row) => row.rating);

if (rows.length !== 30) throw new Error(`Expected 30 rows, received ${rows.length}`);
if (invalid.length) throw new Error(`Invalid rows: ${invalid.map((row) => row.lineNumber).join(", ")}`);
if (unexpected.length) throw new Error(`Malformed rows: ${unexpected.map((row) => row.lineNumber).join(", ")}`);
if (JSON.stringify(generalRatings) !== JSON.stringify([7.8, 7.9, 7.5, 7.1])) {
  throw new Error(`Unexpected recommendation split: ${JSON.stringify(generalRatings)}`);
}
if (rows[0].name !== "喜家德（凯德广场店）" || rows[0].city !== "哈尔滨") {
  throw new Error(`No-space city parsing failed: ${JSON.stringify(rows[0])}`);
}
if (rows[3].city !== "天津" || rows[3].rating !== 8.2) {
  throw new Error(`No-space rating parsing failed: ${JSON.stringify(rows[3])}`);
}
if (rows[5].address !== "黑龙江省哈尔滨市香坊区亚麻街副39-1 号") {
  throw new Error(`Address parsing failed: ${JSON.stringify(rows[5])}`);
}
if (rows[14].note !== "量大便宜") {
  throw new Error(`Note parsing failed: ${JSON.stringify(rows[14])}`);
}

const ambiguousBranch = bestPoiCandidate(rows[0], [
  {
    name: "喜家德虾仁水饺(嘉茂店)",
    address: "埃德蒙顿路48号嘉茂凯德广场",
    city: "哈尔滨市",
    district: "道里区",
    provider_category: "餐饮服务;中餐厅;特色/地方风味餐厅",
  },
  {
    name: "喜家德虾仁水饺(学府凯德店)",
    address: "学府路1号凯德广场负一层",
    city: "哈尔滨市",
    district: "南岗区",
    provider_category: "餐饮服务;中餐厅;特色/地方风味餐厅",
  },
]);
if (!ambiguousBranch?.ambiguous) {
  throw new Error(`Similar branches should require manual selection: ${JSON.stringify(ambiguousBranch)}`);
}

console.table(rows.map(({ lineNumber, name, city, address, note, rating, recommend_level }) => ({
  lineNumber,
  name,
  city,
  address,
  note,
  rating,
  recommend_level,
})));
console.log("Bulk import parser: 30/30 sample rows passed.");
