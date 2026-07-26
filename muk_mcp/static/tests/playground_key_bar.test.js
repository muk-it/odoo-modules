import { beforeEach, describe, expect, test } from '@odoo/hoot';
import { click, edit, queryAll, select } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { mockService, mountWithCleanup } from '@web/../tests/web_test_helpers';

import { KeyBar } from '@muk_mcp/playground/key_bar';
import { MCPClient, STORAGE_KEY } from '@muk_mcp/playground/mcp_client';

describe.current.tags('muk_mcp');

defineMailModels();

let notifications = [];
let generateCalls = [];
let keyChanges = 0;

beforeEach(() => {
    notifications = [];
    generateCalls = [];
    keyChanges = 0;
    mockService('notification', {
        add(message, options) {
            notifications.push([String(message), options && options.type]);
        },
    });
});

function mockKeyOrm({ error = null } = {}) {
    mockService('orm', {
        call(model, method, args, kwargs) {
            if (model === 'muk_mcp.key' && method === 'generate_playground_key') {
                generateCalls.push(kwargs);
                if (error) {
                    return Promise.reject(error);
                }
                return Promise.resolve({
                    name: kwargs.name,
                    key_prefix: 'mcp_1234',
                    plaintext: 'mcp_1234_secret',
                });
            }
            return Promise.reject(new Error(`unexpected ${model}.${method}`));
        },
    });
}

async function mountKeyBar() {
    const client = new MCPClient();
    await mountWithCleanup(KeyBar, {
        props: {
            client,
            keyPrefix: client.key.slice(0, 8),
            onKeyChanged: () => {
                keyChanges += 1;
            },
        },
    });
    return client;
}

// ----------------------------------------------------------
// Pasting a key
// ----------------------------------------------------------

test('shows no key and hides the clear button while none is set', async () => {
    await mountKeyBar();
    expect('.o_muk_mcp_keybar .badge').toHaveText(/none/);
    expect('.o_muk_mcp_keybar .btn-outline-danger').toHaveCount(0);
    expect('.o_muk_mcp_keybar input[type="password"]').toHaveCount(0);
});

test('pasting a key stores it for the tab and notifies the parent', async () => {
    const client = await mountKeyBar();
    await click('.o_muk_mcp_keybar .btn-secondary');
    await animationFrame();
    await click('.o_muk_mcp_keybar input[type="password"]');
    await edit('  pasted-key  ');
    await click(queryAll('.o_muk_mcp_keybar .btn-primary')[1]);
    await animationFrame();
    expect(client.key).toBe('pasted-key');
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe('pasted-key');
    expect(keyChanges).toBe(1);
    expect(notifications).toEqual([['Key set for this tab', 'success']]);
    expect('.o_muk_mcp_keybar input[type="password"]').toHaveCount(0);
});

test('confirming an empty key warns and keeps the key unset', async () => {
    const client = await mountKeyBar();
    await click('.o_muk_mcp_keybar .btn-secondary');
    await animationFrame();
    await click(queryAll('.o_muk_mcp_keybar .btn-primary')[1]);
    await animationFrame();
    expect(client.key).toBe('');
    expect(keyChanges).toBe(0);
    expect(notifications).toEqual([['Key is empty', 'warning']]);
    expect('.o_muk_mcp_keybar input[type="password"]').toHaveCount(1);
});

test('cancelling the paste row discards the typed value', async () => {
    await mountKeyBar();
    await click('.o_muk_mcp_keybar .btn-secondary');
    await animationFrame();
    await click('.o_muk_mcp_keybar input[type="password"]');
    await edit('typed-then-cancelled');
    await click('.o_muk_mcp_keybar .btn-link');
    await animationFrame();
    expect('.o_muk_mcp_keybar input[type="password"]').toHaveCount(0);
    await click('.o_muk_mcp_keybar .btn-secondary');
    await animationFrame();
    expect(queryAll('.o_muk_mcp_keybar input[type="password"]')[0].value).toBe('');
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe(null);
});

// ----------------------------------------------------------
// Generating a key
// ----------------------------------------------------------

test('generating a key loads the plaintext and reports the prefix', async () => {
    mockKeyOrm();
    const client = await mountKeyBar();
    await click(queryAll('.o_muk_mcp_keybar .btn-primary')[0]);
    await animationFrame();
    expect(generateCalls).toHaveLength(1);
    expect(generateCalls[0].scope).toBe('write');
    expect(generateCalls[0].name).toMatch(
        /^Playground \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/,
    );
    expect(client.key).toBe('mcp_1234_secret');
    expect(notifications).toEqual([
        [
            "Generated key '" +
                generateCalls[0].name +
                "' (prefix mcp_1234). Plaintext is now loaded for this tab only.",
            'success',
        ],
    ]);
    expect(keyChanges).toBe(1);
});

test('the label and scope inputs drive the generate call', async () => {
    mockKeyOrm();
    await mountKeyBar();
    await click('.o_muk_mcp_keybar input[type="text"]');
    await edit('CI key');
    await select('read', { target: '.o_muk_mcp_keybar select' });
    await click(queryAll('.o_muk_mcp_keybar .btn-primary')[0]);
    await animationFrame();
    expect(generateCalls).toEqual([{ name: 'CI key', scope: 'read' }]);
});

test('a failed generation is reported and leaves the key unset', async () => {
    mockKeyOrm({ error: new Error('no rights') });
    const client = await mountKeyBar();
    await click(queryAll('.o_muk_mcp_keybar .btn-primary')[0]);
    await animationFrame();
    expect(client.key).toBe('');
    expect(keyChanges).toBe(0);
    expect(notifications).toEqual([['Failed to generate key: no rights', 'danger']]);
});

// ----------------------------------------------------------
// Clearing a key
// ----------------------------------------------------------

test('clearing removes the key from the tab storage', async () => {
    sessionStorage.setItem(STORAGE_KEY, 'live-key');
    const client = await mountKeyBar();
    expect('.o_muk_mcp_keybar .badge').toHaveText(/live-key/);
    await click('.o_muk_mcp_keybar .btn-outline-danger');
    await animationFrame();
    expect(client.key).toBe('');
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe(null);
    expect(keyChanges).toBe(1);
    expect(notifications).toEqual([['Key cleared', 'info']]);
});
