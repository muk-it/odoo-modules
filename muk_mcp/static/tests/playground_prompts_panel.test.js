import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { click, edit, press, queryAll, queryAllTexts, queryOne } from '@odoo/hoot-dom';
import { advanceTime, animationFrame } from '@odoo/hoot-mock';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';

import { STORAGE_KEY } from '@muk_mcp/playground/mcp_client';
import { PromptsPanel } from '@muk_mcp/playground/prompts_panel';

describe.current.tags('muk_mcp');

defineMailModels();

const LAST_PROMPT_KEY = 'muk_mcp.playground.last_prompt';
const ARGS_PREFIX = 'muk_mcp.playground.prompt_args::';

const GREETING = {
    name: 'greeting',
    title: 'Greeting',
    description: 'Say hello to a partner',
    arguments: [
        { name: 'partner', description: 'Partner name', required: true },
        { name: 'tone', required: false },
    ],
};

const SUMMARY = {
    name: 'summary',
    title: 'Record summary',
    description: 'Summarise a record',
    arguments: [],
};

let notifications = [];

beforeEach(() => {
    notifications = [];
});

function mockPanelServices({ prompts = [GREETING, SUMMARY], loadError = null } = {}) {
    mockService('notification', {
        add(message, options) {
            notifications.push([String(message), options && options.type]);
        },
    });
    mockService('orm', {
        call(model, method) {
            if (model === 'muk_mcp.prompt' && method === 'get_playground_prompts') {
                return loadError ? Promise.reject(loadError) : Promise.resolve(prompts);
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

function argInputs() {
    return queryAll('.o_muk_mcp_detail input[type="text"]');
}

async function typeInto(element, value) {
    await click(element);
    await edit(value);
    await animationFrame();
}

// ----------------------------------------------------------
// Catalog
// ----------------------------------------------------------

test('renders the prompt catalog and selects the first prompt', async () => {
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    expect('.o_muk_mcp_tool').toHaveCount(2);
    expect(queryAllTexts('.o_muk_mcp_tool .fw-bold')).toEqual(['greeting', 'summary']);
    expect('.o_muk_mcp_tool.active .fw-bold').toHaveText('greeting');
    expect('.o_muk_mcp_detail h4').toHaveText('greeting');
    expect('.o_muk_mcp_detail').toHaveText(/Say hello to a partner/);
});

test('restores the last used prompt from localStorage', async () => {
    localStorage.setItem(LAST_PROMPT_KEY, 'summary');
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    expect('.o_muk_mcp_tool.active .fw-bold').toHaveText('summary');
    expect('.o_muk_mcp_detail').toHaveText(/This prompt takes no arguments/);
});

test('falls back to the first prompt when the stored one is gone', async () => {
    localStorage.setItem(LAST_PROMPT_KEY, 'deleted_prompt');
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    expect('.o_muk_mcp_tool.active .fw-bold').toHaveText('greeting');
});

test('notifies and renders an empty catalog when loading fails', async () => {
    mockPanelServices({ loadError: new Error('db down') });
    await mountWithCleanup(PromptsPanel, { props: {} });
    expect(notifications).toEqual([['Failed to load prompts: db down', 'danger']]);
    expect('.o_muk_mcp_tool').toHaveCount(0);
    expect('.o_muk_mcp_list').toHaveText(/No matching prompts/);
    expect('.o_muk_mcp_detail').toHaveText(/Select a prompt from the list on the left/);
});

test('filters the prompt list on name, title and description', async () => {
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    await typeInto('.o_muk_mcp_list input[type="search"]', 'GREET');
    expect(queryAllTexts('.o_muk_mcp_tool .fw-bold')).toEqual(['greeting']);
    await typeInto('.o_muk_mcp_list input[type="search"]', '  Record summary ');
    expect(queryAllTexts('.o_muk_mcp_tool .fw-bold')).toEqual(['summary']);
    await typeInto('.o_muk_mcp_list input[type="search"]', 'summarise');
    expect(queryAllTexts('.o_muk_mcp_tool .fw-bold')).toEqual(['summary']);
    await typeInto('.o_muk_mcp_list input[type="search"]', 'nothing-here');
    expect('.o_muk_mcp_tool').toHaveCount(0);
    expect('.o_muk_mcp_list').toHaveText(/No matching prompts/);
});

test('selecting a prompt persists it and swaps the detail pane', async () => {
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    await click(queryAll('.o_muk_mcp_tool')[1]);
    await animationFrame();
    expect('.o_muk_mcp_detail h4').toHaveText('summary');
    expect(localStorage.getItem(LAST_PROMPT_KEY)).toBe('summary');
});

// ----------------------------------------------------------
// Arguments
// ----------------------------------------------------------

test('renders one input per declared argument and persists edits', async () => {
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    expect(argInputs()).toHaveLength(2);
    await typeInto(argInputs()[0], 'Alice');
    expect(argInputs()[0].value).toBe('Alice');
    expect(JSON.parse(localStorage.getItem(ARGS_PREFIX + 'greeting'))).toEqual({
        partner: 'Alice',
        tone: '',
    });
});

test('restores persisted arguments for the selected prompt', async () => {
    localStorage.setItem(ARGS_PREFIX + 'greeting', JSON.stringify({ partner: 'Bob' }));
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    expect(argInputs()[0].value).toBe('Bob');
});

test('ignores corrupted persisted arguments and seeds blanks', async () => {
    localStorage.setItem(ARGS_PREFIX + 'greeting', 'not-json');
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    expect(argInputs()[0].value).toBe('');
    expect(argInputs()[1].value).toBe('');
});

test('reset args clears every argument of the active prompt', async () => {
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    await typeInto(argInputs()[0], 'Alice');
    await click('.o_muk_mcp_detail .btn-outline-secondary');
    await animationFrame();
    expect(argInputs()[0].value).toBe('');
    expect(JSON.parse(localStorage.getItem(ARGS_PREFIX + 'greeting'))).toEqual({
        partner: '',
        tone: '',
    });
});

// ----------------------------------------------------------
// Completion
// ----------------------------------------------------------

test('debounced completion fills the datalist of the edited argument', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'key-abcdefgh-ij');
    let completeCalls = 0;
    let lastArgument = null;
    mockPanelServices();
    mockMcpEndpoint({
        'completion/complete': (body) => {
            completeCalls += 1;
            lastArgument = body.params.argument;
            return jsonResponse({
                jsonrpc: '2.0',
                id: body.id,
                result: { completion: { values: ['Alice', 'Alicia'] } },
            });
        },
    });
    await mountWithCleanup(PromptsPanel, { props: {} });
    await typeInto(argInputs()[0], 'Ali');
    expect('#mcp-prompt-arg-partner option').toHaveCount(0);
    await advanceTime(300);
    await animationFrame();
    expect(completeCalls).toBe(1);
    expect(lastArgument).toEqual({ name: 'partner', value: 'Ali' });
    expect(queryAll('#mcp-prompt-arg-partner option').map((o) => o.value)).toEqual([
        'Alice',
        'Alicia',
    ]);
});

test('successive keystrokes collapse into a single completion request', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'key-abcdefgh-ij');
    let completeCalls = 0;
    mockPanelServices();
    mockMcpEndpoint({
        'completion/complete': (body) => {
            completeCalls += 1;
            return jsonResponse({
                jsonrpc: '2.0',
                id: body.id,
                result: { completion: { values: [] } },
            });
        },
    });
    await mountWithCleanup(PromptsPanel, { props: {} });
    await typeInto(argInputs()[0], 'A');
    await advanceTime(50);
    await typeInto(argInputs()[0], 'Al');
    await advanceTime(300);
    await animationFrame();
    expect(completeCalls).toBe(1);
});

test('no completion request is issued without a key', async () => {
    let completeCalls = 0;
    mockPanelServices();
    mockMcpEndpoint({
        'completion/complete': (body) => {
            completeCalls += 1;
            return jsonResponse({ jsonrpc: '2.0', id: body.id, result: {} });
        },
    });
    await mountWithCleanup(PromptsPanel, { props: {} });
    await typeInto(argInputs()[0], 'Ali');
    await advanceTime(300);
    await animationFrame();
    expect(completeCalls).toBe(0);
});

// ----------------------------------------------------------
// prompts/get
// ----------------------------------------------------------

test('running a prompt sends pruned arguments and renders the messages', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'key-abcdefgh-ij');
    let params = null;
    mockPanelServices();
    mockMcpEndpoint({
        'prompts/get': (body) => {
            params = body.params;
            return jsonResponse({
                jsonrpc: '2.0',
                id: body.id,
                result: {
                    description: 'Rendered greeting',
                    messages: [
                        {
                            role: 'user',
                            content: { type: 'text', text: 'Hello Alice' },
                        },
                        {
                            role: 'assistant',
                            content: { type: 'resource', uri: 'odoo://partner/1' },
                        },
                    ],
                },
            });
        },
    });
    await mountWithCleanup(PromptsPanel, { props: {} });
    await typeInto(argInputs()[0], 'Alice');
    await click('.o_muk_mcp_detail .btn-primary');
    await animationFrame();
    expect(params).toEqual({ name: 'greeting', arguments: { partner: 'Alice' } });
    expect(
        queryAll('.o_muk_mcp_detail .badge').map((b) => b.textContent.trim()),
    ).toEqual(['user', 'assistant']);
    expect(queryAll('.o_muk_mcp_detail pre')[0]).toHaveText('Hello Alice');
    expect(queryAll('.o_muk_mcp_detail pre')[1].textContent).toInclude(
        '"uri": "odoo://partner/1"',
    );
    expect('.o_muk_mcp_detail .fw-bold.text-success').toHaveText('HTTP 200');
    expect(queryOne('.o_muk_mcp_detail details pre').textContent).toInclude(
        '"description": "Rendered greeting"',
    );
});

