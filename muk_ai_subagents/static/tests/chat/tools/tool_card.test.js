import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { queryFirst } from '@odoo/hoot-dom';
import { Component, xml } from '@odoo/owl';
import { mountWithCleanup, patchTranslations } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { buildRenderedTurns, isToolBlockHidden } from '@muk_ai/chat/session/turns';
import { ToolCard } from '@muk_ai/chat/tools/tool_card';
import '@muk_ai_subagents/chat/tools/tool_card';

describe.current.tags('muk_ai_subagents');
defineMailModels();

beforeEach(() => {
    patchTranslations();
});

class Parent extends Component {
    static components = { ToolCard };
    static props = { block: { type: Object } };
    static template = xml`<ToolCard block="props.block"/>`;
}

/**
 * Fold a delegate call and its result into a decorated tool block.
 * @param {object|string} args the call arguments, parsed or raw JSON
 * @param {*} result the tool result, or null while the call still runs
 * @returns {object} the decorated block
 */
function delegateBlock(args, result = null) {
    const log = [
        { kind: 'tool_call', name: 'delegate', arguments: args, call_id: 'd1' },
    ];
    if (result !== null) {
        log.push({ kind: 'tool_result', call_id: 'd1', result });
    }
    return buildRenderedTurns(log)[0].blocks[0];
}

test('a delegate block names the agents instead of showing raw arguments', async () => {
    const block = delegateBlock(
        { tasks: [{ agent: 'Market Reader' }, { agent: 'Numbers Reader' }] },
        '{"status": "delegated"}',
    );
    expect(block.kind).toBe('delegate');
    expect(block.icon).toBe('fa-sitemap');
    expect(block.band).toBe('To Market Reader and 1 more');
    await mountWithCleanup(Parent, { props: { block } });
    expect('.mk_tool_delegate').toHaveCount(1);
    expect('.mk_tool_icon .fa-sitemap').toHaveCount(1);
    expect(queryFirst('.mk_tool_band').textContent).toBe('To Market Reader and 1 more');
});

test('a single delegate names that one agent', () => {
    const block = delegateBlock(
        { tasks: [{ agent: 'Market Reader' }] },
        '{"status": "delegated"}',
    );
    expect(block.band).toBe('To Market Reader');
});

test('a delegate keeps its icon from the call to the last report', () => {
    expect(delegateBlock({ tasks: [] }).band).toBe('Delegating…');
    expect(delegateBlock({ tasks: [{ agent: 'Reader' }] }).icon).toBe('fa-sitemap');
    const reported = delegateBlock(
        { tasks: [{ agent: 'Reader' }] },
        '{"status": "completed", "results": []}',
    );
    expect(reported.icon).toBe('fa-sitemap');
    const refused = delegateBlock(
        { tasks: [{ agent: 'Reader' }] },
        '{"error": "not whitelisted"}',
    );
    expect(refused.icon).toBe('fa-exclamation-triangle');
});

test('another tool keeps the generic card', () => {
    const log = [
        { kind: 'tool_call', name: 'search_read', arguments: {}, call_id: 'c1' },
        { kind: 'tool_result', call_id: 'c1', result: '[]' },
    ];
    const block = buildRenderedTurns(log)[0].blocks[0];
    expect(block.kind).not.toBe('delegate');
    expect(block.band).toBe(undefined);
});

test('the delegate card gives way to the run that streams it', () => {
    // The strip, the spawn line and the result cards already say all of this,
    // and they keep saying it while the subagents work.
    const done = delegateBlock({ tasks: [{ agent: 'Market Reader' }] }, '{}');
    expect(isToolBlockHidden(done, { blocks: [] })).toBe(true);
    const running = delegateBlock({ tasks: [{ agent: 'Market Reader' }] }, null);
    expect(isToolBlockHidden(running, { blocks: [] })).toBe(true);
});

test('a refused delegate keeps its card, having nowhere else to appear', () => {
    const refused = delegateBlock({ tasks: [] }, '{"error": "not allowed"}');
    expect(isToolBlockHidden(refused, { blocks: [] })).toBe(false);
});
