import { Component, t, useProps } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';

import { composerAccessories } from '@muk_ai/chat/conversation/conversation';
import { formatTimestamp } from '@muk_ai/core/utils/utils';

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
    props = useProps({ session: t.object() });
    get plan() {
        const data = this.props.session.data;
        return data.state === 'waiting' && data.pending_ask?.kind === 'wakeup'
            ? data.pending_ask
            : null;
    }
    get line() {
        return waitLine(this.plan);
    }
    wake() {
        return this.props.session.run(
            'action_wake_now',
            [],
            _t('Failed to wake the chat'),
        );
    }
}

composerAccessories.add(WaitBar);
