import {
    Component,
    onMounted,
    proxy,
    signal,
    t,
    useEffect,
    useOnChange,
    useProps,
    usePlugin,
} from '@odoo/owl';

import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';
import { _t } from '@web/core/l10n/translation';
import { UIPlugin } from '@web/core/ui/ui_plugin';
import { useAutoresize } from '@web/core/utils/autoresize';

import { AttachmentCard, toFileModel } from '@muk_ai/core/attachment/attachment';
import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { slashCommands } from '@muk_ai/core/session/session';
import { SessionPills } from '@muk_ai/chat/pills/pills';
import { ToolsMenu } from '@muk_ai/chat/tools_menu/tools_menu';
import { UsageMeter } from '@muk_ai/chat/usage/usage';

const ACCEPT = [
    'image/png',
    'image/jpeg',
    'image/webp',
    'image/gif',
    'application/pdf',
    'text/plain',
    'text/csv',
    'text/markdown',
    '.md',
].join(',');

/**
 * Message box of a chat: text, attachments, slash commands and the agent
 * picker, send, queue and stop. On a chat the user may only read it states
 * so instead of drawing its input row.
 */
export class ChatComposer extends Component {
    static template = 'muk_ai.ChatComposer';
    static components = { AttachmentCard, SessionPills, ToolsMenu, UsageMeter };
    props = useProps({
        session: t.object(),
        placeholder: t.string().optional(''),
        showMeta: t.boolean().optional(true),
    });
    chat = usePlugin(AIChatPlugin);
    ui = usePlugin(UIPlugin);
    fileViewer = useFileViewer();
    textarea = signal.ref();
    state = proxy({ active: 0 });
    accept = ACCEPT;
    setup() {
        useAutoresize(this.textarea);
        useOnChange(
            () => [this.items.length],
            () => (this.state.active = 0),
        );
        useEffect(() => {
            const bus = this.props.session.bus;
            const focus = () => this.focus();
            bus.addEventListener('sent', focus);
            return () => bus.removeEventListener('sent', focus);
        });
        onMounted(() => this.focus());
    }
    get placeholder() {
        const data = this.props.session.data;
        return (
            {
                waiting:
                    data.pending_ask?.kind === 'approval'
                        ? _t('Approve or reject to continue...')
                        : _t('Type your answer...'),
                waiting_schedule: _t('Scheduled. Type to wake the agent...'),
                running: _t('Stop to interrupt...'),
                compacting: _t('Compacting in background, the message will queue...'),
            }[data.state] || this.props.placeholder
        );
    }
    get readonlyNotice() {
        const owner = this.props.session.ownerName;
        return owner
            ? _t('Read only: %s shared this chat with you.', owner)
            : _t('Read only: you cannot write in this chat.');
    }
    get agentMode() {
        return /^\/agent(\s|$)/.test(this.props.session.state.input.trimStart());
    }
    get items() {
        const { session } = this.props;
        const input = session.state.input;
        if (this.agentMode) {
            const query = input
                .trimStart()
                .replace(/^\/agent\s*/, '')
                .toLowerCase();
            const current = session.data.agent_id?.[0];
            return this.chat
                .agents()
                .filter((agent) => agent.name.toLowerCase().includes(query))
                .map((agent) => ({
                    key: agent.id,
                    name: agent.name,
                    hint: agent.id === current ? _t('active') : agent.description || '',
                    agent,
                }));
        }
        const prefix = input.trim().split(/\s+/)[0].toLowerCase();
        return prefix.startsWith('/')
            ? slashCommands
                  .getEntries()
                  .filter(([name]) => name.startsWith(prefix))
                  .map(([name, command]) => ({
                      key: name,
                      name,
                      hint: command.hint,
                      command,
                  }))
            : [];
    }
    get button() {
        const { canSend, canStop, queueing } = this.props.session;
        if (canSend && queueing) {
            return {
                icon: 'schedule',
                cls: 'mk_queue',
                title: _t('Queue (sends after current turn)'),
            };
        }
        if (canStop && !canSend) {
            return { icon: 'stop', cls: 'mk_stop', title: _t('Stop') };
        }
        return { icon: 'arrow_upward', cls: '', title: _t('Send'), disabled: !canSend };
    }
    focus() {
        const input = this.textarea();
        const active = document.activeElement;
        if (
            input &&
            !(
                active !== input &&
                active?.matches('textarea, input, [contenteditable="true"]')
            )
        ) {
            input.focus();
        }
    }
    /**
     * Complete the highlighted slash command, or pick the highlighted agent.
     * @param {number} index the position in the menu
     */
    pick(index) {
        const item = this.items[index];
        const { session } = this.props;
        const state = session.state;
        if (item?.agent) {
            session.setAgent(item.agent.id);
            state.input = '';
        } else if (item) {
            state.input = item.name + (state.input.match(/^\/\S*(\s.*)?$/)?.[1] || '');
        }
        this.state.active = 0;
    }
    onKeydown(ev) {
        const items = this.items;
        const enter = ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing;
        if (items.length && ['ArrowDown', 'ArrowUp'].includes(ev.key)) {
            const step = ev.key === 'ArrowDown' ? 1 : -1;
            this.state.active =
                (this.state.active + step + items.length) % items.length;
        } else if (items.length && ev.key === 'Tab' && !ev.shiftKey) {
            this.pick(this.state.active);
        } else if (items.length && ev.key === 'Escape') {
            this.props.session.state.input = '';
        } else if (items.length && enter) {
            const item = items[this.state.active];
            const completed =
                item.name !== this.props.session.state.input.trim().toLowerCase();
            this.pick(this.state.active);
            if (
                item.command &&
                !item.command.opensPicker &&
                !(item.command.destructive && completed)
            ) {
                this.sendOrStop();
            }
        } else if (enter) {
            this.sendOrStop();
        } else {
            return;
        }
        ev.preventDefault();
    }
    sendOrStop() {
        const { session } = this.props;
        if (session.canStop && !(session.canSend && session.queueing)) {
            return session.stop();
        }
        return session.send();
    }
    onFileChange(ev) {
        this.props.session.attach([...ev.target.files]);
        ev.target.value = '';
    }
    openAttachment(attachment) {
        this.fileViewer.open(toFileModel(attachment));
    }
}
