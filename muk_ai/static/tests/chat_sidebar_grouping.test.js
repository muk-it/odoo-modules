import { describe, expect, test } from '@odoo/hoot';
import { queryAll } from '@odoo/hoot-dom';
import { Component, xml } from '@odoo/owl';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatSidebar } from '@muk_ai/chat/sidebar/chat_sidebar';

describe.current.tags('muk_ai');
defineMailModels();


function dateAtLocal(daysOffset, hour, minute) {
    const now = new Date();
    const local = new Date(now.getFullYear(), now.getMonth(), now.getDate() + daysOffset, hour, minute, 0);
    return local.toISOString().slice(0, 19).replace('T', ' ');
}


function makeParent(sessions) {
    class Parent extends Component {
        static components = { ChatSidebar };
        static props = {};
        static template = xml`
            <ChatSidebar
                sessions="props.sessions"
                onNew="() => {}"
                onSelect="() => {}"
                onRename="() => {}"
                onDelete="() => {}"
            />
        `;
    }
    Parent.props = { sessions: { type: Array } };
    return { Parent, props: { sessions } };
}


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


test('buckets sessions by direct timestamp comparison (today / yesterday / week / month / older)', async () => {
    const sessions = [
        { id: 1, name: 'Today 09:00', state: 'done', create_date: dateAtLocal(0, 9, 0) },
        { id: 2, name: 'Yesterday 18:00', state: 'done', create_date: dateAtLocal(-1, 18, 0) },
        { id: 3, name: 'Five days ago', state: 'done', create_date: dateAtLocal(-5, 12, 0) },
        { id: 4, name: 'Fifteen days ago', state: 'done', create_date: dateAtLocal(-15, 12, 0) },
        { id: 5, name: 'Sixty days ago', state: 'done', create_date: dateAtLocal(-60, 12, 0) },
    ];
    const { Parent, props } = makeParent(sessions);
    await mountWithCleanup(Parent, { props });
    const buckets = bucketsFromDom();
    expect(buckets['Today']).toEqual(['Today 09:00']);
    expect(buckets['Yesterday']).toEqual(['Yesterday 18:00']);
    expect(buckets['Previous 7 days']).toEqual(['Five days ago']);
    expect(buckets['Previous 30 days']).toEqual(['Fifteen days ago']);
    expect(buckets['Older']).toEqual(['Sixty days ago']);
});


test('yesterday-evening session does not leak into Today bucket (regression for #773)', async () => {
    const sessions = [
        { id: 1, name: 'Today morning', state: 'done', create_date: dateAtLocal(0, 9, 0) },
        { id: 2, name: 'Yesterday evening', state: 'done', create_date: dateAtLocal(-1, 22, 30) },
    ];
    const { Parent, props } = makeParent(sessions);
    await mountWithCleanup(Parent, { props });
    const buckets = bucketsFromDom();
    expect(buckets['Today']).toEqual(['Today morning']);
    expect(buckets['Yesterday']).toEqual(['Yesterday evening']);
});


test('null create_date falls into Older bucket', async () => {
    const sessions = [
        { id: 1, name: 'No date', state: 'done', create_date: null },
    ];
    const { Parent, props } = makeParent(sessions);
    await mountWithCleanup(Parent, { props });
    const buckets = bucketsFromDom();
    expect(buckets['Older']).toEqual(['No date']);
});
