import { Component, useRef, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { browser } from '@web/core/browser/browser';
import { ConfirmationDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { useService } from '@web/core/utils/hooks';
import { useSortable } from '@web/core/utils/sortable_owl';

import { RenameDialog } from '@muk_ai/chat/sidebar/rename_dialog';
import { SpaceDialog } from '@muk_ai/chat/sidebar/space_dialog';

const DAY_MS = 24 * 60 * 60 * 1000;
const WIDTH_KEY = 'muk_ai.sidebar_width';
const WIDTH_MIN = 220;
const WIDTH_MAX = 520;
const WIDTH_DEFAULT = 272;

/**
 * Read the sidebar width the user last settled on.
 * @returns {number} a width within the allowed range
 */
function storedWidth() {
    const raw = Number(browser.localStorage.getItem(WIDTH_KEY));
    if (!Number.isFinite(raw) || !raw) {
        return WIDTH_DEFAULT;
    }
    return Math.min(WIDTH_MAX, Math.max(WIDTH_MIN, raw));
}

/**
 * Sidebar listing spaces and chat sessions, with rename/delete actions.
 *
 * Chats can be dragged between spaces but never reordered, as they are
 * listed by date. Spaces carry a sequence and reorder by their grip.
 */
export class ChatSidebar extends Component {
    static template = 'muk_ai.ChatSidebar';
    static props = {
        sessions: { type: Array },
        spaces: { type: Array, optional: true },
        spaceSessions: { type: Object, optional: true },
        spaceUnread: { type: Object, optional: true },
        agents: { type: Array, optional: true },
        unreadIds: { type: Array, optional: true },
        activeSessionId: { type: [Number, { value: null }], optional: true },
        hasMore: { type: Boolean, optional: true },
        loadingMore: { type: Boolean, optional: true },
        searching: { type: Boolean, optional: true },
        searchMode: { type: Boolean, optional: true },
        onNew: { type: Function },
        onSelect: { type: Function },
        onRename: { type: Function },
        onDelete: { type: Function },
        onQuery: { type: Function, optional: true },
        onLoadMore: { type: Function, optional: true },
        onSpaceOpen: { type: Function, optional: true },
        onSpaceCreate: { type: Function, optional: true },
        onSpaceEdit: { type: Function, optional: true },
        onSpaceDelete: { type: Function, optional: true },
        onSpaceReorder: { type: Function, optional: true },
        onSpaceNew: { type: Function, optional: true },
        onSpaceLoadMore: { type: Function, optional: true },
        onSessionFile: { type: Function, optional: true },
    };
    setup() {
        this.dialog = useService('dialog');
        this.state = useState({
            query: '',
            expanded: {},
            creating: false,
            newName: '',
            dropTargetId: null,
            width: storedWidth(),
            resizing: false,
        });
        this.asideRef = useRef('aside');
        this.listRef = useRef('list');
        this.spacesRef = useRef('spaces');
        this.newSpaceRef = useRef('newSpace');
        useSortable({
            ref: this.spacesRef,
            elements: '.mk_space_personal',
            handle: '.mk_space_grip',
            cursor: 'grabbing',
            onDrop: ({ element, previous }) => this.onSpaceDrop(element, previous),
        });
        useSortable({
            ref: this.listRef,
            elements: '.mk_sidebar_item',
            groups: '.mk_space_group',
            connectGroups: true,
            cursor: 'grabbing',
            placeholderClasses: ['mk_drag_placeholder'],
            onGroupEnter: ({ group }) => {
                this.state.dropTargetId = group.dataset.spaceId || 'loose';
            },
            onGroupLeave: () => {
                this.state.dropTargetId = null;
            },
            onDragEnd: () => {
                this.state.dropTargetId = null;
            },
            onDrop: ({ element }) => this.onSessionDropped(element),
        });
    }

    /**
     * Width the sidebar renders at, or none while the drawer covers the page.
     * @returns {string} an inline style, empty when the drawer is in charge
     */
    get widthStyle() {
        if (browser.innerWidth < 768) {
            return '';
        }
        return `width: ${this.state.width}px; min-width: ${this.state.width}px;`;
    }
    onResizeStart(ev) {
        if (browser.innerWidth < 768) {
            return;
        }
        ev.preventDefault();
        const startX = ev.clientX;
        const startWidth = this.asideRef.el.getBoundingClientRect().width;
        this.state.resizing = true;
        const onMove = (move) => {
            this.state.width = Math.min(
                WIDTH_MAX,
                Math.max(WIDTH_MIN, startWidth + move.clientX - startX),
            );
        };
        const onUp = () => {
            this.state.resizing = false;
            browser.localStorage.setItem(WIDTH_KEY, String(this.state.width));
            browser.removeEventListener('pointermove', onMove);
            browser.removeEventListener('pointerup', onUp);
        };
        browser.addEventListener('pointermove', onMove);
        browser.addEventListener('pointerup', onUp);
    }
    onResizeReset() {
        this.state.width = WIDTH_DEFAULT;
        browser.localStorage.setItem(WIDTH_KEY, String(WIDTH_DEFAULT));
    }

    get systemSpaces() {
        return (this.props.spaces || []).filter((space) => space.system);
    }
    get personalSpaces() {
        return (this.props.spaces || []).filter((space) => !space.system);
    }
    get hasSpaces() {
        return !!(this.props.spaces || []).length || this.state.creating;
    }
    isExpanded(spaceId) {
        return !!this.state.expanded[spaceId];
    }
    sessionsInSpace(spaceId) {
        return ((this.props.spaceSessions || {})[spaceId] || {}).sessions || [];
    }
    spaceHasMore(spaceId) {
        return !!((this.props.spaceSessions || {})[spaceId] || {}).hasMore;
    }
    spaceUnread(spaceId) {
        return (this.props.spaceUnread || {})[`${spaceId}`] || 0;
    }
    isDropTarget(spaceId) {
        return this.state.dropTargetId === `${spaceId}`;
    }
    /**
     * Tooltip of the unread badge.
     * Built here rather than in the template because a title assembled in a
     * ``t-att`` expression is not picked up for translation.
     * @param {number} spaceId
     * @returns {string}
     */
    unreadFilterTitle(spaceId) {
        return this.isUnreadOnly(spaceId)
            ? _t('Show all chats')
            : _t('Show only unread');
    }
    isUnreadOnly(spaceId) {
        return !!((this.props.spaceSessions || {})[spaceId] || {}).unreadOnly;
    }
    /**
     * Narrow a space to its unread chats, or widen it again.
     * The badge counts every unread chat while the branch holds one page, so
     * without this the number names chats the tree cannot reach.
     */
    toggleUnreadFilter(spaceId, ev) {
        ev.stopPropagation();
        const next = !this.isUnreadOnly(spaceId);
        this.state.expanded[spaceId] = true;
        if (this.props.onSpaceOpen) {
            this.props.onSpaceOpen(spaceId, next);
        }
    }
    onSpaceLoadMoreClick(spaceId, ev) {
        ev.stopPropagation();
        if (this.props.onSpaceLoadMore) {
            this.props.onSpaceLoadMore(spaceId);
        }
    }
    /**
     * Expand a space and ask the parent to load its chats.
     */
    toggleSpace(spaceId) {
        const open = !this.state.expanded[spaceId];
        this.state.expanded[spaceId] = open;
        if (open && this.props.onSpaceOpen) {
            this.props.onSpaceOpen(spaceId);
        }
    }
    startCreate(ev) {
        ev.stopPropagation();
        this.state.creating = true;
        this.state.newName = '';
        requestAnimationFrame(() => this.newSpaceRef.el && this.newSpaceRef.el.focus());
    }
    cancelCreate() {
        this.state.creating = false;
        this.state.newName = '';
    }
    onCreateInput(ev) {
        this.state.newName = ev.target.value;
    }
    onCreateKeydown(ev) {
        if (ev.key === 'Enter') {
            ev.preventDefault();
            this.submitCreate();
        } else if (ev.key === 'Escape') {
            ev.preventDefault();
            this.cancelCreate();
        }
    }
    submitCreate() {
        const name = this.state.newName.trim();
        this.cancelCreate();
        if (name && this.props.onSpaceCreate) {
            this.props.onSpaceCreate(name);
        }
    }
    onSpaceNewClick(space, ev) {
        ev.stopPropagation();
        this.state.expanded[space.id] = true;
        if (this.props.onSpaceNew) {
            this.props.onSpaceNew(space.id);
        }
    }
    onSpaceEditClick(space, ev) {
        ev.stopPropagation();
        this.dialog.add(SpaceDialog, {
            name: space.name || '',
            icon: space.icon || 'fa-folder-o',
            agentId: space.agent_id || false,
            agents: this.props.agents || [],
            onConfirm: (values) =>
                this.props.onSpaceEdit && this.props.onSpaceEdit(space.id, values),
        });
    }
    onSpaceDeleteClick(space, ev) {
        ev.stopPropagation();
        this.dialog.add(ConfirmationDialog, {
            title: _t('Delete space'),
            body: _t('Delete "%s"? Its chats are kept and become loose.', space.name),
            confirmLabel: _t('Delete'),
            confirmClass: 'btn-danger',
            confirm: () =>
                this.props.onSpaceDelete && this.props.onSpaceDelete(space.id),
            cancel: () => {},
        });
    }
    /**
     * Report the new position of a dragged space to the parent.
     * @param {HTMLElement} element the dragged space row
     * @param {HTMLElement|null} previous the row it was dropped after
     */
    onSpaceDrop(element, previous) {
        if (!this.props.onSpaceReorder) {
            return;
        }
        const spaceId = Number(element.dataset.spaceId);
        const afterId = previous ? Number(previous.dataset.spaceId) : null;
        this.props.onSpaceReorder(spaceId, afterId);
    }

    /**
     * File a dragged chat into the space the cursor was released over.
     * The highlighted space decides, not the placeholder: a system space
     * highlights nothing and must then take no chat at all.
     * @param {HTMLElement} element the dragged chat row
     */
    onSessionDropped(element) {
        const target = this.state.dropTargetId;
        this.state.dropTargetId = null;
        const sessionId = Number(element.dataset.sessionId);
        if (!sessionId || !target || !this.props.onSessionFile) {
            return;
        }
        const spaceId = target === 'loose' ? false : Number(target);
        if (Number(element.dataset.spaceId || 0) === (spaceId || 0)) {
            return;
        }
        if (spaceId) {
            this.state.expanded[spaceId] = true;
        }
        this.props.onSessionFile(sessionId, spaceId);
    }

    isUnread(sessionId) {
        return (this.props.unreadIds || []).includes(sessionId);
    }
    statusLabel(state) {
        return (
            {
                new: _t('New'),
                running: _t('Running'),
                waiting: _t('Waiting'),
                done: _t('Done'),
                error: _t('Error'),
                stopped: _t('Stopped'),
            }[state] || state
        );
    }
    get groups() {
        const query = this.state.query.trim().toLowerCase();
        const useServerSearch = !!this.props.onQuery;
        const filtered =
            query && !useServerSearch
                ? this.props.sessions.filter((s) =>
                      (s.name || '').toLowerCase().includes(query),
                  )
                : this.props.sessions;
        const dayAnchor = new Date();
        dayAnchor.setHours(0, 0, 0, 0);
        const startOfDay = dayAnchor.getTime();
        const buckets = {
            today: { label: _t('Today'), sessions: [] },
            yesterday: { label: _t('Yesterday'), sessions: [] },
            week: { label: _t('Previous 7 days'), sessions: [] },
            month: { label: _t('Previous 30 days'), sessions: [] },
            older: { label: _t('Older'), sessions: [] },
        };
        for (const session of filtered) {
            const ts = this._parseDate(session.create_date);
            if (ts === null) {
                buckets.older.sessions.push(session);
            } else if (ts >= startOfDay) {
                buckets.today.sessions.push(session);
            } else if (ts >= startOfDay - DAY_MS) {
                buckets.yesterday.sessions.push(session);
            } else if (ts >= startOfDay - 7 * DAY_MS) {
                buckets.week.sessions.push(session);
            } else if (ts >= startOfDay - 30 * DAY_MS) {
                buckets.month.sessions.push(session);
            } else {
                buckets.older.sessions.push(session);
            }
        }
        return Object.entries(buckets)
            .filter(([, bucket]) => bucket.sessions.length)
            .map(([key, bucket]) => ({ key, ...bucket }));
    }
    get hasQuery() {
        return !!this.state.query.trim();
    }
    get hasAnySession() {
        return (
            this.props.sessions.length > 0 ||
            this.hasQuery ||
            !!this.props.searchMode ||
            this.hasSpaces
        );
    }
    get isServerSearch() {
        return !!this.props.searchMode || (!!this.props.onQuery && this.hasQuery);
    }
    get showLoadMore() {
        return !!this.props.hasMore && !this.isServerSearch;
    }
    onQueryInput(ev) {
        this.state.query = ev.target.value;
        if (this.props.onQuery) {
            this.props.onQuery(this.state.query);
        }
    }
    onClearQuery() {
        this.state.query = '';
        if (this.props.onQuery) {
            this.props.onQuery('');
        }
    }
    onLoadMoreClick() {
        if (this.props.onLoadMore && !this.props.loadingMore) {
            this.props.onLoadMore();
        }
    }
    onRenameClick(session, ev) {
        ev.stopPropagation();
        this.dialog.add(RenameDialog, {
            title: _t('Rename chat'),
            initial: session.name || '',
            onConfirm: (name) => this.props.onRename(session.id, name),
        });
    }
    onDeleteClick(session, ev) {
        ev.stopPropagation();
        this.dialog.add(ConfirmationDialog, {
            title: _t('Delete chat'),
            body: _t('Delete "%s"? This cannot be undone.', session.name || ''),
            confirmLabel: _t('Delete'),
            confirmClass: 'btn-danger',
            confirm: () => this.props.onDelete(session.id),
            cancel: () => {},
        });
    }
    _parseDate(value) {
        if (!value) {
            return null;
        }
        const normalized =
            typeof value === 'string' && !value.includes('T')
                ? value.replace(' ', 'T') + 'Z'
                : value;
        const ts = new Date(normalized).getTime();
        return Number.isFinite(ts) ? ts : null;
    }
}
