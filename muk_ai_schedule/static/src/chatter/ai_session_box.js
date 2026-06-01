/** @odoo-module */

import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { user } from '@web/core/user';
import { useService } from '@web/core/utils/hooks';

const STATE_LABELS = {
    new: _t('New'),
    running: _t('Running'),
    compacting: _t('Compacting'),
    waiting: _t('Waiting'),
    stopped: _t('Stopped'),
    done: _t('Done'),
    error: _t('Error'),
    schedule: _t('Scheduled'),
};

const STATE_BADGES = {
    new: 'text-bg-secondary',
    running: 'text-bg-info',
    compacting: 'text-bg-info',
    waiting: 'text-bg-warning',
    stopped: 'text-bg-secondary',
    done: 'text-bg-success',
    error: 'text-bg-danger',
    schedule: 'text-bg-primary',
};

export class AISessionBox extends Component {
    static template = 'muk_ai_schedule.AISessionBox';
    static props = {
        threadModel: String,
        threadId: { type: [Number, String] },
    };

    setup() {
        this.orm = useService('orm');
        this.action = useService('action');
        this.bus = useService('bus_service');
        this.state = useState({
            sessions: [],
            total: 0,
            loaded: false,
            expanded: false,
        });
        onWillStart(() => this.loadSessions());
        onWillUpdateProps((nextProps) => {
            if (
                nextProps.threadModel !== this.props.threadModel ||
                nextProps.threadId !== this.props.threadId
            ) {
                return this.loadSessions(nextProps);
            }
        });
        this._busHandler = (event) => this._onBusNotification(event);
        this.bus.addEventListener('notification', this._busHandler);
        onWillUnmount(() => {
            this.bus.removeEventListener('notification', this._busHandler);
        });
    }

    async loadSessions(props = this.props) {
        if (!props.threadModel || !props.threadId) {
            this.state.sessions = [];
            this.state.total = 0;
            this.state.loaded = true;
            return;
        }
        const summary = await this.orm.call(
            props.threadModel,
            'get_ai_sessions_summary',
            [[props.threadId]],
        );
        const payload = summary?.[props.threadId] ?? { entries: [], total: 0 };
        this.state.sessions = payload.entries ?? [];
        this.state.total = payload.total ?? this.state.sessions.length;
        this.state.loaded = true;
    }

    _onBusNotification({ detail }) {
        if (!Array.isArray(detail)) {
            return;
        }
        for (const message of detail) {
            const type = message?.type || '';
            if (
                type !== 'muk_ai.session_state' &&
                type !== 'muk_ai.event'
            ) {
                continue;
            }
            const sessionId = message?.payload?.session_id;
            if (!sessionId) {
                continue;
            }
            if (this.state.sessions.some((entry) => entry.id === sessionId)) {
                this.loadSessions();
                return;
            }
        }
    }

    toggle() {
        this.state.expanded = !this.state.expanded;
    }

    stateLabel(state) {
        return STATE_LABELS[state] || state;
    }

    stateBadge(state) {
        return STATE_BADGES[state] || 'text-bg-secondary';
    }

    relativeName(value) {
        if (!value) {
            return '';
        }
        return value.replace('T', ' ').slice(0, 16);
    }

    openSession(session) {
        const ownerId = Array.isArray(session.user_id) ? session.user_id[0] : session.user_id;
        if (ownerId === user.userId) {
            this.action.doAction({
                type: 'ir.actions.client',
                tag: 'muk_ai.chat',
                name: session.name || _t('AI Chat'),
                params: { session_id: session.id },
            });
            return;
        }
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: session.name || _t('AI Session'),
            res_model: 'muk_ai.session',
            res_id: session.id,
            views: [[false, 'form']],
        });
    }

    openAll() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: _t('AI Sessions'),
            res_model: 'muk_ai.session',
            views: [
                [false, 'list'],
                [false, 'form'],
            ],
            domain: [
                ['res_model', '=', this.props.threadModel],
                ['res_id', '=', this.props.threadId],
            ],
        });
    }

    get hasMore() {
        return this.state.total > this.state.sessions.length;
    }
}
