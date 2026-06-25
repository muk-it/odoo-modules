import { describe, expect, test } from '@odoo/hoot';

import { ResponsePanel } from '@muk_mcp/playground/response_panel';

describe.current.tags('muk_mcp');

function makePanel(response) {
    const inst = Object.create(ResponsePanel.prototype);
    inst.props = { response };
    return inst;
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
