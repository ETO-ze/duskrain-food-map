# Full-Screen Loading and Sidebar Revision

## Behavior

- The domestic and overseas public routes share a full-viewport loading dialog, mounted directly under the document body. It covers the list, map, and page controls while initial map or place data is pending.
- The underlying page is inert during blocking loading. Keyboard focus stays in the dialog. Its theme control, retry, and list fallback remain available. A user can browse the list while the SDK continues loading and reopen the pending map later.
- SDK, tile, data, and error states follow actual readiness. There is no percentage simulation or minimum display duration. Existing network and tile timeouts remain in effect.
- The sidebar uses a compact overview, consistent filters, and shared store cards. Photos have stable dimensions; name, score, and author wrap without horizontal scrolling. Existing categories, recommendation, address, hours, phone, notes, and review links are retained.
- Hover and selection have lightweight feedback. Header content scrolls naturally away while search and filters remain sticky. Filtering brings the first result beneath the sticky controls. Manual scrolling or card interaction takes control of an automatic scroll.
- Review navigation retains the previous list position. Reduced-motion preferences disable the activity animation and visual transitions and use immediate result scrolling.
- The desktop list toggle is positioned outside the list, so it no longer covers the search input.

## Verification

Production build and the four explore utility checks passed. Chromium browser verification passed 28 assertions covering full-screen geometry at 1440 x 900, 390 x 844, 320 x 568, and 844 x 390; mobile cards and sticky controls at 320, 390, and 430 px; day/night screenshots; reduced motion; fallback and map reopening; real AMap completion; local search; store selection; random exploration; review return; SDK error/retry; pending initial data; and overseas synchronization and filtered author visibility.

The domestic list contained 164 records. Review-return scroll was exactly 1771.199951171875 px before and after navigation in the recorded run. Loading screenshots used paused browser timers while the SDK request was deliberately held; timers were resumed before interaction and real-map readiness checks. Data waiting and error/retry checks used real browser timers. These are browser viewport and behavior checks, not a physical-device or FPS benchmark.

## Release

Local source backup: `backups/frontend-before-fullscreen-20261004.zip`. The existing deployment procedure also creates a production source/config archive, an integrity-checked SQLite backup, and a previous-image tag before replacing the food-map container. Source drift is checked against the previous release. Account policy, business data, and provider credentials are outside this change.

Google provider billing was not changed. Overseas layout, list fallback, domestic synchronization, and filtering were verified independently of a successfully billed Google basemap.

Production release: `duskrain-food-map:homepage-20261004-030646`. A private server backup was retained with SQLite integrity check `ok`. Live Chromium verification passed eight checks for desktop/mobile full-screen coverage, ready store cards, first-result/author visibility, mobile store-to-map information, night styling, public API HTTP 200, and overseas fallback/synchronized cards. The deployed entry was `index-ChJT-vGg.js`; 164 domestic stores were available. Deployment and GitHub publication were separate steps.

## Repository Publication

The README now documents the current loading and browsing behavior, stable account ownership, bulk-import defaults, configuration, deployment, and the Google billing limitation. Four reviewed public-page screenshots are included under `assets/screenshots/` with the `20261004` suffix. Private credentials, runtime data, local test artifacts, and backups remain outside the publish set.

Before publication, the production build, four explore utility tests, 30 bulk-import sample rows, whitespace validation, and the repository privacy audit passed again. The built public entry remains `index-ChJT-vGg.js`, matching the verified production release. Browser validation above was not repeated for documentation-only changes.
