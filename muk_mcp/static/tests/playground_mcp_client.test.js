import { afterEach, beforeEach, describe, expect, test } from '@odoo/hoot';
import { mockFetch } from '@odoo/hoot-mock';

import { MCPClient, STORAGE_KEY } from '@muk_mcp/playground/mcp_client';

describe.current.tags('muk_mcp');

beforeEach(() => {
    sessionStorage.removeItem(STORAGE_KEY);
});

afterEach(() => {
    sessionStorage.removeItem(STORAGE_KEY);
});

test('constructor initialises empty state', () => {
    const client = new MCPClient();
    expect(client.sessionId).toBe(null);
    expect(client.initialized).toBe(false);
    expect(client.key).toBe('');
});

test('setting the key stores it in sessionStorage', () => {
    const client = new MCPClient();
    client.key = 'secret';
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe('secret');
    expect(client.key).toBe('secret');
});

test('clearing the key removes it and resets session state', () => {
    const client = new MCPClient();
    client.key = 'secret';
    client.sessionId = 'abc';
    client.initialized = true;
    client.key = '';
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe(null);
    expect(client.sessionId).toBe(null);
    expect(client.initialized).toBe(false);
});

test('setting a new key resets the session state', () => {
    const client = new MCPClient();
    client.key = 'first';
    client.sessionId = 'abc';
    client.initialized = true;
    client.key = 'second';
    expect(client.sessionId).toBe(null);
    expect(client.initialized).toBe(false);
});

test('_headers includes Authorization when a key is set', () => {
    const client = new MCPClient();
    client.key = 'secret';
    const headers = client._headers();
    expect(headers['Authorization']).toBe('Bearer secret');
    expect(headers['Content-Type']).toBe('application/json');
});

test('_headers omits Authorization when no key is set', () => {
    const client = new MCPClient();
    const headers = client._headers();
    expect(headers['Authorization']).toBe(undefined);
});

test('_headers includes Mcp-Session-Id once the session is known', () => {
    const client = new MCPClient();
    client.sessionId = 'sess-1';
    expect(client._headers()['Mcp-Session-Id']).toBe('sess-1');
});

test('_post captures session id from the response headers', async () => {
    mockFetch(
        () =>
            new Response(JSON.stringify({ jsonrpc: '2.0', id: 1, result: {} }), {
                status: 200,
                headers: { 'Mcp-Session-Id': 'sess-abc' },
            }),
    );
    const client = new MCPClient();
    const res = await client._post({ jsonrpc: '2.0', id: 1, method: 'ping' });
    expect(res.status).toBe(200);
    expect(client.sessionId).toBe('sess-abc');
});

test('callTool returns the tool result on success', async () => {
    let postCount = 0;
    mockFetch(async (input, init) => {
        postCount += 1;
        const body = JSON.parse(init.body);
        if (body.method === 'initialize') {
            return new Response(
                JSON.stringify({ jsonrpc: '2.0', id: body.id, result: {} }),
                { status: 200, headers: { 'Mcp-Session-Id': 'sess-1' } },
            );
        }
        if (body.method === 'notifications/initialized') {
            return new Response('', { status: 202 });
        }
        if (body.method === 'tools/call') {
            return new Response(
                JSON.stringify({
                    jsonrpc: '2.0',
                    id: body.id,
                    result: { content: [{ type: 'text', text: 'ok' }] },
                }),
                { status: 200 },
            );
        }
        return new Response('', { status: 400 });
    });
    const client = new MCPClient();
    const result = await client.callTool('whoami', {});
    expect(result.status).toBe(200);
    expect(result.body.result.content[0].text).toBe('ok');
    expect(postCount).toBe(3);
    expect(client.initialized).toBe(true);
});

test('callTool retries once on HTTP 404 (session lost)', async () => {
    let tries = 0;
    mockFetch(async (input, init) => {
        const body = JSON.parse(init.body);
        if (body.method === 'initialize') {
            return new Response(
                JSON.stringify({ jsonrpc: '2.0', id: body.id, result: {} }),
                { status: 200, headers: { 'Mcp-Session-Id': 'sess-fresh' } },
            );
        }
        if (body.method === 'notifications/initialized') {
            return new Response('', { status: 202 });
        }
        if (body.method === 'tools/call') {
            tries += 1;
            if (tries === 1) {
                return new Response('', { status: 404 });
            }
            return new Response(
                JSON.stringify({
                    jsonrpc: '2.0',
                    id: body.id,
                    result: { content: [{ type: 'text', text: 'retried' }] },
                }),
                { status: 200 },
            );
        }
        return new Response('', { status: 400 });
    });
    const client = new MCPClient();
    client.sessionId = 'stale';
    client.initialized = true;
    const result = await client.callTool('whoami', {});
    expect(result.status).toBe(200);
    expect(tries).toBe(2);
});

test('getPrompts initialises once and returns the raw prompts/list response', async () => {
    const methods = [];
    mockFetch(async (input, init) => {
        const body = JSON.parse(init.body);
        methods.push(body.method);
        if (body.method === 'initialize') {
            return new Response(
                JSON.stringify({ jsonrpc: '2.0', id: body.id, result: {} }),
                { status: 200, headers: { 'Mcp-Session-Id': 'sess-p' } },
            );
        }
        if (body.method === 'notifications/initialized') {
            return new Response('', { status: 202 });
        }
        if (body.method === 'prompts/list') {
            return new Response(
                JSON.stringify({
                    jsonrpc: '2.0',
                    id: body.id,
                    result: { prompts: [{ name: 'greeting' }] },
                }),
                { status: 200 },
            );
        }
        return new Response('', { status: 400 });
    });
    const client = new MCPClient();
    const first = await client.getPrompts();
    const second = await client.getPrompts();
    expect(first.body.result.prompts[0].name).toBe('greeting');
    expect(second.status).toBe(200);
    expect(methods).toEqual([
        'initialize',
        'notifications/initialized',
        'prompts/list',
        'prompts/list',
    ]);
});

