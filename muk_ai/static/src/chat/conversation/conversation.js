import {
    Component,
    Resource,
    signal,
    t,
    useEffect,
    useListener,
    useOnChange,
    useProps,
    usePlugin,
} from '@odoo/owl';

import { useDropzone } from '@web/core/dropzone/dropzone_hook';
import { UIPlugin } from '@web/core/ui/ui_plugin';

import { transferFiles } from '@muk_ai/core/attachment/attachment';
import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { renderMarkdown } from '@muk_ai/core/markdown/markdown';
import { ChatComposer } from '@muk_ai/chat/composer/composer';
import { ContextChip } from '@muk_ai/chat/context_chip/context_chip';
import { ShareBar } from '@muk_ai/chat/share/share';
import { ToolCard } from '@muk_ai/chat/tool_card/tool_card';
import { ChatTurn } from '@muk_ai/chat/turn/turn';

const NEAR_BOTTOM = 160;
const NEAR_TOP = 200;

/**
 * Components drawn after the transcript of every chat, with the prop `session`.
 */
export const transcriptFooters = new Resource({
    name: 'muk_ai.transcript_footers',
    validation: t.component(),
});

/**
 * Components drawn above the composer of every chat, with the prop `session`.
 */
export const composerAccessories = new Resource({
    name: 'muk_ai.composer_accessories',
    validation: t.component(),
});

/**
 * Pick the prompt suggestions of an agent that carry a prompt.
 * @param {object} agent the agent, with its `suggestions` JSON
 * @returns {Array} `{label, prompt, preview}` entries, the preview in plain text
 */
export function agentSuggestions(agent) {
    return (Array.isArray(agent?.suggestions) ? agent.suggestions : [])
        .filter(
            (suggestion) =>
                typeof suggestion?.prompt === 'string' && suggestion.prompt.trim(),
        )
        .map(({ label, prompt }) => ({
            label: (typeof label === 'string' && label) || prompt,
            prompt,
            preview: prompt
                .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
                .replace(/[*_`#>]/g, ''),
        }));
}

/**
 * A chat as both surfaces draw it: the transcript with the streaming turn,
 * the queue and errors, followed while it grows, loading older events near
 * its top, taking pasted and dropped files, and the composer under it.
 */
export class ChatConversation extends Component {
    static template = 'muk_ai.ChatConversation';
    static components = { ChatComposer, ChatTurn, ContextChip, ShareBar, ToolCard };
    props = useProps({
        session: t.object(),
        compact: t.boolean().optional(false),
        placeholder: t.string().optional(''),
        onForked: t.function().optional(),
    });
    chat = usePlugin(AIChatPlugin);
    ui = usePlugin(UIPlugin);
    root = signal.ref();
    scroller = signal.ref();
    inner = signal.ref();
    atBottom = signal(true);
    footers = transcriptFooters.items;
    accessories = composerAccessories.items;
    renderMarkdown = renderMarkdown;
    setup() {
        this.anchored = true;
        this.lastTop = 0;
        this.chat.loadAgents();
        useEffect(() => {
            const scroller = this.scroller();
            const inner = this.inner();
            if (scroller && inner) {
                const observer = new ResizeObserver(
                    () => this.anchored && this.scrollToBottom(),
                );
                observer.observe(scroller);
                observer.observe(inner);
                return () => observer.disconnect();
            }
        });
        useEffect(() => {
            const bus = this.props.session.bus;
            const follow = () => this.scrollToBottom();
            bus.addEventListener('sent', follow);
            return () => bus.removeEventListener('sent', follow);
        });
        useOnChange(
            () => [this.props.session],
            () => this.scrollToBottom(),
        );
        useListener(this.scroller, 'scroll', () => this.onScroll(), { passive: true });
        useListener(document, 'paste', (ev) => this.onPaste(ev));
        useDropzone(
            this.root,
            (ev) => this.props.session.attach([...ev.dataTransfer.files]),
            'mk_chat_dropzone',
            () => this.props.session.canAttach,
        );
    }
    get suggestions() {
        const agents = this.chat.agents();
        const id = this.props.session.data.agent_id?.[0];
        return agentSuggestions(agents.find((agent) => agent.id === id) || agents[0]);
    }
    scrollToBottom() {
        this.anchored = true;
        this.atBottom.set(true);
        const scroller = this.scroller();
        if (scroller && this.props.session.turns.length) {
            scroller.scrollTop = scroller.scrollHeight;
        }
    }
    onScroll() {
        const scroller = this.scroller();
        const top = scroller.scrollTop;
        this.anchored =
            scroller.scrollHeight - top - scroller.clientHeight <= NEAR_BOTTOM;
        this.atBottom.set(this.anchored);
        if (top < this.lastTop && top <= NEAR_TOP) {
            this.loadOlder();
        }
        this.lastTop = top;
    }
    /**
     * Load the page of events before the oldest one shown, keeping what the
     * user looks at in place.
     */
    async loadOlder() {
        const { session } = this.props;
        const scroller = this.scroller();
        if (!scroller || session.state.loadingOlder || !session.state.hasMoreOlder) {
            return;
        }
        const fromBottom = scroller.scrollHeight - scroller.scrollTop;
        await session.loadMoreEvents();
        requestAnimationFrame(
            () => (scroller.scrollTop = scroller.scrollHeight - fromBottom),
        );
    }
    onPaste(ev) {
        const files = transferFiles(ev.clipboardData);
        const inside = this.root()?.contains(ev.target) || ev.target === document.body;
        if (
            files.length &&
            inside &&
            !ev.defaultPrevented &&
            this.props.session.canAttach
        ) {
            ev.preventDefault();
            this.props.session.attach(files);
        }
    }
    onSuggestion(prompt) {
        this.props.session.state.input = prompt;
        this.props.session.send();
    }
}
