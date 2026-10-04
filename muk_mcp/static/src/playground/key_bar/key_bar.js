import { Component, proxy, usePlugin } from '@odoo/owl';
import { _t } from '@web/core/l10n/translation';
import { NotificationPlugin } from '@web/core/notifications/notification_plugin';
import { ORM } from '@web/core/orm_plugin';

import { MCPClient } from '@muk_mcp/playground/mcp_client/mcp_client';

/**
 * Toolbar managing the MCP key of the tab: paste an existing key, generate a new
 * scoped key, or clear it.
 */
export class KeyBar extends Component {
    static template = 'muk_mcp.KeyBar';
    mcp = usePlugin(MCPClient);
    orm = usePlugin(ORM);
    notification = usePlugin(NotificationPlugin);
    state = proxy({ pasting: false, pasted: '', label: '', scope: 'write' });
    onPasteToggle() {
        this.state.pasting = !this.state.pasting;
        this.state.pasted = '';
    }
    onPasteConfirm() {
        this.mcp.setKey(this.state.pasted.trim());
        this.onPasteToggle();
    }
    /**
     * Generate a key for the current user and load its plaintext into the tab.
     * @returns {Promise<void>}
     */
    async onGenerate() {
        const now = new Date().toISOString().slice(0, 19).replace('T', ' ');
        const key = await this.orm.call('muk_mcp.key', 'generate_playground_key', [], {
            name: this.state.label.trim() || `Playground ${now}`,
            scope: this.state.scope,
        });
        this.mcp.setKey(key.plaintext);
        this.state.pasting = false;
        this.notification.add(
            _t(
                "Generated key '%s' (prefix %s). Plaintext is now loaded for this tab only.",
                key.name,
                key.key_prefix,
            ),
            { type: 'success', sticky: true },
        );
    }
}
