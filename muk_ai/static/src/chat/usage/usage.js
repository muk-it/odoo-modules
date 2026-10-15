import { Component, t, useProps } from '@odoo/owl';

import { Dropdown } from '@web/core/dropdown/dropdown';
import { _t } from '@web/core/l10n/translation';
import { formatInteger } from '@web/views/fields/formatters';

import { COMPACT_AUTO_RATIO, slashCommands } from '@muk_ai/core/session/session';
import { formatCost } from '@muk_ai/core/utils/utils';

/**
 * Ring showing how full a chat's context window is, opening the token,
 * iteration and cost usage of the last turn and of the whole chat.
 */
export class UsageMeter extends Component {
    static template = 'muk_ai.UsageMeter';
    static components = { Dropdown };
    props = useProps({
        session: t.object(),
        position: t.string().optional('top-end'),
    });
    get percent() {
        const { context_window: window, last_input_tokens: tokens } =
            this.props.session.data;
        return window ? Math.min(100, Math.round(((tokens || 0) / window) * 100)) : 0;
    }
    get level() {
        return this.percent >= 90
            ? 'mk_usage_red'
            : this.percent >= 70
              ? 'mk_usage_amber'
              : '';
    }
    get tokens() {
        const data = this.props.session.data;
        return _t('%(tokens)s / %(window)s tokens', {
            tokens: formatInteger(data.last_input_tokens || 0),
            window: formatInteger(data.context_window || 0),
        });
    }
    get tooltip() {
        return _t('Context window: %s', this.tokens);
    }
    get compactNote() {
        return _t(
            'At %s%% the conversation is compacted automatically',
            Math.round(COMPACT_AUTO_RATIO * 100),
        );
    }
    get rows() {
        const data = this.props.session.data;
        const turn = data.turn_usage || {};
        const count = (value) => formatInteger(value || 0);
        return [
            [
                'login',
                _t('Input'),
                count(turn.input_tokens),
                count(data.total_input_tokens),
            ],
            [
                'cached',
                _t('Cached'),
                count(turn.cached_tokens),
                count(data.total_cached_tokens),
            ],
            [
                'logout',
                _t('Output'),
                count(turn.output_tokens),
                count(data.total_output_tokens),
            ],
            [
                'repeat',
                _t('Iterations'),
                count(turn.iterations),
                count(data.iteration_count),
            ],
            [
                'attach_money',
                _t('Cost'),
                `$${formatCost(turn.cost)}`,
                `$${formatCost(data.total_cost)}`,
            ],
        ];
    }
}

/**
 * Render what the next turn sends as a Markdown table of its parts, with the
 * assembled system prompt below it when the user may read it.
 * @param {object} context the result of `muk_ai.session.get_context`
 * @returns {string} the Markdown summary
 */
export function formatContext(context) {
    const window = context.context_window || 1;
    const share = (tokens) => `${Math.round((tokens / window) * 100)}%`;
    const total = context.parts.reduce((sum, part) => sum + part.tokens, 0);
    const table = [
        `| ${_t('Part')} | ${_t('Tokens')} | ${_t('Share')} |`,
        '| --- | ---: | ---: |',
        ...[
            ...context.parts.map((part) => [part.label, part.tokens]),
            [_t('Free'), Math.max(0, window - total)],
        ].map(
            ([label, tokens]) =>
                `| ${label} | ${formatInteger(tokens)} | ${share(tokens)} |`,
        ),
    ];
    const summary = _t(
        'About %(total)s of %(window)s tokens. Last turn sent %(last)s.',
        {
            total: formatInteger(total),
            window: formatInteger(window),
            last: formatInteger(context.last_input_tokens || 0),
        },
    );
    const prompt = context.system_prompt && ['````', context.system_prompt, '````'];
    return [summary, '', ...table, ...(prompt ? ['', ...prompt] : [])].join('\n');
}

slashCommands.add('/context', {
    hint: _t('Show what the next turn sends and how full the context window is'),
    run: async (session) =>
        session.appendCommand('/context', {
            summary: formatContext(await session.callSession('get_context')),
        }),
});
