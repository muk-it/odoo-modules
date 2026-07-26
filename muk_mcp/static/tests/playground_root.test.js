import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { click, edit, queryAll, queryAllTexts, queryOne } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';

import { STORAGE_KEY } from '@muk_mcp/playground/mcp_client';
import { Playground } from '@muk_mcp/playground/playground';

describe.current.tags('muk_mcp');

defineMailModels();

const LAST_TOOL_KEY = 'muk_mcp.playground.last_tool';
const ACTIVE_PANEL_KEY = 'muk_mcp.playground.active_panel';

const SEARCH_TOOL = {
    name: 'res_partner_search',
    category: 'read',
    kind: 'db',
    description: 'Search partners',
    inputSchema: {
        type: 'object',
        required: ['domain'],
        properties: { domain: { type: 'array' }, limit: { type: 'integer' } },
    },
};

const READ_TOOL = {
    name: 'res_partner_read',
    category: 'read',
    kind: 'db',
    description: 'Read one partner',
    inputSchema: { type: 'object', properties: {} },
};

const CREATE_TOOL = {
    name: 'res_partner_create',
    category: 'write',
    kind: 'method',
    description: 'Create a partner',
    inputSchema: { type: 'object', properties: { name: { type: 'string' } } },
};

let notifications = [];

beforeEach(() => {
    notifications = [];
});

function mockPlaygroundServices({
    tools = [SEARCH_TOOL, READ_TOOL, CREATE_TOOL],
    loadError = null,
} = {}) {
    mockService('notification', {
        add(message, options) {
            notifications.push([String(message), options && options.type]);
        },
    });
    mockService('orm', {
        call(model, method, args, kwargs) {
            if (model === 'muk_mcp.tool' && method === 'get_playground_tools') {
                return loadError ? Promise.reject(loadError) : Promise.resolve(tools);
            }
            if (model === 'muk_mcp.prompt' && method === 'get_playground_prompts') {
                return Promise.resolve([]);
            }
            if (model === 'muk_mcp.key' && method === 'generate_playground_key') {
                return Promise.resolve({
                    name: kwargs.name,
                    key_prefix: 'mcp_abcd',
                    plaintext: 'mcp_abcd_secret',
                });
            }
            return Promise.reject(new Error(`unexpected ${model}.${method}`));
        },
    });
}

