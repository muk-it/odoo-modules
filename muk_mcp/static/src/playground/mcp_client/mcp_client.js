import { Plugin, signal } from '@odoo/owl';

const ENDPOINT = '/api/mcp';
const PROTOCOL_VERSION = '2025-11-25';
const STORAGE_KEY = 'muk_mcp.playground.key';

/**
 * Stateless JSON-RPC client for the MCP endpoint, holding the bearer key of the
 * current tab in sessionStorage.
 */
export class MCPClient extends Plugin {
    key = signal(sessionStorage.getItem(STORAGE_KEY) || '');
    nextId = 1;
    setKey(value) {
        this.key.set(value);
        if (value) {
            sessionStorage.setItem(STORAGE_KEY, value);
        } else {
            sessionStorage.removeItem(STORAGE_KEY);
        }
    }
    /**
     * Build the JSON-RPC request body of a method call.
     * @param {string} method MCP method name
     * @param {object} params method parameters
     * @param {number} [id] JSON-RPC request id
     * @returns {object} the request body
     */
    payload(method, params, id = 1) {
        return { jsonrpc: '2.0', id, method, params };
    }
    /**
     * Render a method call as an indented JSON-RPC body to copy.
     * @param {string} method MCP method name
     * @param {object} params method parameters
     * @returns {string} the indented request body
     */
    jsonrpc(method, params) {
        return JSON.stringify(this.payload(method, params), null, 2);
    }
    /**
     * Render a method call as a curl command to copy.
     * @param {string} method MCP method name
     * @param {object} params method parameters
     * @returns {string} a multi-line curl command
     */
    curl(method, params) {
        return [
            `curl -X POST '${window.location.origin}${ENDPOINT}' \\`,
            `  -H 'Authorization: Bearer ${this.key() || '<YOUR_MCP_KEY>'}' \\`,
            `  -H 'Content-Type: application/json' \\`,
            `  -H 'MCP-Protocol-Version: ${PROTOCOL_VERSION}' \\`,
            `  -d '${JSON.stringify(this.payload(method, params))}'`,
        ].join('\n');
    }
    /**
     * POST a method call to the endpoint.
     * @param {string} method MCP method name
     * @param {object} params method parameters
     * @returns {Promise<object>} `{ status, duration, body, raw }`, `raw` being the
     *   indented body, or the response text when it is not JSON
     */
    async request(method, params) {
        const started = performance.now();
        const response = await fetch(ENDPOINT, {
            method: 'POST',
            headers: {
                Accept: 'application/json',
                Authorization: `Bearer ${this.key()}`,
                'Content-Type': 'application/json',
                'MCP-Protocol-Version': PROTOCOL_VERSION,
            },
            body: JSON.stringify(this.payload(method, params, this.nextId++)),
        });
        const text = await response.text();
        let body;
        try {
            body = JSON.parse(text);
        } catch {
            body = null;
        }
        return {
            status: response.status,
            duration: Math.round(performance.now() - started),
            body,
            raw: body ? JSON.stringify(body, null, 2) : text,
        };
    }
}
