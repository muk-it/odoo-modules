import { describe, expect, test } from '@odoo/hoot';
import { click } from '@odoo/hoot-dom';
import { animationFrame } from '@odoo/hoot-mock';
import {
    mockService,
    mountWithCleanup,
    onRpc,
    patchTranslations,
} from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatWindow } from '@muk_ai/chat/window/chat_window';

import { getSkills } from '@muk_ai_skills/chat/skill_cache';
import '@muk_ai_skills/chat/chat';

describe.current.tags('muk_ai_skills');
defineMailModels();
patchTranslations();

const SESSION_RECORD = {
    id: 31,
    name: 'Routing',
    state: 'done',
    events: [],
    oldest_sequence: null,
    has_more_older: false,
    pending_ask: null,
    view_context: null,
    last_text: '',
    error_message: null,
    iteration_count: 0,
    total_input_tokens: 0,
    total_output_tokens: 0,
    last_input_tokens: 0,
    context_window: 8000,
    total_cost: 0,
    agent_id: false,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
};

const SNAPSHOT_RUNNING = {
    state: 'running',
    events: [],
    oldest_sequence: null,
    has_more_older: false,
    pending_ask: null,
    view_context: null,
    error_message: null,
    iteration_count: 0,
    total_input_tokens: 0,
    total_output_tokens: 0,
    total_cost: 0,
    last_input_tokens: 0,
    context_window: 8000,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
};

/**
 * Register the RPC and service mocks a ChatWindow mount needs.
 * @param {object} [options]
 * @param {Array} [options.skills] skills the discovery RPC returns
 * @param {boolean} [options.failInvoke] make invoke_skill_from_chat reject
 * @returns {object} captured invocations and notifications
 */
function registerMocks({ skills = [{ name: 'alpha' }], failInvoke = false } = {}) {
    const captured = { invocations: [], notifications: [] };
    onRpc('muk_ai.session', 'read', ({ args }) => [
        { ...SESSION_RECORD, id: args[0][0] },
    ]);
    onRpc('muk_ai.session', 'get_snapshot', () => ({
        events: [],
        oldest_sequence: null,
        has_more_older: false,
    }));
    onRpc('muk_ai.session', 'available_skill_names', () => skills);
    onRpc('muk_ai.session', 'invoke_skill_from_chat', ({ args, kwargs }) => {
        captured.invocations.push({ args, kwargs });
        if (failInvoke) {
            throw new Error('boom');
        }
        return SNAPSHOT_RUNNING;
    });
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: () => {},
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
    mockService('action', { doAction: () => Promise.resolve() });
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
    mockService('notification', {
        add: (message, options) => captured.notifications.push({ message, options }),
    });
    return captured;
}

/**
 * Mount a ChatWindow with skill routing installed and the cache primed.
 * @param {number} [sessionId] the session to load
 * @returns {Promise<ChatWindow>}
 */
async function mountRoutedWindow(sessionId = 31) {
    const window_ = await mountWithCleanup(ChatWindow, {
        props: {
            sessionId,
            minimized: false,
            onClose: () => {},
            onToggleMinimized: () => {},
        },
    });
    await animationFrame();
    await animationFrame();
    return window_;
}

test('a skill picked in the panel is dispatched through the same server call', async () => {
    const captured = registerMocks({ skills: [{ name: 'alpha', label: 'Alpha' }] });
    await mountRoutedWindow();
    await click('.mk_skill_btn');
    await animationFrame();
    await click('.mk_skill');
    await animationFrame();
    expect(captured.invocations.length).toBe(1);
    expect(captured.invocations[0].args).toEqual([31, 'alpha']);
    expect(captured.invocations[0].kwargs.user_input).toBe(false);
    expect('.mk_skills_panel').toHaveCount(0);
});

test('a cached skill head is dispatched server-side with its parsed arguments', async () => {
    const captured = registerMocks();
    const window_ = await mountRoutedWindow();
    window_.session.state.input = '/alpha  extra words ';
    await window_.session.onSend();
    await animationFrame();
    expect(captured.invocations.length).toBe(1);
    expect(captured.invocations[0].args).toEqual([31, 'alpha']);
    expect(captured.invocations[0].kwargs.user_input).toBe('extra words');
    expect(window_.session.state.input).toBe('');
    expect(window_.session.state.status).toBe('running');
});

test('a bare skill head sends no user_input', async () => {
    const captured = registerMocks();
    const window_ = await mountRoutedWindow();
    window_.session.state.input = '/alpha';
    await window_.session.onSend();
    await animationFrame();
    expect(captured.invocations.length).toBe(1);
    expect(captured.invocations[0].kwargs.user_input).toBe(false);
});

test('a built-in command head is never routed to a same-named skill', async () => {
    const captured = registerMocks({ skills: [{ name: 'help' }] });
    const window_ = await mountRoutedWindow();
    window_.session.state.input = '/help';
    await window_.session.onSend();
    await animationFrame();
    expect(captured.invocations).toEqual([]);
    expect(window_.session.state.events.at(-1)).toMatchObject({
        kind: 'command',
        name: '/help',
    });
});

test('an unknown head falls through to the original send handler', async () => {
    const captured = registerMocks();
    onRpc('muk_ai.session', 'start', ({ args }) => {
        captured.started = args;
        return SNAPSHOT_RUNNING;
    });
    const window_ = await mountRoutedWindow();
    window_.session.state.input = '/nope';
    await window_.session.onSend();
    await animationFrame();
    expect(captured.invocations).toEqual([]);
    expect(captured.started).toEqual([31, '/nope']);
});

test('a failing invocation raises a danger notification and keeps the input cleared', async () => {
    const captured = registerMocks({ failInvoke: true });
    const window_ = await mountRoutedWindow();
    window_.session.state.input = '/alpha';
    await window_.session.onSend();
    await animationFrame();
    expect(captured.invocations.length).toBe(1);
    expect(captured.notifications.length).toBe(1);
    expect(captured.notifications[0].options.type).toBe('danger');
    expect(String(captured.notifications[0].message)).toMatch(/Failed to invoke skill/);
    expect(window_.session.state.input).toBe('');
    expect(window_.session.state.status).toBe('done');
});

test('switching session loads the new skills and keeps the previous ones cached', async () => {
    registerMocks();
    const window_ = await mountRoutedWindow(31);
    expect(getSkills(31).length).toBe(1);
    await window_.session.load(32);
    await animationFrame();
    await animationFrame();
    expect(getSkills(32).length).toBe(1);
    expect(getSkills(31).length).toBe(1);
});
