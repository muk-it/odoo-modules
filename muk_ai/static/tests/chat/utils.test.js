import { describe, expect, test } from '@odoo/hoot';
import { freezeTime, mockDate } from '@odoo/hoot-mock';
import { patchTranslations } from '@web/../tests/web_test_helpers';

import {
    approvalPill,
    costTooltip,
    effortLabel,
    effortPill,
    formatCost,
    formatDurationSeconds,
    formatRelativeTime,
    inputPlaceholder,
    statusLabel,
} from '@muk_ai/chat/utils';

describe.current.tags('muk_ai');
patchTranslations();

/**
 * Pin the clock so that ``Date.now()`` and ``DateTime.now()`` cannot drift apart.
 *
 * Without freezing, hoot's mocked date still tracks the real performance clock,
 * so the instant a test computes is already a millisecond in the past by the
 * time the formatter reads the clock again.
 */
function freezeClock() {
    mockDate('2026-07-01T12:00:00.000Z');
    freezeTime();
}

test('statusLabel maps known statuses to translated label', () => {
    expect(statusLabel('running').toString()).toMatch(/Running/i);
    expect(statusLabel('waiting').toString()).toMatch(/Waiting/i);
    expect(statusLabel('done').toString()).toMatch(/Done/i);
    expect(statusLabel('error').toString()).toMatch(/Error/i);
    expect(statusLabel('stopped').toString()).toMatch(/Stopped/i);
    expect(statusLabel('new').toString()).toMatch(/New/i);
});

test('statusLabel echoes unknown status back verbatim', () => {
    expect(statusLabel('bizarre')).toBe('bizarre');
});

test('formatCost returns "0" for zero/falsy', () => {
    expect(formatCost(0)).toBe('0');
    expect(formatCost(null)).toBe('0');
    expect(formatCost(undefined)).toBe('0');
    expect(formatCost('notanumber')).toBe('0');
});

test('formatCost uses 4 decimals below 0.01', () => {
    expect(formatCost(0.00123)).toBe('0.0012');
    expect(formatCost(0.009)).toBe('0.0090');
});

test('formatCost uses 3 decimals between 0.01 and 1', () => {
    expect(formatCost(0.05)).toBe('0.050');
    expect(formatCost(0.999)).toBe('0.999');
});

test('formatCost uses 2 decimals at or above 1', () => {
    expect(formatCost(1)).toBe('1.00');
    expect(formatCost(12.3456)).toBe('12.35');
});

test('costTooltip formats 6 decimals with USD suffix', () => {
    expect(costTooltip(0).toString()).toBe('Session cost so far: $0.000000 (USD)');
    expect(costTooltip(0.12345678).toString()).toBe(
        'Session cost so far: $0.123457 (USD)',
    );
});

test('approvalPill returns Bypass pill when mode is off', () => {
    const pill = approvalPill({ effectiveApprovalMode: 'off' });
    expect(pill.label.toString()).toMatch(/Bypass/);
    expect(pill.icon).toBe('fa-bolt');
    expect(pill.className).toMatch(/mk_approval_bypass/);
});

test('approvalPill returns Ask pill when mode is ask', () => {
    const pill = approvalPill({ effectiveApprovalMode: 'ask' });
    expect(pill.label.toString()).toMatch(/Ask/);
    expect(pill.icon).toBe('fa-shield');
    expect(pill.className).toMatch(/mk_approval_ask/);
});

test('approvalPill marks override when approvalMode is set', () => {
    const pill = approvalPill({
        effectiveApprovalMode: 'off',
        approvalMode: 'off',
    });
    expect(pill.className).toMatch(/mk_pill_override/);
    expect(pill.tooltip.toString()).toMatch(/override/);
});

test('approvalPill drops override flag when approvalMode is false', () => {
    const pill = approvalPill({
        effectiveApprovalMode: 'ask',
        approvalMode: false,
    });
    expect(pill.className).not.toMatch(/mk_pill_override/);
    expect(pill.tooltip.toString()).toMatch(/from agent/);
});

test('effortPill is null when the model offers no tiers', () => {
    expect(effortPill({ reasoningEffortOptions: [] })).toBe(null);
});

test('effortPill leads with the agent-default row, then the model tiers', () => {
    const pill = effortPill({
        reasoningEffortOptions: ['low', 'medium', 'high'],
        effectiveReasoningEffort: 'medium',
        agentReasoningEffort: 'medium',
        reasoningEffort: false,
    });
    expect(pill.options.map((o) => o.tier)).toEqual([false, 'low', 'medium', 'high']);
    expect(String(pill.options[0].label)).toMatch(/Agent default/);
    expect(String(pill.options[0].label)).toMatch(/Medium/);
    // Exactly one tick, and while inheriting it belongs to the default row:
    // the pill reads Medium because that is what resolves, not what is pinned.
    expect(pill.options.filter((o) => o.active).map((o) => o.tier)).toEqual([false]);
    expect(String(pill.label)).toBe('Medium');
    expect(pill.className).not.toMatch(/mk_pill_override/);
});

