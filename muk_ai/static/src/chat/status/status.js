import { Component, signal, t, useEffect, useProps } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';

import {
    formatRelativeTime,
    formatTimestamp,
    statusInfo,
} from '@muk_ai/core/utils/utils';

const TICK_MS = 5000;

/**
 * The state of a chat as an avatar, with the countdown of a scheduled chat
 * until it resumes.
 */
export class SessionStatus extends Component {
    static template = 'muk_ai.SessionStatus';
    props = useProps({ session: t.object() });
    tick = signal(0);
    formatTimestamp = formatTimestamp;
    setup() {
        useEffect(() => {
            if (this.scheduled) {
                const interval = setInterval(
                    () => this.tick.set(this.tick() + 1),
                    TICK_MS,
                );
                return () => clearInterval(interval);
            }
        });
    }
    get info() {
        return statusInfo(this.props.session.data.state);
    }
    get title() {
        const agent = this.props.session.agentName;
        return agent ? `${agent} · ${this.info.label}` : this.info.label;
    }
    get scheduled() {
        const data = this.props.session.data;
        return data.state === 'waiting_schedule' && data.resume_at
            ? data.resume_at
            : '';
    }
    get countdown() {
        void this.tick();
        const relative = formatRelativeTime(this.scheduled);
        return relative ? _t('resumes in %s', relative) : '';
    }
}
