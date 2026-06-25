import { describe, expect, test } from '@odoo/hoot';
import { click, queryFirst } from '@odoo/hoot-dom';
import { Component, xml } from '@odoo/owl';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ToolCard } from '@muk_ai/chat/tools/tool_card';

describe.current.tags('muk_ai');
defineMailModels();

function makeParent({ block, expanded = false, streaming = false, onToggle } = {}) {
    class Parent extends Component {
        static components = { ToolCard };
        static props = {};
        static template = xml`
            <ToolCard
                block="props.block"
                expanded="props.expanded"
                streaming="props.streaming"
                onToggle="props.onToggle or (() => {})"
            />
        `;
    }
    Parent.props = {
        block: { type: Object },
        expanded: { type: Boolean },
        streaming: { type: Boolean },
        onToggle: { type: Function, optional: true },
    };
    return { Parent, props: { block, expanded, streaming, onToggle } };
}

test('renders the tool name and a wrench icon when collapsed and idle', async () => {
    const { Parent, props } = makeParent({
        block: { name: 'list_modules', arguments: null, callId: 'c1' },
    });
    await mountWithCleanup(Parent, { props });
    expect(queryFirst('.mk_tool_name').textContent).toBe('list_modules');
    expect('.fa-wrench').toHaveCount(1);
    expect('.fa-circle-o-notch').toHaveCount(0);
    expect('.mk_tool_body').toHaveCount(0);
});

test('streaming swaps wrench for spinner and shows running… status', async () => {
    const { Parent, props } = makeParent({
        block: {
            name: 'search_records',
            arguments: { model: 'res.partner' },
            callId: 'c2',
        },
        streaming: true,
    });
    await mountWithCleanup(Parent, { props });
    expect('.fa-circle-o-notch').toHaveCount(1);
    expect('.fa-wrench').toHaveCount(0);
    expect(queryFirst('.mk_tool_status').textContent.trim()).toBe('running…');
});

test('summary inlines whitespace and truncates over 60 chars with an ellipsis', async () => {
    const longArgs = { padding: 'x'.repeat(200) };
    const { Parent, props } = makeParent({
        block: { name: 't', arguments: longArgs, callId: 'c1' },
    });
    await mountWithCleanup(Parent, { props });
    const summary = queryFirst('.mk_tool_preview').textContent;
    expect(summary.length).toBe(61);
    expect(summary.endsWith('…')).toBe(true);
    expect(/\s{2,}/.test(summary)).toBe(false);
});

test('summary is empty when block has no arguments', async () => {
    const { Parent, props } = makeParent({
        block: { name: 't', arguments: null, callId: 'c1' },
    });
    await mountWithCleanup(Parent, { props });
    expect(queryFirst('.mk_tool_preview').textContent).toBe('');
});

test('expanded shows pretty-printed arguments and parsed JSON-string result', async () => {
    const { Parent, props } = makeParent({
        block: {
            name: 't',
            callId: 'c1',
            arguments: { ids: [1, 2] },
            result: '{"ok":true,"count":2}',
        },
        expanded: true,
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_body').toHaveCount(1);
    expect('.mk_tool_section').toHaveCount(2);
    const code = document.querySelectorAll('.mk_tool_section code');
    expect(code[0].textContent).toBe('{\n  "ids": [\n    1,\n    2\n  ]\n}');
    expect(code[1].textContent).toBe('{\n  "ok": true,\n  "count": 2\n}');
});

test('expanded with non-JSON string result keeps it verbatim', async () => {
    const { Parent, props } = makeParent({
        block: { name: 't', callId: 'c1', arguments: null, result: 'plain answer' },
        expanded: true,
    });
    await mountWithCleanup(Parent, { props });
    expect(queryFirst('.mk_tool_section code').textContent).toBe('plain answer');
});

test('expanded with no result shows the running placeholder', async () => {
    const { Parent, props } = makeParent({
        block: { name: 't', callId: 'c1', arguments: { x: 1 }, result: null },
        expanded: true,
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_section .fa-spinner').toHaveCount(1);
    expect(document.querySelectorAll('.mk_tool_section').length).toBe(2);
});

test('clicking the head emits onToggle with the callId', async () => {
    let toggled = null;
    const { Parent, props } = makeParent({
        block: { name: 't', callId: 'abc', arguments: null },
        onToggle: (id) => {
            toggled = id;
        },
    });
    await mountWithCleanup(Parent, { props });
    await click('.mk_tool_head');
    expect(toggled).toBe('abc');
});

test('streaming suppresses onToggle clicks', async () => {
    let toggled = null;
    const { Parent, props } = makeParent({
        block: { name: 't', callId: 'abc', arguments: null },
        streaming: true,
        onToggle: (id) => {
            toggled = id;
        },
    });
    await mountWithCleanup(Parent, { props });
    await click('.mk_tool_head');
    expect(toggled).toBe(null);
});

test('applies mk_tool_write kind class for create/update tool names', async () => {
    const { Parent, props } = makeParent({
        block: { name: 'create_record', arguments: null, callId: 'c1' },
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_write').toHaveCount(1);
});

test('applies mk_tool_read kind class for search tool names', async () => {
    const { Parent, props } = makeParent({
        block: { name: 'search_read', arguments: null, callId: 'c2' },
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_read').toHaveCount(1);
});

test('applies mk_tool_nav kind class for open tool names', async () => {
    const { Parent, props } = makeParent({
        block: { name: 'open_record', arguments: null, callId: 'c3' },
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_nav').toHaveCount(1);
});

test('applies mk_tool_error when result contains an error', async () => {
    const { Parent, props } = makeParent({
        block: {
            name: 'search_read',
            arguments: null,
            callId: 'c4',
            result: { error: 'access denied' },
        },
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_error').toHaveCount(1);
});

test('applies mk_tool_error when result JSON string contains an error', async () => {
    const { Parent, props } = makeParent({
        block: {
            name: 'search_read',
            arguments: null,
            callId: 'c5',
            result: '{"error": "nope"}',
        },
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_error').toHaveCount(1);
});

test('falls back to default kind for unknown tool name', async () => {
    const { Parent, props } = makeParent({
        block: { name: 'mystery', arguments: null, callId: 'c6' },
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_default').toHaveCount(1);
});

test('detects diff body in result and swaps to language-diff pre', async () => {
    const diff = [
        '--- old.txt',
        '+++ new.txt',
        '@@ -1,1 +1,1 @@',
        '-before',
        '+after',
    ].join('\n');
    const { Parent, props } = makeParent({
        block: { name: 'apply_patch', arguments: null, callId: 'c7', result: diff },
        expanded: true,
    });
    await mountWithCleanup(Parent, { props });
    expect('.language-diff').toHaveCount(2);
});
