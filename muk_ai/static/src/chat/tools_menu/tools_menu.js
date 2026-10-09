import { Component, signal, t, useProps, usePlugin } from '@odoo/owl';

import { Dropdown } from '@web/core/dropdown/dropdown';
import { _t } from '@web/core/l10n/translation';
import { UIPlugin } from '@web/core/ui/ui_plugin';

import { buildPills } from '@muk_ai/chat/pills/pills';

/**
 * The tools of a chat behind one composer button: the abilities and addon
 * sources of `session.data.tool_sources` as switches, grouped by section, and
 * on a narrow surface the pills, which have no row of their own there.
 */
export class ToolsMenu extends Component {
    static template = 'muk_ai.ToolsMenu';
    static components = { Dropdown };
    props = useProps({
        session: t.object(),
        withPills: t.boolean().optional(false),
    });
    ui = usePlugin(UIPlugin);
    expanded = signal('');
    get sources() {
        return this.props.session.data.tool_sources || [];
    }
    get sections() {
        const grouped = Object.groupBy(this.sources, (source) => source.section);
        return Object.entries(grouped).map(([label, sources]) => ({ label, sources }));
    }
    get pills() {
        return this.props.withPills || this.ui.isSmall()
            ? buildPills(this.props.session)
            : [];
    }
    current(pill) {
        return pill.options.find((option) => option.active) || pill.options[0];
    }
    toggle(source) {
        return this.props.session.run(
            'set_tool_source',
            [source.key, !source.enabled],
            _t('Failed to change the tools'),
        );
    }
}
