import {
    Component,
    proxy,
    t,
    untrack,
    useEffect,
    useListener,
    useProps,
    usePlugin,
} from '@odoo/owl';

import { deserializeDateTime, formatDateTime } from '@web/core/l10n/dates';
import { _t } from '@web/core/l10n/translation';
import { ORM } from '@web/core/orm_plugin';
import { user } from '@web/core/user';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';

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
 * chat plugin and opening the chat, or the session form of a foreign one.
 */
export class AISessionBox extends Component {
    static template = 'muk_ai_chatter.AISessionBox';
    props = useProps({
        threadModel: t.string(),
        threadId: t.number(),
        open: t.boolean().optional(false),
        onLoaded: t.function().optional(),
    });
    orm = usePlugin(ORM);
    action = usePlugin(ActionPlugin);
    chat = usePlugin(AIChatPlugin);
    setup() {
        this.state = proxy({ sessions: [], total: 0 });
        useEffect(() => {
            const { threadModel, threadId } = this.props;
            untrack(() => this.load(threadModel, threadId));
            return () => this.props.onLoaded?.(0);
        });
        useListener(this.chat.events, 'session_state', ({ detail }) => {
            const { threadModel, threadId } = this.props;
            if (
                (detail.res_model === threadModel && detail.res_id === threadId) ||
                this.state.sessions.some((row) => row.id === detail.session_id)
            ) {
                this.load(this.props.threadModel, this.props.threadId);
            }
        });
    }
    get hasMore() {
        return this.state.total > this.state.sessions.length;
    }
    /**
     * Fetch the sessions linked to a record and report their count.
     * @param {string} model the model of the record
     * @param {number} id the record
     */
    async load(model, id) {
        const summary = await this.orm.call(model, 'get_ai_sessions_summary', [[id]]);
        const { entries, total } = summary[id];
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
            return this.chat.openFullChat(session.id);
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
