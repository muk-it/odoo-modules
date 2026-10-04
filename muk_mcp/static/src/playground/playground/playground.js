import {
    Component,
    onWillStart,
    providePlugins,
    proxy,
    signal,
    useEffect,
    usePlugin,
} from '@odoo/owl';
import { _t } from '@web/core/l10n/translation';
import { ORM } from '@web/core/orm_plugin';
import { registry } from '@web/core/registry';

import { KeyBar } from '@muk_mcp/playground/key_bar/key_bar';
import { MCPClient } from '@muk_mcp/playground/mcp_client/mcp_client';
import { ToolDetail } from '@muk_mcp/playground/tool_detail/tool_detail';
import { categoryBadge, groupTools } from '@muk_mcp/playground/utils/utils';

const LAST_TOOL_KEY = 'muk_mcp.playground.last_tool';
const ACTIVE_PANEL_KEY = 'muk_mcp.playground.active_panel';

/**
 * MCP playground client action: the tool browser plus the side panels registered
 * in `muk_mcp.playground.panels`, all sharing one MCP client.
 */
export class Playground extends Component {
    static template = 'muk_mcp.Playground';
    static components = { KeyBar, ToolDetail };
    orm = usePlugin(ORM);
    searchInput = signal.ref();
    state = proxy({
        tools: [],
        search: '',
        selected: null,
        panel: localStorage.getItem(ACTIVE_PANEL_KEY),
    });
    categoryBadge = categoryBadge;
    setup() {
        providePlugins([MCPClient]);
        onWillStart(() => this.loadTools());
        useEffect(() => this.searchInput()?.focus());
    }
    /**
     * List the built-in tools panel and the registered panels by sequence.
     * @returns {object[]} panels with `id`, `label`, `icon`, `sequence` and, for a
     *   registered panel, its `component`
     */
    get panels() {
        const registered = registry
            .category('muk_mcp.playground.panels')
            .getEntries()
            .map(([id, panel]) => ({ id, sequence: 50, ...panel }));
        return [{ id: 'tools', label: _t('Tools'), icon: 'build', sequence: 0 }]
            .concat(registered)
            .sort((a, b) => a.sequence - b.sequence);
    }
    get activePanel() {
        const panels = this.panels;
        return panels.find((panel) => panel.id === this.state.panel) || panels[0];
    }
    /**
     * Group the tools matching the search on name or description.
     * @returns {Array} `[category, tools]` entries
     */
    get groups() {
        const term = this.state.search.trim().toLowerCase();
        return groupTools(
            this.state.tools.filter(
                (tool) =>
                    tool.name.toLowerCase().includes(term) ||
                    (tool.description || '').toLowerCase().includes(term),
            ),
        );
    }
    get selectedTool() {
        return this.state.tools.find((tool) => tool.name === this.state.selected);
    }
    /**
     * Load the tool catalog and select the last used tool, or the first one.
     * @returns {Promise<void>}
     */
    async loadTools() {
        const tools = await this.orm.call('muk_mcp.tool', 'get_playground_tools', []);
        const last = localStorage.getItem(LAST_TOOL_KEY);
        this.state.tools = tools;
        this.state.selected = (tools.find((t) => t.name === last) || tools[0])?.name;
    }
    onSelectPanel(id) {
        this.state.panel = id;
        localStorage.setItem(ACTIVE_PANEL_KEY, id);
    }
    onSelectTool(name) {
        this.state.selected = name;
        localStorage.setItem(LAST_TOOL_KEY, name);
    }
}

registry.category('actions').add('muk_mcp.playground', Playground);
