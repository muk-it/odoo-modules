import { describe, expect, test } from '@odoo/hoot';

import {
    allSlashCommands,
    commandRoute,
    sessionSlashCommands,
} from '@muk_ai/chat/session/use_ai_session';

describe.current.tags('muk_ai');

test('an addon command joins the list the composer and /help read', () => {
    sessionSlashCommands.add(
        '/remember',
        { name: '/remember', hint: 'Write a memory by hand' },
        { force: true },
    );
    const names = allSlashCommands().map((entry) => entry.name);
    expect(names).toInclude('/help');
    expect(names).toInclude('/remember');
});

test('a command route calls its session method and logs the answer', async () => {
    const calls = [];
    const logged = [];
    const route = commandRoute({ '/kb': 'knowledge_preview' });
    const context = {
        state: { sessionId: 7 },
        orm: {
            call(model, method, args) {
                calls.push([model, method, args]);
                return 'Found 3 passages';
            },
        },
        appendCommand: (name, extra) => logged.push([name, extra]),
    };
    expect(await route(context, '  /kb  warranty period  ')).toBe(true);
    expect(calls).toEqual([
        ['muk_ai.session', 'knowledge_preview', [7, 'warranty period']],
    ]);
    expect(logged).toEqual([['/kb', { summary: 'Found 3 passages' }]]);
});

test('a command route declines anything it does not own', async () => {
    const route = commandRoute({ '/kb': 'knowledge_preview' });
    const context = { state: { sessionId: 7 }, orm: {}, appendCommand: () => {} };
    expect(await route(context, '/compact')).toBe(false);
    expect(await route(context, 'what is our warranty period?')).toBe(false);
});

test('a command route swallows its command when there is no session yet', async () => {
    const route = commandRoute({ '/kb': 'knowledge_preview' });
    let called = false;
    const context = {
        state: { sessionId: null },
        orm: {
            call() {
                called = true;
            },
        },
        appendCommand: () => {},
    };
    expect(await route(context, '/kb anything')).toBe(true);
    expect(called).toBe(false);
});

test('a command route answers the same command whatever its case', async () => {
    const calls = [];
    const route = commandRoute({ '/kb': 'knowledge_preview' });
    const context = {
        state: { sessionId: 7 },
        orm: {
            call(model, method, args) {
                calls.push(args[1]);
                return 'ok';
            },
        },
        appendCommand: () => {},
    };
    expect(await route(context, '/KB warranty')).toBe(true);
    expect(calls).toEqual(['warranty']);
});
