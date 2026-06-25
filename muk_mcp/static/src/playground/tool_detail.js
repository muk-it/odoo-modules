import { Component, onWillUpdateProps, useState } from '@odoo/owl';
import { useService } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';
import { STORAGE_KEY } from './mcp_client';
import { SchemaForm } from './schema_form';
import { ResponsePanel } from './response_panel';
import {
    buildCurl,
    buildInitialValue,
    buildJsonRpc,
    categoryBadge,
    cleanValue,
} from './utils';

/**
 * Detail pane for the selected tool: renders its argument form, schema, and the
 * call response, and offers run plus curl/JSON-RPC copy actions.
 */
export class ToolDetail extends Component {
    static template = 'muk_mcp.ToolDetail';
    static components = { SchemaForm, ResponsePanel };
    static props = {
        tool: { type: Object, optional: true },
        response: { type: [Object, { value: null }], optional: true },
        running: Boolean,
        hasKey: Boolean,
        onTry: Function,
    };
    setup() {
        this.notification = useService('notification');
        this.state = useState({
            tab: 'form',
            argsByTool: {},
        });
        this._ensureArgs(this.props.tool);
        onWillUpdateProps((next) => this._ensureArgs(next.tool));
    }
    /**
     * Lazily seed the argument state for a tool from its input schema, once per tool.
     * @param {object} tool the tool descriptor, or a falsy value when none is selected
     */
    _ensureArgs(tool) {
        if (tool && !(tool.name in this.state.argsByTool)) {
            this.state.argsByTool[tool.name] = buildInitialValue(
                tool.inputSchema || {},
            );
        }
    }
    onKeyDown(ev) {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter') {
            ev.preventDefault();
            if (!this.props.running && this.props.hasKey) {
                this.onRun();
            }
        }
    }
    get statusClass() {
        const status = this.props.response?.status;
        if (!status) {
            return 'text-muted';
        }
        if (status >= 200 && status < 300) {
            return 'text-success';
        }
        if (status >= 400 && status < 500) {
            return 'text-warning';
        }
        return 'text-danger';
    }
    get currentArgs() {
        if (!this.props.tool) {
            return {};
        }
        return this.state.argsByTool[this.props.tool.name] || {};
    }
    onArgsChange(next) {
        if (!this.props.tool) {
            return;
        }
        this.state.argsByTool[this.props.tool.name] = next;
    }
    onTabChange(tab) {
        this.state.tab = tab;
    }
    onReset() {
        if (!this.props.tool) {
            return;
        }
        this.state.argsByTool[this.props.tool.name] = buildInitialValue(
            this.props.tool.inputSchema || {},
        );
    }
    /**
     * Trigger a tool call with the current arguments, pruned of empty values.
     */
    onRun() {
        if (!this.props.tool) {
            return;
        }
        this.props.onTry({
            name: this.props.tool.name,
            args: cleanValue(this.currentArgs),
        });
    }
    get schemaJson() {
        if (!this.props.tool) {
            return '{}';
        }
        return JSON.stringify(this.props.tool.inputSchema || {}, null, 2);
    }
    /**
     * Copy text to the clipboard and notify, reporting failure when unavailable.
     * @param {string} text text to copy
     * @param {string} message success notification message
     * @returns {Promise<void>}
     */
    async _copy(text, message) {
        try {
            await navigator.clipboard.writeText(text);
            this.notification.add(message, { type: 'success' });
        } catch {
            this.notification.add(_t('Clipboard unavailable'), {
                type: 'danger',
            });
        }
    }
    /**
     * Build a curl command for the tools/call request and copy it to the clipboard.
     * Uses the stored key when present, otherwise a placeholder.
     */
    onCopyCurl() {
        if (!this.props.tool) {
            return;
        }
        const key = sessionStorage.getItem(STORAGE_KEY) || '<YOUR_MCP_KEY>';
        const curl = buildCurl({
            baseUrl: window.location.origin,
            key,
            toolName: this.props.tool.name,
            args: cleanValue(this.currentArgs),
        });
        this._copy(curl, _t('curl copied'));
    }
    onCopyJsonRpc() {
        if (!this.props.tool) {
            return;
        }
        this._copy(
            buildJsonRpc(this.props.tool.name, cleanValue(this.currentArgs)),
            _t('JSON-RPC payload copied'),
        );
    }
    get toolCategoryBadge() {
        return categoryBadge(this.props.tool?.category);
    }
}
