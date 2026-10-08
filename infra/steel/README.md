# Steel compatibility image

This image derives from the fixed Steel OSS 0.5.3 image used by CareerAct. The
`rebrowser-puppeteer-core` 23.6.101 alias is installed with an npm lockfile.
No Steel source tree is vendored and no CareerAct business rules move into Steel.

In local BOSS login canaries, the stock image and the alias alone both navigated
the top-level page to `about:blank`. With the alias and Steel's explicit Runtime
observation disabled, the login document remained visible after ten seconds.
This establishes a compatibility dependency, not a universal anti-bot guarantee.
Site challenges still require the user and no challenge is solved automatically.

`configure-runtime.cjs` adds a configuration guard at the three explicit Runtime
enable sites in the fixed image; an unexpected source layout fails the build.
`CAREERACT_STEEL_RUNTIME_OBSERVATION=false` is the default. Runtime console and
execution-context telemetry is unavailable in this mode; leases, authorization,
page/network observation and deterministic business verification remain required.
The package alias follows the [maintainer's integration instructions](https://github.com/rebrowser/rebrowser-patches).

The pinned `live-details` controller incorrectly calls `getBrowserState()` for
its `browserVersion` field. That exports cookies and storage and, in the local
compatibility canary, removes the page from the persistent Puppeteer directory
after the first lookup even though Chromium still owns it. The image replaces
that call with `pages[0].browser().version()`. It neither exports credentials
through page discovery nor bypasses CareerAct's session/page ownership checks.
Repeated discovery, BOSS navigation, screencast frames and release pass in an
isolated container with this correction; actual account login is a separate gate.

`REBROWSER_PATCHES_RUNTIME_FIX_MODE=alwaysIsolated` keeps Steel's metadata
evaluation in its isolated world. The default binding mode stalled renderer
reads after the BOSS login transition in the local canary. Context capture uses
CDP Network/DOMStorage through `cdp-use`, without enabling Runtime observation;
the encrypted cookie snapshot has restored an actual manually logged-in account
in a new isolated session. Product cookie restore and capture of both cookies
and localStorage at release have passed locally. Later full-context navigation
failed the site-retention check, with the page subsequently observed on the BOSS
home or verification page. A transient `about:blank` remains an unverified
hypothesis. After allowing empty URLs within the bounded navigation window and
reloading the daily service, a product session restored the logged-in BOSS home
page without another QR login. Release and encrypted full-context update passed;
persistent empty URLs and foreign origins remain rejected.
Account forgetting, joint revocation and deployment remain separate gates.

Build through the development Compose file. Production Compose still uses the
stock image and is not validated for BOSS login; publish and pin a verified
derived image before deploying this path. An image upgrade must rerun login,
Viewer interaction, snapshot restore, isolation and physical release checks.
