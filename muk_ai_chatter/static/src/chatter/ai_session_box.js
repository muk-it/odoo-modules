import {
    Component,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    useState,
} from '@odoo/owl';

import { deserializeDateTime } from '@web/core/l10n/dates';
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
    new: 'o-state-idle',
    running: 'o-state-busy',
    compacting: 'o-state-busy',
    waiting: 'o-state-waiting',
    stopped: 'o-state-idle',
    done: 'o-state-done',
    error: 'o-state-error',
    schedule: 'o-state-busy',
};

/**
 * Chatter panel listing the AI sessions linked to the current record, kept live
 * via bus notifications and opening either the chat or the session form.
 */
export class AISessionBox extends Component {
    static template = 'muk_ai_chatter.AISessionBox';
    static props = {
        threadModel: String,
        threadId: { type: [Number, String] },
        open: { type: Boolean, optional: true },
        onLoaded: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService('orm');
        this.action = useService('action');
        this.bus = useService('bus_service');
        this.state = useState({
            sessions: [],
            total: 0,
            loaded: false,
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
        this._busHandler = (payload) => this._onSessionPush(payload);
        this.bus.subscribe('muk_ai.session_state', this._busHandler);
        this.bus.subscribe('muk_ai.event', this._busHandler);
        onWillUnmount(() => {
            this.bus.unsubscribe('muk_ai.session_state', this._busHandler);
            this.bus.unsubscribe('muk_ai.event', this._busHandler);
            // The count belongs to the topbar toggle, which outlives this
            // component: a record whose chatter moves on would otherwise keep
            // a button offering sessions there are none of.
            this.props.onLoaded?.(0);
        });
    }

    /**
     * Fetch the linked-session summary for the thread and store entries and total.
     * @param {object} props the props to load from, defaulting to current props
     * @returns {Promise<void>}
     */
    async loadSessions(props = this.props) {
        if (!props.threadModel || !props.threadId) {
            this.state.sessions = [];
            this.state.total = 0;
            this.state.loaded = true;
            this.props.onLoaded?.(0);
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
        // The count belongs to the toggle in the topbar, which is drawn by the
        // chatter and cannot know it until the sessions have been fetched.
        this.props.onLoaded?.(this.state.total);
    }

    /**
     * Reload sessions when a push targets one of the listed sessions.
     * @param {object} payload the pushed session payload
     */
    _onSessionPush(payload) {
        const sessionId = payload?.session_id;
        if (sessionId && this.state.sessions.some((row) => row.id === sessionId)) {
            this.loadSessions();
        }
    }

    stateLabel(state) {
        return STATE_LABELS[state] || state;
    }

    stateBadge(state) {
        return STATE_BADGES[state] || 'o-state-idle';
    }

    /**
     * Return what a row says on hover: who answered, and how it went.
     *
     * The row itself shows the state as a coloured dot, which is enough to
     * spot the one that failed without reading a word; the word it stands for
     * lives here, where somebody who wants it can ask for it.
     *
     * @param {object} session the session entry to describe
     * @returns {string} the agent name and the state, as one line
     */
    tooltip(session) {
        const agent = Array.isArray(session.agent_id) ? session.agent_id[1] : '';
        const state = this.stateLabel(session.state);
        return agent ? `${agent} — ${state}` : state;
    }

    /**
     * Say how long ago a session was started, the way the chatter dates a message.
     * @param {string} value the ISO datetime to describe
     * @returns {string} a relative label, or an empty string when falsy
     */
    relativeName(value) {
        if (!value) {
            return '';
        }
        return deserializeDateTime(value).toRelative();
    }

    /**
     * Open the session: the live chat for the current user, else the form view.
     * @param {object} session the session entry to open
     */
    openSession(session) {
        const ownerId = Array.isArray(session.user_id)
            ? session.user_id[0]
            : session.user_id;
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