test('selecting another prompt clears the previous response', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'key-abcdefgh-ij');
    mockPanelServices();
    mockMcpEndpoint({
        'prompts/get': (body) =>
            jsonResponse({
                jsonrpc: '2.0',
                id: body.id,
                result: {
                    messages: [{ role: 'user', content: { type: 'text', text: 'hi' } }],
                },
            }),
    });
    await mountWithCleanup(PromptsPanel, { props: {} });
    await click('.o_muk_mcp_detail .btn-primary');
    await animationFrame();
    expect('.o_muk_mcp_detail details').toHaveCount(1);
    await click(queryAll('.o_muk_mcp_tool')[1]);
    await animationFrame();
    expect('.o_muk_mcp_detail details').toHaveCount(0);
});

test('a JSON-RPC error envelope is surfaced as an alert', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'key-abcdefgh-ij');
    mockPanelServices();
    mockMcpEndpoint({
        'prompts/get': (body) =>
            jsonResponse(
                {
                    jsonrpc: '2.0',
                    id: body.id,
                    error: { code: -32602, message: 'Missing required argument' },
                },
                400,
            ),
    });
    await mountWithCleanup(PromptsPanel, { props: {} });
    await click('.o_muk_mcp_detail .btn-primary');
    await animationFrame();
    expect('.o_muk_mcp_detail .alert-danger').toHaveText(
        'JSON-RPC error -32602: Missing required argument',
    );
    expect('.o_muk_mcp_detail .fw-bold.text-warning').toHaveText('HTTP 400');
    expect(notifications).toEqual([]);
});

