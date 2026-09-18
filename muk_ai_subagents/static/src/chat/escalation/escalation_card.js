import { Component, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { useSessionState } from '@muk_ai/chat/session/use_ai_session';
import { formatError } from '@muk_ai/chat/utils';

import {
    blockedChildren,
    childAsk,
    colorClass,
    openChild,
    shortName,
} from '@muk_ai_subagents/chat/run/run_store';

/**
 * One card per child blocked on the user, drawn in the parent transcript.
 *
 * The buttons act on the child session: an approval or an answer given here
 * lands on the child, never on the parent chat that shows it.
 */
export class SubagentEscalations extends Component {
    static template = 'muk_ai_subagents.SubagentEscalations';
    static props = {
        session: { type: Object },
    };
    setup() {
        this.orm = useService('orm');
        this.notification = useService('notification');
        this.state = useState({ answers: {}, busy: {} });
        this.session = useSessionState(this.props.session);
    }
    get blocked() {
        return blockedChildren(this.session);
    }
    get canWrite() {
        return this.session.canWrite();
    }
    askOf(child) {
        return childAsk(child);
    }
    colorClass(child) {
        return colorClass(child.color);
    }
    title(child) {
        return this.askOf(child).kind === 'approval'
            ? _t('%s needs your confirmation', shortName(child))
            : _t('%s asks', shortName(child));
    }
    answerDraft(child) {
        return this.state.answers[child.id] || '';
    }
    onAnswerInput(child, ev) {
        this.state.answers = { ...this.state.answers, [child.id]: ev.target.value };
    }
    isBusy(child) {
        return !!this.state.busy[child.id];
    }
    openLabel(child) {
        return _t('Open the conversation of %s', shortName(child));
    }
    async callChild(child, method, args = []) {
        if (this.isBusy(child)) {
            return;
        }
        this.state.busy = { ...this.state.busy, [child.id]: true };
        try {
            await this.orm.call('muk_ai.session', method, [child.id, ...args]);
        } catch (error) {
            this.notification.add(
                _t('Failed to answer %(name)s: %(error)s', {
                    name: child.name,
                    error: formatError(error),
                }),
                { type: 'danger' },
            );
        } finally {
            this.state.busy = { ...this.state.busy, [child.id]: false };
        }
    }
    onApprove(child) {
        return this.callChild(child, 'approve_tool');
    }
    onApproveForSession(child) {
        return this.callChild(child, 'approve_for_session');
    }
    onReject(child) {
        return this.callChild(child, 'reject_tool');
    }
    onAnswer(child, text) {
        const answer = (text || '').trim();
        if (!answer) {
            return;
        }
        this.state.answers = { ...this.state.answers, [child.id]: '' };
        return this.callChild(child, 'answer', [answer]);
    }
    onAnswerKeydown(child, ev) {
        if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            this.onAnswer(child, ev.target.value);
        }
    }
    onOpen(child) {
        openChild(this.session, child);
    }
}
