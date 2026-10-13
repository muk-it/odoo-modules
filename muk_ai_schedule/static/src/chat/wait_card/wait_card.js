import { _t } from '@web/core/l10n/translation';

import { describeToolBlock, toolBlockDecorators } from '@muk_ai/core/session/turns';
import { modelNames } from '@muk_ai/chat/tool_card/tool_labels';

const WAKE_REASONS = {
    time: () => _t('Woke up on time'),
    timeout: () => _t('Woke up: the wait timed out'),
    condition_met: () => _t('Woke up: the record is ready'),
    message: (result) => _t('Woke up: %s wrote a message', result.message?.author),
    record_deleted: () => _t('Woke up: the record is gone'),
    condition_invalid: () => _t('Woke up: the condition no longer works'),
    manual: () => _t('Woken up by hand'),
    user_message: () => _t('Woken up by a message'),
    stopped_by_user: () => _t('Stopped while waiting'),
};

/**
 * Say why a wait call ended.
 * @param {object} result the result of the call
 * @returns {string} the sentence, empty when the call failed
 */
function wakeLine(result) {
    if (result?.status === 'condition_met') {
        return _t('The record was ready already');
    }
    return WAKE_REASONS[result?.reason]?.(result) || '';
}

toolBlockDecorators.add('muk_ai_schedule.wait', (block) => {
    if (block.name === 'wait') {
        describeToolBlock(block, {
            icon: () => 'schedule',
            label: ({ args }) =>
                args.model
                    ? _t('Wait for %s', modelNames(args.model).name)
                    : _t('Wait'),
            band: ({ args, result, pending }) =>
                pending ? args.note || '' : wakeLine(result),
        });
    }
});
