# Homepage Loading and Browsing Update

## Scope

Domestic and overseas public maps, map loader helpers, direct review navigation, and route-level code splitting. No account policy, backend endpoint, business data, API credential, or billing configuration was changed.

## Behavior

- Public places load independently of map SDKs. Local search supports shop names, cities and addresses; category, recommendation, city and author filters operate on the loaded public dataset.
- Map loading has day/night styling, indeterminate progress, actual SDK/tile stages, timeout, retry and a list fallback. It never imposes an artificial minimum wait.
- Public list scrolling uses a native scroll container and sticky search/filters instead of per-frame section height changes. Session-only filter/theme/scroll memory preserves navigation; precise user geolocation is not persisted.
- Nearby results respect the displayed 30 km radius, with an explicit option to expand to 100 km. AMap shop coordinates are converted to WGS84 for browser-location distance comparisons. Reset cancels pending geolocation and clears spatial restrictions.
- Map movement offers an explicit search-this-area action. Ordinary filters preserve the camera; selecting a city or requesting nearby results can fit the selected area.
- AMap cluster instances use setData; unchanged city markers are reused. Google markers are reconciled by place ID. Neither route rebuilds its map instance for ordinary filters.
- Review links navigate directly; telephone links can dial. Overseas review pages retain their source map route.
- Backend/developer/guide/review routes are lazy-loaded. Guide-only fonts are no longer part of the public homepage stylesheet.

## Verification

- Vite production build: passed. Public entry approximately 126.64 kB JS and 48.60 kB CSS before compression. Separate route chunks are fetched on demand.
- Explore utility checks: 4 passed (search, date-line bounds, explicit nearby radius, distance stability).
- Existing bulk-import parser: 30/30 samples passed.
- Existing developer-account suite: 10/10 passed in an isolated Python 3.12 environment. Initial system Python lacked the required dependencies; tests were rerun after isolated installation.
- Chromium browser: actual AMap loaded successfully; 164 public domestic records remained browsable while its SDK request was deliberately held.
- SDK failure/retry: blocked AMap request showed an error, then recovered without refreshing the page. Blocked Google SDK retained the list fallback.
- Viewports 320, 390 and 430 px: no document horizontal overflow; sticky controls left room for the list.
- Mobile store selection, return-to-list scroll retention, direct review navigation, return-from-review restoration, empty search, nearby reset: passed.
- Tianjin real-map zoom/pan: visible labels remained after both 2 and 4 seconds idle; search-this-area refreshed after a subsequent pan. This is a functional check, not an FPS benchmark.
- Overseas domestic synchronization: 164 stores; search for Tianjin returned 44; disabling synchronization removed domestic-only categories.
- Production homepage and public places API: HTTP 200; actual map loaded; mobile 390 px had no horizontal overflow.

## Loading Visual Revision

The later visual pass replaces the technical numbered steps with a centered DuskRain identity and the existing guide rain mark. Day mode uses a neutral white surface; night mode uses graphite. One thin activity ring indicates indeterminate loading. There is no new animation dependency, image download, percentage simulation, or minimum display timer. Short landscape viewports use a compact layout so the actions remain visible. The list fallback and retry retain their original behavior.

Chromium checks passed for desktop day/night, 390 x 844 and 320 x 568 portrait, 844 x 390 landscape, reduced motion, SDK failure, list fallback, and successful AMap retry (13 assertions). Overseas synchronization/filter/fallback checks also passed. This is browser viewport testing, not a physical-phone performance benchmark. Production build and all four explore utility checks passed again.

Reference patterns: [Apple Maps](https://www.apple.com/maps/) for visual hierarchy and [Atlassian skeleton guidance](https://atlassian.design/components/skeleton/usage) for stable layout and removing the loading placeholder as soon as real content is ready. The DuskRain visual treatment is original and does not copy third-party brand assets.

## Known External Limitation

Google returned `BillingNotEnabledMapError` during real-provider testing. Its official billing warning remains intact. No billing was enabled, no key restriction was bypassed, and successful overseas basemap operation is not claimed. The application also handles SDK network errors and the documented authentication-failure callback.

## Release Safety

Local source archive, production source/config archive, SQLite online backup (integrity check `ok`) and previous Docker image tags were retained before deployment. The release reuses the existing backend image and copies locally built frontend assets, avoiding a Node build on the low-memory server. Only the food-map container was recreated. No GitHub push was performed.

## References

- [AMap MarkerCluster setData](https://developer.amap.com/api/maps-javascript-api/reference/amap-marker/markercluster)
- [Google Maps events and tile lifecycle](https://developers.google.com/maps/documentation/javascript/reference/map)
- [Google Maps error messages](https://developers.google.com/maps/documentation/javascript/error-messages)
