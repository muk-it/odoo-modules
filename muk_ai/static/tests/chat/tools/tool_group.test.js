import { describe, expect, test } from '@odoo/hoot';
import { click, queryAll, queryAllTexts, queryFirst } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { Component, xml } from '@odoo/owl';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import {
    ToolGroup,
    buildTurnItems,
    toolBlockHasError,
} from '@muk_ai/chat/tools/tool_group';

describe.current.tags('muk_ai');
defineMailModels();

function tool(name, extra = {}) {
    return {
        type: 'tool',
        name,
        callId: name,
        arguments: null,
        result: null,
        ...extra,
    };
}

function text(content) {
    return { type: 'text', text: content };
}

const never = () => false;

// ----------------------------------------------------------
// toolBlockHasError
// ----------------------------------------------------------

test('toolBlockHasError: false for missing or successful results', () => {
    expect(toolBlockHasError({ result: null })).toBe(false);
    expect(toolBlockHasError({ result: undefined })).toBe(false);
    expect(toolBlockHasError({ result: { ok: true, count: 2 } })).toBe(false);
    expect(toolBlockHasError({ result: 'plain answer' })).toBe(false);
    expect(toolBlockHasError({ result: '{"ok": true}' })).toBe(false);
});

test('toolBlockHasError: true for object error or ok:false', () => {
    expect(toolBlockHasError({ result: { error: 'nope' } })).toBe(true);
    expect(toolBlockHasError({ result: { ok: false } })).toBe(true);
});

test('toolBlockHasError: true for JSON-string error payloads', () => {
    expect(toolBlockHasError({ result: '{"error": "denied"}' })).toBe(true);
    expect(toolBlockHasError({ result: '{"ok": false}' })).toBe(true);
});

// ----------------------------------------------------------
// buildTurnItems
// ----------------------------------------------------------

test('buildTurnItems: an empty or missing block list yields no items', () => {
    expect(buildTurnItems([], never)).toEqual([]);
    expect(buildTurnItems(undefined, never)).toEqual([]);
});

test('buildTurnItems: a lone tool stays a bare tool item, never a group', () => {
    const items = buildTurnItems([text('hi'), tool('search_records')], never);
    expect(items.map((i) => i.type)).toEqual(['text', 'tool']);
    expect(items[1].block.name).toBe('search_records');
});

test('buildTurnItems: two or more consecutive tools collapse into one group', () => {
    const items = buildTurnItems([tool('a'), tool('b'), tool('c')], never);
    expect(items).toHaveLength(1);
    expect(items[0].type).toBe('group');
    expect(items[0].tools.map((t) => t.block.name)).toEqual(['a', 'b', 'c']);
});

test('buildTurnItems: text and ask blocks break a run of tools', () => {
    const items = buildTurnItems(
        [tool('a'), tool('b'), text('mid'), tool('c'), tool('d')],
        never,
    );
    expect(items.map((i) => i.type)).toEqual(['group', 'text', 'group']);
    expect(items[0].tools).toHaveLength(2);
    expect(items[2].tools).toHaveLength(2);
});

test('buildTurnItems: a single tool between two texts is not grouped', () => {
    const items = buildTurnItems([text('a'), tool('x'), text('b')], never);
    expect(items.map((i) => i.type)).toEqual(['text', 'tool', 'text']);
});

test('buildTurnItems: hidden tools are excluded and split surrounding tools', () => {
    const isHidden = (b) => b.name === 'hidden';
    const items = buildTurnItems([tool('a'), tool('hidden'), tool('b')], isHidden);
    // The hidden tool falls through as its own item; neighbours stay bare.
    expect(items.map((i) => i.type)).toEqual(['tool', 'tool', 'tool']);
    expect(items.map((i) => i.block.name)).toEqual(['a', 'hidden', 'b']);
});