function jsonResponse(body, status = 200) {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

function mockMcpEndpoint(routes = {}) {
    onRpc('/mcp', async (request) => {
        if (request.method !== 'POST') {
            return new Response('', { status: 204 });
        }
        const body = await request.json();
        if (routes[body.method]) {
            return routes[body.method](body);
        }
        if (body.method === 'initialize') {
            return jsonResponse({ jsonrpc: '2.0', id: body.id, result: {} });
        }
        if (body.method === 'notifications/initialized') {
            return new Response('', { status: 202 });
        }
        return new Response('', { status: 400 });
    });
}

function panelTab(label) {
    return queryAll('.o_muk_mcp_panel_tab').find((tab) =>
        tab.textContent.includes(label),
    );
}

// ----------------------------------------------------------
// Tool catalog
// ----------------------------------------------------------

test('groups the tool catalog by category and selects the first tool', async () => {
    mockPlaygroundServices();
    await mountWithCleanup(Playground, { props: {} });
    expect(
        queryAll('.o_muk_mcp_group_header .badge').map((b) => b.textContent.trim()),
    ).toEqual(['Read', 'Write']);
    expect(queryAllTexts('.o_muk_mcp_tool .fw-bold')).toEqual([
        'res_partner_read',
        'res_partner_search',
        'res_partner_create',
    ]);
    expect('.o_muk_mcp_tool.active .fw-bold').toHaveText('res_partner_search');
    expect('.o_muk_mcp_detail h4').toHaveText('res_partner_search');
});

test('restores the last used tool from localStorage', async () => {
    localStorage.setItem(LAST_TOOL_KEY, 'res_partner_create');
    mockPlaygroundServices();
    await mountWithCleanup(Playground, { props: {} });
    expect('.o_muk_mcp_detail h4').toHaveText('res_partner_create');
    expect('.o_muk_mcp_tool.active .fw-bold').toHaveText('res_partner_create');
});

test('falls back to the first tool when the stored one disappeared', async () => {
    localStorage.setItem(LAST_TOOL_KEY, 'removed_tool');
    mockPlaygroundServices();
    await mountWithCleanup(Playground, { props: {} });
    expect('.o_muk_mcp_detail h4').toHaveText('res_partner_search');
});

test('notifies and renders an empty catalog when loading tools fails', async () => {
    mockPlaygroundServices({ loadError: new Error('registry blew up') });
    await mountWithCleanup(Playground, { props: {} });
    expect(notifications).toEqual([
        ['Failed to load tools: registry blew up', 'danger'],
    ]);
    expect('.o_muk_mcp_list').toHaveText(/No matching tools/);
    expect('.o_muk_mcp_detail').toHaveText(/Select a tool from the list on the left/);
});

test('searching drops non-matching tools and empty groups', async () => {
    mockPlaygroundServices();
    await mountWithCleanup(Playground, { props: {} });
    await click('.o_muk_mcp_list input[type="search"]');
    await edit('CREATE');
    await animationFrame();
    expect(
        queryAll('.o_muk_mcp_group_header .badge').map((b) => b.textContent.trim()),
    ).toEqual(['Write']);
    expect(queryAllTexts('.o_muk_mcp_tool .fw-bold')).toEqual(['res_partner_create']);
    await click('.o_muk_mcp_list input[type="search"]');
    await edit('Read one partner');
    await animationFrame();
    expect(queryAllTexts('.o_muk_mcp_tool .fw-bold')).toEqual(['res_partner_read']);
    await click('.o_muk_mcp_list input[type="search"]');
    await edit('nothing');
    await animationFrame();
    expect('.o_muk_mcp_tool').toHaveCount(0);
    expect('.o_muk_mcp_list').toHaveText(/No matching tools/);
});

test('selecting a tool persists it and reseeds the argument form', async () => {
    mockPlaygroundServices();
    await mountWithCleanup(Playground, { props: {} });
    await click(queryAll('.o_muk_mcp_tool')[2]);
    await animationFrame();
    expect('.o_muk_mcp_detail h4').toHaveText('res_partner_create');
    expect(localStorage.getItem(LAST_TOOL_KEY)).toBe('res_partner_create');
    expect(queryAllTexts('.o_muk_mcp_detail .form-label .fw-bold')).toEqual(['name']);
});

// ----------------------------------------------------------
// Running a tool
// ----------------------------------------------------------

test('the run button stays disabled while no key is set', async () => {
    mockPlaygroundServices();
    await mountWithCleanup(Playground, { props: {} });
    expect(queryOne('.o_muk_mcp_detail .btn-primary').disabled).toBe(true);
    expect('.o_muk_mcp_detail').toHaveText(/Pick or generate an MCP key first/);
    expect('.o_muk_mcp_keybar .badge').toHaveText(/none/);
});

test('running a tool renders the response through the response panel', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'key-abcdefgh-ij');
    let params = null;
    mockPlaygroundServices();
    mockMcpEndpoint({
        'tools/call': (body) => {
            params = body.params;
            return jsonResponse({
                jsonrpc: '2.0',
                id: body.id,
                result: { content: [{ type: 'text', text: '{"count": 2}' }] },
            });
        },
    });
    await mountWithCleanup(Playground, { props: {} });
    await click('.o_muk_mcp_detail .btn-primary');
    await animationFrame();
    expect(params).toEqual({
        name: 'res_partner_search',
        arguments: { domain: [] },
    });
    expect('.o_muk_mcp_detail .alert-success strong').toHaveText('OK');
    expect(JSON.parse(queryOne('.o_muk_mcp_detail pre.mb-3').textContent)).toEqual({
        count: 2,
    });
    expect('.o_muk_mcp_detail .fw-bold.text-success').toHaveText('HTTP 200');
});

