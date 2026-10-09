import {
    Component,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    useState,
} from '@odoo/owl';

import { deserializeDateTime, formatDateTime } from '@web/core/l10n/dates';
import { _t } from '@web/core/l10n/translation';
import { user } from '@web/core/user';
import { useService } from '@web/core/utils/hooks';

import { aiSessionChatAction } from '@muk_ai/webclient/notification/session_redirect';

const STATES = {
    new: [_t('New'), 'idle'],
    running: [_t('Running'), 'busy'],
    compacting: [_t('Compacting'), 'busy'],
    waiting: [_t('Waiting'), 'waiting'],
    stopped: [_t('Stopped'), 'idle'],
    done: [_t('Done'), 'done'],
    error: [_t('Error'), 'error'],
};

/**
 * Chatter panel listing the AI sessions linked to a record, kept live by the
 * session bus and opening the chat, or the session form of a foreign one.
 */
export class AISessionBox extends Component {
    static template = 'muk_ai_chatter.AISessionBox';
    static props = {
        threadModel: String,
        threadId: Number,
        open: { type: Boolean, optional: true },
        onLoaded: { type: Function, optional: true },
    };
    setup() {
        this.orm = useService('orm');
        this.action = useService('action');
        this.bus = useService('bus_service');
        this.state = useState({ sessions: [], total: 0 });
        onWillStart(() => this.load(this.props));
        onWillUpdateProps((next) => {
            if (
                next.threadModel !== this.props.threadModel ||
                next.threadId !== this.props.threadId
            ) {
                return this.load(next);
            }
        });
        const onSessionState = (detail) => {
            const { threadModel, threadId } = this.props;
            if (
                (detail.res_model === threadModel && detail.res_id === threadId) ||
                this.state.sessions.some((row) => row.id === detail.session_id)
            ) {
                this.load(this.props);
            }
        };
        this.bus.subscribe('muk_ai.session_state', onSessionState);
        onWillUnmount(() => {
            this.bus.unsubscribe('muk_ai.session_state', onSessionState);
            this.props.onLoaded?.(0);
        });
    }
    get hasMore() {
        return this.state.total > this.state.sessions.length;
    }
    /**
     * Fetch the sessions linked to a record and report their count.
     * @param {{threadModel: string, threadId: number}} props the record
     */
    async load({ threadModel, threadId }) {
        const summary = await this.orm.call(threadModel, 'get_ai_sessions_summary', [
            [threadId],
        ]);
        const { entries, total } = summary[threadId];
        Object.assign(this.state, { sessions: entries, total });
        this.props.onLoaded?.(total);
    }
    stateLabel(session) {
        return STATES[session.state]?.[0] || session.state;
    }
    stateClass(session) {
        return `mk_state_${STATES[session.state]?.[1] || 'idle'}`;
    }
    tooltip(session) {
        const agent = session.agent_id?.[1];
        return agent
            ? _t('%(agent)s: %(state)s', { agent, state: this.stateLabel(session) })
            : this.stateLabel(session);
    }
    relativeDate(session) {
        return deserializeDateTime(session.create_date).toRelative();
    }
    startedAt(session) {
        return formatDateTime(deserializeDateTime(session.create_date));
    }
    onItemKeydown(ev, session) {
        if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            this.openSession(session);
        }
    }
    /**
     * Open the chat of an own session, the session form of a foreign one.
     * @param {object} session the session entry to open
     */
    openSession(session) {
        if (session.user_id?.[0] === user.userId) {
            return this.action.doAction(aiSessionChatAction(session.id));
        }
        return this.action.doAction({
            type: 'ir.actions.act_window',
            name: session.name,
            res_model: 'muk_ai.session',
            res_id: session.id,
            views: [[false, 'form']],
        });
    }
    openAll() {
        return this.action.doAction({
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
}
