/** @odoo-module */

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

import { MCPClient } from "./mcp_client";
import { KeyBar } from "./key_bar";
import { ToolList } from "./tool_list";
import { ToolDetail } from "./tool_detail";
import { groupTools } from "./utils";

const LAST_TOOL_STORAGE_KEY = "muk_mcp.playground.last_tool";

export class Playground extends Component {
    static template = "muk_mcp.Playground";
    static components = { KeyBar, ToolList, ToolDetail };
    static props = ["*"];
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.client = new MCPClient();
        this.rootRef = useRef("root");
        this.state = useState({
            loading: true,
            tools: [],
            groups: [],
            search: "",
            selected: null,
            keyPrefix: this._currentPrefix(),
            hasKey: !!this.client.key,
            response: null,
            running: false,
        });
        onWillStart(async () => {
            await this.loadTools();
        });
        onMounted(() => {
            const search = this.rootRef.el?.querySelector(
                ".o_muk_mcp_list input[type=search]"
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
    async loadTools() {
        this.state.loading = true;
        try {
            const tools = await this.orm.call(
                "muk_mcp.tool",
                "get_playground_tools",
                []
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
                _t("Failed to load tools: %s", error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }
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
                        (t.description || "").toLowerCase().includes(term)
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
    async onTryTool({ name, args }) {
        if (!this.client.key) {
            this.notification.add(
                _t("Select or generate an MCP key first."),
                { type: "warning" }
            );
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
                raw: "",
                exception: error.message || String(error),
            };
        } finally {
            this.state.running = false;
        }
    }
}

registry.category("actions").add("muk_mcp.playground", Playground);
