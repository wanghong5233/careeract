# Site Adapters

Recruiting-site-specific navigation, forms, and verification logic live here.
Follow the [P0 account-protection contract](../../../docs/topics/recruiting-communication/README.md#p0-账号保护与执行准入).

## Current boundary

The legacy BOSS component-state reader, script controls and sender have been deleted.
The authenticated business endpoints fail closed, and automatic lifecycle owners permit
release only. There is no legacy fallback or configuration switch to reopen execution.
Do not restore these implementations from history. Historical successful reads are not
evidence that the removed mechanism is acceptable for a new adapter.

`boss.py` contains pure parsing and result validation. Its older component-derived
contracts remain for historical data compatibility and parser regression only; they do
not authorize a new reader to inspect internal component state. The parser opens no
browser, retains no profile, sends no message and writes no CareerAct domain state.
New observation must use visible DOM/accessibility/screenshots and preserve durable
conversation/message identity and existing deduplication records. Unknown identity or
material version must remain unknown, not be inferred from an old component flag.

## Retained human login and profile lifecycle

`boss_login.py` supplies a fixed navigation callback during signed physical creation,
while the lifecycle row lock excludes Viewers and executors. It checks the active Steel
session and single blank page, reuses `cdp-use` at the configured internal CDP origin,
and disconnects before human takeover. Product assembly uses the login destination;
the automatic conversation-navigation callback has been removed. Successful navigation
does not prove login, platform permission or long-term stability.

`boss_profile.py` captures login state only. It checks the owned live Steel session and
single BOSS HTTPS page. Denied/login/challenge URLs stop capture before page attachment,
Cookie or DOM access. Normal capture reads scoped Cookie/localStorage and checks account
navigation and the message entry without enabling Runtime or executing page scripts.
It has no conversation reader, arbitrary evaluation or send operation. These bounded
login observations do not replace CareerAct's durable connection status.

`boss_lifecycle.py` binds profile callbacks to the shared lifecycle. Explicit login and
saved-login viewing retain encrypted capture/restore and existing authorization. Old
automatic owners can release resources but cannot create or finish new sessions.
Domain records, authorization, attempt evidence and applied migrations remain intact.

## New adapter acceptance

First validate a mature driver's normal input on local synthetic pages with the existing
Steel, Viewer and lease boundaries. Observe the visible target, input, and read back the
result; reject hidden, obscured, disabled, ambiguous or changed targets. Stop on takeover,
revocation, denial or uncertain writes. Arbitrary JS/HTTP/Shell model tools and unsafe
upstream fallbacks are not admissible. Only then reconnect the business path according
to the [implementation plan](../../../docs/topics/recruiting-communication/README.md#5-实施阶段和验收门槛).

Synthetic tests do not establish live platform availability or immunity from account risk.
