import { describe, expect, test } from '@odoo/hoot';
import { queryAll, queryFirst } from '@odoo/hoot-dom';
import { Component, xml } from '@odoo/owl';
import { contains, mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';
import { browser } from '@web/core/browser/browser';

import { ChatSidebar } from '@muk_ai/chat/sidebar/chat_sidebar';

describe.current.tags('muk_ai');
defineMailModels();

const AUTOMATIC_KEY = 'muk_ai.sidebar_automatic_open';

function space(id, name, values = {}) {
    return {
        id,
        name,
        icon: 'fa-folder-o',
        agent_id: false,
        agent_name: '',
        instructions: '',
        system: true,
        pinned: false,
        session_domain: [],
        ...values,
    };
}

const SPACES = [
    space(1, 'Shared with Me', { pinned: true }),
    space(2, 'Records'),
    space(3, 'Writing Helper'),
    space(4, 'My Notes', { system: false }),
];

async function mountSidebar(spaceUnread = {}) {
    class Parent extends Component {
        static components = { ChatSidebar };
        static props = {};
        static template = xml`
            <ChatSidebar
                sessions="[]"
                spaces="props.spaces"
                spaceUnread="props.spaceUnread"
                onNew="() => {}"
                onSelect="() => {}"
                onRename="() => {}"
                onDelete="() => {}"
                onSpaceCreate="() => {}"
            />
        `;
    }
    Parent.props = {
        spaces: { type: Array },
        spaceUnread: { type: Object },
    };
    await mountWithCleanup(Parent, { props: { spaces: SPACES, spaceUnread } });
}

/** @returns {string[]} the space names the sidebar currently renders */
function renderedSpaces() {
    return queryAll('.mk_space_name').map((el) => el.textContent.trim());
}

test('the collapsed section shows only the pinned system space', async () => {
    browser.localStorage.removeItem(AUTOMATIC_KEY);
    await mountSidebar();
    expect(renderedSpaces()).toEqual(['My Notes', 'Shared with Me']);
    expect(queryFirst('.mk_space_auto_count').textContent.trim()).toBe('2');
});

test('personal spaces come before the divider and the system ones', async () => {
    browser.localStorage.removeItem(AUTOMATIC_KEY);
    await mountSidebar();
    const rows = queryAll('.mk_space_name, .mk_space_divider, .mk_space_auto_label');
    expect(rows.map((el) => el.textContent.trim())).toEqual([
        'My Notes',
        '',
        'Shared with Me',
        'Automatic',
    ]);
});

test('opening the section reveals the folded spaces and drops the count', async () => {
    browser.localStorage.removeItem(AUTOMATIC_KEY);
    await mountSidebar();
    await contains('.mk_space_auto').click();
    expect(renderedSpaces()).toEqual([
        'My Notes',
        'Shared with Me',
        'Records',
        'Writing Helper',
    ]);
    expect(queryFirst('.mk_space_auto_count')).toBe(null);
    expect(browser.localStorage.getItem(AUTOMATIC_KEY)).toBe('1');
});

test('unread inside the fold rolls up to the header', async () => {
    browser.localStorage.removeItem(AUTOMATIC_KEY);
    await mountSidebar({ 2: 7, 3: 2 });
    // The rows stay folded: a space is shown because it is pinned, never
    // because it happens to be busy.
    expect(renderedSpaces()).toEqual(['My Notes', 'Shared with Me']);
    expect(queryFirst('.mk_space_auto_unread').textContent.trim()).toBe('9');
    expect(queryFirst('.mk_space_auto_count').textContent.trim()).toBe('2');
});

test('the header carries no unread badge when the fold is quiet', async () => {
    browser.localStorage.removeItem(AUTOMATIC_KEY);
    await mountSidebar();
    expect(queryFirst('.mk_space_auto_unread')).toBe(null);
});

test('the section reopens the way it was left', async () => {
    browser.localStorage.setItem(AUTOMATIC_KEY, '1');
    await mountSidebar();
    expect(renderedSpaces()).toHaveLength(4);
    browser.localStorage.removeItem(AUTOMATIC_KEY);
});
