import { describe, expect, test } from '@odoo/hoot';
import { advanceTime, animationFrame, Deferred } from '@odoo/hoot-mock';
import { mockService, mountWithCleanup, onRpc } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { AIChat, SESSION_PAGE_SIZE } from '@muk_ai/chat/chat';

describe.current.tags('muk_ai');
defineMailModels();

const SESSION_RECORD = {
    id: 7,
    name: 'Demo session',
    state: 'done',
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
    user_id: false,
    agent_id: false,
    override_approval_mode: false,
    effective_approval_mode: 'ask',
    pending_user_messages: [],
};

const SNAPSHOT = {
    state: 'done',
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
    pending_user_messages: [],
};

function makePage(count, offset = 0, prefix = 'S') {
    return Array.from({ length: count }, (_v, i) => ({
        id: offset + i + 1,
        name: `${prefix}${offset + i + 1}`,
        state: 'done',
        create_date: `2026-04-${String(28 - ((offset + i) % 27)).padStart(
            2,
            '0',
        )} 10:00:00`,
    }));
}

function baseMocks() {
    onRpc('muk_ai.session', 'read', ({ args }) => [
        { ...SESSION_RECORD, id: args[0][0] },
    ]);
    onRpc('muk_ai.session', 'get_snapshot', () => SNAPSHOT);
    onRpc('muk_ai.agent', 'search_read', () => []);
    onRpc('muk_ai.space', 'fetch_spaces', () => []);
    mockService('muk_ai.chat_window', {
        state: { windows: [] },
        open: () => {},
        close: () => {},
        toggleMinimized: () => {},
        get activeSessionId() {
            return null;
        },
    });
    mockService('bus_service', {
        addChannel() {},
        deleteChannel() {},
        subscribe() {},
        unsubscribe() {},
    });
    mockService('notification', { add: () => {} });
}

test('sidebar search debounces, filters by name and marks search mode', async () => {
    const calls = [];
    baseMocks();
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        calls.push(kwargs);
        const named = kwargs.domain.find((d) => d[1] === 'ilike');
        return named ? [{ id: 3, name: 'Budget', state: 'done' }] : makePage(2);
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    const initial = calls.length;
    chat.onSidebarQuery('bud');
    expect(chat.state.sessionsSearchMode).toBe(true);
    expect(calls.length).toBe(initial);
    await advanceTime(300);
    await animationFrame();
    expect(calls.length).toBe(initial + 1);
    const searchCall = calls.at(-1);
    expect(searchCall.domain.at(-1)).toEqual(['name', 'ilike', 'bud']);
    expect(searchCall.limit).toBe(100);
    expect(chat.state.sessions.map((s) => s.name)).toEqual(['Budget']);
    expect(chat.state.sessionsHasMore).toBe(false);
    expect(chat.state.sessionsSearching).toBe(false);
});

test('retyping within the debounce window issues a single query', async () => {
    let searches = 0;
    baseMocks();
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        if (kwargs.domain.some((d) => d[1] === 'ilike')) {
            searches++;
        }
        return [];
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat.onSidebarQuery('b');
    await advanceTime(100);
    chat.onSidebarQuery('bu');
    await advanceTime(100);
    chat.onSidebarQuery('bud');
    await advanceTime(300);
    await animationFrame();
    expect(searches).toBe(1);
});

test('clearing the sidebar query leaves search mode and reloads the plain list', async () => {
    baseMocks();
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) =>
        kwargs.domain.some((d) => d[1] === 'ilike')
            ? [{ id: 3, name: 'Budget' }]
            : makePage(2),
    );
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat.onSidebarQuery('bud');
    await advanceTime(300);
    await animationFrame();
    expect(chat.state.sessions).toHaveLength(1);
    chat.onSidebarQuery('  ');
    await animationFrame();
    expect(chat.state.sessionsSearchMode).toBe(false);
    expect(chat.state.sessionsSearching).toBe(false);
    expect(chat.state.sessions).toHaveLength(2);
});

test('a slow search result is dropped once the query moved on', async () => {
    baseMocks();
    const slow = new Deferred();
    let searchIndex = 0;
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        if (!kwargs.domain.some((d) => d[1] === 'ilike')) {
            return makePage(2);
        }
        searchIndex++;
        return searchIndex === 1 ? slow : [{ id: 9, name: 'Late', state: 'done' }];
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat.onSidebarQuery('one');
    await advanceTime(300);
    chat.onSidebarQuery('two');
    await advanceTime(300);
    await animationFrame();
    slow.resolve([{ id: 1, name: 'Stale', state: 'done' }]);
    await animationFrame();
    expect(chat.state.sessions.map((s) => s.name)).toEqual(['Late']);
});

