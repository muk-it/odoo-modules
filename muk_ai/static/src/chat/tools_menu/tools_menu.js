import { Component, useState } from '@odoo/owl';

import { Dropdown } from '@web/core/dropdown/dropdown';

import { useSessionState } from '@muk_ai/chat/session/use_ai_session';

/**
 * The tools of a chat behind one composer button: the abilities and addon
 * sources of `session.state.toolSources` as switches, grouped by section.
 */
export class ToolsMenu extends Component {
    static template = 'muk_ai.ToolsMenu';
    static components = { Dropdown };
    static props = { session: Object };
    setup() {
        this.session = useSessionState(this.props.session);
        this.local = useState({ expanded: '' });
    }
    get sources() {
        return this.session.state.toolSources || [];
    }
    get sections() {
        const sections = new Map();
        for (const source of this.sources) {
            if (!sections.has(source.section)) {
                sections.set(source.section, []);
            }
            sections.get(source.section).push(source);
        }
        return [...sections].map(([label, sources]) => ({ label, sources }));
    }
    toggleExpanded(key) {
        this.local.expanded = this.local.expanded === key ? '' : key;
    }
    toggle(source) {
        return this.props.session.setToolSource(source.key, !source.enabled);
    }
}
