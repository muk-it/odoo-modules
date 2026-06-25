const MCP_ENDPOINT = '/mcp';
const PROTOCOL_VERSION = '2025-03-26';
export const STORAGE_KEY = 'muk_mcp.playground.key';

/**
 * Stateful JSON-RPC client for the MCP endpoint, handling session lifecycle,
 * lazy initialization, and bearer-key persistence in sessionStorage.
 */
export class MCPClient {
    constructor() {
        this.sessionId = null;
        this.initialized = false;
        this._nextId = 1;
    }
    get key() {
        return sessionStorage.getItem(STORAGE_KEY) || '';
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
    /**
     * Assemble request headers, adding auth and session headers when available.
     * @param {object} extra additional headers to merge in
     * @returns {object} the complete header map
     */
    _headers(extra = {}) {
        const headers = {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            ...extra,
        };
        if (this.key) {
            headers['Authorization'] = `Bearer ${this.key}`;
        }
        if (this.sessionId) {
            headers['Mcp-Session-Id'] = this.sessionId;
        }
        return headers;
    }
    /**
     * POST a JSON-RPC body to the endpoint and capture any returned session id.
     * @param {object} body JSON-RPC request payload
     * @returns {Promise<object>} `{ status, body, raw }` with the parsed and raw response
     */
    async _post(body) {
        const res = await fetch(MCP_ENDPOINT, {
            method: 'POST',
            headers: this._headers(),
            body: JSON.stringify(body),
        });
        const sid = res.headers.get('Mcp-Session-Id');
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
    /**
     * Perform the MCP initialize handshake once per session.
     * @returns {Promise<void>}
     * @throws {Error} if the initialize call fails
     */
    async _ensureInitialized() {
        if (this.initialized) {
            return;
        }
        const init = await this._post({
            jsonrpc: '2.0',
            id: this._nextId++,
            method: 'initialize',
            params: {
                protocolVersion: PROTOCOL_VERSION,
                capabilities: {},
                clientInfo: { name: 'muk_mcp.playground', version: '1.0' },
            },
        });
        if (init.status !== 200 || !init.body || init.body.error) {
            throw new Error(
                init.body?.error?.message || `Initialize failed (HTTP ${init.status})`,
            );
        }
        await this._post({
            jsonrpc: '2.0',
            method: 'notifications/initialized',
            params: {},
        });
        this.initialized = true;
    }
    /**
     * Invoke a tool, retrying once after re-initializing on a stale-session 404.
     * @param {string} name tool name
     * @param {object} args tool arguments
     * @param {object} [options]
     * @param {boolean} [options.retried] internal flag guarding against infinite retry
     * @returns {Promise<object>} `{ status, duration, body, raw }`
     */
    async callTool(name, args, { retried = false } = {}) {
        await this._ensureInitialized();
        const started = performance.now();
        const res = await this._post({
            jsonrpc: '2.0',
            id: this._nextId++,
            method: 'tools/call',
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
    /**
     * List the available prompts via prompts/list.
     * @returns {Promise<object>} the raw `{ status, body, raw }` response
     */
    async getPrompts() {
        await this._ensureInitialized();
        const res = await this._post({
            jsonrpc: '2.0',
            id: this._nextId++,
            method: 'prompts/list',
            params: {},
        });
        return res;
    }
    /**
     * Fetch a rendered prompt via prompts/get, retrying once on a stale-session 404.
     * @param {string} name prompt name
     * @param {object} args prompt arguments
     * @param {object} [options]
     * @param {boolean} [options.retried] internal flag guarding against infinite retry
     * @returns {Promise<object>} `{ status, duration, body, raw }`
     */
    async getPrompt(name, args, { retried = false } = {}) {
        await this._ensureInitialized();
        const started = performance.now();
        const res = await this._post({
            jsonrpc: '2.0',
            id: this._nextId++,
            method: 'prompts/get',
            params: { name, arguments: args || {} },
        });
        const duration = Math.round(performance.now() - started);
        if (res.status === 404 && !retried) {
            this.sessionId = null;
            this.initialized = false;
            return this.getPrompt(name, args, { retried: true });
        }
        return {
            status: res.status,
            duration,
            body: res.body,
            raw: res.raw,
        };
    }
    /**
     * Request argument autocompletion via completion/complete.
     * @param {object} ref completion reference (e.g. `{ type, name }`)
     * @param {object} argument the argument `{ name, value }` being completed
     * @param {object} [options]
     * @param {boolean} [options.retried] internal flag guarding against infinite retry
     * @returns {Promise<Array>} the suggested completion values (empty when none)
     */
    async complete(ref, argument, { retried = false } = {}) {
        await this._ensureInitialized();
        const res = await this._post({
            jsonrpc: '2.0',
            id: this._nextId++,
            method: 'completion/complete',
            params: { ref, argument },
        });
        if (res.status === 404 && !retried) {
            this.sessionId = null;
            this.initialized = false;
            return this.complete(ref, argument, { retried: true });
        }
        return res.body?.result?.completion?.values || [];
    }
    /**
     * Tear down the current session, best-effort deleting it server-side.
     * @returns {Promise<void>}
     */
    async reset() {
        if (this.sessionId) {
            try {
                await fetch(MCP_ENDPOINT, {
                    method: 'DELETE',
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
