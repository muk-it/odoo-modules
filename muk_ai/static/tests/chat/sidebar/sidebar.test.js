import { describe, expect, test } from '@odoo/hoot';
import { click, queryAll, queryFirst } from '@odoo/hoot-dom';
import { Component, xml } from '@odoo/owl';
import { contains, mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatSidebar } from '@muk_ai/chat/sidebar/chat_sidebar';

describe.current.tags('muk_ai');
defineMailModels();

function makeParent({
    sessions = [],
    activeSessionId = null,
    onNew,
    onSelect,
    onRename,
    onDelete,
} = {}) {
    class Parent extends Component {
        static components = { ChatSidebar };
        static props = {};
        static template = xml`
            <ChatSidebar
                sessions="props.sessions"
                activeSessionId="props.activeSessionId"
                onNew="props.onNew or (() => {})"
                onSelect="props.onSelect or (() => {})"
                onRename="props.onRename or (() => {})"
                onDelete="props.onDelete or (() => {})"
            />
        `;
    }
    Parent.props = {
        sessions: { type: Array },
        activeSessionId: { type: [Number, { value: null }], optional: true },
        onNew: { type: Function, optional: true },
        onSelect: { type: Function, optional: true },
        onRename: { type: Function, optional: true },
        onDelete: { type: Function, optional: true },
    };
    return {
        Parent,
        props: { sessions, activeSessionId, onNew, onSelect, onRename, onDelete },
    };
}

function isoDaysAgo(days) {
    const d = new Date();
    d.setDate(d.getDate() - days);
    return d.toISOString().slice(0, 19).replace('T', ' ');
}

/**
 * Build a naive-UTC ``create_date`` for a given local wall-clock day and time.
 * @param {number} daysOffset days to add to today (negative for the past)
 * @param {number} hour local hour of day
 * @param {number} minute local minute of hour
 * @returns {string} server-style datetime string
 */
function dateAtLocal(daysOffset, hour, minute) {
    const now = new Date();
    const local = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate() + daysOffset,
        hour,
        minute,
        0,
    );
    return local.toISOString().slice(0, 19).replace('T', ' ');
}

/**
 * Read the rendered sidebar back as a ``{ group label: [session names] }`` map.
 * @returns {object} session names bucketed by their rendered group label
 */
function bucketsFromDom() {
    const buckets = {};
    let current = null;
    for (const node of queryAll('.mk_sidebar_group_label, .mk_sidebar_item')) {
        if (node.classList.contains('mk_sidebar_group_label')) {
            current = node.textContent.trim();
            buckets[current] = [];
        } else if (current) {
            const name = node.querySelector('.mk_sidebar_name');
            buckets[current].push(name ? name.textContent : '');
        }
    }
    return buckets;
}

test('shows empty-state when no sessions', async () => {
    const { Parent, props } = makeParent();
    await mountWithCleanup(Parent, { props });
    expect('.mk_sidebar_item').toHaveCount(0);
    expect('.mk_sidebar_search').toHaveCount(0);
    expect(queryFirst('.mk_sidebar_list').textContent).toMatch(/No chats yet/);
});

test('groups sessions into Today / Yesterday / Previous 7 days / Previous 30 days / Older', async () => {
    const { Parent, props } = makeParent({
        sessions: [
            {
                id: 1,
                name: 'Today A',
                state: 'done',
                create_date: dateAtLocal(0, 9, 0),
            },
            {
                id: 2,
                name: 'Yesterday evening',
                state: 'done',
                create_date: dateAtLocal(-1, 22, 30),
            },
            {
                id: 3,
                name: 'Week A',
                state: 'done',
                create_date: dateAtLocal(-4, 12, 0),
            },
            {
                id: 4,
                name: 'Month A',
                state: 'done',
                create_date: dateAtLocal(-15, 12, 0),
            },
            {
                id: 5,
                name: 'Older A',
                state: 'done',
                create_date: dateAtLocal(-60, 12, 0),
            },
        ],
    });
    await mountWithCleanup(Parent, { props });
    const labels = queryAll('.mk_sidebar_group_label').map((el) =>
        el.textContent.trim(),
    );
    expect(labels).toEqual([
        'Today',
        'Yesterday',
        'Previous 7 days',
        'Previous 30 days',
        'Older',
    ]);
    const buckets = bucketsFromDom();
    expect(buckets['Today']).toEqual(['Today A']);
    expect(buckets['Yesterday']).toEqual(['Yesterday evening']);
    expect(buckets['Previous 7 days']).toEqual(['Week A']);
    expect(buckets['Previous 30 days']).toEqual(['Month A']);
    expect(buckets['Older']).toEqual(['Older A']);
});

