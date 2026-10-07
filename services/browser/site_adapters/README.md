# Site Adapters

Recruiting-site-specific navigation, forms, and verification logic live here.

The BOSS adapter currently exposes only `parse_boss_page`. It classifies a captured
page as ready, login-required, risk, unstable, or unknown and extracts job summaries
from synthetic HTML. It does not open a browser, retain a profile, send messages, or
write CareerAct domain state. Browser drivers must supply the captured URL, title, and
HTML; unknown structure fails loudly so a caller cannot treat an unverified page as a
successful read.
