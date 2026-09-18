import { _t } from '@web/core/l10n/translation';

import {
    describeToolBlock,
    hiddenToolBlocks,
    toolBlockDecorators,
    toolPayload,
} from '@muk_ai/chat/session/turns';

import { DELEGATE_TOOL } from '@muk_ai_subagents/chat/run/run_store';

/**
 * Say what a delegate call asked for, in one line.
 *
 * The raw arguments are a wall of JSON, and the run itself is reported by the
 * cards that follow — so the card only has to name the agents it started.
 * @param {object} block the tool block being built
 */
function decorateDelegateBlock(block) {
    if (block.name !== DELEGATE_TOOL) {
        return;
    }
    describeToolBlock(block, {
        kind: 'delegate',
        // The call first returns `delegated`, then the whole run's outcome
        // once every subagent has reported; only a refusal carries an error.
        icon: ({ result }) =>
            result && result.error ? 'fa-exclamation-triangle' : 'fa-sitemap',
        band: ({ args }) => {
            const names = (args.tasks || [])
                .map((task) => task && task.agent)
                .filter(Boolean);
            if (!names.length) {
                return _t('Delegating…');
            }
            return names.length === 1
                ? _t('To %s', names[0])
                : _t('To %(first)s and %(count)s more', {
                      first: names[0],
                      count: names.length - 1,
                  });
        },
    });
}

toolBlockDecorators.add('muk_ai_subagents.delegate_tool', decorateDelegateBlock);

// The run has its own strip, spawn line and result cards, which stream and say
// far more; only a refusal has nothing else to appear in.
hiddenToolBlocks.add(
    'muk_ai_subagents.delegate_tool',
    (block) => block.name === DELEGATE_TOOL && !(toolPayload(block.result) || {}).error,
);

export { decorateDelegateBlock };
