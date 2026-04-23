/** @odoo-module */

import { markup, onWillUnmount, useState } from '@odoo/owl';

import { ConfirmationDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { fileToBase64 } from '@muk_ai/core/attachment/file_helpers';
import { renderMarkdown as renderMarkdownToHtml } from '@muk_ai/core/markdown/markdown';
import { formatError } from '@muk_ai/core/utils/error';

import { buildRenderedTurns } from './turns';

const SESSION_READ_FIELDS = [
    'id', 'name', 'state', 'tool_log', 'pending_ask',
    'view_context', 'last_text', 'error_message',
    'iteration_count', 'total_input_tokens', 'total_output_tokens',
    'last_input_tokens', 'context_window', 'agent_id', 'total_cost',
    'override_approval_mode', 'effective_approval_mode',
];

export const SLASH_COMMANDS = [
    {
        name: '/help',
        hint: 'Show available slash commands',
    },
    {
        name: '/clear',
        hint: 'Start a fresh conversation in this session',
    },
    {
        name: '/compact',
        hint: 'Summarize and collapse older turns to free context',
    },
    {
        name: '/unpin',
        hint: 'Clear the view context pinned to this session',
    },
];

const COMPACT_WARN_RATIO = 0.85;
const COMPACT_AUTO_RATIO = 0.95;

export function useAiSession(options = {}) {
    const orm = useService('orm');
    const bus = useService('bus_service');
    const notification = useService('notification');
    const actionService = useService('action');
    const dialog = useService('dialog');

    const state = useState({
        sessionId: null,
        name: '',
        status: 'new',
        loading: true,
        log: [],
        pendingAsk: null,
        error: null,
        input: '',
        iterationCount: 0,
        inputTokens: 0,
        outputTokens: 0,
        totalCost: 0,
        lastInputTokens: 0,
        contextWindow: 0,
        expandedTools: {},
        streamingText: '',
        streamingTools: [],
        pendingAttachments: [],
        focusToken: 0,
        agentId: null,
        agentName: '',
        autoCompactPending: false,
        viewContext: null,
        approvalMode: false,
        effectiveApprovalMode: 'ask',
    });

    let busHandler = null;
    let logKeys = new Set();
    let onScrollCallback = null;

    // ----------------------------------------------------------
    // Bus
    // ----------------------------------------------------------

    function connectBus() {
        disconnectBus();
        busHandler = (payload) => onBusEvent(payload);
        bus.subscribe('muk_ai.event', busHandler);
    }

    function disconnectBus() {
        if (busHandler) {
            bus.unsubscribe('muk_ai.event', busHandler);
            busHandler = null;
        }
    }

    function onBusEvent(event) {
        if (!event || event.session_id !== state.sessionId) {
            return;
        }
        if (event.type === 'log') {
            const key = JSON.stringify(event.payload);
            if (logKeys.has(key)) {
                return;
            }
            logKeys.add(key);
            state.log = [...state.log, event.payload];
            const kind = event.payload?.kind;
            if (kind === 'text') {
                state.streamingText = '';
            } else if (kind === 'tool_call') {
                state.streamingTools = state.streamingTools.filter(
                    (t) => t.callId !== event.payload.call_id,
                );
            }
            requestScroll();
        } else if (event.type === 'text_delta') {
            const delta = (event.payload || {}).delta || '';
            if (delta) {
                state.streamingText = (state.streamingText || '') + delta;
                requestScroll();
            }
        } else if (event.type === 'tool_call_start') {
            const callId = event.payload?.call_id;
            if (!callId) {
                return;
            }
            if (!state.streamingTools.some((t) => t.callId === callId)) {
                state.streamingTools = [
                    ...state.streamingTools,
                    { callId, name: event.payload?.name || '', argsBuffer: '' },
                ];
                requestScroll();
            }
        } else if (event.type === 'tool_call_args_delta') {
            const { call_id: callId, delta } = event.payload || {};
            if (!callId || !delta) {
                return;
            }
            state.streamingTools = state.streamingTools.map((t) =>
                t.callId === callId ? { ...t, argsBuffer: (t.argsBuffer || '') + delta } : t,
            );
            requestScroll();
        } else if (event.type === 'state') {
            if (event.payload.state) {
                state.status = event.payload.state;
                if (event.payload.state !== 'running') {
                    state.streamingText = '';
                    state.streamingTools = [];
                }
            }
            if (event.payload.ask) {
                state.pendingAsk = event.payload.ask;
            } else if (event.payload.state && event.payload.state !== 'waiting') {
                state.pendingAsk = null;
            }
            if (event.payload.error) {
                state.error = event.payload.error;
            }
            if (typeof event.payload.last_input_tokens === 'number') {
                state.lastInputTokens = event.payload.last_input_tokens;
            }
            if (typeof event.payload.context_window === 'number') {
                state.contextWindow = event.payload.context_window;
            }
            if (typeof event.payload.total_cost === 'number') {
                state.totalCost = event.payload.total_cost;
            }
        } else if (event.type === 'ui_action') {
            handleUiAction(event.payload);
        } else if (event.type === 'view_context') {
            state.viewContext = (event.payload || {}).view_context || null;
        }
    }

    async function handleUiAction(payload) {
        const action = payload && payload.action;
        if (!action || typeof action !== 'object') {
            return;
        }
        try {
            await actionService.doAction(action);
        } catch (error) {
            notification.add(
                _t('Failed to execute UI action: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }

    // ----------------------------------------------------------
    // Loading & snapshot
    // ----------------------------------------------------------

    async function load(sessionId) {
        disconnectBus();
        state.sessionId = sessionId;
        state.loading = true;
        state.input = '';
        state.error = null;
        state.pendingAsk = null;
        state.log = [];
        state.streamingText = '';
        state.streamingTools = [];
        state.pendingAttachments = [];
        logKeys = new Set();
        if (!sessionId) {
            state.loading = false;
            return null;
        }
        let record = null;
        try {
            const [result] = await orm.read(
                'muk_ai.session', [sessionId], SESSION_READ_FIELDS,
            );
            record = result || null;
        } catch (error) {
            state.error = formatError(error);
        }
        if (record) {
            applyRecord(record);
            connectBus();
        }
        state.loading = false;
        state.focusToken += 1;
        return record;
    }

    function applyRecord(record) {
        state.name = record.name || '';
        state.status = record.state;
        state.log = record.tool_log || [];
        state.pendingAsk = record.pending_ask || null;
        state.viewContext = record.view_context || null;
        state.approvalMode = record.override_approval_mode || false;
        state.effectiveApprovalMode = record.effective_approval_mode || 'ask';
        state.error = record.error_message || null;
        state.iterationCount = record.iteration_count || 0;
        state.inputTokens = record.total_input_tokens || 0;
        state.outputTokens = record.total_output_tokens || 0;
        state.totalCost = record.total_cost || 0;
        state.lastInputTokens = record.last_input_tokens || 0;
        state.contextWindow = record.context_window || 0;
        const agent = record.agent_id;
        state.agentId = Array.isArray(agent) ? agent[0] : null;
        state.agentName = Array.isArray(agent) ? agent[1] : '';
        rebuildLogKeys();
    }

    function applySnapshot(snapshot) {
        if (!snapshot) {
            return;
        }
        state.status = snapshot.state;
        state.log = snapshot.tool_log || [];
        state.pendingAsk = snapshot.pending_ask || null;
        state.viewContext = snapshot.view_context || null;
        state.approvalMode = snapshot.override_approval_mode || false;
        state.effectiveApprovalMode = snapshot.effective_approval_mode || 'ask';
        state.error = snapshot.error_message || null;
        state.iterationCount = snapshot.iteration_count || 0;
        state.inputTokens = snapshot.total_input_tokens || 0;
        state.outputTokens = snapshot.total_output_tokens || 0;
        if (typeof snapshot.total_cost === 'number') {
            state.totalCost = snapshot.total_cost;
        }
        state.lastInputTokens = snapshot.last_input_tokens || 0;
        if (typeof snapshot.context_window === 'number') {
            state.contextWindow = snapshot.context_window;
        }
        state.streamingText = '';
        state.streamingTools = [];
        rebuildLogKeys();
    }

    function rebuildLogKeys() {
        logKeys = new Set((state.log || []).map((entry) => JSON.stringify(entry)));
    }

    // ----------------------------------------------------------
    // User actions
    // ----------------------------------------------------------

    function canSend() {
        const hasContent = state.input.trim().length > 0
            || state.pendingAttachments.length > 0;
        return !!state.sessionId && hasContent && state.status !== 'running';
    }

    function canAttach() {
        return !!state.sessionId && state.status !== 'running';
    }

    function canStop() {
        return state.status === 'running';
    }

    function composerDisabled() {
        return state.status === 'running';
    }

    function onInputChange(value) {
        state.input = value;
    }

    async function onSend() {
        if (!canSend()) {
            return;
        }
        const slash = parseSlashCommand(state.input);
        if (slash) {
            state.input = '';
            await dispatchCommand(slash);
            state.focusToken += 1;
            return;
        }
        await maybeAutoCompact();
        const message = state.input;
        const attachments = [...state.pendingAttachments];
        const attachmentIds = attachments.map((a) => a.id);
        state.input = '';
        state.pendingAttachments = [];
        const wasWaitingQuestion = state.status === 'waiting'
            && (state.pendingAsk || {}).kind === 'question';
        const optimistic = wasWaitingQuestion
            ? {
                  kind: 'answer',
                  answer: message,
                  question: (state.pendingAsk || {}).text,
                  attachments,
              }
            : { kind: 'user_message', content: message, attachments };
        state.log = [...state.log, optimistic];
        logKeys.add(JSON.stringify(optimistic));
        state.streamingText = '';
        state.streamingTools = [];
        state.pendingAsk = null;
        state.status = 'running';
        state.error = null;
        requestScroll();
        try {
            const method = wasWaitingQuestion
                ? 'answer'
                : (
                    state.iterationCount === 0 && state.log.length <= 1 && !state.streamingText
                        ? 'start'
                        : 'send_message'
                );
            const snapshot = await orm.call(
                'muk_ai.session', method,
                [state.sessionId, message],
                { attachment_ids: attachmentIds },
            );
            applySnapshot(snapshot);
        } catch (error) {
            state.status = 'error';
            state.error = formatError(error);
        }
        state.focusToken += 1;
        requestScroll();
    }

    async function onStop() {
        if (!state.sessionId) {
            return;
        }
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'action_stop', [state.sessionId],
            );
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t('Failed to stop session: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }

    async function onAttachFiles(files) {
        if (!state.sessionId || !files || !files.length) {
            return;
        }
        try {
            const payloads = await Promise.all(files.map((file) => fileToBase64(file)));
            const descriptors = await orm.call(
                'muk_ai.session', 'upload_attachments',
                [state.sessionId, payloads],
            );
            state.pendingAttachments = [
                ...state.pendingAttachments, ...descriptors,
            ];
        } catch (error) {
            notification.add(
                _t('Attachment upload failed: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }

    // ----------------------------------------------------------
    // Slash commands
    // ----------------------------------------------------------

    function parseSlashCommand(raw) {
        const trimmed = (raw || '').trim();
        if (!trimmed.startsWith('/')) {
            return null;
        }
        const parts = trimmed.slice(1).split(/\s+/);
        const name = parts.shift().toLowerCase();
        if (!name) {
            return null;
        }
        if (!SLASH_COMMANDS.some((c) => c.name === `/${name}`)) {
            return null;
        }
        return { name: `/${name}`, args: parts.join(' ') };
    }

    function filterSlashCommands(raw) {
        const trimmed = (raw || '').trim();
        if (!trimmed.startsWith('/')) {
            return [];
        }
        const prefix = trimmed.split(/\s+/)[0].toLowerCase();
        return SLASH_COMMANDS.filter((c) => c.name.startsWith(prefix));
    }

    async function dispatchCommand(slash) {
        if (slash.name === '/help') {
            appendLocalCommandLog('/help', {
                summary: _helpSummary(),
            });
            return;
        }
        if (slash.name === '/clear') {
            await runClear();
            return;
        }
        if (slash.name === '/compact') {
            await runCompact({ silent: false });
            return;
        }
        if (slash.name === '/unpin') {
            await runUnpin();
            return;
        }
    }

    async function runUnpin() {
        if (!state.sessionId) {
            return;
        }
        if (!state.viewContext) {
            notification.add(
                _t("No view context is pinned."),
                { type: 'info' },
            );
            return;
        }
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'unpin_view_context',
                [state.sessionId],
            );
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t("Failed to clear view context: %s", formatError(error)),
                { type: 'danger' },
            );
        }
    }

    async function setApprovalMode(mode) {
        if (!state.sessionId) {
            return;
        }
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'set_approval_mode',
                [state.sessionId, mode || false],
            );
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t("Failed to set approval mode: %s", formatError(error)),
                { type: 'danger' },
            );
        }
    }

    function isAwaitingApproval() {
        return state.status === 'waiting'
            && (state.pendingAsk || {}).kind === 'approval';
    }

    function cycleApprovalMode() {
        const order = [false, 'ask', 'off'];
        const current = state.approvalMode === false || state.approvalMode === undefined
            ? false
            : state.approvalMode;
        const index = order.indexOf(current);
        const next = order[(index + 1) % order.length];
        return setApprovalMode(next);
    }

    async function approveTool() {
        if (!state.sessionId || !isAwaitingApproval()) {
            return;
        }
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'approve_tool', [state.sessionId],
            );
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t('Failed to approve tool: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }

    async function approveForSession() {
        if (!state.sessionId || !isAwaitingApproval()) {
            return;
        }
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'approve_for_session',
                [state.sessionId],
            );
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t('Failed to approve tool: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }

    async function rejectTool(reason) {
        if (!state.sessionId || !isAwaitingApproval()) {
            return;
        }
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'reject_tool',
                [state.sessionId],
                { reason: reason || '' },
            );
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t('Failed to reject tool: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }

    async function openPinnedContext() {
        const ctx = state.viewContext;
        if (!ctx || !ctx.model) {
            return;
        }
        const action = {
            type: 'ir.actions.act_window',
            res_model: ctx.model,
        };
        if (ctx.kind === 'record' && ctx.id) {
            action.res_id = ctx.id;
            action.view_mode = 'form';
            action.views = [[false, 'form']];
        } else {
            const viewType = ctx.view_type || 'list';
            action.view_mode = viewType;
            action.views = [[false, viewType]];
            if (Array.isArray(ctx.domain)) {
                action.domain = ctx.domain;
            }
        }
        try {
            await actionService.doAction(action);
        } catch (error) {
            notification.add(
                _t("Failed to open view: %s", formatError(error)),
                { type: 'danger' },
            );
        }
    }

    function _helpSummary() {
        return SLASH_COMMANDS
            .map((c) => `**${c.name}** — ${c.hint}`)
            .join('\n\n');
    }

    function appendLocalCommandLog(name, extra) {
        const entry = {
            kind: 'command',
            name,
            ...(extra || {}),
        };
        state.log = [...state.log, entry];
        logKeys.add(JSON.stringify(entry));
        requestScroll();
    }

    async function runClear() {
        if (!state.sessionId) {
            return;
        }
        if (state.status === 'running') {
            notification.add(
                _t("Stop the running session before clearing."),
                { type: 'warning' },
            );
            return;
        }
        const confirmed = await new Promise((resolve) => {
            dialog.add(ConfirmationDialog, {
                title: _t("Clear conversation"),
                body: _t(
                    "Wipe the current conversation and tool log? " +
                    "The session record and agent remain.",
                ),
                confirmLabel: _t("Clear"),
                cancelLabel: _t("Cancel"),
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            });
        });
        if (!confirmed) {
            return;
        }
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'clear', [state.sessionId],
            );
            applySnapshot(snapshot);
            if (options.onRefresh) {
                await options.onRefresh();
            }
        } catch (error) {
            notification.add(
                _t("Failed to clear session: %s", formatError(error)),
                { type: 'danger' },
            );
        }
    }

    async function runCompact({ silent }) {
        if (!state.sessionId) {
            return;
        }
        if (state.status === 'running') {
            notification.add(
                _t("Stop the running session before compacting."),
                { type: 'warning' },
            );
            return;
        }
        const savedStatus = state.status;
        state.status = 'running';
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'compact', [state.sessionId],
            );
            applySnapshot(snapshot);
            if (!silent) {
                notification.add(
                    _t("Conversation compacted."),
                    { type: 'success' },
                );
            }
        } catch (error) {
            state.status = savedStatus;
            notification.add(
                _t("Failed to compact conversation: %s", formatError(error)),
                { type: 'danger' },
            );
        }
    }

    async function maybeAutoCompact() {
        if (!state.contextWindow || !state.lastInputTokens) {
            return;
        }
        const ratio = state.lastInputTokens / state.contextWindow;
        if (ratio >= COMPACT_AUTO_RATIO) {
            await runCompact({ silent: true });
            notification.add(
                _t("Auto-compacted: context window was %s%% full.",
                    Math.round(ratio * 100)),
                { type: 'info' },
            );
        } else if (ratio >= COMPACT_WARN_RATIO && !state.autoCompactPending) {
            state.autoCompactPending = true;
            notification.add(
                _t(
                    "Context window at %s%%. Type /compact to free room " +
                    "before continuing.",
                    Math.round(ratio * 100),
                ),
                { type: 'warning' },
            );
        }
    }

    async function setAgent(agentId, agentName = '') {
        if (!state.sessionId) {
            return;
        }
        try {
            await orm.write('muk_ai.session', [state.sessionId], {
                agent_id: agentId || false,
            });
            state.agentId = agentId || null;
            state.agentName = agentName;
        } catch (error) {
            notification.add(
                _t('Failed to change agent: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }

    async function onRemoveAttachment(attachmentId) {
        state.pendingAttachments = state.pendingAttachments.filter(
            (a) => a.id !== attachmentId,
        );
        if (!state.sessionId) {
            return;
        }
        try {
            await orm.call(
                'muk_ai.session', 'discard_attachments',
                [state.sessionId, [attachmentId]],
            );
        } catch (_error) {
            // Non-fatal: attachment is cleaned when the session is unlinked.
        }
    }

    function toggleToolBlock(callId) {
        if (!callId) {
            return;
        }
        state.expandedTools = {
            ...state.expandedTools,
            [callId]: !state.expandedTools[callId],
        };
    }

    function isToolExpanded(callId) {
        return !!(callId && state.expandedTools[callId]);
    }

    // ----------------------------------------------------------
    // Rendering
    // ----------------------------------------------------------

    function renderedTurns() {
        return buildRenderedTurns(state.log);
    }

    function renderMarkdown(text) {
        return markup(renderMarkdownToHtml(text));
    }

    // ----------------------------------------------------------
    // Scroll plumbing
    // ----------------------------------------------------------

    function setScrollCallback(callback) {
        onScrollCallback = callback;
    }

    function requestScroll() {
        if (onScrollCallback) {
            onScrollCallback();
        }
    }

    // ----------------------------------------------------------
    // Lifecycle
    // ----------------------------------------------------------

    onWillUnmount(() => disconnectBus());

    return {
        state,
        load,
        applySnapshot,
        onInputChange,
        onSend,
        onStop,
        onAttachFiles,
        onRemoveAttachment,
        setAgent,
        toggleToolBlock,
        isToolExpanded,
        renderedTurns,
        renderMarkdown,
        setScrollCallback,
        canSend,
        canAttach,
        canStop,
        composerDisabled,
        runUnpin,
        setApprovalMode,
        cycleApprovalMode,
        openPinnedContext,
        approveTool,
        approveForSession,
        rejectTool,
    };
}
