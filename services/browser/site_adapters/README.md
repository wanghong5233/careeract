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
the active Steel session and single blank page, connects with Playwright to the configured
internal CDP origin, navigates only to the fixed BOSS login URL, then disconnects before
human takeover. It receives no credentials, retries no navigation, and writes no product
login result. Navigation returning successfully does not prove platform login or page
stability; the current BOSS page still becomes blank during real local verification.
