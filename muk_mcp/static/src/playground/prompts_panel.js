import { Component, onWillStart, useState } from '@odoo/owl';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';

import { MCPClient, STORAGE_KEY } from '@muk_mcp/playground/mcp_client';
import { KeyBar } from '@muk_mcp/playground/key_bar';

const LAST_PROMPT_STORAGE_KEY = 'muk_mcp.playground.last_prompt';
const ARGS_STORAGE_PREFIX = 'muk_mcp.playground.prompt_args::';

export class PromptsPanel extends Component {
    static template = 'muk_mcp.PromptsPanel';
    static components = { KeyBar };
    static props = ['*'];
    setup() {
        this.orm = useService('orm');
        this.notification = useService('notification');
        this.client = new MCPClient();
        this.state = useState({
            loading: true,
            prompts: [],
            selected: null,
            search: '',
            argsByName: {},
            completions: {},
            response: null,
            running: false,
            hasKey: !!this.client.key,
            keyPrefix: this.client.key.slice(0, 8),
        });
        this._completeTimers = {};
        onWillStart(async () => {
            await this.loadPrompts();
        });
    }
    async loadPrompts() {
        this.state.loading = true;
        try {
            const prompts = await this.orm.call(
                'muk_mcp.prompt',
                'get_playground_prompts',
                [],
            );
            this.state.prompts = prompts;
            if (!this.state.selected && prompts.length) {
                const last = localStorage.getItem(LAST_PROMPT_STORAGE_KEY);
                this.state.selected =
                    prompts.find((p) => p.name === last)?.name || prompts[0].name;
            }
        } catch (error) {
            this.notification.add(
                _t('Failed to load prompts: %s', error.message || error),
                { type: 'danger' },
            );
        } finally {
            this.state.loading = false;
        }
    }
    get filteredPrompts() {
        const term = this.state.search.trim().toLowerCase();
        if (!term) {
            return this.state.prompts;
        }
        return this.state.prompts.filter(
            (p) =>
                p.name.toLowerCase().includes(term) ||
                (p.title || '').toLowerCase().includes(term) ||
                (p.description || '').toLowerCase().includes(term),
        );
    }
    get selectedPrompt() {
        return this.state.prompts.find((p) => p.name === this.state.selected) || null;
    }
    get currentArgs() {
        const prompt = this.selectedPrompt;
        if (!prompt) {
            return {};
        }
        if (prompt.name in this.state.argsByName) {
            return this.state.argsByName[prompt.name];
        }
        const persisted = this._restoreArgs(prompt.name);
        const seed = persisted || {};
        if (!persisted) {
            for (const arg of prompt.arguments || []) {
                seed[arg.name] = '';
            }
        }
        this.state.argsByName[prompt.name] = seed;
        return seed;
    }
    _restoreArgs(name) {
        try {
            const raw = localStorage.getItem(ARGS_STORAGE_PREFIX + name);
            const parsed = raw ? JSON.parse(raw) : null;
            return parsed && typeof parsed === 'object' ? parsed : null;
        } catch {
            return null;
        }
    }
    _persistArgs(name, args) {
        try {
            localStorage.setItem(
                ARGS_STORAGE_PREFIX + name,
                JSON.stringify(args || {}),
            );
        } catch {
            // localStorage can be unavailable; ignore
        }
    }
    onSearch(ev) {
        this.state.search = ev.target.value;
    }
    onSelect(name) {
        this.state.selected = name;
        this.state.response = null;
        this.state.completions = {};
        try {
            localStorage.setItem(LAST_PROMPT_STORAGE_KEY, name);
        } catch {
            // ignore
        }
    }
    onKeyChanged() {
        this.state.hasKey = !!this.client.key;
        this.state.keyPrefix = this.client.key.slice(0, 8);
    }
    argValue(argName) {
        return this.currentArgs[argName] ?? '';
    }
    completionsFor(argName) {
        return this.state.completions[argName] || [];
    }
    onArgInput(argName, ev) {
        const prompt = this.selectedPrompt;
        if (!prompt) {
            return;
        }
        const next = { ...this.currentArgs, [argName]: ev.target.value };
        this.state.argsByName[prompt.name] = next;
        this._persistArgs(prompt.name, next);
        this._scheduleComplete(argName, ev.target.value);
    }
    _scheduleComplete(argName, value) {
        const prompt = this.selectedPrompt;
        if (!prompt || !this.client.key) {
            return;
        }
        clearTimeout(this._completeTimers[argName]);
        this._completeTimers[argName] = setTimeout(async () => {
            try {
                const values = await this.client.complete(
                    { type: 'ref/prompt', name: prompt.name },
                    { name: argName, value: value || '' },
                );
                this.state.completions = {
                    ...this.state.completions,
                    [argName]: values,
                };
            } catch {
                // completion is best-effort; ignore errors
            }
        }, 200);
    }
    onReset() {
        const prompt = this.selectedPrompt;
        if (!prompt) {
            return;
        }
        const seed = {};
        for (const arg of prompt.arguments || []) {
            seed[arg.name] = '';
        }
        this.state.argsByName[prompt.name] = seed;
        this._persistArgs(prompt.name, seed);
    }
    _cleanArgs() {
        const out = {};
        for (const [k, v] of Object.entries(this.currentArgs)) {
            if (v !== '' && v !== null && v !== undefined) {
                out[k] = v;
            }
        }
        return out;
    }
    async onGet() {
        const prompt = this.selectedPrompt;
        if (!prompt || this.state.running) {
            return;
        }
        this.state.running = true;
        this.state.response = null;
        try {
            this.state.response = await this.client.getPrompt(
                prompt.name,
                this._cleanArgs(),
            );
        } catch (error) {
            this.notification.add(
                _t('prompts/get failed: %s', error.message || error),
                { type: 'danger' },
            );
        } finally {
            this.state.running = false;
            this.onKeyChanged();
        }
    }
    onKeyDown(ev) {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter') {
            ev.preventDefault();
            if (!this.state.running && this.state.hasKey) {
                this.onGet();
            }
        }
    }
    get messages() {
        return this.state.response?.body?.result?.messages || [];
    }
    get responseError() {
        const body = this.state.response?.body;
        if (body?.error) {
            return `JSON-RPC error ${body.error.code}: ${body.error.message}`;
        }
        return null;
    }
    get responseDescription() {
        return this.state.response?.body?.result?.description || '';
    }
    messageText(message) {
        const content = message.content;
        if (content && typeof content === 'object') {
            if (content.type === 'text') {
                return content.text;
            }
            return JSON.stringify(content, null, 2);
        }
        return String(content ?? '');
    }
    get rawBody() {
        const res = this.state.response;
        if (!res) {
            return '';
        }
        if (res.body === null || res.body === undefined) {
            return res.raw || '';
        }
        try {
            return JSON.stringify(res.body, null, 2);
        } catch {
            return String(res.body);
        }
    }
    get statusClass() {
        const status = this.state.response?.status;
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
    _payload() {
        return {
            jsonrpc: '2.0',
            id: 1,
            method: 'prompts/get',
            params: {
                name: this.selectedPrompt?.name,
                arguments: this._cleanArgs(),
            },
        };
    }
    async _copy(text, message) {
        try {
            await navigator.clipboard.writeText(text);
            this.notification.add(message, { type: 'success' });
        } catch {
            this.notification.add(_t('Clipboard unavailable'), { type: 'danger' });
        }
    }
    onCopyCurl() {
        if (!this.selectedPrompt) {
            return;
        }
        const key = sessionStorage.getItem(STORAGE_KEY) || '<YOUR_MCP_KEY>';
        const auth = key ? ` \\\n  -H 'Authorization: Bearer ${key}'` : '';
        const curl = [
            `curl -X POST '${window.location.origin}/mcp'${auth} \\`,
            `  -H 'Content-Type: application/json' \\`,
            `  -H 'Accept: application/json' \\`,
            `  -d '${JSON.stringify(this._payload())}'`,
        ].join('\n');
        this._copy(curl, _t('curl copied'));
    }
    onCopyJsonRpc() {
        if (!this.selectedPrompt) {
            return;
        }
        this._copy(
            JSON.stringify(this._payload(), null, 2),
            _t('JSON-RPC payload copied'),
        );
    }
}

registry.category('muk_mcp.playground.panels').add('prompts', {
    label: _t('Prompts'),
    icon: 'fa-comment-o',
    sequence: 10,
    component: PromptsPanel,
});
