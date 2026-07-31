import {
    Component,
    markup,
    onMounted,
    onPatched,
    onWillStart,
    onWillUnmount,
    useRef,
    useState,
} from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { router } from '@web/core/browser/router';
import { user } from '@web/core/user';
import { useService } from '@web/core/utils/hooks';
import { useDropzone } from '@web/core/dropzone/dropzone_hook';
import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';

import { Dropdown } from '@web/core/dropdown/dropdown';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';

import { toFileModel, toInlineImageFile } from '@muk_ai/core/attachment/attachment';
import { AttachmentCard } from '@muk_ai/core/attachment/attachment_card';
import { useNotificationBadge } from '@muk_ai/core/notification_badge';
import {
    approvalPill,
    costTooltip,
    formatCost,
    formatRelativeTime,
    formatTimestamp,
    inputPlaceholder,
    statusBadgeClass,
    statusIcon,
    statusLabel,
} from '@muk_ai/chat/utils';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';
import { useAiSession } from '@muk_ai/chat/session/use_ai_session';
import {
    onScrollUpNearTop,
    preserveAnchor,
    useChatScrollAnchor,
} from '@muk_ai/chat/session/use_scroll_anchor';
import { ChatSidebar } from '@muk_ai/chat/sidebar/chat_sidebar';
import { ChatArtifactsPanel } from '@muk_ai/chat/artifacts/chat_artifacts_panel';
import { SourceIcon, SourceList } from '@muk_ai/chat/artifacts/types/sources_tab';
import '@muk_ai/chat/artifacts/types/attachments_type';
import '@muk_ai/chat/artifacts/types/sources_type';
import { ChatSearch } from '@muk_ai/chat/search/chat_search';
import {
    buildIndex,
    entryFirstMatchIndex,
    escapeAndHighlight,
    findMatches,
    highlightHtml,
} from '@muk_ai/chat/search/search_index';
import { ToolCard } from '@muk_ai/chat/tools/tool_card';
import { ToolGroup, buildTurnItems } from '@muk_ai/chat/tools/tool_group';
import {
    askArgsText,
    askViewMode,
    toggleAskViewMode,
} from '@muk_ai/chat/session/ask_view';
import {
    viewContextLabel,
    viewContextTooltip,
} from '@muk_ai/chat/session/view_context_format';
import { seedSessionContext } from '@muk_ai/views/context';

export const SESSION_PAGE_SIZE = 20;
export const SPACE_PAGE_SIZE = 10;
const SESSION_SEARCH_LIMIT = 100;
const SESSION_SEARCH_DEBOUNCE_MS = 250;

function normalizeSuggestions(raw) {
    if (!Array.isArray(raw)) {
        return [];
    }
    return raw
        .filter((s) => s && typeof s.prompt === 'string' && s.prompt.trim())
        .map((s) => ({
            label: (typeof s.label === 'string' && s.label) || s.prompt,
            prompt: s.prompt,
        }));
}

