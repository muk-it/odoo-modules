import { describe, expect, test } from '@odoo/hoot';
import { queryOne, queryText } from '@odoo/hoot-dom';
import { advanceTime, animationFrame } from '@odoo/hoot-mock';

import { mountWithCleanup } from '@web/../tests/web_test_helpers';

import { BlockUIProgress } from '@muk_web_utils/core/block_progress/block_progress_ui';

describe.current.tags('muk_web_utils');

// ----------------------------------------------------------
// Helper

/**
 * Mount the blocking progress overlay for the given progress payload.
 * @param {object} progressData the reactive progress payload
 * @param {number} totalSteps the number of steps of the whole operation
 * @returns {Promise<object>} the mounted component
 */
async function mountOverlay(progressData, totalSteps = 4) {
    return mountWithCleanup(BlockUIProgress, {
        props: { progressData, totalSteps },
    });
}

// ----------------------------------------------------------
// Tests

test('the overlay shows the current step and fills the progress bar', async () => {
    await mountOverlay({ step: 2, value: 25 });
    expect('.mk_block_progress_overlay').toHaveCount(1);
    expect(queryText('.mk_block_progress_card')).toInclude('Batch');
    expect(queryText('.mk_block_progress_card')).toInclude('2');
    expect(queryText('.mk_block_progress_card')).toInclude('4');
    const bar = queryOne('.progress-bar');
    expect(bar.style.width).toBe('25%');
    expect(queryText('.progress-bar')).toBe('25%');
});

test('no estimate is shown while the progress is still at zero', async () => {
    await mountOverlay({ step: 0, value: 0 });
    await advanceTime(60000);
    await animationFrame();
    expect(queryText('.mk_block_progress_card')).not.toInclude('Estimated time left');
});

test('the estimate is shown in minutes once it exceeds one', async () => {
    await mountOverlay({ step: 1, value: 50 });
    await advanceTime(90000);
    await animationFrame();
    expect(queryText('.mk_block_progress_card')).toInclude('Estimated time left');
    expect(queryText('.mk_block_progress_card')).toInclude('1.50');
    expect(queryText('.mk_block_progress_card')).toInclude('minutes');
});

test('the estimate falls back to seconds below one minute', async () => {
    await mountOverlay({ step: 3, value: 75 });
    await advanceTime(60000);
    await animationFrame();
    expect(queryText('.mk_block_progress_card')).toInclude('20');
    expect(queryText('.mk_block_progress_card')).toInclude('seconds');
    expect(queryText('.mk_block_progress_card')).not.toInclude('minutes');
});

test('a zero progress is treated as one percent instead of dividing by zero', async () => {
    const component = await mountOverlay({ step: 0, value: 0 });
    await advanceTime(60000);
    expect(component.state.timeLeft).toBeCloseTo(99, { margin: 0.1 });
});

test('the estimate keeps shrinking as the progress advances', async () => {
    const progressData = { step: 1, value: 20 };
    const component = await mountOverlay(progressData);
    await advanceTime(60000);
    expect(component.state.timeLeft).toBeCloseTo(4, { margin: 0.01 });
    progressData.value = 80;
    await advanceTime(60000);
    expect(component.state.timeLeft).toBeCloseTo(0.5, { margin: 0.01 });
});