test('omits empty groups', async () => {
    const { Parent, props } = makeParent({
        sessions: [
            { id: 1, name: 'Only Older', state: 'done', create_date: isoDaysAgo(120) },
        ],
    });
    await mountWithCleanup(Parent, { props });
    const labels = queryAll('.mk_sidebar_group_label').map((el) =>
        el.textContent.trim(),
    );
    expect(labels).toEqual(['Older']);
});

test('search filters by name (case-insensitive, substring)', async () => {
    const { Parent, props } = makeParent({
        sessions: [
            {
                id: 1,
                name: 'Sales pipeline',
                state: 'done',
                create_date: isoDaysAgo(0),
            },
            {
                id: 2,
                name: 'Marketing brief',
                state: 'done',
                create_date: isoDaysAgo(0),
            },
            {
                id: 3,
                name: 'sales follow-up',
                state: 'done',
                create_date: isoDaysAgo(0),
            },
        ],
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_sidebar_item').toHaveCount(3);
    await contains('.mk_sidebar_search_input').edit('SALES', { confirm: false });
    expect('.mk_sidebar_item').toHaveCount(2);
    expect(queryAll('.mk_sidebar_name').map((el) => el.textContent)).toEqual([
        'Sales pipeline',
        'sales follow-up',
    ]);
});

test('search empty-state when no match', async () => {
    const { Parent, props } = makeParent({
        sessions: [{ id: 1, name: 'Foo', state: 'done', create_date: isoDaysAgo(0) }],
    });
    await mountWithCleanup(Parent, { props });
    await contains('.mk_sidebar_search_input').edit('zzz', { confirm: false });
    expect('.mk_sidebar_item').toHaveCount(0);
    expect(queryFirst('.mk_sidebar_list').textContent).toMatch(/No chats match/);
    expect(queryFirst('.mk_sidebar_list strong').textContent).toBe('zzz');
});

test('clear button resets the query', async () => {
    const { Parent, props } = makeParent({
        sessions: [
            { id: 1, name: 'Foo', state: 'done', create_date: isoDaysAgo(0) },
            { id: 2, name: 'Bar', state: 'done', create_date: isoDaysAgo(0) },
        ],
    });
    await mountWithCleanup(Parent, { props });
    await contains('.mk_sidebar_search_input').edit('foo', { confirm: false });
    expect('.mk_sidebar_item').toHaveCount(1);
    await contains('.mk_sidebar_search_clear').click();
    expect('.mk_sidebar_item').toHaveCount(2);
});

test('marks active session and emits onSelect on click', async () => {
    let selected = null;
    const { Parent, props } = makeParent({
        sessions: [
            { id: 7, name: 'A', state: 'done', create_date: isoDaysAgo(0) },
            { id: 8, name: 'B', state: 'done', create_date: isoDaysAgo(0) },
        ],
        activeSessionId: 7,
        onSelect: (id) => {
            selected = id;
        },
    });
    await mountWithCleanup(Parent, { props });
    const items = queryAll('.mk_sidebar_item');
    expect(items[0].classList.contains('active')).toBe(true);
    expect(items[1].classList.contains('active')).toBe(false);
    await click(items[1]);
    expect(selected).toBe(8);
});

test('running and waiting states get visual indicators', async () => {
    const { Parent, props } = makeParent({
        sessions: [
            { id: 1, name: 'Running', state: 'running', create_date: isoDaysAgo(0) },
            { id: 2, name: 'Waiting', state: 'waiting', create_date: isoDaysAgo(0) },
            { id: 3, name: 'Error', state: 'error', create_date: isoDaysAgo(0) },
            { id: 4, name: 'Done', state: 'done', create_date: isoDaysAgo(0) },
        ],
    });
    await mountWithCleanup(Parent, { props });
    expect('.fa-circle-o-notch').toHaveCount(1);
    expect('.fa-question').toHaveCount(1);
    expect('.fa-exclamation').toHaveCount(1);
    expect('.mk_state_done .fa').toHaveCount(0);
    expect(queryAll('.mk_sidebar_item.mk_running').length).toBe(2);
});

test('does not crash on missing or malformed create_date', async () => {
    const { Parent, props } = makeParent({
        sessions: [
            { id: 1, name: 'No date', state: 'done', create_date: null },
            { id: 2, name: 'Bogus', state: 'done', create_date: 'not-a-date' },
        ],
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_sidebar_item').toHaveCount(2);
    expect(bucketsFromDom()['Older']).toEqual(['No date', 'Bogus']);
});
