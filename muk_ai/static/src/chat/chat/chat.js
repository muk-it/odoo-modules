import {
    Component,
    onWillStart,
    proxy,
    signal,
    untrack,
    useEffect,
    useListener,
    useProps,
    usePlugin,
} from '@odoo/owl';

import { browser } from '@web/core/browser/browser';
import { Dropdown } from '@web/core/dropdown/dropdown';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { UIPlugin } from '@web/core/ui/ui_plugin';

import { AIChatPlugin, useAISession } from '@muk_ai/core/chat_plugin/chat_plugin';
import { ArtifactsPanel } from '@muk_ai/chat/artifacts/artifacts';
import { ContextChip } from '@muk_ai/chat/context_chip/context_chip';
import {
    agentSuggestions,
    ChatConversation,
} from '@muk_ai/chat/conversation/conversation';
import { ChatSearch } from '@muk_ai/chat/search/search';
import { ChatSidebar } from '@muk_ai/chat/sidebar/sidebar';
import { SessionStatus } from '@muk_ai/chat/status/status';

/** Full-page AI chat: the sidebar, the chat, its search and its artifacts. */
export class AIChat extends Component {
    static template = 'muk_ai.Chat';
    static path = 'ai-chat';
    static displayName = _t('MuK AI Chat');
    static components = {
        ArtifactsPanel,
        ChatConversation,
        ChatSearch,
        ChatSidebar,
        ContextChip,
        Dropdown,
        DropdownItem,
        SessionStatus,
    };
    props = useProps();
    chat = usePlugin(AIChatPlugin);
    ui = usePlugin(UIPlugin);
    main = signal.ref();
    state = proxy({
        sessionId: null,
        ready: false,
        sidebarHidden: false,
        artifactsHidden: true,
        focus: null,
        searchOpen: false,
    });
    session = useAISession(() => this.state.sessionId);
    setup() {
        onWillStart(async () => {
            const requested = Number(this.props.action.params?.session_id);
            const shown = requested || this.props.resId;
            await Promise.all([this.chat.loadAgents(), shown || this.selectFirst()]);
            if (shown) {
                this.select(shown);
            }
            this.state.sidebarHidden = Boolean(requested) || this.ui.isSmall();
            this.state.ready = true;
        });
        useEffect(() => {
            this.chat.pageSessionId = this.state.sessionId;
            return () => (this.chat.pageSessionId = null);
        });
        useEffect(() => {
            if (this.session()?.state.missing) {
                untrack(() => {
                    this.chat.notification.add(
                        _t('That AI session no longer exists.'),
                        {
                            type: 'warning',
                        },
                    );
                    this.selectFirst();
                });
            }
        });
        useEffect(() => {
            const bus = this.session()?.bus;
            const focus = ({ detail }) => this.openArtifacts(detail);
            bus?.addEventListener('artifact', focus);
            return () => bus?.removeEventListener('artifact', focus);
        });
        useListener(this.chat.events, 'session_state', ({ detail }) => {
            if (detail.deleted && detail.session_id === this.state.sessionId) {
                this.selectFirst();
            }
        });
    }
    get suggestions() {
        return agentSuggestions(this.chat.agents()[0]);
    }
    get agentTitle() {
        return this.session().readonly
            ? _t('The agent of a shared chat cannot be changed')
            : _t('Switch agent');
    }
    get placeholder() {
        return this.ui.isSmall()
            ? _t('Message the assistant...')
            : _t('Message the assistant... (Enter to send, Shift+Enter for newline)');
    }
    /**
     * Show a chat, or the welcome page without one.
     * @param {number|null} id the chat
     */
    select(id) {
        this.state.sessionId = id || null;
        if (this.ui.isSmall()) {
            this.state.sidebarHidden = true;
        }
        this.props.updateActionState({ resId: id || false });
    }
    /**
     * Show the most recent chat of the user, or none.
     */
    async selectFirst() {
        const [first] = await this.chat.orm.searchRead(
            'muk_ai.session',
            this.chat.chatDomain,
            ['id'],
            { limit: 1, order: 'create_date DESC' },
        );
        this.select(first?.id);
    }
    /**
     * Start a chat on the view on screen, moving over what is typed while it
     * is created.
     * @param {object} [values] extra values of the new chat
     * @returns {Promise<number>} the new chat
     */
    async newSession(values = {}) {
        const previous = this.session();
        const draft = previous?.state.input;
        const id = await this.chat.createSession(values);
        if (previous && previous.state.input !== draft) {
            this.chat.session(id).state.input = previous.state.input.slice(
                draft.length,
            );
            previous.state.input = draft;
        }
        this.select(id);
        return id;
    }
    async startWithPrompt(prompt) {
        const session = this.chat.acquire(await this.newSession());
        await session.ready;
        session.state.input = prompt;
        await session.send();
        this.chat.release(session.id);
    }
    openArtifacts(focus = null) {
        Object.assign(this.state, { artifactsHidden: false, focus });
        if (browser.innerWidth < 1200) {
            this.state.sidebarHidden = true;
        }
    }
    toggleArtifacts() {
        if (this.state.artifactsHidden) {
            this.openArtifacts();
        } else {
            this.state.artifactsHidden = true;
        }
    }
}

registry.category('actions').add('muk_ai.chat', AIChat);
