import { beforeEach, describe, expect, test } from '@odoo/hoot';
import {
    press,
    queryAll,
    queryAllTexts,
    queryAllValues,
    queryFirst,
    queryOne,
} from '@odoo/hoot-dom';
import { advanceTime, animationFrame } from '@odoo/hoot-mock';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { contains, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';

import { Playground } from '@muk_mcp/playground/playground/playground';

describe.current.tags('muk_mcp');

defineMailModels();

const KEY_STORAGE = 'muk_mcp.playground.key';

const TOOLS = [
    {
        name: 'res_partner_search',
        category: 'read',
        kind: 'db',
        description: 'Search partners',
        inputSchema: {
            type: 'object',
            required: ['model', 'domain'],
            properties: {
                model: { type: 'string' },
                domain: { type: 'array' },
                limit: { type: 'integer', default: 80 },
            },
        },
    },
    {
        name: 'res_partner_read',
        category: 'read',
        kind: 'db',
        description: 'Read one partner',
        inputSchema: { type: 'object', properties: {} },
    },
    {
        name: 'res_partner_create',
        category: 'write',
        kind: 'method',
        description: 'Create a partner',
        inputSchema: { type: 'object', properties: { name: { type: 'string' } } },
    },
];

const PROMPTS = [
    {
        name: 'greeting',
        title: 'Greeting',
        description: 'Say hello to a partner',
        arguments: [
            { name: 'partner', description: 'Partner name', required: true },
            { name: 'tone' },
        ],
    },
    { name: 'summary', title: 'Record summary', description: 'Summarise a record' },
];

let requests;
let reply;

beforeEach(() => {
    requests = [];
    reply = () => [
        200,
        { result: { content: [{ type: 'text', text: '{"count": 2}' }] } },
    ];
    onRpc('get_playground_tools', () => TOOLS);
    onRpc('get_playground_prompts', () => PROMPTS);
    onRpc('generate_playground_key', ({ kwargs }) => ({
        name: kwargs.name,
        key_prefix: 'mcp_abcd',
        plaintext: 'mcp_abcd_secret',
    }));
    onRpc('/api/mcp', async (request) => {
        const body = await request.json();
        requests.push({ body, headers: request.headers });
        const [status, payload] = reply(body);
        return new Response(
            typeof payload === 'string'
                ? payload
                : JSON.stringify({ jsonrpc: '2.0', id: body.id, ...payload }),
            { status },
        );
    });
});

function badges(selector) {
    return queryAll(selector).map((badge) => badge.textContent);
}

async function mountPlayground({ key, panel } = {}) {
    if (key) {
        sessionStorage.setItem(KEY_STORAGE, key);
    }
    if (panel) {
        localStorage.setItem('muk_mcp.playground.active_panel', panel);
    }
    await mountWithCleanup(Playground);
}

// ----------------------------------------------------------
// Tool catalog
// ----------------------------------------------------------

test('lists the tools by category and opens the first one', async () => {
    await mountPlayground();
    expect(badges('.mk_mcp_group_header .badge')).toEqual(['read', 'write']);
    expect(queryAllTexts('.mk_mcp_entry .fw-bold')).toEqual([
        'res_partner_read',
        'res_partner_search',
        'res_partner_create',
    ]);
    expect('.mk_mcp_entry.active .fw-bold').toHaveText('res_partner_search');
    expect('.mk_mcp_detail h4').toHaveText('res_partner_search');
    expect('.mk_mcp_detail .badge.text-bg-info').toHaveText('read');
    expect(queryAllValues('.mk_mcp_detail .form-control')).toEqual(['', '[]', 80]);
    expect('.mk_mcp_list input[type=search]').toBeFocused();
});

test('restores the last tool and ignores an unknown stored panel', async () => {
    localStorage.setItem('muk_mcp.playground.last_tool', 'res_partner_create');
    await mountPlayground({ panel: 'panel-of-an-uninstalled-module' });
    expect('.mk_mcp_panel_tab.active').toHaveAttribute('title', 'Tools');
    expect('.mk_mcp_detail h4').toHaveText('res_partner_create');
});

test('searching matches name and description and drops empty groups', async () => {
    await mountPlayground();
    await contains('.mk_mcp_list input[type=search]').edit('CREATE');
    expect(badges('.mk_mcp_group_header .badge')).toEqual(['write']);
    expect(queryAllTexts('.mk_mcp_entry .fw-bold')).toEqual(['res_partner_create']);
    await contains('.mk_mcp_list input[type=search]').edit('read one');
    expect(queryAllTexts('.mk_mcp_entry .fw-bold')).toEqual(['res_partner_read']);
    await contains('.mk_mcp_list input[type=search]').edit('nothing');
    expect('.mk_mcp_entry').toHaveCount(0);
    expect('.mk_mcp_list').toHaveText(/No matching tools/);
});

test('selecting a tool remembers it and shows its form', async () => {
    await mountPlayground();
    await contains('.mk_mcp_entry:contains(res_partner_create)').click();
    expect('.mk_mcp_detail h4').toHaveText('res_partner_create');
    expect('.mk_mcp_detail .badge.text-bg-warning').toHaveText('write');
    expect(queryAllTexts('.mk_mcp_detail .form-label .fw-bold')).toEqual(['name']);
    expect(localStorage.getItem('muk_mcp.playground.last_tool')).toBe(
        'res_partner_create',
    );
});

// ----------------------------------------------------------
// Key bar
// ----------------------------------------------------------

test('generating a key unlocks the run and names the key', async () => {
    const generated = [];
    onRpc('generate_playground_key', ({ kwargs }) => {
        generated.push(kwargs);
    });
    await mountPlayground();
    expect('.mk_mcp_keybar .badge').toHaveText('none');
    expect('.mk_mcp_detail .btn-primary').not.toBeEnabled();
    expect('.mk_mcp_detail').toHaveText(/Pick or generate an MCP key first/);
    await contains('.mk_mcp_keybar button:contains(Generate new)').click();
    expect(generated[0].scope).toBe('write');
    expect(generated[0].name).toMatch(/^Playground \d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/);
    expect('.mk_mcp_keybar .badge').toHaveText('mcp_abcd...');
    expect(sessionStorage.getItem(KEY_STORAGE)).toBe('mcp_abcd_secret');
    expect('.o_notification_content').toHaveText(
        `Generated key '${generated[0].name}' (prefix mcp_abcd). Plaintext is now loaded for this tab only.`,
    );
    expect('.mk_mcp_detail .btn-primary').toBeEnabled();
    await contains('.mk_mcp_keybar input[type=text]').edit('CI key');
    await contains('.mk_mcp_keybar select').select('read');
    await contains('.mk_mcp_keybar button:contains(Generate new)').click();
    expect([generated[1].name, generated[1].scope]).toEqual(['CI key', 'read']);
});

test('a pasted key is trimmed and stored, cancel discards it, clear removes it', async () => {
    await mountPlayground();
    await contains('.mk_mcp_keybar button:contains(Use existing)').click();
    expect('.mk_mcp_keybar .btn-primary:contains(Use)').not.toBeEnabled();
    await contains('.mk_mcp_keybar input[type=password]').edit('typed-then-cancelled');
    await contains('.mk_mcp_keybar button:contains(Cancel)').click();
    expect('.mk_mcp_keybar input[type=password]').toHaveCount(0);
    await contains('.mk_mcp_keybar button:contains(Use existing)').click();
    expect('.mk_mcp_keybar input[type=password]').toHaveValue('');
    await contains('.mk_mcp_keybar input[type=password]').edit('  pasted-key-123  ');
    await contains('.mk_mcp_keybar .btn-primary:contains(Use)').click();
    expect('.mk_mcp_keybar .badge').toHaveText('pasted-k...');
    expect(sessionStorage.getItem(KEY_STORAGE)).toBe('pasted-key-123');
    await contains('.mk_mcp_keybar .btn-outline-danger').click();
    expect('.mk_mcp_keybar .badge').toHaveText('none');
    expect(sessionStorage.getItem(KEY_STORAGE)).toBe(null);
});

// ----------------------------------------------------------
// Running a tool
// ----------------------------------------------------------

test('running a tool posts the pruned arguments with the key and version', async () => {
    await mountPlayground({ key: 'live-key' });
    await contains('.mk_mcp_detail input[type=text]').edit('res.partner');
    await contains('.mk_mcp_detail button:contains(Try it)').click();
    const [{ body, headers }] = requests;
    expect(body.method).toBe('tools/call');
    expect(body.params).toEqual({
        name: 'res_partner_search',
        arguments: { model: 'res.partner', domain: [], limit: 80 },
    });
    expect(headers.get('Authorization')).toBe('Bearer live-key');
    expect(headers.get('MCP-Protocol-Version')).toBe('2025-11-25');
    expect('.mk_mcp_detail .alert-success').toHaveText(/OK/);
    expect(JSON.parse(queryFirst('.mk_mcp_response pre').textContent)).toEqual({
        count: 2,
    });
});

test('the outcome follows the HTTP status and the JSON-RPC body', async () => {
    const cases = [
        [200, { result: { content: [] } }, 'text-success', 'alert-success'],
        [
            200,
            { result: { isError: true, content: [] } },
            'text-success',
            'alert-warning',
        ],
        [
            400,
            { error: { code: -32602, message: 'x' } },
            'text-warning',
            'alert-danger',
        ],
        [502, 'Bad Gateway', 'text-danger', 'alert-secondary'],
    ];
    await mountPlayground({ key: 'live-key' });
    for (const [status, payload, statusClass, alertClass] of cases) {
        reply = () => [status, payload];
        await contains('.mk_mcp_detail button:contains(Try it)').click();
        expect(`.mk_mcp_detail .fw-bold.${statusClass}`).toHaveText(`HTTP ${status}`);
        expect(`.mk_mcp_response .alert.${alertClass}`).toHaveCount(1);
    }
    expect(queryOne('.mk_mcp_response details pre').textContent).toBe('Bad Gateway');
});

test('ctrl+enter runs the tool only while a key is set', async () => {
    await mountPlayground({ key: 'live-key' });
    await contains('.mk_mcp_detail input[type=text]').click();
    await press(['ctrl', 'Enter']);
    await animationFrame();
    expect(requests).toHaveLength(1);
    await contains('.mk_mcp_keybar .btn-outline-danger').click();
    await contains('.mk_mcp_detail input[type=text]').click();
    await press(['ctrl', 'Enter']);
    await animationFrame();
    expect(requests).toHaveLength(1);
});

test('the schema tab shows the input schema and reset restores the defaults', async () => {
    await mountPlayground();
    await contains('.mk_mcp_detail input[type=number]').edit('5');
    await contains('.mk_mcp_detail .nav-link:contains(Schema)').click();
    expect(JSON.parse(queryOne('.mk_mcp_detail pre').textContent)).toEqual(
        TOOLS[0].inputSchema,
    );
    await contains('.mk_mcp_detail .nav-link:contains(Form)').click();
    expect('.mk_mcp_detail input[type=number]').toHaveValue(5);
    await contains('.mk_mcp_detail button:contains(Reset args)').click();
    expect('.mk_mcp_detail input[type=number]').toHaveValue(80);
});

test('the copy buttons put the request on the clipboard as curl and JSON-RPC', async () => {
    await mountPlayground();
    await contains('.mk_mcp_detail .o_clipboard_button:contains(curl)').click();
    const curl = await navigator.clipboard.readText();
    expect(curl).toInclude(`curl -X POST '${window.location.origin}/api/mcp'`);
    expect(curl).toInclude("-H 'Authorization: Bearer <YOUR_MCP_KEY>'");
    expect(curl).toInclude("-H 'MCP-Protocol-Version: 2025-11-25'");
    expect(curl).toInclude(
        '"method":"tools/call","params":{"name":"res_partner_search","arguments":{"domain":[],"limit":80}}',
    );
    await contains('.mk_mcp_detail .o_clipboard_button:contains(JSON-RPC)').click();
    expect(JSON.parse(await navigator.clipboard.readText())).toEqual({
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/call',
        params: { name: 'res_partner_search', arguments: { domain: [], limit: 80 } },
    });
});

// ----------------------------------------------------------
// Prompts panel
// ----------------------------------------------------------

test('the panel rail opens the prompts and remembers the panel', async () => {
    await mountPlayground();
    await contains('.mk_mcp_panel_tab[title=Prompts]').click();
    expect('.mk_mcp_prompts').toHaveCount(1);
    expect('.mk_mcp_detail h4').toHaveText('greeting');
    expect(localStorage.getItem('muk_mcp.playground.active_panel')).toBe('prompts');
});

test('the prompt list restores the last prompt and filters', async () => {
    localStorage.setItem('muk_mcp.playground.last_prompt', 'summary');
    await mountPlayground({ panel: 'prompts' });
    expect('.mk_mcp_entry.active .fw-bold').toHaveText('summary');
    expect('.mk_mcp_detail').toHaveText(/This prompt takes no arguments/);
    for (const [term, names] of [
        ['GREET', ['greeting']],
        ['record summary', ['summary']],
        ['say hello', ['greeting']],
    ]) {
        await contains('.mk_mcp_list input[type=search]').edit(term);
        expect(queryAllTexts('.mk_mcp_entry .fw-bold')).toEqual(names);
    }
    await contains('.mk_mcp_list input[type=search]').edit('nothing');
    expect('.mk_mcp_list').toHaveText(/No matching prompts/);
});

test('prompt arguments are kept per prompt until reset', async () => {
    await mountPlayground({ panel: 'prompts' });
    await contains('.mk_mcp_detail input[type=text]').edit('Alice');
    await contains('.mk_mcp_entry:contains(summary)').click();
    await contains('.mk_mcp_entry:contains(greeting)').click();
    expect(queryAllValues('.mk_mcp_detail input[type=text]')).toEqual(['Alice', '']);
    await contains('.mk_mcp_detail button:contains(Reset args)').click();
    expect(queryAllValues('.mk_mcp_detail input[type=text]')).toEqual(['', '']);
    expect(localStorage.getItem('muk_mcp.playground.prompt_args::greeting')).toBe(null);
});

test('argument completion is debounced and needs a key', async () => {
    reply = ({ params }) => [
        200,
        {
            result: {
                completion: { values: [`${params.argument.value}ce`, 'Alicia'] },
            },
        },
    ];
    await mountPlayground({ key: 'live-key', panel: 'prompts' });
    await contains('.mk_mcp_detail input[type=text]').edit('A');
    await contains('.mk_mcp_detail input[type=text]').edit('Ali');
    await advanceTime(300);
    await animationFrame();
    expect(requests.map(({ body }) => body.params)).toEqual([
        {
            ref: { type: 'ref/prompt', name: 'greeting' },
            argument: { name: 'partner', value: 'Ali' },
        },
    ]);
    expect(queryAll('#mk_mcp_arg_partner option').map((o) => o.value)).toEqual([
        'Alice',
        'Alicia',
    ]);
    await contains('.mk_mcp_keybar .btn-outline-danger').click();
    await contains('.mk_mcp_detail input[type=text]').edit('Bob');
    await advanceTime(300);
    expect(requests).toHaveLength(1);
});

test('getting a prompt renders its messages', async () => {
    reply = () => [
        200,
        {
            result: {
                description: 'Rendered greeting',
                messages: [
                    { role: 'user', content: { type: 'text', text: 'Hello Alice' } },
                    {
                        role: 'assistant',
                        content: { type: 'resource', uri: 'odoo://p/1' },
                    },
                ],
            },
        },
    ];
    await mountPlayground({ key: 'live-key', panel: 'prompts' });
    await contains('.mk_mcp_detail input[type=text]').edit('Alice');
    await contains('.mk_mcp_detail button:contains(Get prompt)').click();
    expect(requests.at(-1).body.params).toEqual({
        name: 'greeting',
        arguments: { partner: 'Alice' },
    });
    expect('.mk_mcp_detail .fw-bold.text-success').toHaveText('HTTP 200');
    expect('.mk_mcp_response').toHaveText(/Rendered greeting/);
    expect(badges('.mk_mcp_response .badge')).toEqual(['user', 'assistant']);
    const [text, resource] = queryAll('.mk_mcp_response .mb-2 pre');
    expect(text).toHaveText('Hello Alice');
    expect(resource.textContent).toInclude('"uri": "odoo://p/1"');
    await contains('.mk_mcp_entry:contains(summary)').click();
    expect('.mk_mcp_response').toHaveCount(0);
});

test('a failed prompts/get shows the error or the raw body', async () => {
    await mountPlayground({ key: 'live-key', panel: 'prompts' });
    reply = () => [400, { error: { code: -32602, message: 'Missing argument' } }];
    await contains('.mk_mcp_detail input[type=text]').press(['ctrl', 'Enter']);
    expect('.mk_mcp_response .alert-danger').toHaveText(
        'JSON-RPC error -32602: Missing argument',
    );
    reply = () => [502, 'Bad Gateway'];
    await contains('.mk_mcp_detail button:contains(Get prompt)').click();
    expect('.mk_mcp_response').toHaveText(/No messages returned/);
    expect(queryOne('.mk_mcp_response details pre').textContent).toBe('Bad Gateway');
});

test('the prompt request is copied with its arguments', async () => {
    await mountPlayground({ key: 'live-key', panel: 'prompts' });
    await contains('.mk_mcp_detail input[type=text]').edit('Alice');
    await contains('.mk_mcp_detail .o_clipboard_button:contains(curl)').click();
    const curl = await navigator.clipboard.readText();
    expect(curl).toInclude("-H 'Authorization: Bearer live-key'");
    expect(curl).toInclude(
        '"method":"prompts/get","params":{"name":"greeting","arguments":{"partner":"Alice"}}',
    );
});
