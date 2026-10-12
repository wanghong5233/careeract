import json
import shutil
import subprocess

import pytest

from services.browser.site_adapters.boss_context import BOSS_RENDERED_MESSAGES, BOSS_RESUME_CONTROL


@pytest.mark.parametrize(
    "changed",
    [None, "selected", "message", "key", "direction", "latest", "text", "component", "duplicate"],
)
def test_live_message_script_separates_delivery_status_and_rejects_changed_binding(
    changed: str | None,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime unavailable for synthetic DOM script check")
    fixture = """
const target = 'thread-1';
const source = {uniqueId: target, friendId: 7, lastMsgId: 123};
const message = {uniqueId: target, friendId: 7, mid: 123,
    time: 1700000000000, isSelf: true, text: 'Synthetic text'};
const body = {textContent: 'Synthetic text'};
const content = {textContent: '已读 Synthetic text',
    __vue__: {$options: {name: 'MessageText'}},
    querySelectorAll: () => [body]};
const row = {__vue__: {$options: {name: 'ChatMessage'},
    $props: {message}, $vnode: {key: 123}},
    querySelector: () => content,
    classList: {contains: value => value === 'item-myself'}};
const box = {__vue__: {$options: {name: 'conversation-box'}, selectedFriend$: source},
    querySelectorAll: () => [row]};
const selected = {__vue__: {$props: {source}}, querySelector: () => ({})};
const document = {querySelector: () => box, querySelectorAll: () => [selected]};
if (changed === 'selected') box.__vue__.selectedFriend$ = {uniqueId: 'other'};
if (changed === 'message') message.uniqueId = 'other';
if (changed === 'key') row.__vue__.$vnode.key = 999;
if (changed === 'direction') message.isSelf = false;
if (changed === 'latest') source.lastMsgId = 999;
if (changed === 'text') body.textContent = 'Different text';
if (changed === 'component') content.__vue__.$options.name = 'Unknown';
if (changed === 'duplicate') content.querySelectorAll = () => [body, body];
"""
    expression = BOSS_RENDERED_MESSAGES.replace("__TARGET__", json.dumps("thread-1"))
    script = "const changed = " + json.dumps(changed) + ";\n" + fixture
    script += "\nprocess.stdout.write(" + expression + ");"
    result = subprocess.run(
        [node, "-"], input=script, text=True, capture_output=True, timeout=5, check=True
    )
    messages = json.loads(result.stdout)
    if changed:
        assert messages == []
    else:
        assert messages[0]["content"] == "Synthetic text"
        assert messages[0]["sender"] == "candidate"
        assert messages[0]["message_id"] == "123"


@pytest.mark.parametrize("changed", [None, "disabled", "hidden", "editor", "duplicate", "selected"])
def test_resume_script_observes_control_without_granting_material_authorization(
    changed: str | None,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime unavailable")
    fixture = """
const source = {uniqueId: 'thread-1', lastMsgId: 123};
const button = {classList: {contains: () => changed === 'disabled'},
    hasAttribute: () => false, getAttribute: () => null,
    getClientRects: () => changed === 'hidden' ? [] : [{}]};
const upload = {__vue__: {$options: {name: 'choose-upload-resume'}, $props: {hasResume: false}}};
const resume = {__vue__: {$options: {name: 'resumeBtn'}},
    querySelectorAll: selector => selector === '.toolbar-btn' ? [button] : [upload]};
const toolbar = {__vue__: {$options: {name: 'ConversationToolbar'}},
    querySelectorAll: () => changed === 'duplicate' ? [resume, resume] : [resume]};
const editor = {__vue__: {$options: {name: 'Editor'},
    $props: {uniqueId: changed === 'editor' ? 'other' : 'thread-1'}}};
const box = {__vue__: {$options: {name: 'conversation-box'},
    selectedFriend$: changed === 'selected' ? {uniqueId: 'other'} : source},
    querySelectorAll: selector => selector === '.chat-editor' ? [toolbar] : [editor]};
const selected = {__vue__: {$props: {source}}, querySelector: () => ({})};
const document = {querySelector: () => box, querySelectorAll: () => [selected]};
"""
    script = "const changed = " + json.dumps(changed) + ";\n" + fixture
    script += (
        "\nprocess.stdout.write("
        + BOSS_RESUME_CONTROL.replace("__TARGET__", json.dumps("thread-1"))
        + ");"
    )
    result = subprocess.run(
        [node, "-"], input=script, text=True, capture_output=True, timeout=5, check=True
    )
    control = json.loads(result.stdout)
    if changed == "selected":
        assert control is None
    else:
        assert control["state"] == (
            "unavailable" if changed == "disabled" else "unknown" if changed else "available"
        )
        assert control["attachment_reported"] is (False if changed in {None, "disabled"} else None)
