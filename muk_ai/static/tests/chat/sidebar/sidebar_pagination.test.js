import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import { click, queryFirst } from '@odoo/hoot-dom';
import { Component, useState, xml } from '@odoo/owl';
import { contains, mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatSidebar } from '@muk_ai/chat/sidebar/chat_sidebar';

describe.current.tags('muk_ai');
defineMailModels();

function makeHostFactory({
    sessions = [],
    hasMore = false,
    onQuery = null,
    onLoadMore = null,
} = {}) {
    class Host extends Component {
        static components = { ChatSidebar };
        static props = {};
        static template = xml`
            <ChatSidebar
                sessions="state.sessions"
                hasMore="state.hasMore"
                loadingMore="state.loadingMore"
                searching="state.searching"
                searchMode="state.searchMode"
                onNew="() => {}"
                onSelect="() => {}"
                onRename="() => {}"
                onDelete="() => {}"
                onQuery="(q) => this.host_onQuery(q)"
                onLoadMore="() => this.host_onLoadMore()"
            />
        `;
        setup() {
            this.state = useState({
                sessions: [...sessions],
                hasMore,
                loadingMore: false,
                searching: false,
                searchMode: false,
            });
            this.queries = [];
            this.loadMoreCalls = 0;
        }
        host_onQuery(q) {
            this.queries.push(q);
            if (onQuery) {
                onQuery(this, q);
            }
        }
        host_onLoadMore() {
            this.loadMoreCalls += 1;
            if (onLoadMore) {
                onLoadMore(this);
            }
        }
    }
    return Host;
}

test('shows Load more button when hasMore is true and no search active', async () => {
    const Host = makeHostFactory({
        sessions: [{ id: 1, name: 'A', state: 'done', create_date: null }],
        hasMore: true,
    });
    await mountWithCleanup(Host);
    expect(queryFirst('.mk_load_more')).not.toBe(null);
});

test('Load more button clicks emit onLoadMore', async () => {
    const Host = makeHostFactory({
        sessions: [{ id: 1, name: 'A', state: 'done', create_date: null }],
        hasMore: true,
    });
    const host = await mountWithCleanup(Host);
    await click(queryFirst('.mk_load_more'));
    expect(host.loadMoreCalls).toBe(1);
});

test('Load more hidden during server search mode', async () => {
    const Host = makeHostFactory({
        sessions: [{ id: 1, name: 'A', state: 'done', create_date: null }],
        hasMore: true,
    });
    const host = await mountWithCleanup(Host);
    expect(queryFirst('.mk_load_more')).not.toBe(null);
    host.state.searchMode = true;
    await animationFrame();
    expect(queryFirst('.mk_load_more')).toBe(null);
});

test('typing in the search input emits onQuery (server search)', async () => {
    const Host = makeHostFactory({
        sessions: [{ id: 1, name: 'A', state: 'done', create_date: null }],
    });
    const host = await mountWithCleanup(Host);
    await contains('.mk_sidebar_search_input').edit('hello', { confirm: false });
    expect(host.queries.includes('hello')).toBe(true);
});

test('clearing search emits empty onQuery', async () => {
    const Host = makeHostFactory({
        sessions: [{ id: 1, name: 'A', state: 'done', create_date: null }],
    });
    const host = await mountWithCleanup(Host);
    await contains('.mk_sidebar_search_input').edit('foo', { confirm: false });
    await contains('.mk_sidebar_search_clear').click();
    const last = host.queries[host.queries.length - 1];
    expect(last === '').toBe(true);
});

test('searching indicator shows when sessions empty + searching=true', async () => {
    const Host = makeHostFactory({
        sessions: [],
        hasMore: false,
    });
    const host = await mountWithCleanup(Host);
    host.state.searching = true;
    host.state.searchMode = true;
    await animationFrame();
    const placeholder = queryFirst('.mk_sidebar_list .fa-spinner.fa-spin');
    expect(placeholder).not.toBe(null);
});
