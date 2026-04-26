import { markup, onWillUnmount, useState } from '@odoo/owl';

import { ConfirmationDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { fileToBase64 } from '@muk_ai/core/attachment/file_helpers';
import { renderMarkdown as renderMarkdownToHtml } from '@muk_ai/core/markdown/markdown';
import { formatError } from '@muk_ai/chat/utils';

import { buildRenderedTurns } from '@muk_ai/chat/session/turns';

const SESSION_READ_FIELDS = [
    'id', 'name', 'state', 'pending_ask',
    'view_context', 'last_text', 'error_message',
    'iteration_count', 'total_input_tokens', 'total_output_tokens',
    'last_input_tokens', 'context_window', 'agent_id', 'total_cost',
    'override_approval_mode', 'effective_approval_mode',
    'pending_user_messages',
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
    const sessionNotification = useService('muk_ai.session_notification');

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
        streamingReasoning: '',
        streamingTools: [],
        pendingAttachments: [],
        focusToken: 0,
        agents: [],
        agentId: null,
        agentName: '',
        autoCompactPending: false,
        viewContext: null,
        approvalMode: false,
        effectiveApprovalMode: 'ask',
        pendingMessages: [],
    });

    let busHandler = null;
    let logKeys = new Set();
    let onScrollCallback = null;

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

    function logKey(entry) {
        const {at, ...rest} = entry || {};
        return canonicalStringify(rest);
    }

    function canonicalStringify(value) {
        if (value === null || typeof value !== 'object') {
            return JSON.stringify(value);
        }
        if (Array.isArray(value)) {
            return '[' + value.map(canonicalStringify).join(',') + ']';
        }
        const keys = Object.keys(value).sort();
        return '{' + keys.map(
            (k) => JSON.stringify(k) + ':' + canonicalStringify(value[k]),
        ).join(',') + '}';
    }

    function onBusEvent(event) {
        if (!event || event.session_id !== state.sessionId) {
            return;
        }
        if (event.type === 'log') {
            const key = logKey(event.payload);
            if (logKeys.has(key)) {
                return;
            }
            logKeys.add(key);
            state.log = [...state.log, event.payload];
            const kind = event.payload?.kind;
            if (kind === 'text') {
                state.streamingText = '';
                state.streamingReasoning = '';
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
        } else if (event.type === 'reasoning_delta') {
            const delta = (event.payload || {}).delta || '';
            if (delta) {
                state.streamingReasoning = (state.streamingReasoning || '') + delta;
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
                    state.streamingReasoning = '';
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
        } else if (event.type === 'queue') {
            state.pendingMessages = (event.payload || {}).pending || [];
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

    async function load(sessionId) {
        disconnectBus();
        sessionNotification.markInactive(state.sessionId);
        sessionNotification.markActive(sessionId);
        state.sessionId = sessionId;
        state.loading = true;
        state.input = '';
        state.error = null;
        state.pendingAsk = null;
        state.log = [];
        state.streamingText = '';
        state.streamingReasoning = '';
        state.streamingTools = [];
        state.pendingAttachments = [];
        logKeys = new Set();
        if (!sessionId) {
            state.loading = false;
            return null;
        }
        let record = null;
        let snapshot = null;
        try {
            const [result] = await orm.read(
                'muk_ai.session', [sessionId], SESSION_READ_FIELDS,
            );
            record = result || null;
        } catch (error) {
            state.error = formatError(error);
        }
        if (record) {
            try {
                snapshot = await orm.call(
                    'muk_ai.session', 'get_snapshot', [sessionId],
                );
            } catch (error) {
                snapshot = null;
            }
            applyRecord(record);
            if (snapshot && snapshot.tool_log !== undefined) {
                state.log = snapshot.tool_log || [];
                rebuildLogKeys();
            }
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
        state.pendingMessages = record.pending_user_messages || [];
        rebuildLogKeys();
    }

    function applySnapshot(snapshot) {
        if (!snapshot) {
            return;
        }
        state.status = snapshot.state;
        const incomingLog = snapshot.tool_log || [];
        if (incomingLog.length || state.status !== 'running') {
            state.log = incomingLog;
        }
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
        state.streamingReasoning = '';
        state.streamingTools = [];
        state.pendingMessages = snapshot.pending_user_messages || [];
        rebuildLogKeys();
    }

    function rebuildLogKeys() {
        logKeys = new Set((state.log || []).map((entry) => logKey(entry)));
    }

    function canSend() {
        const hasContent = state.input.trim().length > 0
            || state.pendingAttachments.length > 0;
        const idle = state.status !== 'running'
            && state.status !== 'compacting';
        return !!state.sessionId && hasContent && idle;
    }

    function canAttach() {
        return !!state.sessionId
            && state.status !== 'running'
            && state.status !== 'compacting';
    }

    function canStop() {
        return state.status === 'running';
    }

    function composerDisabled() {
        return false;
    }

    function isQueueing() {
        return state.status === 'running' || (
            state.status === 'waiting'
            && (state.pendingAsk || {}).kind === 'approval'
        );
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
        const message = state.input;
        const attachments = [...state.pendingAttachments];
        const attachmentIds = attachments.map((a) => a.id);
        state.input = '';
        state.pendingAttachments = [];
        if (isQueueing()) {
            const optimisticEntry = {
                content: message,
                attachment_ids: attachmentIds,
                queued_at: new Date().toISOString(),
            };
            state.pendingMessages = [...state.pendingMessages, optimisticEntry];
            state.focusToken += 1;
            requestScroll();
            try {
                const snapshot = await orm.call(
                    'muk_ai.session', 'enqueue_message',
                    [state.sessionId, message],
                    { attachment_ids: attachmentIds },
                );
                applySnapshot(snapshot);
            } catch (error) {
                notification.add(
                    _t('Failed to queue message: %s', formatError(error)),
                    { type: 'danger' },
                );
                state.pendingMessages = state.pendingMessages.filter(
                    (m) => m !== optimisticEntry,
                );
            }
            return;
        }
        await maybeAutoCompact();
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
        logKeys.add(logKey(optimistic));
        state.streamingText = '';
        state.streamingReasoning = '';
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

    async function cancelQueued(index) {
        if (!state.sessionId) {
            return;
        }
        const removed = state.pendingMessages[index];
        state.pendingMessages = state.pendingMessages.filter(
            (_m, i) => i !== index,
        );
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'cancel_queued',
                [state.sessionId, index],
            );
            applySnapshot(snapshot);
        } catch (error) {
            if (removed) {
                state.pendingMessages = [
                    ...state.pendingMessages.slice(0, index),
                    removed,
                    ...state.pendingMessages.slice(index),
                ];
            }
            notification.add(
                _t('Failed to cancel queued message: %s', formatError(error)),
                { type: 'danger' },
            );
        }
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

    async function onRegenerate() {
        if (!state.sessionId || state.status === 'running' || state.status === 'waiting') {
            return;
        }
        try {
            const snapshot = await orm.call(
                'muk_ai.session', 'regenerate_last_turn', [state.sessionId],
            );
            applySnapshot(snapshot);
        } catch (error) {
            notification.add(
                _t('Failed to regenerate: %s', formatError(error)),
                { type: 'danger' },
            );
        }
    }

    function canRegenerate() {
        if (!state.sessionId) return false;
        if (state.status === 'running' || state.status === 'waiting') return false;
        return (state.log || []).some((e) => e.kind === 'user_message' || e.kind === 'answer');
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

    async function answerWithOption(option) {
        if (state.status === 'running' || !option) {
            return;
        }
        state.input = option;
        await onSend();
    }

    async function respondYesno(decision) {
        const pending = state.pendingAsk || {};
        if (pending.kind === 'approval') {
            if (decision === 'approve') {
                return approveTool();
            }
            if (decision === 'session') {
                return approveForSession();
            }
            return rejectTool();
        }
        const labels = { approve: 'Approve', session: 'Approve', reject: 'Reject' };
        return answerWithOption(labels[decision] || decision);
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
        logKeys.add(logKey(entry));
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

    async function loadAgents() {
        try {
            state.agents = await orm.searchRead(
                'muk_ai.agent',
                [['active', '=', true]],
                ['id', 'name', 'description', 'suggestions'],
                { order: 'sequence, name' },
            );
        } catch (_error) {
            state.agents = [];
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

    async function onSetAgent(agentId) {
        const agent = state.agents.find((a) => a.id === agentId);
        await setAgent(agentId || null, agent ? agent.name : '');
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

    let cachedTurnsLog = null;
    let cachedTurns = [];
    function renderedTurns() {
        if (state.log !== cachedTurnsLog) {
            cachedTurnsLog = state.log;
            cachedTurns = buildRenderedTurns(state.log);
        }
        return cachedTurns;
    }

    function latestReasoningLine() {
        const text = state.streamingReasoning || '';
        if (!text) {
            return '';
        }
        const lines = text
            .split(/\n+/)
            .map((l) => l.trim().replace(/^[#*\->\s]+/, '').replace(/[*]+$/, ''))
            .filter((l) => l.length > 0);
        if (!lines.length) {
            return '';
        }
        return lines[lines.length - 1];
    }

    function renderMarkdown(text) {
        return markup(renderMarkdownToHtml(text));
    }

    function copyText(text) {
        if (!text || !navigator.clipboard) {
            return;
        }
        navigator.clipboard.writeText(String(text)).then(
            () => notification.add(_t('Copied to clipboard'), { type: 'success' }),
            () => notification.add(_t('Copy failed'), { type: 'danger' }),
        );
    }

    function setScrollCallback(callback) {
        onScrollCallback = callback;
    }

    function requestScroll() {
        if (onScrollCallback) {
            onScrollCallback();
        }
    }
    onWillUnmount(() => {
        sessionNotification.markInactive(state.sessionId);
        disconnectBus();
    });

    return {
        state,
        load,
        applySnapshot,
        onInputChange,
        onSend,
        onStop,
        onAttachFiles,
        onRemoveAttachment,
        loadAgents,
        setAgent,
        onSetAgent,
        toggleToolBlock,
        isToolExpanded,
        renderedTurns,
        latestReasoningLine,
        renderMarkdown,
        copyText,
        onRegenerate,
        canRegenerate,
        setScrollCallback,
        canSend,
        canAttach,
        canStop,
        composerDisabled,
        isQueueing,
        cancelQueued,
        runUnpin,
        setApprovalMode,
        cycleApprovalMode,
        openPinnedContext,
        approveTool,
        approveForSession,
        rejectTool,
        answerWithOption,
        respondYesno,
    };
}