test('a failed handshake surfaces as an exception response', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'revoked');
    mockPlaygroundServices();
    mockMcpEndpoint({
        initialize: (body) =>
            jsonResponse(
                {
                    jsonrpc: '2.0',
                    id: body.id,
                    error: { code: -32001, message: 'Invalid MCP key' },
                },
                401,
            ),
    });
    await mountWithCleanup(Playground, { props: {} });
    await click('.o_muk_mcp_detail .btn-primary');
    await animationFrame();
    expect('.o_muk_mcp_detail .alert-secondary strong').toHaveText('Empty');
    expect(queryOne('.o_muk_mcp_detail .alert-secondary').textContent).toInclude(
        'Invalid MCP key',
    );
    expect('.o_muk_mcp_detail .fw-bold.text-muted').toHaveText('HTTP 0');
    expect(notifications).toEqual([]);
});

test('a tool-level error keeps the payload and flags the result', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'key-abcdefgh-ij');
    mockPlaygroundServices();
    mockMcpEndpoint({
        'tools/call': (body) =>
            jsonResponse({
                jsonrpc: '2.0',
                id: body.id,
                result: {
                    isError: true,
                    content: [{ type: 'text', text: 'AccessError: not allowed' }],
                },
            }),
    });
    await mountWithCleanup(Playground, { props: {} });
    await click('.o_muk_mcp_detail .btn-primary');
    await animationFrame();
    expect('.o_muk_mcp_detail .alert-warning strong').toHaveText('Tool Error');
    expect(queryOne('.o_muk_mcp_detail pre.mb-3').textContent).toBe(
        'AccessError: not allowed',
    );
});

// ----------------------------------------------------------
// Panels
// ----------------------------------------------------------

test('the panel rail switches to a registered panel and persists it', async () => {
    mockPlaygroundServices();
    await mountWithCleanup(Playground, { props: {} });
    expect('.o_muk_mcp_panel_tab.active').toHaveText(/Tools/);
    await click(panelTab('Prompts'));
    await animationFrame();
    expect('.o_muk_mcp_prompts').toHaveCount(1);
    expect('.o_muk_mcp_body .o_muk_mcp_list input[type="search"]').toHaveAttribute(
        'placeholder',
        'Search prompts…',
    );
    expect(localStorage.getItem(ACTIVE_PANEL_KEY)).toBe('prompts');
});

test('an unknown stored panel falls back to the tools panel', async () => {
    localStorage.setItem(ACTIVE_PANEL_KEY, 'panel-from-an-uninstalled-module');
    mockPlaygroundServices();
    await mountWithCleanup(Playground, { props: {} });
    expect('.o_muk_mcp_panel_tab.active').toHaveText(/Tools/);
    expect('.o_muk_mcp_detail h4').toHaveText('res_partner_search');
});

test('a stored panel id is restored on mount', async () => {
    localStorage.setItem(ACTIVE_PANEL_KEY, 'prompts');
    mockPlaygroundServices();
    await mountWithCleanup(Playground, { props: {} });
    expect('.o_muk_mcp_panel_tab.active').toHaveText(/Prompts/);
    expect('.o_muk_mcp_prompts').toHaveCount(1);
});

test('generating a key in the key bar unlocks the run button', async () => {
    let params = null;
    mockPlaygroundServices();
    mockMcpEndpoint({
        'tools/call': (body) => {
            params = body.params;
            return jsonResponse({
                jsonrpc: '2.0',
                id: body.id,
                result: { content: [{ type: 'text', text: 'ran' }] },
            });
        },
    });
    await mountWithCleanup(Playground, { props: {} });
    expect(queryOne('.o_muk_mcp_detail .btn-primary').disabled).toBe(true);
    await click('.o_muk_mcp_keybar .btn-primary');
    await animationFrame();
    expect('.o_muk_mcp_keybar .badge').toHaveText(/mcp_abcd/);
    expect(queryOne('.o_muk_mcp_detail .btn-primary').disabled).toBe(false);
    await click('.o_muk_mcp_detail .btn-primary');
    await animationFrame();
    expect(params.name).toBe('res_partner_search');
    expect('.o_muk_mcp_detail .alert-success strong').toHaveText('OK');
});
