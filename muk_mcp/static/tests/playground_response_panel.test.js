import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { click, queryAll, queryOne } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import {
    mockService,
    mountWithCleanup,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import { ResponsePanel } from '@muk_mcp/playground/response_panel';

describe.current.tags('muk_mcp');

defineMailModels();

let notifications = [];

beforeEach(() => {
    notifications = [];
    mockService('notification', {
        add(message, options) {
            notifications.push([String(message), options && options.type]);
        },
    });
});

function makePanel(response) {
    const inst = Object.create(ResponsePanel.prototype);
    inst.props = { response };
    return inst;
}

async function mountPanel(response) {
    await mountWithCleanup(ResponsePanel, { props: { response } });
}

test('parsed returns null when no response', () => {
    expect(makePanel(null).parsed).toBe(null);
});

test('parsed classifies an OK tool result', () => {
    const inst = makePanel({
        status: 200,
        body: { result: { content: [{ type: 'text', text: 'hi' }] } },
    });
    expect(inst.parsed.kind).toBe('ok');
});

test('parsed classifies a tool-level error', () => {
    const inst = makePanel({
        status: 200,
        body: {
            result: {
                isError: true,
                content: [{ type: 'text', text: 'boom' }],
            },
        },
    });
    expect(inst.parsed.kind).toBe('tool_error');
});

test('parsed classifies a JSON-RPC error envelope', () => {
    const inst = makePanel({
        status: 500,
        body: { error: { code: -32603, message: 'Internal' } },
    });
    expect(inst.parsed.kind).toBe('error');
    expect(inst.parsed.code).toBe(-32603);
});

test('prettyResult pretty-prints JSON from OK results', () => {
    const inst = makePanel({
        status: 200,
        body: {
            result: { content: [{ type: 'text', text: '{"a":1}' }] },
        },
    });
    expect(inst.prettyResult).toBe('{\n  "a": 1\n}');
});

test('prettyResult returns JSON-RPC error string for rpc errors', () => {
    const inst = makePanel({
        status: 500,
        body: { error: { code: -32603, message: 'boom' } },
    });
    expect(inst.prettyResult).toBe('JSON-RPC error -32603: boom');
});

test('rawBody serialises the response body', () => {
    const inst = makePanel({
        status: 200,
        body: { result: { ok: true } },
        raw: '{"result":{"ok":true}}',
    });
    expect(inst.rawBody).toBe('{\n  "result": {\n    "ok": true\n  }\n}');
});

test('rawBody falls back to raw text when body is null', () => {
    const inst = makePanel({
        status: 500,
        body: null,
        raw: 'not json',
    });
    expect(inst.rawBody).toBe('not json');
});

test('statusClass maps kinds to Bootstrap alert classes', () => {
    expect(
        makePanel({
            status: 200,
            body: { result: { content: [{ type: 'text', text: '' }] } },
        }).statusClass,
    ).toBe('alert-success');
    expect(
        makePanel({
            status: 200,
            body: {
                result: {
                    isError: true,
                    content: [{ type: 'text', text: '' }],
                },
            },
        }).statusClass,
    ).toBe('alert-warning');
    expect(
        makePanel({
            status: 500,
            body: { error: { code: -1, message: '' } },
        }).statusClass,
    ).toBe('alert-danger');
});

test('blocks exposes the typed content blocks list', () => {
    const inst = makePanel({
        status: 200,
        body: {
            result: {
                content: [
                    { type: 'text', text: 'hi' },
                    { type: 'image', data: 'AA', mimeType: 'image/png' },
                ],
            },
        },
    });
    expect(inst.blocks).toHaveLength(2);
    expect(inst.blocks[0].type).toBe('text');
    expect(inst.blocks[1].type).toBe('image');
});

test('dataUri builds a base64 data URI with mime fallback', () => {
    const inst = makePanel({ status: 200, body: { result: { content: [] } } });
    expect(inst.dataUri('image/png', 'AA')).toBe('data:image/png;base64,AA');
    expect(inst.dataUri(null, 'BB')).toBe('data:application/octet-stream;base64,BB');
});

test('downloadName sanitises odoo:// uris into a filename', () => {
    const inst = makePanel({ status: 200, body: { result: { content: [] } } });
    expect(
        inst.downloadName({
            type: 'resource',
            resource: { uri: 'odoo://attachment/42' },
        }),
    ).toBe('odoo_attachment_42');
});

test('statusLabel maps kinds to user-facing labels', () => {
    expect(
        makePanel({
            status: 200,
            body: { result: { content: [{ type: 'text', text: '' }] } },
        }).statusLabel,
    ).toBe('OK');
    expect(
        makePanel({
            status: 200,
            body: {
                result: {
                    isError: true,
                    content: [{ type: 'text', text: '' }],
                },
            },
        }).statusLabel,
    ).toBe('Tool Error');
    expect(
        makePanel({
            status: 500,
            body: { error: { code: -1, message: '' } },
        }).statusLabel,
    ).toBe('JSON-RPC Error');
});

// ----------------------------------------------------------
// Rendered blocks
// ----------------------------------------------------------

test('renders a placeholder until a tool has been called', async () => {
    await mountPanel(null);
    expect('.text-muted').toHaveText('Click "Try it" to run the tool.');
});

test('renders every content block type of a tool result', async () => {
    await mountPanel({
        status: 200,
        body: {
            result: {
                content: [
                    { type: 'text', text: '{"ok": true}' },
                    { type: 'image', data: 'AAAA', mimeType: 'image/png' },
                    { type: 'audio', data: 'BBBB', mimeType: 'audio/mpeg' },
                    {
                        type: 'resource',
                        resource: {
                            uri: 'odoo://attachment/42',
                            mimeType: 'application/pdf',
                            blob: 'CCCC',
                        },
                    },
                    { type: 'future_block', payload: 1 },
                ],
            },
        },
    });
    expect('.alert-success strong').toHaveText('OK');
    expect(JSON.parse(queryAll('pre')[0].textContent)).toEqual({ ok: true });
    expect(queryAll('pre')[0].textContent).toInclude('\n');
    expect('img').toHaveCount(1);
    expect(queryOne('audio')).toHaveAttribute('src', 'data:audio/mpeg;base64,BBBB');
    const link = queryOne('a.btn');
    expect(link).toHaveAttribute('href', 'data:application/pdf;base64,CCCC');
    expect(link).toHaveAttribute('download', 'odoo_attachment_42');
    expect(queryAll('code')[0]).toHaveText('odoo://attachment/42');
    expect('.border.rounded.text-muted').toHaveText(
        /Unknown content block type: future_block/,
    );
});

test('an inline text resource is rendered without a download link', async () => {
    await mountPanel({
        status: 200,
        body: {
            result: {
                content: [
                    {
                        type: 'resource',
                        resource: {
                            uri: 'odoo://note/1',
                            mimeType: 'text/plain',
                            text: 'inline payload',
                            name: 'note.txt',
                        },
                    },
                ],
            },
        },
    });
    expect('a.btn').toHaveCount(0);
    expect(queryAll('pre')[0].textContent).toBe('inline payload');
});

test('copying the result and the raw body fills the clipboard', async () => {
    await mountPanel({
        status: 200,
        body: { result: { content: [{ type: 'text', text: '{"ok": true}' }] } },
        raw: '{"result": {"content": []}}',
    });
    await click(queryAll('button')[0]);
    await animationFrame();
    expect(JSON.parse(await navigator.clipboard.readText())).toEqual({ ok: true });
    expect(notifications).toEqual([['Result copied', 'success']]);
    await click(queryAll('button')[1]);
    await animationFrame();
    expect(
        JSON.parse(await navigator.clipboard.readText()).result.content,
    ).toHaveLength(1);
    expect(notifications.at(-1)).toEqual(['Raw response copied', 'success']);
});

test('a blocked clipboard is reported for both copy buttons', async () => {
    patchWithCleanup(navigator.clipboard, {
        writeText: () => Promise.reject(new Error('denied')),
    });
    await mountPanel({
        status: 200,
        body: { result: { content: [{ type: 'text', text: 'hi' }] } },
    });
    await click(queryAll('button')[0]);
    await animationFrame();
    await click(queryAll('button')[1]);
    await animationFrame();
    expect(notifications).toEqual([
        ['Clipboard unavailable', 'danger'],
        ['Clipboard unavailable', 'danger'],
    ]);
});
