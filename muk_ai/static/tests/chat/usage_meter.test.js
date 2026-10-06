import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import { click, queryAllTexts } from '@odoo/hoot-dom';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { AIUsageMeter } from '@muk_ai/chat/usage/usage_meter';

describe.current.tags('muk_ai');
defineMailModels();

function usageState(values = {}) {
    return {
        contextWindow: 8000,
        lastInputTokens: 2000,
        inputTokens: 12000,
        outputTokens: 900,
        iterationCount: 6,
        totalCost: 0.5,
        turnUsage: { input_tokens: 4000, output_tokens: 300, iterations: 2, cost: 0.12 },
        ...values,
    };
}

test('the ring shows the context fill and colours it near the limit', async () => {
    const state = usageState();
    const meter = await mountWithCleanup(AIUsageMeter, { props: { state } });
    expect(meter.percent).toBe(25);
    expect(meter.level).toBe('');
    expect('.mk_usage_meter').toHaveText('25%');
    state.lastInputTokens = 6000;
    expect(meter.level).toBe('mk_usage_amber');
    state.lastInputTokens = 7600;
    expect(meter.level).toBe('mk_usage_red');
    state.contextWindow = 0;
    expect(meter.percent).toBe(0);
});

test('the popover lists the last turn next to the session', async () => {
    await mountWithCleanup(AIUsageMeter, { props: { state: usageState() } });
    expect('.mk_usage_pop').toHaveCount(0);
    await click('.mk_usage_meter');
    await animationFrame();
    expect('.mk_usage_pop').toHaveCount(1);
    expect(queryAllTexts('.mk_usage_num')).toEqual([
        '4,000',
        '12,000',
        '300',
        '900',
        '2',
        '6',
        '$0.120',
        '$0.500',
    ]);
});

test('a session without a finished turn reads zero for the turn', async () => {
    await mountWithCleanup(AIUsageMeter, {
        props: { state: usageState({ turnUsage: {} }) },
    });
    await click('.mk_usage_meter');
    await animationFrame();
    expect(queryAllTexts('.mk_usage_num')).toEqual([
        '0',
        '12,000',
        '0',
        '900',
        '0',
        '6',
        '$0',
        '$0.500',
    ]);
});

test('a click outside closes the popover', async () => {
    await mountWithCleanup(AIUsageMeter, { props: { state: usageState() } });
    await click('.mk_usage_meter');
    await animationFrame();
    await click('.mk_usage_pop');
    await animationFrame();
    expect('.mk_usage_pop').toHaveCount(1);
    await click(document.body);
    await animationFrame();
    expect('.mk_usage_pop').toHaveCount(0);
});
