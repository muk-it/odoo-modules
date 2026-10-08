import { Component, useProps } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

import { buildRenderedTurns } from '@muk_ai/core/session/turns';
import { ChatTurn } from '@muk_ai/chat/turn/turn';

/** Read-only field drawing a session's events as its chat transcript. */
export class SessionEventsField extends Component {
    static template = 'muk_ai.SessionEventsField';
    static components = { ChatTurn };
    props = useProps(standardFieldProps);
    get turns() {
        const events = this.props.record.data[this.props.name];
        return Array.isArray(events) ? buildRenderedTurns(events) : [];
    }
}

registry.category('fields').add('ai_session_events', {
    component: SessionEventsField,
    displayName: _t('AI Session Events'),
    supportedTypes: ['json'],
});
