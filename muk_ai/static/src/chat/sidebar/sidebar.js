import {
    Component,
    onWillDestroy,
    onWillStart,
    proxy,
    signal,
    t,
    useEffect,
    useListener,
    useProps,
    usePlugin,
} from '@odoo/owl';

import { browser } from '@web/core/browser/browser';
import { ConfirmationDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { _t } from '@web/core/l10n/translation';
import { ResizablePanel } from '@web/core/resizable_panel/resizable_panel';
import { user } from '@web/core/user';
import { useSortable } from '@web/core/utils/sortable_owl';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { avatarUrl, statusInfo } from '@muk_ai/core/utils/utils';
import {
    RenameDialog,
    SpaceDialog,
} from '@muk_ai/chat/sidebar_dialogs/sidebar_dialogs';

const PAGE_SIZE = 20;
const SPACE_PAGE_SIZE = 10;
const SEARCH_LIMIT = 100;
const SEARCH_DEBOUNCE_MS = 250;
const DAY_MS = 24 * 60 * 60 * 1000;
const FIELDS = [
    'id',
    'name',
    'state',
    'create_date',
    'space_id',
    'share_user_ids',
    'user_id',
];
const WIDTH_KEY = 'muk_ai.sidebar_width';
const AUTOMATIC_KEY = 'muk_ai.sidebar_automatic_open';
const WIDTH = { min: 220, max: 520, initial: 272 };

/**
 * Append the ids of a page to a list, skipping those already in it.
 * @param {number[]} ids the list
 * @param {Array} page the records read
 * @returns {number[]} the merged ids
 */
function merge(ids, page) {
    return [...ids, ...page.map((row) => row.id).filter((id) => !ids.includes(id))];
}

/**
 * The spaces and chats of the current user: searchable, paged, grouped by
 * date, with the spaces reordered by their grip and chats dragged between
 * them. It loads and keeps its own lists; the rows come from the chat plugin.
 */
export class ChatSidebar extends Component {
    static template = 'muk_ai.ChatSidebar';
    static components = { ResizablePanel };
    props = useProps({
        activeId: t.number().optional(),
        onSelect: t.function(),
        onNew: t.function(),
    });
    chat = usePlugin(AIChatPlugin);
    list = signal.ref();
    spacesList = signal.ref();
    newSpace = signal.ref();
    avatarUrl = avatarUrl;
    statusInfo = statusInfo;
    state = proxy({
        spaces: [],
        generalDomain: null,
        ids: [],
        offset: 0,
        hasMore: false,
        loadingMore: false,
        query: '',
        searching: false,
        branches: {},
        expanded: {},
        creating: false,
        dropTarget: null,
        automaticOpen: browser.localStorage.getItem(AUTOMATIC_KEY) === '1',
    });
    width = Math.min(
        WIDTH.max,
        Math.max(
            WIDTH.min,
            Number(browser.localStorage.getItem(WIDTH_KEY)) || WIDTH.initial,
        ),
    );
    setup() {
        this.seq = 0;
        this.branchSeq = {};
        onWillStart(() =>
            Promise.all([
                this.loadSpaces(),
                this.loadSessions(),
                this.chat.loadBadge(),
            ]),
        );
        onWillDestroy(() => clearTimeout(this.searchTimer));
        useListener(this.chat.events, 'session_state', ({ detail }) =>
            this.onSessionState(detail),
        );
        useListener(this.chat.events, 'created', () => this.reload());
        useListener(document, 'mousedown', (ev) => this.onMouseDown(ev));
        useEffect(() => this.newSpace()?.focus());
        useSortable({
            ref: this.spacesList,
            elements: '.mk_space_personal',
            handle: '.mk_space_grip',
            cursor: 'grabbing',
            onDrop: ({ element, previous }) =>
                this.reorderSpace(
                    Number(element.dataset.spaceId),
                    previous && Number(previous.dataset.spaceId),
                ),
        });
        useSortable({
            ref: this.list,
            elements: '.mk_sidebar_item:not(.mk_sidebar_shared)',
            groups: '.mk_space_group',
            connectGroups: true,
            cursor: 'grabbing',
            placeholderClasses: ['d-none'],
            onGroupEnter: ({ group }) =>
                (this.state.dropTarget = group.dataset.spaceId || 'loose'),
            onGroupLeave: () => (this.state.dropTarget = null),
            onDragEnd: () => (this.state.dropTarget = null),
            onDrop: ({ element }) => this.onChatDropped(element),
        });
    }
    /**
     * What counts as one of the user's chats, before any narrowing.
     * @returns {Array} a domain on `muk_ai.session`
     */
    get baseDomain() {
        return [['user_id', '=', user.userId]];
    }
    get searchMode() {
        return !!this.state.query.trim();
    }
    get rows() {
        return this.state.ids.map((id) => this.chat.rows[id]).filter(Boolean);
    }
    get groups() {
        const today = new Date().setHours(0, 0, 0, 0);
        const buckets = [
            [today, _t('Today')],
            [today - DAY_MS, _t('Yesterday')],
            [today - 7 * DAY_MS, _t('Previous 7 days')],
            [today - 30 * DAY_MS, _t('Previous 30 days')],
            [-Infinity, _t('Older')],
        ].map(([from, label]) => ({ from, label, rows: [] }));
        for (const row of this.rows) {
            const created =
                Date.parse(`${(row.create_date || '').replace(' ', 'T')}Z`) ||
                -Infinity;
            buckets.find((bucket) => created >= bucket.from).rows.push(row);
        }
        return buckets.filter((bucket) => bucket.rows.length);
    }
    get personalSpaces() {
        return this.state.spaces.filter((space) => !space.system);
    }
    get pinnedSpaces() {
        return this.state.spaces.filter((space) => space.system && space.pinned);
    }
    get foldedSpaces() {
        return this.state.spaces.filter((space) => space.system && !space.pinned);
    }
    get foldedUnread() {
        return this.foldedSpaces.reduce(
            (total, space) => total + this.unread(space),
            0,
        );
    }
    unread(space) {
        return this.chat.badge.spaceUnread[space.id] || 0;
    }
    branch(space) {
        return this.state.branches[space.id] || { ids: [] };
    }
    branchRows(space) {
        return this.branch(space)
            .ids.map((id) => this.chat.rows[id])
            .filter(Boolean);
    }
    isOwn(row) {
        return !row.user_id || row.user_id[0] === user.userId;
    }
    unreadTitle(branch) {
        return branch.unreadOnly ? _t('Show all chats') : _t('Show only unread');
    }
    sharedTitle(row) {
        return _t(
            'Shared with %s person(s), they can read it',
            row.share_user_ids.length,
        );
    }
    /**
     * Read a page of chats into the shared rows.
     * @param {Array} domain the domain on `muk_ai.session`
     * @param {number} offset the first record
     * @param {number} limit the page size
     * @returns {Promise<Array>} the records
     */
    async fetch(domain, offset, limit) {
        const page = await this.chat.orm.searchRead('muk_ai.session', domain, FIELDS, {
            offset,
            limit,
            order: 'create_date DESC',
        });
        this.chat.setRows(page);
        return page;
    }
    async loadSpaces() {
        const [spaces, generalDomain] = await Promise.all([
            this.chat.orm.call('muk_ai.space', 'fetch_spaces', []),
            this.chat.orm.call('muk_ai.space', 'fetch_general_domain', []),
        ]);
        Object.assign(this.state, { spaces, generalDomain });
    }
    /**
     * Load the first page of loose chats, or the next one, or the matches of
     * the search typed.
     * @param {boolean} [more] append the next page
     */
    async loadSessions(more = false) {
        const state = this.state;
        if (more && (state.loadingMore || !state.hasMore)) {
            return;
        }
        const seq = more ? this.seq : ++this.seq;
        const query = state.query.trim();
        const domain = query
            ? [...this.baseDomain, ['name', 'ilike', query]]
            : [
                  ...this.baseDomain,
                  ...(state.generalDomain ?? [['space_id', '=', false]]),
              ];
        const offset = more ? state.offset : 0;
        Object.assign(state, { loadingMore: more, searching: !!query });
        const page = await this.fetch(domain, offset, query ? SEARCH_LIMIT : PAGE_SIZE);
        if (seq === this.seq) {
            Object.assign(state, {
                ids: merge(more ? state.ids : [], page),
                offset: offset + page.length,
                hasMore: !query && page.length === PAGE_SIZE,
                loadingMore: false,
                searching: false,
            });
        }
    }
    /**
     * Load a page of the chats of a space into its branch.
     * @param {number} spaceId the space
     * @param {boolean} [more] append the next page
     * @param {boolean} [unreadOnly] narrow to unread chats, the branch's
     *     current filter when omitted
     */
    async loadBranch(spaceId, more = false, unreadOnly = undefined) {
        const space = this.state.spaces.find((item) => item.id === spaceId);
        if (!space) {
            return;
        }
        const branch = this.branch(space);
        const unread = unreadOnly ?? !!branch.unreadOnly;
        const offset = more ? branch.offset : 0;
        const seq = (this.branchSeq[spaceId] = (this.branchSeq[spaceId] || 0) + 1);
        const domain = [
            '|',
            ['user_id', '=', user.userId],
            ['share_user_ids', 'in', [user.userId]],
            ...space.session_domain,
            ...(unread ? [['notification_unread', '=', true]] : []),
        ];
        const page = await this.fetch(domain, offset, SPACE_PAGE_SIZE);
        if (this.branchSeq[spaceId] === seq) {
            this.state.branches[spaceId] = {
                ids: merge(more ? branch.ids : [], page),
                offset: offset + page.length,
                hasMore: page.length === SPACE_PAGE_SIZE,
                unreadOnly: unread,
            };
        }
    }
    reload() {
        const branches = Object.keys(this.state.branches).map(Number);
        return Promise.all([
            this.loadSessions(),
            ...branches.map((id) => this.loadBranch(id)),
        ]);
    }
    /**
     * Follow a chat's state: drop a deleted chat, and look for one this list
     * does not hold yet where it belongs.
     * @param {object} payload the `muk_ai.session_state` notification
     */
    async onSessionState({ session_id: id, deleted }) {
        const branches = Object.values(this.state.branches);
        if (deleted) {
            this.state.ids = this.state.ids.filter((item) => item !== id);
            branches.forEach(
                (branch) => (branch.ids = branch.ids.filter((item) => item !== id)),
            );
            return;
        }
        const known =
            this.state.ids.includes(id) || branches.some((b) => b.ids.includes(id));
        if (known || this.searchMode || this.fetching?.has(id)) {
            return;
        }
        (this.fetching ||= new Set()).add(id);
        const domain = [
            ['id', '=', id],
            ...(this.state.generalDomain ?? [['space_id', '=', false]]),
            ...this.baseDomain,
        ];
        const [row] = await this.fetch(domain, 0, 1).finally(() =>
            this.fetching.delete(id),
        );
        if (!row) {
            await this.reload();
        } else if (!this.state.ids.includes(id)) {
            const ids = this.state.ids;
            const index = ids.findIndex(
                (item) => this.chat.rows[item]?.create_date < row.create_date,
            );
            ids.splice(index < 0 ? ids.length : index, 0, id);
        }
    }
    onQuery(ev) {
        this.state.query = ev.target.value;
        clearTimeout(this.searchTimer);
        if (this.searchMode) {
            this.state.searching = true;
            this.searchTimer = setTimeout(
                () => this.loadSessions(),
                SEARCH_DEBOUNCE_MS,
            );
        } else {
            this.loadSessions();
        }
    }
    clearQuery() {
        this.onQuery({ target: { value: '' } });
    }
    toggleSpace(space) {
        const open = !this.state.expanded[space.id];
        this.state.expanded[space.id] = open;
        if (open) {
            this.loadBranch(space.id);
        }
    }
    toggleUnread(space) {
        this.state.expanded[space.id] = true;
        this.loadBranch(space.id, false, !this.branch(space).unreadOnly);
    }
    toggleAutomatic() {
        this.state.automaticOpen = !this.state.automaticOpen;
        browser.localStorage.setItem(
            AUTOMATIC_KEY,
            this.state.automaticOpen ? '1' : '0',
        );
    }
    onResize(width) {
        browser.localStorage.setItem(WIDTH_KEY, String(Math.round(width)));
    }
    onMouseDown(ev) {
        if (
            ev.detail === 2 &&
            ev.target.matches('.mk_sidebar > .o_resizable_panel_handle')
        ) {
            ev.target.parentElement.style.width = `${WIDTH.initial}px`;
            this.onResize(WIDTH.initial);
        }
    }
    async createSpace(ev) {
        const name = ev.target.value.trim();
        this.state.creating = false;
        if (name) {
            await this.chat.orm.create('muk_ai.space', [{ name }]);
            await this.loadSpaces();
        }
    }
    onCreateKeydown(ev) {
        if (ev.key === 'Enter') {
            ev.target.blur();
        } else if (ev.key === 'Escape') {
            ev.target.value = '';
            ev.target.blur();
        }
    }
    async newChatIn(space) {
        this.state.expanded[space.id] = true;
        await this.props.onNew(
            space.agent_id
                ? { space_id: space.id, agent_id: space.agent_id }
                : { space_id: space.id },
        );
        await this.loadBranch(space.id);
    }
    editSpace(space) {
        this.chat.dialog.add(SpaceDialog, {
            space,
            onConfirm: async (values) => {
                await this.chat.orm.write('muk_ai.space', [space.id], values);
                await this.loadSpaces();
            },
        });
    }
    deleteSpace(space) {
        this.chat.dialog.add(ConfirmationDialog, {
            title: _t('Delete space'),
            body: _t('Delete "%s"? Its chats are kept and become loose.', space.name),
            confirmLabel: _t('Delete'),
            confirmClass: 'btn-danger',
            confirm: async () => {
                await this.chat.orm.unlink('muk_ai.space', [space.id]);
                delete this.state.branches[space.id];
                await Promise.all([this.loadSpaces(), this.loadSessions()]);
            },
            cancel: () => {},
        });
    }
    /**
     * Persist the order of the personal spaces after one was dragged.
     * @param {number} spaceId the space moved
     * @param {number|null} afterId the space it follows now, null when first
     */
    async reorderSpace(spaceId, afterId) {
        const ids = this.personalSpaces
            .map((space) => space.id)
            .filter((id) => id !== spaceId);
        ids.splice(afterId ? ids.indexOf(afterId) + 1 : 0, 0, spaceId);
        const byId = Object.fromEntries(
            this.state.spaces.map((space) => [space.id, space]),
        );
        this.state.spaces = [
            ...this.state.spaces.filter((space) => space.system),
            ...ids.map((id) => byId[id]),
        ];
        await this.chat.orm
            .call('muk_ai.space', 'reorder', [ids])
            .catch(() => this.loadSpaces());
    }
    /**
     * File a dragged chat into the space released over, or loosen it. The
     * highlighted space decides: a system space highlights nothing and takes
     * no chat.
     * @param {HTMLElement} element the dragged chat row
     */
    async onChatDropped(element) {
        const target = this.state.dropTarget;
        const sessionId = Number(element.dataset.sessionId);
        const spaceId = target === 'loose' ? false : Number(target);
        const from = Number(element.dataset.spaceId) || false;
        this.state.dropTarget = null;
        if (!target || spaceId === from) {
            return;
        }
        if (spaceId) {
            this.state.expanded[spaceId] = true;
        }
        await this.chat.orm.write('muk_ai.session', [sessionId], { space_id: spaceId });
        await Promise.all([
            this.loadSessions(),
            ...[from, spaceId].filter(Boolean).map((id) => this.loadBranch(id)),
        ]);
    }
    rename(row) {
        this.chat.dialog.add(RenameDialog, {
            initial: row.name || '',
            onConfirm: (name) => this.chat.rename(row.id, name),
        });
    }
    remove(row) {
        this.chat.dialog.add(ConfirmationDialog, {
            title: _t('Delete chat'),
            body: _t('Delete "%s"? This cannot be undone.', row.name || ''),
            confirmLabel: _t('Delete'),
            confirmClass: 'btn-danger',
            confirm: () => this.chat.remove(row.id),
            cancel: () => {},
        });
    }
}
