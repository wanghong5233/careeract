"""Bounded observation of the current platform attachment list, without file contents."""

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MaterialReason = Literal["page", "heading", "count", "filename", "revision"]


@dataclass(frozen=True, slots=True, repr=False)
class BossPlatformMaterial:
    filename: str
    displayed_size: str
    displayed_revision: str
    reference: str


@dataclass(frozen=True, slots=True, repr=False)
class BossMaterialCatalog:
    state: Literal["observed", "empty", "unknown", "needs_login", "risk"]
    materials: tuple[BossPlatformMaterial, ...] = ()
    # A metadata reference is not a hash of the attachment bytes or send permission.
    identity_basis: Literal["rendered_metadata"] = "rendered_metadata"
    reason: MaterialReason | None = None


class _Material(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    filename: str = Field(
        min_length=1, max_length=300, pattern=r"^[^/\\\x00-\x1f\x7f]+\.(?i:pdf|docx?)$"
    )
    displayed_size: str = Field(pattern=r"^\d+(?:\.\d+)?\s*(?:B|KB|MB)$")
    displayed_revision: str = Field(
        pattern=r"^20\d{2}[./-]\d{2}[./-]\d{2}(?: \d{2}:\d{2}(?::\d{2})?)?$"
    )


class _Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    state: Literal["observed", "empty", "unknown"]
    materials: list[_Material] = Field(max_length=3)
    reason: MaterialReason | None = None


def parse_material_catalog(captured: str) -> BossMaterialCatalog:
    if len(captured.encode()) > 8192:
        raise ValueError("BOSS material capture exceeds limit")
    value = _Catalog.model_validate_json(captured)
    if (
        value.state != "observed"
        and value.materials
        or value.state == "observed"
        and not value.materials
        or len({m.filename for m in value.materials}) != len(value.materials)
        or any("…" in m.filename or "..." in m.filename for m in value.materials)
    ):
        raise ValueError("BOSS material binding incomplete")
    return BossMaterialCatalog(
        value.state,
        tuple(
            BossPlatformMaterial(
                m.filename,
                m.displayed_size,
                m.displayed_revision,
                sha256(
                    json.dumps(m.model_dump(), ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest(),
            )
            for m in value.materials
        ),
        reason=value.reason,
    )


# Fixed read-only geometry/text inspection. No title attributes, hidden descendants,
# component state or network data. A clipped/occluded field is not a material identity.
_VISIBLE_TEXT = r"""
    const normalize = t => (t || '').replace(/\s+/g, ' ').trim();
    const visibleText = (root, strict = true) => {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        const parts = [];
        let node, count = 0;
        while ((node = walker.nextNode())) {
            if (++count > 4096) return null;
            if (!normalize(node.textContent)) continue;
            let hidden = false;
            for (let p = node.parentElement; p; p = p.parentElement) {
                const style = getComputedStyle(p);
                if (style.display === 'none' || style.visibility !== 'visible'
                    || (strict ? Number(style.opacity) !== 1 : Number(style.opacity) <= 0)
                    || strict && p.hasAttribute('aria-hidden')
                        && p.getAttribute('aria-hidden') === 'true') hidden = true;
            }
            if (hidden) continue;
            const range = document.createRange();
            range.selectNodeContents(node);
            const rects = Array.from(range.getClientRects());
            if (!rects.length) return null;
            for (const r of rects) {
                if (r.width <= 0 || r.height <= 0 || r.left < 0 || r.top < 0
                    || r.right > innerWidth || r.bottom > innerHeight) return null;
                // Avoid inline text-edge rounding; inspect three interior points.
                for (const x of [r.left + Math.min(4, r.width / 4),
                    (r.left + r.right) / 2, r.right - Math.min(4, r.width / 4)]) {
                    const hit = document.elementFromPoint(x, (r.top + r.bottom) / 2);
                    if (!hit || !(hit === node.parentElement
                        || node.parentElement.contains(hit))) return null;
                }
            }
            parts.push(node.textContent);
            if (parts.join(' ').length > 16384) return null;
        }
        return normalize(parts.join(' '));
    };
"""

# Only the visible attachment manager is observed. Do not inspect the online resume,
# download URLs, credentials, full component state, or private platform endpoints.
BOSS_MATERIAL_CATALOG = (
    "JSON.stringify((() => {"
    + _VISIBLE_TEXT
    + r"""
    const unknown = reason => ({state: 'unknown', materials: [], reason});
    if (location.origin !== 'https://www.zhipin.com'
        || location.pathname !== '/web/geek/resume') return unknown('page');
    const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,div,span'))
        .filter(n => visibleText(n) === '附件管理'
            && !Array.from(n.children).some(c => visibleText(c) === '附件管理'));
    if (headings.length !== 1) return unknown('heading');
    let panel = headings[0].parentElement;
    for (let i = 0; i < 4 && panel; i++, panel = panel.parentElement) {
        const text = visibleText(panel);
        if (text === null) return unknown('count');
        const count = text.match(/文件\s*[（(]\s*([0-3])\s*\/\s*3\s*[）)]/);
        if (!count) continue;
        const expected = Number(count[1]);
        const candidates = Array.from(panel.querySelectorAll('*')).filter(n =>
            /\.(pdf|docx?)$/i.test(visibleText(n) || ''));
        const names = candidates.filter(n => !candidates.some(c => c !== n
            && n.contains(c) && visibleText(c) === visibleText(n)));
        if (names.length !== expected) return unknown('filename');
        if (expected === 0) return {state: 'empty', materials: []};
        const materials = [];
        for (const node of names) {
            const filename = visibleText(node);
            if (filename === null) return unknown('filename');
            if (filename.includes('…') || filename.includes('...')
                || !filename)
                return unknown('filename');
            let row = node.parentElement, found = null;
            for (let j = 0; j < 4 && row && row !== panel; j++, row = row.parentElement) {
                const rowText = visibleText(row);
                if (rowText === null) return unknown('revision');
                const sizes = rowText.match(/\b\d+(?:\.\d+)?\s*(?:KB|MB|B)\b/g) || [];
                const revisionPattern = /20\d{2}[./-]\d{2}[./-]\d{2}(?: \d{2}:\d{2}(?::\d{2})?)?/g;
                const revisions = rowText.match(revisionPattern) || [];
                if (sizes.length === 1 && revisions.length === 1) {
                    found = {filename, displayed_size: sizes[0], displayed_revision: revisions[0]};
                    break;
                }
            }
            if (!found) return unknown('revision');
            materials.push(found);
        }
        return {state: 'observed', materials};
    }
    return unknown('count');
})())"""
)
