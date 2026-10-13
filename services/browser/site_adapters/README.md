# Site Adapters

Recruiting-site-specific navigation, forms, and verification logic live here.

The read-only BOSS adapter exposes `parse_boss_page`. It classifies a captured
page as ready, login-required, risk, unstable, or unknown and extracts job and
conversation/message summaries from captured HTML and bounded rendered-component
contracts. Live list rows bind `source.uniqueId` to the virtual list key and expose
`lastMsgId`. The selected conversation and each rendered message are checked against
that identity, stable message IDs, direction, timestamp and rendered content; the
list's latest ID must identify a loaded message. BOSS can append an information card
after that anchor without advancing the list ID. Such a suffix is accepted only when
the anchor text matches the list preview and each appended article binds the same
message object and one matching article title; an unrelated text suffix fails closed.
Observation order is preserved. A real conversation (initially five,
then eight currently loaded messages) has passed the signed product read and persistence path.
This covers currently loaded
messages, not all history or permission to send a resume. The selected conversation
reader also records the uniquely bound resume button as available/unavailable/unknown
and the component's attachment flag. A false flag leaves material identity unknown:
the real account's recommendation page displays an attachment tile despite the chat
control reporting false. Neither this tile nor the flag identifies the current version.
Missing/changed controls remain unknown, and material identity/version still requires
verification before any send.
The reader also observes historical resume cards only after their child component
binds the same message object and its displayed title matches the bounded filename.
It returns the filename, message-side flag and optional request message ID, excluding
attachment URLs and contents. A real card passed signed read, persistence and product
readback. These references do not establish delivery or the current material version;
partially rendered hyperlink messages wait within the existing observation window.
The parser does not open a browser, retain a profile, send messages, or write CareerAct domain state. Browser
drivers must supply the captured URL, title, and HTML; unknown structure fails loudly
so a caller cannot treat an unverified page as a successful read.

`boss_login.py` supplies a dedicated login navigation callback during signed physical
creation, while the lifecycle row lock excludes human Viewers and executors. It checks
the active Steel session and single blank page, reuses browser-use's `cdp-use` client at the configured
internal CDP origin, navigates only to the server-selected fixed BOSS login or conversation URL,
checks a short stable site window, then disconnects before
human takeover. It receives no credentials, retries no navigation, and writes no product
login result. Navigation returning successfully does not prove platform login or page
stability. The development Steel compatibility image addresses the observed Runtime
observation conflict; see [Steel compatibility](../../../infra/steel/README.md).

`boss_context.py` reads scoped Cookie/localStorage through the same mature CDP
client without enabling Runtime. Its bounded `page_snapshot` path separately
uses `DOM.getDocument`, a body selector and `DOM.getOuterHTML` to capture the current BOSS URL, title,
and HTML for read-only site parsing. The signed page endpoint holds `snapshot_guard`
through capture and disconnect, excluding human control and automatic writers;
standalone callers must provide equivalent exclusion. Capture checks the sole live
Steel session and sole BOSS page. Login/verification routes return only a classified URL
with query/fragment removed and empty title/HTML, without attaching to credential DOM. It rejects more than
4 MiB of body HTML, verifies the page URL after capture, and always disconnects.
The separately bounded structured API/result payload remains at 512 KiB; raw DOM is
never returned or stored. Script/style contents do not classify page state. A bounded
three-observation window (15 seconds) waits for initial SPA structure without replaying
navigation. Unrecognized structure remains a failed business read even when capture succeeds.
Account navigation and a page snapshot are local observations, not substitutes
for CareerAct's durable connection status or business read checks.
The dedicated signed conversation endpoint acquires single-writer control and uses
`executor_action_guard` with `ExecutorLifecycle`. It clicks the uniquely bound row
once, then only observes within a bounded window; opening may mark messages read.
Text extraction excludes delivery/read-status labels. Unknown content, identity or
latest-message mismatch fails closed. Confirmed CDP disconnection precedes lease
release; uncertain disconnection keeps ownership for reconciliation.
Failed message binding logs only a fixed boundary code, not message text, identities,
attachment URLs, or raw DOM. The diagnostic uses the same capture checks.
When an encryption key is configured, signed creation imports only the user's
current profile; signed release saves the observed logged-in state before physical
release. Read tasks restore the saved profile but do not overwrite it during release;
explicit login and saved-login viewing retain their authenticated snapshot-save behavior.
`boss_lifecycle.py` supplies these callbacks to the site-independent lifecycle;
synthetic multi-site checks cover profile isolation.
