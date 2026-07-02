import { Component, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { ConfirmationDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { useService } from '@web/core/utils/hooks';

import { RenameDialog } from '@muk_ai/chat/sidebar/rename_dialog';

const DAY_MS = 24 * 60 * 60 * 1000;

/** Sidebar listing chat sessions grouped by date, with rename/delete actions. */
export class ChatSidebar extends Component {
    static template = 'muk_ai.ChatSidebar';
    static props = {
        sessions: { type: Array },
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
    };
    setup() {
        this.dialog = useService('dialog');
        this.state = useState({ query: '' });
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
            this.props.sessions.length > 0 || this.hasQuery || !!this.props.searchMode
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