test('getPrompt retries once after a stale-session 404', async () => {
    let tries = 0;
    mockFetch(async (input, init) => {
        const body = JSON.parse(init.body);
        if (body.method === 'initialize') {
            return new Response(
                JSON.stringify({ jsonrpc: '2.0', id: body.id, result: {} }),
                { status: 200, headers: { 'Mcp-Session-Id': 'sess-fresh' } },
            );
        }
        if (body.method === 'notifications/initialized') {
            return new Response('', { status: 202 });
        }
        if (body.method === 'prompts/get') {
            tries += 1;
            if (tries === 1) {
                return new Response('', { status: 404 });
            }
            return new Response(
                JSON.stringify({
                    jsonrpc: '2.0',
                    id: body.id,
                    result: { messages: [] },
                }),
                { status: 200 },
            );
        }
        return new Response('', { status: 400 });
    });
    const client = new MCPClient();
    client.sessionId = 'stale';
    client.initialized = true;
    const result = await client.getPrompt('greeting', { partner: 'Alice' });
    expect(result.status).toBe(200);
    expect(tries).toBe(2);
    expect(client.sessionId).toBe('sess-fresh');
});

test('complete returns the suggested values and [] when none are sent', async () => {
    let completion = { values: ['Alice'] };
    mockFetch(async (input, init) => {
        const body = JSON.parse(init.body);
        if (body.method === 'initialize') {
            return new Response(
                JSON.stringify({ jsonrpc: '2.0', id: body.id, result: {} }),
                { status: 200 },
            );
        }
        if (body.method === 'notifications/initialized') {
            return new Response('', { status: 202 });
        }
        if (body.method === 'completion/complete') {
            return new Response(
                JSON.stringify({ jsonrpc: '2.0', id: body.id, result: { completion } }),
                { status: 200 },
            );
        }
        return new Response('', { status: 400 });
    });
    const client = new MCPClient();
    expect(
        await client.complete(
            { type: 'ref/prompt', name: 'greeting' },
            { name: 'partner' },
        ),
    ).toEqual(['Alice']);
    completion = undefined;
    expect(
        await client.complete(
            { type: 'ref/prompt', name: 'greeting' },
            { name: 'partner' },
        ),
    ).toEqual([]);
});

test('complete retries once after a stale-session 404', async () => {
    let tries = 0;
    mockFetch(async (input, init) => {
        const body = JSON.parse(init.body);
        if (body.method === 'initialize') {
            return new Response(
                JSON.stringify({ jsonrpc: '2.0', id: body.id, result: {} }),
                { status: 200 },
            );
        }
        if (body.method === 'notifications/initialized') {
            return new Response('', { status: 202 });
        }
        if (body.method === 'completion/complete') {
            tries += 1;
            if (tries === 1) {
                return new Response('', { status: 404 });
            }
            return new Response(
                JSON.stringify({
                    jsonrpc: '2.0',
                    id: body.id,
                    result: { completion: { values: ['Alicia'] } },
                }),
                { status: 200 },
            );
        }
        return new Response('', { status: 400 });
    });
    const client = new MCPClient();
    client.sessionId = 'stale';
    client.initialized = true;
    expect(
        await client.complete(
            { type: 'ref/prompt', name: 'greeting' },
            { name: 'partner' },
        ),
    ).toEqual(['Alicia']);
    expect(tries).toBe(2);
});

test('reset deletes the session server-side and forgets it locally', async () => {
    const calls = [];
    mockFetch(async (input, init) => {
        calls.push([init.method, init.headers.get('Mcp-Session-Id')]);
        return new Response('', { status: 204 });
    });
    const client = new MCPClient();
    client.sessionId = 'sess-to-drop';
    client.initialized = true;
    await client.reset();
    expect(calls).toEqual([['DELETE', 'sess-to-drop']]);
    expect(client.sessionId).toBe(null);
    expect(client.initialized).toBe(false);
});

test('reset without a session does not call the endpoint', async () => {
    let calls = 0;
    mockFetch(async () => {
        calls += 1;
        return new Response('', { status: 204 });
    });
    const client = new MCPClient();
    await client.reset();
    expect(calls).toBe(0);
});

test('reset swallows a transport failure', async () => {
    mockFetch(async () => {
        throw new Error('offline');
    });
    const client = new MCPClient();
    client.sessionId = 'sess-x';
    client.initialized = true;
    await client.reset();
    expect(client.sessionId).toBe(null);
    expect(client.initialized).toBe(false);
});

test('callTool does not retry a second 404 (bounded recursion)', async () => {
    let tries = 0;
    mockFetch(async (input, init) => {
        const body = JSON.parse(init.body);
        if (body.method === 'initialize') {
            return new Response(
                JSON.stringify({ jsonrpc: '2.0', id: body.id, result: {} }),
                { status: 200, headers: { 'Mcp-Session-Id': 'sess-x' } },
            );
        }
        if (body.method === 'notifications/initialized') {
            return new Response('', { status: 202 });
        }
        if (body.method === 'tools/call') {
            tries += 1;
            return new Response('', { status: 404 });
        }
        return new Response('', { status: 400 });
    });
    const client = new MCPClient();
    const result = await client.callTool('whoami', {});
    expect(result.status).toBe(404);
    expect(tries).toBe(2);
});