test('a non-JSON server failure falls back to the raw body', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'key-abcdefgh-ij');
    mockPanelServices();
    mockMcpEndpoint({
        'prompts/get': () => new Response('502 Bad Gateway', { status: 502 }),
    });
    await mountWithCleanup(PromptsPanel, { props: {} });
    await click('.o_muk_mcp_detail .btn-primary');
    await animationFrame();
    expect('.o_muk_mcp_detail .fw-bold.text-danger').toHaveText('HTTP 502');
    expect(queryOne('.o_muk_mcp_detail details pre').textContent).toBe(
        '502 Bad Gateway',
    );
    expect('.o_muk_mcp_detail').toHaveText(/No messages returned/);
});

test('a failed handshake is reported through a notification', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'revoked-key');
    mockPanelServices();
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
    await mountWithCleanup(PromptsPanel, { props: {} });
    await click('.o_muk_mcp_detail .btn-primary');
    await animationFrame();
    expect(notifications).toEqual([['prompts/get failed: Invalid MCP key', 'danger']]);
    expect('.o_muk_mcp_detail details').toHaveCount(0);
});

test('ctrl+enter runs the selected prompt', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'key-abcdefgh-ij');
    let getCalls = 0;
    mockPanelServices();
    mockMcpEndpoint({
        'prompts/get': (body) => {
            getCalls += 1;
            return jsonResponse({
                jsonrpc: '2.0',
                id: body.id,
                result: {
                    messages: [{ role: 'user', content: { type: 'text', text: 'hi' } }],
                },
            });
        },
    });
    await mountWithCleanup(PromptsPanel, { props: {} });
    await click(argInputs()[0]);
    await press(['ctrl', 'Enter']);
    await animationFrame();
    expect(getCalls).toBe(1);
    expect('.o_muk_mcp_detail pre').toHaveCount(2);
});

test('the run button is disabled and warns while no key is set', async () => {
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    expect(queryOne('.o_muk_mcp_detail .btn-primary').disabled).toBe(true);
    expect('.o_muk_mcp_detail').toHaveText(/Pick or generate an MCP key first/);
});

// ----------------------------------------------------------
// Copy actions
// ----------------------------------------------------------

test('copy curl writes an authenticated prompts/get command', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'secret-key');
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    await typeInto(argInputs()[0], 'Alice');
    await click(queryAll('.o_muk_mcp_detail .btn-secondary')[0]);
    await animationFrame();
    const copied = await navigator.clipboard.readText();
    expect(copied).toInclude("-H 'Authorization: Bearer secret-key'");
    expect(copied).toInclude(
        '"method":"prompts/get","params":{"name":"greeting","arguments":{"partner":"Alice"}}',
    );
    expect(notifications).toEqual([['curl copied', 'success']]);
});

test('copy JSON-RPC writes the indented payload without the key', async () => {
    mockPanelServices();
    await mountWithCleanup(PromptsPanel, { props: {} });
    await click(queryAll('.o_muk_mcp_detail .btn-secondary')[1]);
    await animationFrame();
    expect(JSON.parse(await navigator.clipboard.readText())).toEqual({
        jsonrpc: '2.0',
        id: 1,
        method: 'prompts/get',
        params: { name: 'greeting', arguments: {} },
    });
    expect(notifications).toEqual([['JSON-RPC payload copied', 'success']]);
});
