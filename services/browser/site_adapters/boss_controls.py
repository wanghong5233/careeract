# Reuse the established selected-friend and Editor identities. Find one visible
# semantic send control; ambiguous or changed markup never triggers a click.
BOSS_TEXT_CONTROL = """(() => {
    const target = __TARGET__;
    const box = document.querySelector('.chat-conversation');
    const selected = Array.from(document.querySelectorAll('.friend-content-warp'))
        .filter(row => row.querySelector('.friend-content.selected'));
    const source = selected.length === 1 ? selected[0].__vue__?.$props?.source : null;
    if (source?.uniqueId !== target || box?.__vue__?.$options?.name !== 'conversation-box'
        || box.__vue__.selectedFriend$?.uniqueId !== target) return null;
    const editors = Array.from(box.querySelectorAll('.editor-container')).filter(node =>
        node.__vue__?.$options?.name === 'Editor' && node.__vue__.$props?.uniqueId === target);
    if (editors.length !== 1) return null;
    const inputs = Array.from(editors[0].querySelectorAll('[contenteditable="true"]'))
        .filter(node => node.getClientRects().length > 0);
    const buttons = Array.from(editors[0].querySelectorAll('*')).filter(node =>
        node.textContent.trim() === '发送' && node.getClientRects().length > 0
        && !Array.from(node.children).some(child => child.textContent.trim() === '发送'));
    if (inputs.length !== 1 || buttons.length !== 1) return null;
    const input = inputs[0], button = buttons[0];
    const disabled = button.closest('[disabled],[aria-disabled="true"],.disabled,.unable');
    return {input, button, disabled: !!disabled, text: input.innerText.trim()};
})()"""
