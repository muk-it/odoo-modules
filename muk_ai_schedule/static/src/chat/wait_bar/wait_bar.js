import { Component } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { formatError, formatTimestamp } from '@muk_ai/chat/utils';

/**
 * Return the plan of the wait call a chat is paused on.
 * @param {object} state the session state
 * @returns {object|null} `{resume_at, note, record, condition, on_message}`
 */
export function wakeupPlan(state) {
    return state.status === 'waiting' && state.pendingAsk?.kind === 'wakeup'
        ? state.pendingAsk
        : null;
}

/**
 * Say what a waiting chat waits for, from the plan of its wait call.
 * @param {object} plan `{resume_at, record, condition, on_message}`
 * @returns {string} the sentence
 */
function waitLine(plan) {
    const until = formatTimestamp(plan.resume_at);
    const name = plan.record?.name;
    if (!name) {
        return _t('Waiting until %s', until);
    }
    if (plan.condition && plan.on_message) {
        return _t('Waiting for %s to be ready or for a message, until %s', name, until);
    }
    if (plan.condition) {
        return _t('Waiting for %s to be ready, until %s', name, until);
    }
    return _t('Waiting for a message on %s, until %s', name, until);
}

/**
 * What sits above the composer while a chat waits for its wake-up: what it
 * waits for, the note it left itself, and buttons to wake or stop it.
 */
export class WaitBar extends Component {
    static template = 'muk_ai_schedule.WaitBar';
    static props = { session: { type: Object } };
    setup() {
        this.orm = useService('orm');
        this.notification = useService('notification');
    }
    get plan() {
        return wakeupPlan(this.props.session.state);
    }
    get line() {
        return waitLine(this.plan);
    }
    async wake() {
        const session = this.props.session;
        try {
            session.applySnapshot(
                await this.orm.call('muk_ai.session', 'action_wake_now', [
                    session.state.sessionId,
                ]),
            );
        } catch (error) {
            this.notification.add(
                _t('Failed to wake the chat: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }
}
