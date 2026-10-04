import { describe, expect, test } from '@odoo/hoot';
import { queryAll } from '@odoo/hoot-dom';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { contains, mountWithCleanup } from '@web/../tests/web_test_helpers';

import { ResponsePanel } from '@muk_mcp/playground/response_panel/response_panel';

describe.current.tags('muk_mcp');

defineMailModels();

function mountPanel(body, raw = JSON.stringify(body, null, 2)) {
    return mountWithCleanup(ResponsePanel, {
        props: { response: { status: 200, duration: 1, body, raw } },
    });
}

test('the alert names the outcome of the call', async () => {
    const cases = [
        [{ result: { content: [] } }, 'alert-success', /^OK$/],
        [{ result: { isError: true, content: [] } }, 'alert-warning', /^Tool Error$/],
        [{ error: { code: -32603, message: 'boom' } }, 'alert-danger', /-32603\s*boom/],
        [null, 'alert-secondary', /^Empty$/],
    ];
    for (const [body, alertClass, label] of cases) {
        await mountPanel(body, 'raw');
        expect(`.alert.${alertClass}`).toHaveText(label);
    }
});

test('every content block type is rendered', async () => {
    await mountPanel({
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
                {
                    type: 'resource',
                    resource: { uri: 'odoo://note/1', text: 'inline payload' },
                },
                { type: 'future_block' },
            ],
        },
    });
    expect(queryAll('pre')[0].textContent).toBe('{\n  "ok": true\n}');
    expect('div:has(> img)').toHaveText(/image · image\/png/);
    expect('audio').toHaveAttribute('src', 'data:audio/mpeg;base64,BBBB');
    expect('a.btn').toHaveCount(1);
    expect('a.btn').toHaveAttribute('href', 'data:application/pdf;base64,CCCC');
    expect('a.btn').toHaveAttribute('download', 'odoo_attachment_42');
    expect(queryAll('code').map((code) => code.textContent)).toEqual([
        'odoo://attachment/42',
        'odoo://note/1',
        'future_block',
    ]);
    expect('pre:contains(inline payload)').toHaveCount(1);
    expect('.text-muted:contains(Unknown content block type)').toHaveCount(1);
});

test('the text result and the raw body are copied to the clipboard', async () => {
    await mountPanel({
        result: { content: [{ type: 'text', text: '{"ok": true}' }] },
    });
    await contains('.alert .o_clipboard_button').click();
    expect(JSON.parse(await navigator.clipboard.readText())).toEqual({ ok: true });
    await contains('summary').click();
    await contains('details .o_clipboard_button').click();
    expect(JSON.parse(await navigator.clipboard.readText())).toEqual({
        result: { content: [{ type: 'text', text: '{"ok": true}' }] },
    });
});
