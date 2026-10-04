import { Component, proxy, t, usePlugin, useProps } from '@odoo/owl';
import { CopyButton } from '@web/core/copy_button/copy_button';

import { MCPClient } from '@muk_mcp/playground/mcp_client/mcp_client';
import { ResponsePanel } from '@muk_mcp/playground/response_panel/response_panel';
import { SchemaForm } from '@muk_mcp/playground/schema_form/schema_form';
import {
    buildInitialValue,
    categoryBadge,
    cleanValue,
    statusClass,
} from '@muk_mcp/playground/utils/utils';

/**
 * Detail pane of a tool: its argument form and schema, the call and its response,
 * and the request to copy as curl or JSON-RPC.
 */
export class ToolDetail extends Component {
    static template = 'muk_mcp.ToolDetail';
    static components = { CopyButton, ResponsePanel, SchemaForm };
    props = useProps({ tool: t.object() });
    mcp = usePlugin(MCPClient);
    state = proxy({
        tab: 'form',
        args: buildInitialValue(this.schema),
        response: null,
        running: false,
    });
    categoryBadge = categoryBadge;
    statusClass = statusClass;
    get schema() {
        return this.props.tool.inputSchema || {};
    }
    get schemaJson() {
        return JSON.stringify(this.schema, null, 2);
    }
    get params() {
        return { name: this.props.tool.name, arguments: cleanValue(this.state.args) };
    }
    get canRun() {
        return !this.state.running && Boolean(this.mcp.key());
    }
    onReset() {
        this.state.args = buildInitialValue(this.schema);
    }
    onKeyDown(ev) {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter' && this.canRun) {
            ev.preventDefault();
            this.onRun();
        }
    }
    async onRun() {
        this.state.running = true;
        this.state.response = null;
        try {
            this.state.response = await this.mcp.request('tools/call', this.params);
        } finally {
            this.state.running = false;
        }
    }
}
