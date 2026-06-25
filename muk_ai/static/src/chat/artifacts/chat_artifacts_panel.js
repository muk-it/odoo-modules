import { Component, useState } from '@odoo/owl';

import { registry } from '@web/core/registry';

import { AttachmentsTab } from '@muk_ai/chat/artifacts/types/attachments_tab';

/** Side panel grouping session artifacts (attachments, etc.) into tabs. */
export class ChatArtifactsPanel extends Component {
    static template = 'muk_ai.ChatArtifactsPanel';
    static components = { AttachmentsTab };
    static props = {
        session: { type: Object },
        onClose: { type: Function },
        onOpenAttachment: { type: Function, optional: true },
    };
    setup() {
        this.state = useState({
            activeTabId: null,
        });
    }
    get tabs() {
        const sessionState = this.props.session?.state || {};
        const definitions = registry.category('muk_ai.artifact_types').getAll();
        const tabs = [];
        for (const def of definitions) {
            if (!def || typeof def.collect !== 'function') {
                continue;
            }
            let items;
            try {
                items = def.collect(sessionState) || [];
            } catch {
                items = [];
            }
            if (!items.length) {
                continue;
            }
            tabs.push({
                id: def.id,
                label: def.label,
                icon: def.icon,
                sequence: def.sequence || 0,
                component: def.component,
                items,
            });
        }
        tabs.sort((a, b) => a.sequence - b.sequence);
        return tabs;
    }
    get activeTab() {
        const tabs = this.tabs;
        if (!tabs.length) {
            return null;
        }
        const wanted =
            this.state.activeTabId && tabs.find((t) => t.id === this.state.activeTabId);
        return wanted || tabs[0];
    }
    get bodyProps() {
        const tab = this.activeTab;
        if (!tab) {
            return null;
        }
        return {
            items: tab.items,
            session: this.props.session,
            onOpenAttachment: this.props.onOpenAttachment || (() => {}),
        };
    }
    onSelectTab(tabId) {
        this.state.activeTabId = tabId;
    }
}