test('effortPill moves the tick onto the pinned tier', () => {
    const pill = effortPill({
        reasoningEffortOptions: ['low', 'medium', 'high'],
        effectiveReasoningEffort: 'high',
        agentReasoningEffort: 'low',
        reasoningEffort: 'high',
    });
    expect(pill.options.filter((o) => o.active).map((o) => o.tier)).toEqual(['high']);
    expect(pill.className).toMatch(/mk_pill_override/);
    expect(pill.tooltip.toString()).toMatch(/override/);
});

test('effortPill ignores an override the model no longer accepts', () => {
    const pill = effortPill({
        reasoningEffortOptions: ['low', 'medium'],
        effectiveReasoningEffort: 'low',
        agentReasoningEffort: 'low',
        reasoningEffort: 'max',
    });
    expect(pill.options.filter((o) => o.active).map((o) => o.tier)).toEqual([false]);
    expect(pill.className).not.toMatch(/mk_pill_override/);
    expect(String(pill.label)).toBe('Low');
});

test('effortPill falls back to Default when nothing resolves a tier', () => {
    const pill = effortPill({
        reasoningEffortOptions: ['low'],
        effectiveReasoningEffort: false,
        agentReasoningEffort: false,
        reasoningEffort: false,
    });
    expect(String(pill.label)).toBe('Default');
    expect(String(pill.options[0].label)).toBe('Agent default');
});

test('effortLabel names known tiers and passes unknown ones through', () => {
    expect(String(effortLabel('xhigh'))).toBe('Extra High');
    expect(String(effortLabel('banana'))).toBe('banana');
});

test('inputPlaceholder overrides default when waiting for a question', () => {
    const text = inputPlaceholder(
        { status: 'waiting', pendingAsk: { kind: 'question' } },
        'default text',
    );
    expect(text.toString()).toMatch(/answer/i);
});

test('inputPlaceholder overrides default when waiting for approval', () => {
    const text = inputPlaceholder(
        { status: 'waiting', pendingAsk: { kind: 'approval' } },
        'default text',
    );
    expect(text.toString()).toMatch(/Approve|reject/i);
});

test('inputPlaceholder overrides default when running', () => {
    const text = inputPlaceholder({ status: 'running' }, 'default text');
    expect(text.toString()).toMatch(/Stop/i);
});

test('inputPlaceholder returns default when idle', () => {
    const text = inputPlaceholder({ status: 'done' }, 'default text');
    expect(text).toBe('default text');
});

test('inputPlaceholder overrides default for waiting_schedule', () => {
    const text = inputPlaceholder({ status: 'waiting_schedule' }, 'default text');
    expect(text.toString()).toMatch(/Scheduled/i);
});

test('formatRelativeTime returns empty string for falsy or past', () => {
    expect(formatRelativeTime(null)).toBe('');
    expect(formatRelativeTime('')).toBe('');
    expect(formatRelativeTime('2000-01-01T00:00:00Z')).toBe('');
});

test('formatRelativeTime renders future minutes/seconds', () => {
    freezeClock();
    const future = new Date(Date.now() + 5 * 60 * 1000 + 12 * 1000).toISOString();
    expect(formatRelativeTime(future).toString()).toBe('5m 12s');
});

test('formatRelativeTime renders sub-minute distances in seconds', () => {
    freezeClock();
    const future = new Date(Date.now() + 42 * 1000).toISOString();
    expect(formatRelativeTime(future).toString()).toBe('42s');
});

test('formatRelativeTime renders future hours/minutes', () => {
    freezeClock();
    const future = new Date(
        Date.now() + 3 * 3600 * 1000 + 12 * 60 * 1000,
    ).toISOString();
    expect(formatRelativeTime(future).toString()).toBe('3h 12m');
});

test('formatDurationSeconds picks the right unit', () => {
    expect(formatDurationSeconds(60).toString()).toBe('1m');
    expect(formatDurationSeconds(300).toString()).toBe('5m');
    expect(formatDurationSeconds(3600).toString()).toBe('1h');
    expect(formatDurationSeconds(86400).toString()).toBe('1d');
    expect(formatDurationSeconds(45).toString()).toBe('45s');
    expect(formatDurationSeconds(0)).toBe('');
    expect(formatDurationSeconds(null)).toBe('');
});