test('buildTurnItems: every item carries a stable, unique key', () => {
    const items = buildTurnItems([text('a'), tool('x'), tool('y'), text('b')], never);
    const keys = items.map((i) => i.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(items[1].type).toBe('group');
    expect(items[1].key).toBe('g-1');
});

// ----------------------------------------------------------
// ToolGroup component
// ----------------------------------------------------------

function makeGroup(tools, { onToggleTool, expandedIds = [], compact = false } = {}) {
    const toolItems = tools.map((block, blockIndex) => ({
        key: 't-' + blockIndex,
        block,
        blockIndex,
    }));
    class Parent extends Component {
        static components = { ToolGroup };
        static props = {};
        static template = xml`
            <ToolGroup
                tools="props.tools"
                compact="props.compact"
                isToolExpanded="props.isToolExpanded"
                onToggleTool="props.onToggleTool"
            />
        `;
    }
    Parent.props = {
        tools: { type: Array },
        compact: { type: Boolean },
        isToolExpanded: { type: Function },
        onToggleTool: { type: Function },
    };
    return {
        Parent,
        props: {
            tools: toolItems,
            compact,
            isToolExpanded: (id) => expandedIds.includes(id),
            onToggleTool: onToggleTool || (() => {}),
        },
    };
}

test('ToolGroup: header shows the tool count and is collapsed by default', async () => {
    const { Parent, props } = makeGroup([tool('a'), tool('b')]);
    await mountWithCleanup(Parent, { props });
    expect(queryFirst('.mk_tool_group_label').textContent.trim()).toBe('Used 2 tools');
    expect('.mk_tool_group_body').toHaveCount(0);
    expect(queryFirst('.mk_tool_group').dataset.expanded).toBe('0');
});

test('ToolGroup: clicking the head expands and reveals an inner card per tool', async () => {
    const { Parent, props } = makeGroup([tool('a'), tool('b'), tool('c')]);
    await mountWithCleanup(Parent, { props });
    await click('.mk_tool_group_head');
    await animationFrame();
    expect('.mk_tool_group_body').toHaveCount(1);
    expect('.mk_tool_group_body .mk_tool').toHaveCount(3);
    expect(queryFirst('.mk_tool_group').dataset.expanded).toBe('1');
    await click('.mk_tool_group_head');
    await animationFrame();
    expect('.mk_tool_group_body').toHaveCount(0);
});

test('ToolGroup: all-success cluster shows only an ok badge', async () => {
    const { Parent, props } = makeGroup([
        tool('a', { result: { ok: true } }),
        tool('b', { result: { ok: true } }),
    ]);
    await mountWithCleanup(Parent, { props });
    expect('.mk_tg_ok').toHaveCount(1);
    expect('.mk_tg_err').toHaveCount(0);
    expect(queryFirst('.mk_tg_ok').textContent.trim()).toBe('2');
    expect('.mk_tool_group_has_error').toHaveCount(0);
});

test('ToolGroup: a failing tool adds an error badge and the error class', async () => {
    const { Parent, props } = makeGroup([
        tool('a', { result: { ok: true } }),
        tool('b', { result: { error: 'denied' } }),
    ]);
    await mountWithCleanup(Parent, { props });
    expect(queryFirst('.mk_tg_ok').textContent.trim()).toBe('1');
    expect(queryFirst('.mk_tg_err').textContent.trim()).toBe('1');
    expect('.mk_tool_group_has_error').toHaveCount(1);
});

test('ToolGroup: chips list each tool name', async () => {
    const { Parent, props } = makeGroup([tool('search_records'), tool('read_records')]);
    await mountWithCleanup(Parent, { props });
    expect(queryAllTexts('.mk_tool_group_chip')).toEqual([
        'search_records',
        'read_records',
    ]);
});

test('ToolGroup: chips cap at four names and add an ellipsis overflow chip', async () => {
    const { Parent, props } = makeGroup(
        ['a', 'b', 'c', 'd', 'e', 'f'].map((n) => tool(n)),
    );
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_group_chip').toHaveCount(5);
    expect(queryFirst('.mk_tool_group_chip_more').textContent.trim()).toBe('…');
});

test('ToolGroup: compact mode hides the chips but keeps count and badges', async () => {
    const { Parent, props } = makeGroup(
        [tool('a', { result: { ok: true } }), tool('b', { result: { error: 'x' } })],
        { compact: true },
    );
    await mountWithCleanup(Parent, { props });
    expect('.mk_tool_group_chips').toHaveCount(0);
    expect(queryFirst('.mk_tool_group_label').textContent.trim()).toBe('Used 2 tools');
    expect('.mk_tg_ok').toHaveCount(1);
    expect('.mk_tg_err').toHaveCount(1);
});

test('ToolGroup: inner card toggle bubbles the callId to onToggleTool', async () => {
    let toggled = null;
    const { Parent, props } = makeGroup([tool('a'), tool('b')], {
        onToggleTool: (id) => {
            toggled = id;
        },
    });
    await mountWithCleanup(Parent, { props });
    await click('.mk_tool_group_head');
    await animationFrame();
    const heads = queryAll('.mk_tool_group_body .mk_tool_head');
    await click(heads[1]);
    expect(toggled).toBe('b');
});
