import { Component, t, useProps } from '@odoo/owl';

import { statusInfo } from '@muk_ai/core/utils/utils';

/**
 * The state of a chat as an avatar.
 */
export class SessionStatus extends Component {
    static template = 'muk_ai.SessionStatus';
    props = useProps({ session: t.object() });
    get info() {
        return statusInfo(this.props.session.data.state);
    }
    get title() {
        const agent = this.props.session.agentName;
        return agent ? `${agent} · ${this.info.label}` : this.info.label;
    }
}
