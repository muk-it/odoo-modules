import { describe, expect, test } from '@odoo/hoot';
import { queryOne, queryText } from '@odoo/hoot-dom';
import { advanceTime, animationFrame } from '@odoo/hoot-mock';

import { registry } from '@web/core/registry';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';

import { BlockUIProgress } from '@muk_web_utils/core/block_progress/block_progress_ui';

describe.current.tags('muk_web_utils');

// ----------------------------------------------------------
// Helper

/**
 * Mount the blocking progress overlay for the given progress payload.
 * @param {object} progressData the progress payload
 * @returns {Promise<object>} the mounted component
 */
async function mountOverlay(progressData) {
    return mountWithCleanup(BlockUIProgress, {
        props: { progressData, totalSteps: 4 },
    });
}

/**
 * Let time pass and return the rendered card text.
 * @param {number} ms the milliseconds to advance
 * @returns {Promise<string>} the card text
 */
async function cardTextAfter(ms) {
    await advanceTime(ms);
    await animationFrame();
    return queryText('.mk_block_progress_card');
}

// ----------------------------------------------------------
// Tests

test('block and unblock add and remove the overlay main component', async () => {
    const service = registry.category('services').get('block_progress').start();
    const mainComponents = registry.category('main_components');
    service.block({ totalSteps: 2, progressData: { step: 0, value: 0 } });
    expect(mainComponents.get('BlockUIProgress').props.totalSteps).toBe(2);
    service.unblock();
    expect(mainComponents.contains('BlockUIProgress')).toBe(false);
});

test('the overlay shows the current step and fills the progress bar', async () => {
    await mountOverlay({ step: 2, value: 25 });
    expect(queryText('.mk_block_progress_card')).toInclude('Batch 2 out of 4');
    expect(queryOne('.progress-bar').style.width).toBe('25%');
    expect('.progress-bar').toHaveText('25%');
});

test('no estimate is shown while the progress is still at zero', async () => {
    await mountOverlay({ step: 0, value: 0 });
    expect(await cardTextAfter(60000)).not.toInclude('Estimated time left');
});

test('the estimate switches from minutes to seconds as the progress advances', async () => {
    const progressData = { step: 1, value: 50 };
    await mountOverlay(progressData);
    expect(await cardTextAfter(90000)).toInclude('1.50 minutes');
    progressData.value = 90;
    expect(await cardTextAfter(30000)).toInclude('13 seconds');
});
