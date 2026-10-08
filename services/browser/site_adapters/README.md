# Site Adapters

Recruiting-site-specific navigation, forms, and verification logic live here.

The read-only BOSS adapter exposes `parse_boss_page`. It classifies a captured
page as ready, login-required, risk, unstable, or unknown and extracts job summaries
from synthetic HTML. It does not open a browser, retain a profile, send messages, or
write CareerAct domain state. Browser drivers must supply the captured URL, title, and
HTML; unknown structure fails loudly so a caller cannot treat an unverified page as a
successful read.

`boss_login.py` supplies a dedicated login navigation callback during signed physical
creation, while the lifecycle row lock excludes human Viewers and executors. It checks
the active Steel session and single blank page, reuses browser-use's `cdp-use` client at the configured
internal CDP origin, navigates only to the fixed BOSS login URL, checks a short stable site window, then disconnects before
human takeover. It receives no credentials, retries no navigation, and writes no product
login result. Navigation returning successfully does not prove platform login or page
stability. The development Steel compatibility image addresses the observed Runtime
observation conflict; see [Steel compatibility](../../../infra/steel/README.md).

`boss_context.py` reads scoped Cookie/localStorage through the same mature CDP
client without enabling Runtime. The caller must hold the lifecycle guard and
exclude the human Viewer. Capture checks the sole live Steel session and sole
BOSS page, and always disconnects. Account navigation is a local observation,
not a substitute for CareerAct's durable connection status or business read checks.
When an encryption key is configured, signed creation imports only the user's
current profile; signed release saves the observed logged-in state before physical
release. Capture failures still release the browser and report an uncertain result.