/** Full-page AI chat client: sidebar, conversation, and composer. */
export class AIChat extends Component {
    static template = 'muk_ai.Chat';
    static components = {
        ChatSidebar,
        ChatArtifactsPanel,
        ChatSearch,
        ToolCard,
        ToolGroup,
        ChatComposer,
        AttachmentCard,
        SourceIcon,
        SourceList,
        Dropdown,
        DropdownItem,
    };
    static props = ['*'];
    get suggestions() {
        const agents = this.session.state.agents || [];
        const agent =
            agents.find((a) => a.id === this.session.state.agentId) || agents[0];
        return normalizeSuggestions(agent && agent.suggestions);
    }
    setup() {
        this.orm = useService('orm');
        this.bus = useService('bus_service');
        this.action = useService('action');
        this.chatWindow = useService('muk_ai.chat_window');
        this.notification = useService('notification');
        this.ui = useService('ui');
        this.session = useAiSession({
            surface: 'fullscreen',
            onRefresh: () => this._loadSessions(),
            onForked: async (newId) => {
                await this._loadSessions();
                await this._selectSession(newId);
            },
            onHandedOver: async (sessionId) => {
                this.state.sessions = this.state.sessions.filter(
                    (s) => s.id !== sessionId,
                );
                if (this.session.state.sessionId === sessionId) {
                    await this._selectSession(this.state.sessions[0]?.id || null);
                }
                await this._loadSessions();
            },
        });
        this.fileViewer = useFileViewer();
        this.badge = useNotificationBadge();
        this.state = useState({
            loading: true,
            sessions: [],
            spaces: [],
            spaceSessions: {},
            sessionsOffset: 0,
            sessionsHasMore: false,
            sessionsLoadingMore: false,
            sessionsQuery: '',
            sessionsSearchMode: false,
            sessionsSearching: false,
            sidebarHidden: false,
            artifactsHidden: true,
            searchOpen: false,
            searchQuery: '',
            activeMatchIdx: 0,
            scrollTarget: null,
            askViews: {},
            sourcesExpanded: {},
            resumeTick: 0,
        });
        this._sessionsSearchSeq = 0;
        this._sessionsSearchTimer = null;
        this._resumeTickInterval = null;
        this.rootRef = useRef('root');
        const {
            scrollRef,
            scrollToBottom,
            state: scrollState,
        } = useChatScrollAnchor('scrollArea');
        this.scrollRef = scrollRef;
        this.scrollToBottom = scrollToBottom;
        this.scrollState = scrollState;
        this.session.setScrollCallback(scrollToBottom);
        onScrollUpNearTop(scrollRef, () =>
            preserveAnchor(scrollRef, () => this.session.loadMoreEvents()),
        );
        this._userBusHandler = null;
        this._loadSeq = 0;
        this._spaceLoadSeq = {};
        this._sessionFetchIds = new Set();
        useDropzone(
            this.rootRef,
            (event) => {
                const files = Array.from(event.dataTransfer?.files || []);
                if (files.length) {
                    this.session.onAttachFiles(files);
                }
            },
            'mk_chat_dropzone',
            () => this.session.canAttach(),
        );
        onWillStart(async () => {
            await Promise.all([
                this._loadSessions(),
                this._loadSpaces(),
                this.session.loadAgents(),
            ]);
            this._connectUserBus();
            const requested = this._getRequestedSessionId();
            const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
            let opened = false;
            if (requested) {
                if (this.state.sessions.some((s) => s.id === requested)) {
                    await this._selectSession(requested);
                    this.state.sidebarHidden = true;
                    opened = true;
                } else {
                    const record = await this.session.load(requested);
                    if (record) {
                        this.state.sidebarHidden = true;
                        opened = true;
                    } else {
                        this.notification.add(_t('That AI session no longer exists.'), {
                            type: 'warning',
                        });
                    }
                }
            }
            if (!opened && this.state.sessions.length) {
                await this._selectSession(this.state.sessions[0].id);
                if (isMobile) {
                    this.state.sidebarHidden = true;
                }
            }
            this.state.loading = false;
        });
        onMounted(() => {
            this._installImageClickHandler();
            this._installRootPasteHandler();
            this._resumeTickInterval = window.setInterval(() => {
                if (
                    this.session.state.status === 'waiting_schedule' &&
                    this.session.state.resumeAt
                ) {
                    this.state.resumeTick += 1;
                }
            }, 5000);
        });
        onPatched(() => {
            this._handleScrollTarget();
        });
        onWillUnmount(() => {
            this._disconnectUserBus();
            this._uninstallRootPasteHandler();
            if (this._sessionsSearchTimer !== null) {
                window.clearTimeout(this._sessionsSearchTimer);
                this._sessionsSearchTimer = null;
            }
            if (this._resumeTickInterval !== null) {
                window.clearInterval(this._resumeTickInterval);
                this._resumeTickInterval = null;
            }
        });
    }
    _installImageClickHandler() {
        const root = this.rootRef.el;
        if (!root) return;
        root.addEventListener('click', (ev) => {
            const img = ev.target.closest('.mk_md_image');
            if (!img || !img.src) return;
            ev.preventDefault();
            this._openInlineImage(img.src);
        });
    }
    _installRootPasteHandler() {
        const root = this.rootRef.el;
        if (!root) return;
        this._rootPasteHandler = (ev) => {
            if (!root.isConnected) return;
            if (!this.session.canAttach()) return;
            if (ev.target && ev.target.closest('.mk_composer textarea')) return;
            const items = (ev.clipboardData && ev.clipboardData.items) || [];
            const files = [];
            for (const item of items) {
                if (item.kind === 'file') {
                    const file = item.getAsFile();
                    if (file) files.push(file);
                }
            }
            if (files.length) {
                ev.preventDefault();
                this.session.onAttachFiles(files);
            }
        };
        document.addEventListener('paste', this._rootPasteHandler);
    }
    _uninstallRootPasteHandler() {
        if (this._rootPasteHandler) {
            document.removeEventListener('paste', this._rootPasteHandler);
        }
        this._rootPasteHandler = null;
    }
    _openInlineImage(src) {
        this.fileViewer.open(toInlineImageFile(src));
    }
    /**
     * Load the spaces shown in the sidebar tree.
     */
    async _loadSpaces() {
        this.state.spaces = await this.orm.call('muk_ai.space', 'fetch_spaces', []);
    }
    /**
     * Load a page of the chats of one space into its branch of the tree.
     * The cursor counts the rows the server returned rather than the ones
     * kept after removing duplicates, so an all-duplicate page still
     * advances it instead of asking for the same slice forever.
     * @param {number} spaceId
     * @param {boolean} [more] append the next page instead of reloading
     * @param {boolean|null} [unreadOnly] narrow to unread, null to keep as is
     */
    async _loadSpaceSessions(spaceId, more = false, unreadOnly = null) {
        const space = this.state.spaces.find((entry) => entry.id === spaceId);
        if (!space) {
            return;
        }
        const branch = this.state.spaceSessions[spaceId];
        const filtered =
            unreadOnly === null ? !!(branch && branch.unreadOnly) : unreadOnly;
        const domain = [
            ['user_id', '=', user.userId],
            ...space.session_domain,
            ...(filtered ? [['notification_unread', '=', true]] : []),
        ];
        const offset = more && branch ? branch.offset : 0;
        const seq = (this._spaceLoadSeq[spaceId] || 0) + 1;
        this._spaceLoadSeq[spaceId] = seq;
        const page = await this.orm.searchRead(
            'muk_ai.session',
            domain,
            ['id', 'name', 'state', 'create_date', 'space_id'],
            { limit: SPACE_PAGE_SIZE, offset, order: 'create_date DESC' },
        );
        if (this._spaceLoadSeq[spaceId] !== seq) {
            return;
        }
        const known = offset && branch ? branch.sessions : [];
        const seen = new Set(known.map((session) => session.id));
        this.state.spaceSessions[spaceId] = {
            sessions: [...known, ...page.filter((session) => !seen.has(session.id))],
            offset: offset + page.length,
            hasMore: page.length === SPACE_PAGE_SIZE,
            unreadOnly: filtered,
        };
    }
    async _loadSessions() {
        if (this.state.sessionsSearchMode) {
            await this._searchSessions(this.state.sessionsQuery);
            return;
        }
        const seq = ++this._loadSeq;
        const sessions = await this.orm.searchRead(
            'muk_ai.session',
            [
                ['user_id', '=', user.userId],
                ['space_id', '=', false],
            ],
            ['id', 'name', 'state', 'create_date', 'space_id'],
            { limit: SESSION_PAGE_SIZE, offset: 0, order: 'create_date DESC' },
        );
        if (seq === this._loadSeq) {
            this.state.sessions = sessions;
            this.state.sessionsOffset = sessions.length;
            this.state.sessionsHasMore = sessions.length === SESSION_PAGE_SIZE;
        }
    }
    async _loadMoreSessions() {
        if (
            this.state.sessionsLoadingMore ||
            !this.state.sessionsHasMore ||
            this.state.sessionsSearchMode
        ) {
            return;
        }
        this.state.sessionsLoadingMore = true;
        try {
            const seq = this._loadSeq;
            const next = await this.orm.searchRead(
                'muk_ai.session',
                [
                    ['user_id', '=', user.userId],
                    ['space_id', '=', false],
                ],
                ['id', 'name', 'state', 'create_date', 'space_id'],
                {
                    limit: SESSION_PAGE_SIZE,
                    offset: this.state.sessionsOffset,
                    order: 'create_date DESC',
                },
            );
            if (seq !== this._loadSeq) {
                return;
            }
            const known = new Set(this.state.sessions.map((s) => s.id));
            const fresh = next.filter((s) => !known.has(s.id));
            this.state.sessions = [...this.state.sessions, ...fresh];
            this.state.sessionsOffset += next.length;
            this.state.sessionsHasMore = next.length === SESSION_PAGE_SIZE;
        } finally {
            this.state.sessionsLoadingMore = false;
        }
    }
    async _searchSessions(query) {
        const seq = ++this._sessionsSearchSeq;
        this.state.sessionsSearching = true;
        try {
            const sessions = await this.orm.searchRead(
                'muk_ai.session',
                [
                    ['user_id', '=', user.userId],
                    ['name', 'ilike', query],
                ],
                ['id', 'name', 'state', 'create_date', 'space_id'],
                { limit: SESSION_SEARCH_LIMIT, order: 'create_date DESC' },
            );
            if (seq !== this._sessionsSearchSeq) {
                return;
            }
            this.state.sessions = sessions;
            this.state.sessionsHasMore = false;
        } finally {
            if (seq === this._sessionsSearchSeq) {
                this.state.sessionsSearching = false;
            }
        }
    }
    onSidebarQuery(query) {
        const trimmed = (query || '').trim();
        this.state.sessionsQuery = query || '';
        if (this._sessionsSearchTimer !== null) {
            window.clearTimeout(this._sessionsSearchTimer);
            this._sessionsSearchTimer = null;
        }
        if (!trimmed) {
            this._sessionsSearchSeq++;
            this.state.sessionsSearchMode = false;
            this.state.sessionsSearching = false;
            this._loadSessions();
            return;
        }
        this.state.sessionsSearchMode = true;
        this._sessionsSearchTimer = window.setTimeout(() => {
            this._sessionsSearchTimer = null;
            this._searchSessions(trimmed);
        }, SESSION_SEARCH_DEBOUNCE_MS);
    }
    onSidebarLoadMore() {
        return this._loadMoreSessions();
    }
    async _selectSession(sessionId) {
        if (this.session.state.sessionId === sessionId) {
            return;
        }
        await this.session.load(sessionId);
        this.scrollToBottom(true);
        if (typeof window !== 'undefined' && window.innerWidth < 768) {
            this.state.sidebarHidden = true;
        }
        router.pushState({ session_id: sessionId || undefined });
    }
    /**
     * Create and switch to a new session. Raises state.loading before the
     * first RPC so the composer (canSend gates on it) stays closed for the
     * whole switch — a send in that window would run in the outgoing
     * session and paint nothing in the new one.
     * @param {object} [values] extra values written on the created session
     * @returns {Promise<number>} the created session id
     */
    async onNewSession(values = {}) {
        const name = _t('Chat %s', new Date().toLocaleString());
        const carryOver = this.session.state.viewContext;
        this.session.state.loading = true;
        let id;
        try {
            const sessionId = await this.orm.create('muk_ai.session', [
                { name, ...values },
            ]);
            id = Array.isArray(sessionId) ? sessionId[0] : sessionId;
            if (carryOver && carryOver.model) {
                await seedSessionContext(this.env, id, carryOver);
            }
        } catch (error) {
            this.session.state.loading = false;
            throw error;
        }
        await this._selectSession(id);
        await this._loadSessions();
        return id;
    }
    async onStartWithPrompt(prompt) {
        await this.onNewSession();
        this.session.state.input = prompt;
        this.session.state.focusToken += 1;
        await this.session.onSend();
        this._refreshSidebar();
    }
    async onSubmitSuggestion(prompt) {
        this.session.state.input = prompt;
        this.session.state.focusToken += 1;
        await this.session.onSend();
        this._refreshSidebar();
    }
    async onSelectSession(sessionId) {
        await this._selectSession(sessionId);
    }
    async onRenameSession(sessionId, name) {
        await this.orm.write('muk_ai.session', [sessionId], { name });
        await this._loadSessions();
        if (this.session.state.sessionId === sessionId) {
            this.session.state.name = name;
        }
    }
    async onDeleteSession(sessionId) {
        await this.orm.unlink('muk_ai.session', [sessionId]);
        this.state.sessions = this.state.sessions.filter((s) => s.id !== sessionId);
        if (this.session.state.sessionId === sessionId) {
            const next = this.state.sessions[0]?.id || null;
            await this._selectSession(next);
        }
        await this._loadSessions();
    }
    onSpaceOpen(spaceId, unreadOnly = null) {
        return this._loadSpaceSessions(spaceId, false, unreadOnly);
    }
    onSpaceLoadMore(spaceId) {
        return this._loadSpaceSessions(spaceId, true);
    }
    async onSpaceCreate(name) {
        await this.orm.create('muk_ai.space', [{ name }]);
        await this._loadSpaces();
    }
    async onSpaceEdit(spaceId, values) {
        await this.orm.write('muk_ai.space', [spaceId], values);
        await this._loadSpaces();
    }
    async onSpaceDelete(spaceId) {
        await this.orm.unlink('muk_ai.space', [spaceId]);
        delete this.state.spaceSessions[spaceId];
        await Promise.all([this._loadSpaces(), this._loadSessions()]);
    }
    /**
     * Persist the new order of the personal spaces after a drag.
     * @param {number} spaceId the space that moved
     * @param {number|null} afterId the space it now follows, null when first
     */
    async onSpaceReorder(spaceId, afterId) {
        const ids = this.state.spaces
            .filter((space) => !space.system)
            .map((space) => space.id)
            .filter((id) => id !== spaceId);
        const after = afterId === null ? -1 : ids.indexOf(afterId);
        if (afterId !== null && after === -1) {
            return;
        }
        ids.splice(after + 1, 0, spaceId);
        const byId = new Map(this.state.spaces.map((space) => [space.id, space]));
        this.state.spaces = [
            ...this.state.spaces.filter((space) => space.system),
            ...ids.map((id) => byId.get(id)),
        ];
        try {
            await this.orm.call('muk_ai.space', 'reorder', [ids]);
        } catch (error) {
            await this._loadSpaces();
            throw error;
        }
    }
    /** Start a chat inside a space, preselecting the agent it defaults to. */
    async onSpaceNew(spaceId) {
        const space = this.state.spaces.find((entry) => entry.id === spaceId);
        const values = { space_id: spaceId };
        if (space && space.agent_id) {
            values.agent_id = space.agent_id;
        }
        await this.onNewSession(values);
        await this._loadSpaceSessions(spaceId);
    }
    /**
     * File a chat into a space, or loosen it again when spaceId is false.
     * @param {number} sessionId
     * @param {number|false} spaceId
     */
    async onSessionFile(sessionId, spaceId) {
        const previous = Object.keys(this.state.spaceSessions)
            .map(Number)
            .filter((id) =>
                this.state.spaceSessions[id].sessions.some((s) => s.id === sessionId),
            );
        await this.orm.write('muk_ai.session', [sessionId], {
            space_id: spaceId || false,
        });
        const branches = [...new Set([...previous, ...(spaceId ? [spaceId] : [])])];
        await Promise.all([
            this._loadSessions(),
            ...branches.map((id) => this._loadSpaceSessions(id)),
        ]);
    }
    toggleSidebar() {
        this.state.sidebarHidden = !this.state.sidebarHidden;
    }
    toggleArtifacts() {
        const willOpen = this.state.artifactsHidden;
        this.state.artifactsHidden = !this.state.artifactsHidden;
        if (willOpen && typeof window !== 'undefined' && window.innerWidth < 1200) {
            this.state.sidebarHidden = true;
        }
    }
    closeArtifacts() {
        this.state.artifactsHidden = true;
    }
    toggleSearch() {
        if (this.state.searchOpen) {
            this.closeSearch();
        } else {
            this.state.searchOpen = true;
        }
    }
    closeSearch() {
        this.state.searchOpen = false;
        this.state.searchQuery = '';
        this.state.activeMatchIdx = 0;
        this.state.scrollTarget = null;
    }
    onSearchChange(query) {
        this.state.searchQuery = query || '';
        this.state.activeMatchIdx = 0;
        const matches = this.searchMatches;
        if (matches.length) {
            this.state.scrollTarget = matches[0].entry.anchorId;
        } else {
            this.state.scrollTarget = null;
        }
    }
    onSearchPrev() {
        const matches = this.searchMatches;
        if (!matches.length) return;
        const next = (this.state.activeMatchIdx - 1 + matches.length) % matches.length;
        this.state.activeMatchIdx = next;
        this.state.scrollTarget = matches[next].entry.anchorId;
    }
    onSearchNext() {
        const matches = this.searchMatches;
        if (!matches.length) return;
        const next = (this.state.activeMatchIdx + 1) % matches.length;
        this.state.activeMatchIdx = next;
        this.state.scrollTarget = matches[next].entry.anchorId;
    }
    _searchCache(turns, query) {
        const cache = this._searchMemo;
        if (cache && cache.turns === turns && cache.query === query) {
            return cache;
        }
        const index = buildIndex(turns);
        const matches = findMatches(index, query);
        const memo = { turns, query, index, matches };
        this._searchMemo = memo;
        return memo;
    }
    get searchIndex() {
        if (!this.state.searchOpen || !this.state.searchQuery) {
            return [];
        }
        return this._searchCache(this.renderedTurns, this.state.searchQuery).index;
    }
    get searchMatches() {
        if (!this.state.searchOpen || !this.state.searchQuery) {
            return [];
        }
        return this._searchCache(this.renderedTurns, this.state.searchQuery).matches;
    }
    get clampedActiveMatchIdx() {
        const matches = this.searchMatches;
        if (!matches.length) return 0;
        if (this.state.activeMatchIdx >= matches.length) return matches.length - 1;
        if (this.state.activeMatchIdx < 0) return 0;
        return this.state.activeMatchIdx;
    }
    _handleScrollTarget() {
        const target = this.state.scrollTarget;
        if (!target) return;
        const el = document.getElementById(target);
        if (el) {
            try {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch {
                el.scrollIntoView();
            }
            el.classList.add('mk_search_pulse');
            window.setTimeout(() => {
                el.classList.remove('mk_search_pulse');
            }, 600);
        }
        this.state.scrollTarget = null;
    }
    renderUserText(text) {
        if (this.state.searchOpen && this.state.searchQuery) {
            const matches = this.searchMatches;
            const entry = this.searchIndex.find(
                (e) => e.role === 'user' && e.text === text,
            );
            const firstIdx = entry ? entryFirstMatchIndex(matches, entry) : -1;
            const html = escapeAndHighlight(
                text,
                this.state.searchQuery,
                this.clampedActiveMatchIdx,
                firstIdx,
            );
            return markup(html);
        }
        return text == null ? '' : String(text);
    }
    renderAssistantMarkdown(text) {
        const rendered = this.session.renderMarkdown(text);
        if (!this.state.searchOpen || !this.state.searchQuery) {
            return rendered;
        }
        const matches = this.searchMatches;
        const entry = this.searchIndex.find(
            (e) => e.role === 'assistant' && e.text === text,
        );
        const firstIdx = entry ? entryFirstMatchIndex(matches, entry) : -1;
        const sourceHtml =
            typeof rendered === 'string'
                ? rendered
                : rendered && rendered.toString
                  ? rendered.toString()
                  : String(rendered || '');
        const highlighted = highlightHtml(
            sourceHtml,
            this.state.searchQuery,
            this.clampedActiveMatchIdx,
            firstIdx,
        );
        return markup(highlighted);
    }
    onPopout() {
        if (!this.session.state.sessionId) {
            return;
        }
        if (this.ui.isSmall) {
            this.action.doAction('muk_ai.action_ai_chat', {
                additionalContext: { default_session_id: this.session.state.sessionId },
            });
            return;
        }
        this.chatWindow.open(this.session.state.sessionId);
    }
    async onSend() {
        await this.session.onSend();
        this._refreshSidebar();
    }
    async onStop() {
        await this.session.onStop();
        this._refreshSidebar();
    }
    onInputChange(value) {
        this.session.onInputChange(value);
    }
    onAttachFiles(files) {
        return this.session.onAttachFiles(files);
    }
    onRemoveAttachment(attachmentId) {
        return this.session.onRemoveAttachment(attachmentId);
    }
    toggleToolBlock(callId) {
        this.session.toggleToolBlock(callId);
    }
    turnSourcesKey(turn, index) {
        return turn.eventId ? `e${turn.eventId}` : `t${index}`;
    }
    isTurnSourcesExpanded(turn, index) {
        return !!this.state.sourcesExpanded[this.turnSourcesKey(turn, index)];
    }
    toggleTurnSources(turn, index) {
        const key = this.turnSourcesKey(turn, index);
        this.state.sourcesExpanded = {
            ...this.state.sourcesExpanded,
            [key]: !this.state.sourcesExpanded[key],
        };
    }
    onOpenAttachment(attachment) {
        const file = toFileModel(attachment);
        this.fileViewer.open(file);
    }
    async _fetchSidebarSession(sessionId) {
        if (this.state.sessionsSearchMode || this._sessionFetchIds.has(sessionId)) {
            return;
        }
        this._sessionFetchIds.add(sessionId);
        try {
            const seq = this._loadSeq;
            const [session] = await this.orm.searchRead(
                'muk_ai.session',
                [
                    ['id', '=', sessionId],
                    ['user_id', '=', user.userId],
                ],
                ['id', 'name', 'state', 'create_date', 'space_id'],
                { limit: 1 },
            );
            if (
                !session ||
                seq !== this._loadSeq ||
                this.state.sessionsSearchMode ||
                this.state.sessions.some((s) => s.id === session.id)
            ) {
                return;
            }
            const pos = this.state.sessions.findIndex(
                (s) => s.create_date < session.create_date,
            );
            if (pos < 0) {
                this.state.sessions = [...this.state.sessions, session];
            } else {
                this.state.sessions = [
                    ...this.state.sessions.slice(0, pos),
                    session,
                    ...this.state.sessions.slice(pos),
                ];
            }
        } finally {
            this._sessionFetchIds.delete(sessionId);
        }
    }
    _connectUserBus() {
        this._disconnectUserBus();
        this._userBusHandler = (payload) => this._onUserBusEvent(payload);
        this.bus.subscribe('muk_ai.session_state', this._userBusHandler);
    }
    _disconnectUserBus() {
        if (this._userBusHandler) {
            this.bus.unsubscribe('muk_ai.session_state', this._userBusHandler);
            this._userBusHandler = null;
        }
    }
    _onUserBusEvent(payload) {
        if (!payload || !payload.session_id) {
            return;
        }
        if (payload.deleted) {
            this.state.sessions = this.state.sessions.filter(
                (s) => s.id !== payload.session_id,
            );
            if (this.session.state.sessionId === payload.session_id) {
                this._selectSession(this.state.sessions[0]?.id || null);
            }
            return;
        }
        const idx = this.state.sessions.findIndex((s) => s.id === payload.session_id);
        if (idx < 0) {
            this._fetchSidebarSession(payload.session_id);
            return;
        }
        const updated = { ...this.state.sessions[idx] };
        if (payload.state) updated.state = payload.state;
        if (payload.name) updated.name = payload.name;
        this.state.sessions = [
            ...this.state.sessions.slice(0, idx),
            updated,
            ...this.state.sessions.slice(idx + 1),
        ];
        if (payload.session_id === this.session.state.sessionId) {
            if (payload.name) this.session.state.name = payload.name;
            if (payload.state) this.session.state.status = payload.state;
            if (typeof payload.iteration_count === 'number') {
                this.session.state.iterationCount = payload.iteration_count;
            }
            if (typeof payload.total_input_tokens === 'number') {
                this.session.state.inputTokens = payload.total_input_tokens;
            }
            if (typeof payload.total_output_tokens === 'number') {
                this.session.state.outputTokens = payload.total_output_tokens;
            }
            if (typeof payload.last_input_tokens === 'number') {
                this.session.state.lastInputTokens = payload.last_input_tokens;
            }
            if (typeof payload.context_window === 'number') {
                this.session.state.contextWindow = payload.context_window;
            }
        }
    }
    _refreshSidebar() {
        const id = this.session.state.sessionId;
        if (!id) return;
        const idx = this.state.sessions.findIndex((s) => s.id === id);
        if (idx < 0) {
            this._loadSessions();
            return;
        }
        const updated = {
            ...this.state.sessions[idx],
            state: this.session.state.status,
        };
        this.state.sessions = [
            ...this.state.sessions.slice(0, idx),
            updated,
            ...this.state.sessions.slice(idx + 1),
        ];
    }
    _getRequestedSessionId() {
        try {
            const actionParam = this.props?.action?.params?.session_id;
            if (actionParam) {
                const actionId = parseInt(actionParam, 10);
                if (Number.isInteger(actionId) && actionId > 0) {
                    return actionId;
                }
            }
            const params = new URLSearchParams(window.location.search);
            const raw = params.get('session_id');
            const id = raw ? parseInt(raw, 10) : 0;
            return Number.isInteger(id) && id > 0 ? id : null;
        } catch {
            return null;
        }
    }
    get renderedTurns() {
        return this.session.renderedTurns();
    }
    renderMarkdown(text) {
        return this.session.renderMarkdown(text);
    }
    formatTimestamp(at) {
        return formatTimestamp(at);
    }
    isToolExpanded(callId) {
        return this.session.isToolExpanded(callId);
    }
    isToolHiddenForAsk(block, turn) {
        if (block.result !== null && block.result !== undefined) {
            return false;
        }
        const pending = this.session.state.pendingAsk;
        if (pending && pending.call_id === block.callId) {
            return true;
        }
        return turn.blocks.some((b) => b.type === 'ask' && b.callId === block.callId);
    }
    isToolStreaming(block) {
        if (block.result !== null && block.result !== undefined) {
            return false;
        }
        const status = this.session.state.status;
        return status === 'running' || status === 'compacting';
    }
    turnItems(turn) {
        return buildTurnItems(turn.blocks, (block) =>
            this.isToolHiddenForAsk(block, turn),
        );
    }
    get isCompact() {
        return false;
    }
    get canSend() {
        return this.isOwner && this.session.canSend();
    }
    get canAttach() {
        return this.isOwner && this.session.canAttach();
    }
    get canStop() {
        return this.isOwner && this.session.canStop();
    }
    get composerDisabled() {
        return this.session.composerDisabled() || !this.isOwner;
    }
    get isOwner() {
        const ownerId = this.session.state.ownerId;
        return ownerId == null || ownerId === user.userId;
    }
    get isQueueing() {
        return this.session.isQueueing();
    }
    /**
     * Placeholder for the composer.
     * The keyboard hint is dropped on narrow screens, where it wraps and a
     * touch keyboard has no Shift+Enter to offer.
     */
    get inputPlaceholder() {
        if (!this.isOwner) {
            return _t('Read only — you are not the owner of this session.');
        }
        const narrow = typeof window !== 'undefined' && window.innerWidth < 768;
        return inputPlaceholder(
            this.session.state,
            narrow
                ? _t('Message the assistant…')
                : _t('Message the assistant… (Enter to send, Shift+Enter for newline)'),
        );
    }
    statusLabel(status) {
        return statusLabel(status);
    }
    statusBadgeClass(status) {
        return statusBadgeClass(status);
    }
    statusIcon(status) {
        return statusIcon(status);
    }
    get resumeRelativeText() {
        void this.state.resumeTick;
        const relative = formatRelativeTime(this.session.state.resumeAt);
        if (!relative) {
            return '';
        }
        return _t('resumes in %s', relative);
    }
    get contextPercent() {
        const window = this.session.state.contextWindow;
        if (!window) {
            return 0;
        }
        return Math.max(
            0,
            Math.min(
                100,
                Math.round((this.session.state.lastInputTokens / window) * 100),
            ),
        );
    }
    get contextClass() {
        const pct = this.contextPercent;
        if (pct >= 90) return 'mk_context_red';
        if (pct >= 70) return 'mk_context_amber';
        return 'mk_context_green';
    }
    get costPill() {
        const cost = this.session.state.totalCost;
        return { label: formatCost(cost), tooltip: costTooltip(cost) };
    }
    get contextTooltip() {
        const tokens = this.session.state.lastInputTokens || 0;
        const window = this.session.state.contextWindow || 0;
        const fmt = new Intl.NumberFormat();
        return _t('Context window: %(tokens)s / %(window)s tokens', {
            tokens: fmt.format(tokens),
            window: fmt.format(window),
        });
    }
    askArgsText(block) {
        return askArgsText(block);
    }
    askViewMode(block) {
        return askViewMode(block, this.state.askViews);
    }
    toggleAskView(callId) {
        if (!callId) {
            return;
        }
        const block = this.renderedTurns
            .flatMap((t) => t.blocks || [])
            .find((b) => b.callId === callId);
        this.state.askViews = {
            ...this.state.askViews,
            [callId]: toggleAskViewMode(block, this.state.askViews),
        };
    }
    get viewContextLabel() {
        return viewContextLabel(this.session.state.viewContext);
    }
    get viewContextTooltip() {
        return viewContextTooltip(this.session.state.viewContext);
    }
    get approvalPill() {
        return approvalPill(this.session.state);
    }
}

registry.category('actions').add('muk_ai.chat', AIChat);
