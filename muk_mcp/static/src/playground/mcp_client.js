/** @odoo-module */

const MCP_ENDPOINT = "/mcp";
const PROTOCOL_VERSION = "2025-03-26";
export const STORAGE_KEY = "muk_mcp.playground.key";

export class MCPClient {
    constructor() {
        this.sessionId = null;
        this.initialized = false;
        this._nextId = 1;
    }
    get key() {
        return sessionStorage.getItem(STORAGE_KEY) || "";
    }
    set key(value) {
        if (value) {
            sessionStorage.setItem(STORAGE_KEY, value);
        } else {
            sessionStorage.removeItem(STORAGE_KEY);
        }
        this.sessionId = null;
        this.initialized = false;
    }
    _headers(extra = {}) {
        const headers = {
            "Content-Type": "application/json",
            Accept: "application/json",
            ...extra,
        };
        if (this.key) {
            headers["Authorization"] = `Bearer ${this.key}`;
        }
        if (this.sessionId) {
            headers["Mcp-Session-Id"] = this.sessionId;
        }
        return headers;
    }
    async _post(body) {
        const res = await fetch(MCP_ENDPOINT, {
            method: "POST",
            headers: this._headers(),
            body: JSON.stringify(body),
        });
        const sid = res.headers.get("Mcp-Session-Id");
        if (sid) {
            this.sessionId = sid;
        }
        const text = await res.text();
        let json;
        try {
            json = text ? JSON.parse(text) : null;
        } catch {
            json = null;
        }
        return { status: res.status, body: json, raw: text };
    }
    async _ensureInitialized() {
        if (this.initialized) {
            return;
        }
        const init = await this._post({
            jsonrpc: "2.0",
            id: this._nextId++,
            method: "initialize",
            params: {
                protocolVersion: PROTOCOL_VERSION,
                capabilities: {},
                clientInfo: { name: "muk_mcp.playground", version: "1.0" },
            },
        });
        if (init.status !== 200 || !init.body || init.body.error) {
            throw new Error(
                init.body?.error?.message ||
                    `Initialize failed (HTTP ${init.status})`
            );
        }
        await this._post({
            jsonrpc: "2.0",
            method: "notifications/initialized",
            params: {},
        });
        this.initialized = true;
    }
    async callTool(name, args, { retried = false } = {}) {
        await this._ensureInitialized();
        const started = performance.now();
        const res = await this._post({
            jsonrpc: "2.0",
            id: this._nextId++,
            method: "tools/call",
            params: { name, arguments: args },
        });
        const duration = Math.round(performance.now() - started);
        if (res.status === 404 && !retried) {
            this.sessionId = null;
            this.initialized = false;
            return this.callTool(name, args, { retried: true });
        }
        return {
            status: res.status,
            duration,
            body: res.body,
            raw: res.raw,
        };
    }
    async reset() {
        if (this.sessionId) {
            try {
                await fetch(MCP_ENDPOINT, {
                    method: "DELETE",
                    headers: this._headers(),
                });
            } catch {
                // best effort
            }
        }
        this.sessionId = null;
        this.initialized = false;
    }
}
