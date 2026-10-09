import { Component, t, useProps } from '@odoo/owl';

import { Dropdown } from '@web/core/dropdown/dropdown';
import { DropdownItem } from '@web/core/dropdown/dropdown_item';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

/**
 * The pills under the composer, as `{sequence, build(session), onSelect}`:
 * `build` returns `{label, title, slider, icon, className, tooltip, options}` or nothing,
 * each option `{value, label, hint, active}`, and `onSelect(session, value)`
 * acts on the choice. With `slider`, the tools menu draws the ordered options
 * as a slider instead of chips.
 */
export const sessionPills = registry.category('muk_ai.session_pills');

const EFFORTS = {
    minimal: [_t('Minimal'), _t('Answers immediately, barely thinks')],
    low: [_t('Low'), _t('Fastest, everyday questions')],
    medium: [_t('Medium'), _t('Balanced')],
    high: [_t('High'), _t('Hard analysis · costs more')],
    xhigh: [_t('Extra High'), _t('Long chains of reasoning · costs much more')],
    max: [_t('Maximum'), _t('Everything the model has · slowest')],
};

/**
 * Build the pills of a chat.
 * @param {object} session the chat
 * @returns {Array} `{key, entry, pill}` for every entry that builds a pill
 */
export function buildPills(session) {
    return sessionPills
        .getEntries()
        .map(([key, entry]) => ({ key, entry, pill: entry.build(session) }))
        .filter((item) => item.pill);
}

/** The pills of a chat: approval mode, reasoning effort and addon pills. */
export class SessionPills extends Component {
    static template = 'muk_ai.SessionPills';
    static components = { Dropdown, DropdownItem };
    props = useProps({ session: t.object() });
    get pills() {
        return buildPills(this.props.session);
    }
}

sessionPills.add(
    'approval',
    {
        build(session) {
            const data = session.data;
            const off = data.effective_approval_mode === 'off';
            const override = ![false, undefined].includes(data.override_approval_mode);
            const source = override ? _t('override') : _t('from agent');
            return {
                label: off ? _t('Bypass') : _t('Ask'),
                title: _t('Approvals'),
                icon: off ? 'flash_on' : 'security',
                className: `${off ? 'mk_pill_bypass' : 'mk_pill_ask'} ${override ? 'mk_pill_override' : ''}`,
                tooltip: session.readonly
                    ? _t('Approvals of a shared chat cannot be changed')
                    : off
                      ? _t('Bypass (%s)', source)
                      : _t('Ask before risky writes (%s)', source),
                options: [
                    {
                        value: 'ask',
                        label: _t('Ask first'),
                        hint: _t('Ask before risky writes'),
                        active: !off,
                    },
                    {
                        value: 'off',
                        label: _t('Bypass'),
                        hint: _t('Run without asking'),
                        active: off,
                    },
                ],
            };
        },
        onSelect: (session, value) => session.setApprovalMode(value),
    },
    { sequence: 10 },
);

sessionPills.add(
    'effort',
    {
        build(session) {
            const data = session.data;
            const tiers = data.reasoning_effort_options || [];
            if (!tiers.length) {
                return null;
            }
            const override =
                tiers.includes(data.override_reasoning_effort) &&
                data.override_reasoning_effort;
            const label = (tier) => EFFORTS[tier]?.[0] || tier;
            const agent = data.agent_reasoning_effort;
            return {
                label: data.effective_reasoning_effort
                    ? label(data.effective_reasoning_effort)
                    : _t('Default'),
                title: _t('Reasoning effort'),
                slider: true,
                icon: 'speed',
                className: override ? 'mk_pill_override' : '',
                tooltip: override
                    ? _t('How hard the model thinks (override)')
                    : _t('How hard the model thinks (from agent)'),
                options: [
                    {
                        value: false,
                        label: agent
                            ? _t('Agent default: %s', label(agent))
                            : _t('Agent default'),
                        active: !override,
                    },
                    ...tiers.map((tier) => ({
                        value: tier,
                        label: label(tier),
                        hint: EFFORTS[tier]?.[1],
                        active: tier === override,
                    })),
                ],
            };
        },
        onSelect: (session, value) => session.setReasoningEffort(value),
    },
    { sequence: 90 },
);
