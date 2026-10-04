import { Component, onWillStart, proxy, usePlugin } from '@odoo/owl';
import { CopyButton } from '@web/core/copy_button/copy_button';
import { _t } from '@web/core/l10n/translation';
import { ORM } from '@web/core/orm_plugin';
import { registry } from '@web/core/registry';
import { useDebounced } from '@web/core/utils/timing';

import { KeyBar } from '@muk_mcp/playground/key_bar/key_bar';
import { MCPClient } from '@muk_mcp/playground/mcp_client/mcp_client';
import { cleanValue, statusClass } from '@muk_mcp/playground/utils/utils';

const LAST_PROMPT_KEY = 'muk_mcp.playground.last_prompt';
const ARGS_KEY_PREFIX = 'muk_mcp.playground.prompt_args::';

/**
 * Playground panel to browse the prompts, fill their arguments with server-side
 * completion, and preview what prompts/get renders.
 */
export class PromptsPanel extends Component {
    static template = 'muk_mcp.PromptsPanel';
    static components = { CopyButton, KeyBar };
    mcp = usePlugin(MCPClient);
    orm = usePlugin(ORM);
    state = proxy({
        prompts: [],
        search: '',
        selected: null,
        args: {},
        completions: {},
        response: null,
        running: false,
    });
    statusClass = statusClass;
    complete = useDebounced(this.fetchCompletions.bind(this), 200);
    setup() {
        onWillStart(() => this.loadPrompts());
    }
    get filteredPrompts() {
        const term = this.state.search.trim().toLowerCase();
        return this.state.prompts.filter((prompt) =>
            [prompt.name, prompt.title, prompt.description].some((text) =>
                (text || '').toLowerCase().includes(term),
            ),
        );
    }
    get prompt() {
        return this.state.prompts.find((prompt) => prompt.name === this.state.selected);
    }
    get params() {
        return { name: this.state.selected, arguments: cleanValue(this.state.args) };
    }
    get canRun() {
        return !this.state.running && Boolean(this.mcp.key());
    }
    get messages() {
        return this.state.response.body?.result?.messages || [];
    }
    /**
     * Load the prompt catalog and select the last used prompt, or the first one.
     * @returns {Promise<void>}
     */
    async loadPrompts() {
        const prompts = await this.orm.call(
            'muk_mcp.prompt',
            'get_playground_prompts',
            [],
        );
        const last = localStorage.getItem(LAST_PROMPT_KEY);
        this.state.prompts = prompts;
        const prompt = prompts.find((p) => p.name === last) || prompts[0];
        if (prompt) {
            this.onSelect(prompt.name);
        }
    }
    /**
     * Select a prompt and restore the arguments last entered for it.
     * @param {string} name prompt name
     */
    onSelect(name) {
        localStorage.setItem(LAST_PROMPT_KEY, name);
        Object.assign(this.state, {
            selected: name,
            args: JSON.parse(localStorage.getItem(ARGS_KEY_PREFIX + name)) || {},
            completions: {},
            response: null,
        });
    }
    /**
     * Store an argument for the selected prompt and ask for its completions.
     * @param {string} name argument name
     * @param {string} value entered value
     */
    setArg(name, value) {
        this.state.args = { ...this.state.args, [name]: value };
        localStorage.setItem(
            ARGS_KEY_PREFIX + this.state.selected,
            JSON.stringify(this.state.args),
        );
        if (this.mcp.key()) {
            this.complete(name, value);
        }
    }
    /**
     * Fetch the completion values of an argument via completion/complete.
     * @param {string} name argument name
     * @param {string} value entered value
     * @returns {Promise<void>}
     */
    async fetchCompletions(name, value) {
        const response = await this.mcp.request('completion/complete', {
            ref: { type: 'ref/prompt', name: this.state.selected },
            argument: { name, value },
        });
        this.state.completions[name] = response.body?.result?.completion?.values || [];
    }
    onReset() {
        this.state.args = {};
        localStorage.removeItem(ARGS_KEY_PREFIX + this.state.selected);
    }
    onKeyDown(ev) {
        if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter' && this.canRun) {
            ev.preventDefault();
            this.onGet();
        }
    }
    async onGet() {
        this.state.running = true;
        this.state.response = null;
        try {
            this.state.response = await this.mcp.request('prompts/get', this.params);
        } finally {
            this.state.running = false;
        }
    }
    /**
     * Render the content of a prompt message, structured content as JSON.
     * @param {object} message prompt message with a `content` field
     * @returns {string} the text to display
     */
    messageText(message) {
        const content = message.content;
        return content?.type === 'text'
            ? content.text
            : JSON.stringify(content, null, 2);
    }
}

registry.category('muk_mcp.playground.panels').add('prompts', {
    label: _t('Prompts'),
    icon: 'chat_bubble',
    sequence: 10,
    component: PromptsPanel,
});
