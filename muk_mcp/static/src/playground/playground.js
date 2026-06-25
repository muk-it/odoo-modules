import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useRef,
    useState,
} from '@odoo/owl';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';

import { MCPClient } from './mcp_client';
import { KeyBar } from './key_bar';
import { ToolList } from './tool_list';
import { ToolDetail } from './tool_detail';
import { groupTools } from './utils';

const LAST_TOOL_STORAGE_KEY = 'muk_mcp.playground.last_tool';
const ACTIVE_PANEL_STORAGE_KEY = 'muk_mcp.playground.active_panel';
const TOOLS_PANEL_ID = 'tools';

/**
 * Root client action rendering the MCP playground: tool browser, key bar, and
 * pluggable side panels contributed via the `muk_mcp.playground.panels` registry.
 */
export class Playground extends Component {
    static template = 'muk_mcp.Playground';
    static components = { KeyBar, ToolList, ToolDetail };
    static props = ['*'];
    setup() {
        this.orm = useService('orm');
        this.notification = useService('notification');
        this.client = new MCPClient();
        this.rootRef = useRef('root');
        this.toolsPanelId = TOOLS_PANEL_ID;
        this.state = useState({
            loading: true,
            tools: [],
            groups: [],
            search: '',
            selected: null,
            keyPrefix: this._currentPrefix(),
            hasKey: !!this.client.key,
            response: null,
            running: false,
            activePanel: this._initialActivePanel(),
        });
        onWillStart(async () => {
            await this.loadTools();
        });
        onMounted(() => {
            const search = this.rootRef.el?.querySelector(
                '.o_muk_mcp_list input[type=search]',
            );
            search?.focus();
        });
        onWillUnmount(() => {
            this.client.reset();
        });
    }
    _currentPrefix() {
        return this.client.key.slice(0, 8);
    }
    _initialActivePanel() {
        let stored;
        try {
            stored = localStorage.getItem(ACTIVE_PANEL_STORAGE_KEY);
        } catch {
            stored = null;
        }
        const valid = this.panels.some((p) => p.id === stored);
        return valid ? stored : TOOLS_PANEL_ID;
    }
    /**
     * Assemble the ordered panel list: the built-in Tools panel plus any panels
     * contributed to the `muk_mcp.playground.panels` registry, sorted by sequence.
     * @returns {object[]} panel definitions carrying `id`, `label`, `icon`, `sequence`
     */
    get panels() {
        const tools = {
            id: TOOLS_PANEL_ID,
            label: _t('Tools'),
            icon: 'fa-wrench',
            sequence: 0,
        };
        const extras = registry
            .category('muk_mcp.playground.panels')
            .getEntries()
            .map(([id, def]) => ({ id, sequence: 50, ...def }))
            .filter((p) => p.id !== TOOLS_PANEL_ID);
        return [tools, ...extras].sort((a, b) => a.sequence - b.sequence);
    }
    get activePanelDef() {
        const all = this.panels;
        return all.find((p) => p.id === this.state.activePanel) || all[0];
    }
    onSelectPanel(id) {
        this.state.activePanel = id;
        localStorage.setItem(ACTIVE_PANEL_STORAGE_KEY, id);
    }
    /**
     * Fetch the playground tool catalog, group it, and select an initial tool.
     * Restores the last-used tool from localStorage when nothing is selected yet.
     * @returns {Promise<void>}
     */
    async loadTools() {
        this.state.loading = true;
        try {
            const tools = await this.orm.call(
                'muk_mcp.tool',
                'get_playground_tools',
                [],
            );
            this.state.tools = tools;
            this.state.groups = groupTools(tools);
            if (!this.state.selected && tools.length) {
                const last = localStorage.getItem(LAST_TOOL_STORAGE_KEY);
                this.state.selected =
                    tools.find((t) => t.name === last)?.name || tools[0].name;
            }
        } catch (error) {
            this.notification.add(
                _t('Failed to load tools: %s', error.message || error),
                { type: 'danger' },
            );
        } finally {
            this.state.loading = false;
        }
    }
    /**
     * Filter the grouped tools by the search term against name and description.
     * @returns {Array} groups with non-matching tools and empty groups removed
     */
    get filteredGroups() {
        const term = this.state.search.trim().toLowerCase();
        if (!term) {
            return this.state.groups;
        }
        return this.state.groups
            .map(([cat, tools]) => [
                cat,
                tools.filter(
                    (t) =>
                        t.name.toLowerCase().includes(term) ||
                        (t.description || '').toLowerCase().includes(term),
                ),
            ])
            .filter(([, tools]) => tools.length > 0);
    }
    get selectedTool() {
        return this.state.tools.find((t) => t.name === this.state.selected);
    }
    onSelectTool(name) {
        this.state.selected = name;
        this.state.response = null;
        try {
            localStorage.setItem(LAST_TOOL_STORAGE_KEY, name);
        } catch {
            // localStorage can be unavailable (e.g. private mode); ignore
        }
    }
    onSearch(ev) {
        this.state.search = ev.target.value;
    }
    onKeyChanged() {
        this.state.keyPrefix = this._currentPrefix();
        this.state.hasKey = !!this.client.key;
        this.state.response = null;
    }
    /**
     * Run the selected tool against the MCP endpoint and store the response.
     * Warns and aborts when no key is set; captures thrown errors as an
     * exception response rather than propagating them.
     * @param {object} request
     * @param {string} request.name tool name
     * @param {object} request.args tool arguments
     * @returns {Promise<void>}
     */
    async onTryTool({ name, args }) {
        if (!this.client.key) {
            this.notification.add(_t('Select or generate an MCP key first.'), {
                type: 'warning',
            });
            return;
        }
        this.state.running = true;
        this.state.response = null;
        try {
            const result = await this.client.callTool(name, args);
            this.state.response = result;
        } catch (error) {
            this.state.response = {
                status: 0,
                duration: 0,
                body: null,
                raw: '',
                exception: error.message || String(error),
            };
        } finally {
            this.state.running = false;
        }
    }
}

registry.category('actions').add('muk_mcp.playground', Playground);
