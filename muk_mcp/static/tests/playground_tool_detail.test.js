import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { click, edit, press, queryAll, queryOne } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import {
    mockService,
    mountWithCleanup,
    patchWithCleanup,
} from '@web/../tests/web_test_helpers';

import { STORAGE_KEY } from '@muk_mcp/playground/mcp_client';
import { ToolDetail } from '@muk_mcp/playground/tool_detail';

describe.current.tags('muk_mcp');

defineMailModels();

const TOOL = {
    name: 'res_partner_search',
    category: 'read',
    kind: 'db',
    description: 'Search partners',
    inputSchema: {
        type: 'object',
        required: ['domain', 'model'],
        properties: {
            model: { type: 'string', description: 'Technical model name' },
            domain: { type: 'array' },
            limit: { type: 'integer', default: 80 },
        },
    },
};

let notifications = [];
let calls = [];

beforeEach(() => {
    notifications = [];
    calls = [];
    mockService('notification', {
        add(message, options) {
            notifications.push([String(message), options && options.type]);
        },
    });
});

async function mountDetail(props = {}) {
    return mountWithCleanup(ToolDetail, {
        props: {
            tool: TOOL,
            response: null,
            running: false,
            hasKey: true,
            onTry: (payload) => calls.push(payload),
            ...props,
        },
    });
}

// ----------------------------------------------------------
// Rendering
// ----------------------------------------------------------

test('renders the tool header and seeds the form from the schema', async () => {
    await mountDetail();
    expect('.o_muk_mcp_detail h4').toHaveText('res_partner_search');
    expect('.o_muk_mcp_detail .badge.text-bg-info').toHaveText('read');
    expect(queryAll('.o_muk_mcp_detail .badge.text-bg-light')[0]).toHaveText('DB');
    expect('.o_muk_mcp_detail').toHaveText(/Search partners/);
    expect(queryOne('.o_muk_mcp_detail input[type="text"]').value).toBe('');
    expect(queryOne('.o_muk_mcp_detail textarea').value).toBe('[]');
    expect(queryOne('.o_muk_mcp_detail input[type="number"]').value).toBe('80');
});

test('renders a placeholder when no tool is selected', async () => {
    await mountDetail({ tool: undefined });
    expect('.o_muk_mcp_detail').toHaveText('Select a tool from the list on the left.');
});

test('the schema tab shows the indented input schema', async () => {
    await mountDetail();
    await click(queryAll('.o_muk_mcp_detail .nav-link')[1]);
    await animationFrame();
    expect(JSON.parse(queryOne('.o_muk_mcp_detail pre').textContent)).toEqual(
        TOOL.inputSchema,
    );
    await click(queryAll('.o_muk_mcp_detail .nav-link')[0]);
    await animationFrame();
    expect('.o_muk_mcp_detail pre').toHaveCount(0);
    expect('.o_muk_mcp_detail textarea').toHaveCount(1);
});

// ----------------------------------------------------------
// Running
// ----------------------------------------------------------

test('running emits the pruned arguments of the edited form', async () => {
    await mountDetail();
    await click('.o_muk_mcp_detail input[type="text"]');
    await edit('res.partner');
    await animationFrame();
    await click('.o_muk_mcp_detail .btn-primary');
    expect(calls).toEqual([
        {
            name: 'res_partner_search',
            args: { model: 'res.partner', domain: [], limit: 80 },
        },
    ]);
});

test('ctrl+enter runs the tool', async () => {
    await mountDetail();
    await click('.o_muk_mcp_detail input[type="text"]');
    await press(['ctrl', 'Enter']);
    expect(calls).toHaveLength(1);
});

test('ctrl+enter is ignored while a call is running', async () => {
    await mountDetail({ running: true });
    await click('.o_muk_mcp_detail input[type="text"]');
    await press(['ctrl', 'Enter']);
    expect(calls).toHaveLength(0);
});

test('ctrl+enter is ignored while no key is set', async () => {
    await mountDetail({ hasKey: false });
    await click('.o_muk_mcp_detail input[type="text"]');
    await press(['ctrl', 'Enter']);
    expect(calls).toHaveLength(0);
});

test('reset restores the schema defaults after an edit', async () => {
    await mountDetail();
    await click('.o_muk_mcp_detail input[type="text"]');
    await edit('res.users');
    await animationFrame();
    await click('.o_muk_mcp_detail .btn-outline-secondary');
    await animationFrame();
    expect(queryOne('.o_muk_mcp_detail input[type="text"]').value).toBe('');
    expect(queryOne('.o_muk_mcp_detail input[type="number"]').value).toBe('80');
});

// ----------------------------------------------------------
// Response status
// ----------------------------------------------------------

test('a 2xx response is shown as a success status', async () => {
    await mountDetail({
        response: { status: 200, duration: 12, body: { result: { content: [] } } },
    });
    expect('.o_muk_mcp_detail .fw-bold.text-success').toHaveText('HTTP 200');
});

test('a 4xx response is shown as a warning status', async () => {
    await mountDetail({
        response: {
            status: 404,
            duration: 3,
            body: { error: { code: -1, message: 'x' } },
        },
    });
    expect('.o_muk_mcp_detail .fw-bold.text-warning').toHaveText('HTTP 404');
});

test('a 5xx response is shown as a danger status', async () => {
    await mountDetail({
        response: { status: 500, duration: 3, body: null, raw: 'boom' },
    });
    expect('.o_muk_mcp_detail .fw-bold.text-danger').toHaveText('HTTP 500');
    expect(queryOne('.o_muk_mcp_detail details pre').textContent).toBe('boom');
});

// ----------------------------------------------------------
// Copy actions
// ----------------------------------------------------------

test('copy curl uses a placeholder when no key is stored', async () => {
    await mountDetail();
    await click(queryAll('.o_muk_mcp_detail .btn-secondary')[0]);
    await animationFrame();
    const copied = await navigator.clipboard.readText();
    expect(copied).toInclude("-H 'Authorization: Bearer <YOUR_MCP_KEY>'");
    expect(copied).toInclude('"method":"tools/call"');
    expect(notifications).toEqual([['curl copied', 'success']]);
});

test('copy curl embeds the stored key', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'live-key');
    await mountDetail();
    await click(queryAll('.o_muk_mcp_detail .btn-secondary')[0]);
    await animationFrame();
    expect(await navigator.clipboard.readText()).toInclude(
        "-H 'Authorization: Bearer live-key'",
    );
});

test('copy JSON-RPC writes the indented tools/call payload', async () => {
    await mountDetail();
    await click(queryAll('.o_muk_mcp_detail .btn-secondary')[1]);
    await animationFrame();
    expect(JSON.parse(await navigator.clipboard.readText())).toEqual({
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/call',
        params: {
            name: 'res_partner_search',
            arguments: { domain: [], limit: 80 },
        },
    });
    expect(notifications).toEqual([['JSON-RPC payload copied', 'success']]);
});

test('a blocked clipboard is reported to the user', async () => {
    patchWithCleanup(navigator.clipboard, {
        writeText: () => Promise.reject(new Error('denied')),
    });
    await mountDetail();
    await click(queryAll('.o_muk_mcp_detail .btn-secondary')[1]);
    await animationFrame();
    expect(notifications).toEqual([['Clipboard unavailable', 'danger']]);
});
