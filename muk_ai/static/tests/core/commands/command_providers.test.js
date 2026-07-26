import { describe, expect, test } from '@odoo/hoot';
import { patchTranslations } from '@web/../tests/web_test_helpers';
import { registry } from '@web/core/registry';

import '@muk_ai/core/commands/command_providers';

describe.current.tags('muk_ai');
patchTranslations();

function getProvider() {
    return registry.category('command_provider').get('muk_ai_sessions');
}

function makeEnv({ sessions = [], createdIds = [100] } = {}) {
    const seen = [];
    const env = {
        services: {
            orm: {
                async searchRead(model, domain, fields, opts) {
                    seen.push({ op: 'search_read', model, domain, fields, opts });
                    return sessions;
                },
                async create(model, values) {
                    seen.push({ op: 'create', model, values });
                    return createdIds;
                },
            },
            action: {
                actions: [],
                doAction(action) {
                    this.actions.push(action);
                    return Promise.resolve();
                },
            },
        },
    };
    return { env, seen };
}

test('provider returns a "New Chat" entry first, then sessions', async () => {
    const { env } = makeEnv({
        sessions: [
            { id: 1, name: 'Alpha' },
            { id: 2, name: 'Bravo' },
        ],
    });
    const provider = getProvider();
    const commands = await provider.provide(env, { searchValue: '' });
    expect(commands).toHaveLength(3);
    expect(commands[0].name.toString()).toMatch(/New Chat/i);
    expect(commands[1].name).toBe('Alpha');
    expect(commands[2].name).toBe('Bravo');
});

test('provider filters sessions when a search value is given', async () => {
    const { env, seen } = makeEnv({ sessions: [] });
    const provider = getProvider();
    await provider.provide(env, { searchValue: 'rep' });
    const domain = seen.find((s) => s.op === 'search_read').domain;
    expect(
        domain.some((d) => d[0] === 'name' && d[1] === 'ilike' && d[2] === 'rep'),
    ).toBe(true);
});

test('running a session command opens the chat via action service', async () => {
    const { env } = makeEnv({ sessions: [{ id: 7, name: 'Demo' }] });
    const provider = getProvider();
    const commands = await provider.provide(env, { searchValue: '' });
    commands[1].action();
    await Promise.resolve();
    expect(env.services.action.actions).toHaveLength(1);
    expect(env.services.action.actions[0].tag).toBe('muk_ai.chat');
    expect(env.services.action.actions[0].params.session_id).toBe(7);
});

test('running "New Chat" creates session then opens it', async () => {
    const { env, seen } = makeEnv({ sessions: [], createdIds: [33] });
    const provider = getProvider();
    const commands = await provider.provide(env, { searchValue: 'Planning' });
    await commands[0].action();
    const created = seen.find((s) => s.op === 'create');
    expect(created.values[0].name).toBe('Planning');
    expect(env.services.action.actions[0].params.session_id).toBe(33);
});

test('New Chat without a search value uses a timestamped default name', async () => {
    const { env, seen } = makeEnv({ createdIds: [34] });
    const provider = getProvider();
    const commands = await provider.provide(env, { searchValue: '' });
    await commands[0].action();
    const created = seen.find((s) => s.op === 'create');
    expect(String(created.values[0].name)).toMatch(/Chat /);
});

test('session with empty name falls back to a "Chat N" label', async () => {
    const { env } = makeEnv({ sessions: [{ id: 9, name: '' }] });
    const provider = getProvider();
    const commands = await provider.provide(env, { searchValue: '' });
    expect(String(commands[1].name)).toMatch(/Chat/);
});