test('a sidebar refresh while searching keeps the filtered list', async () => {
    baseMocks();
    const seen = [];
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        const filtered = kwargs.domain.some((d) => d[1] === 'ilike');
        seen.push(filtered);
        return filtered ? [{ id: 3, name: 'Budget', state: 'done' }] : makePage(2);
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat.onSidebarQuery('bud');
    await advanceTime(300);
    await animationFrame();
    await chat._loadSessions();
    expect(seen.at(-1)).toBe(true);
    expect(chat.state.sessions.map((s) => s.name)).toEqual(['Budget']);
});

test('loading more sessions appends the next page and skips known ids', async () => {
    baseMocks();
    const offsets = [];
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        offsets.push(kwargs.offset);
        return kwargs.offset
            ? makePage(SESSION_PAGE_SIZE, SESSION_PAGE_SIZE - 1)
            : makePage(SESSION_PAGE_SIZE);
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    expect(chat.state.sessionsHasMore).toBe(true);
    expect(chat.state.sessionsOffset).toBe(SESSION_PAGE_SIZE);
    await chat.onSidebarLoadMore();
    expect(offsets.at(-1)).toBe(SESSION_PAGE_SIZE);
    expect(chat.state.sessions).toHaveLength(SESSION_PAGE_SIZE * 2 - 1);
    expect(chat.state.sessionsOffset).toBe(SESSION_PAGE_SIZE * 2);
    expect(chat.state.sessionsHasMore).toBe(true);
    expect(chat.state.sessionsLoadingMore).toBe(false);
});

test('a short page ends the sidebar pagination', async () => {
    baseMocks();
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) =>
        kwargs.offset ? makePage(3, SESSION_PAGE_SIZE) : makePage(SESSION_PAGE_SIZE),
    );
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSidebarLoadMore();
    expect(chat.state.sessions).toHaveLength(SESSION_PAGE_SIZE + 3);
    expect(chat.state.sessionsHasMore).toBe(false);
    await chat.onSidebarLoadMore();
    expect(chat.state.sessions).toHaveLength(SESSION_PAGE_SIZE + 3);
});

test('pagination is disabled while the sidebar shows search results', async () => {
    baseMocks();
    let paged = 0;
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        if (kwargs.offset) {
            paged++;
        }
        return kwargs.domain.some((d) => d[1] === 'ilike')
            ? []
            : makePage(SESSION_PAGE_SIZE);
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat.onSidebarQuery('bud');
    await advanceTime(300);
    await animationFrame();
    await chat.onSidebarLoadMore();
    expect(paged).toBe(0);
});

test('a bus event for an unknown session inserts it in create-date order', async () => {
    baseMocks();
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        if (kwargs.limit === 1) {
            return [
                {
                    id: 50,
                    name: 'Fresh',
                    state: 'running',
                    create_date: '2026-04-25 10:00:00',
                },
            ];
        }
        return [
            { id: 1, name: 'A', state: 'done', create_date: '2026-04-26 10:00:00' },
            { id: 2, name: 'B', state: 'done', create_date: '2026-04-24 10:00:00' },
        ];
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat._onUserBusEvent({ session_id: 50, state: 'running' });
    await animationFrame();
    expect(chat.state.sessions.map((s) => s.id)).toEqual([1, 50, 2]);
});

test('an unknown session older than every row is appended last', async () => {
    baseMocks();
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        if (kwargs.limit === 1) {
            return [
                {
                    id: 50,
                    name: 'Old',
                    state: 'done',
                    create_date: '2026-01-01 10:00:00',
                },
            ];
        }
        return [
            { id: 1, name: 'A', state: 'done', create_date: '2026-04-26 10:00:00' },
            { id: 2, name: 'B', state: 'done', create_date: '2026-04-24 10:00:00' },
        ];
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat._onUserBusEvent({ session_id: 50, state: 'done' });
    await animationFrame();
    expect(chat.state.sessions.map((s) => s.id)).toEqual([1, 2, 50]);
});

test('an unknown session that no longer exists is not inserted', async () => {
    baseMocks();
    onRpc('muk_ai.session', 'search_read', ({ kwargs }) => {
        if (kwargs.limit === 1) {
            return [];
        }
        return [
            { id: 1, name: 'A', state: 'done', create_date: '2026-04-26 10:00:00' },
        ];
    });
    const chat = await mountWithCleanup(AIChat, { props: {} });
    chat._onUserBusEvent({ session_id: 50, state: 'done' });
    await animationFrame();
    expect(chat.state.sessions.map((s) => s.id)).toEqual([1]);
});

test('a deleted session is dropped from the sidebar and the next one opens', async () => {
    baseMocks();
    onRpc('muk_ai.session', 'search_read', () => [
        { id: 1, name: 'A', state: 'done', create_date: '2026-04-26 10:00:00' },
        { id: 2, name: 'B', state: 'done', create_date: '2026-04-24 10:00:00' },
    ]);
    const chat = await mountWithCleanup(AIChat, { props: {} });
    await chat.onSelectSession(1);
    chat._onUserBusEvent({ session_id: 1, deleted: true });
    await animationFrame();
    expect(chat.state.sessions.map((s) => s.id)).toEqual([2]);
    expect(chat.session.state.sessionId).toBe(2);
});
