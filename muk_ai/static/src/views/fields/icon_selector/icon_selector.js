import { Component, t, useProps } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { SelectMenu } from '@web/core/select_menu/select_menu';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

/**
 * The Material Symbols a space can carry, all of them in the subset of the
 * icon font the web client ships.
 */
export const SPACE_ICONS = `
    folder folder_open work business home group person star favorite bookmark flag
    label sell inventory_2 shopping_cart storefront payments attach_money
    receipt_long account_balance bar_chart pie_chart show_chart calculate mail
    forum chat_bubble campaign phone calendar_today schedule timer hourglass_top
    public location_on local_shipping flight directions_car travel build settings
    tune code terminal bug_report science school book description article newspaper
    lightbulb rocket_launch flash_on wand_stars security lock key gavel balance eco
    factory local_hospital medical_services support help info warning share
    extension deployed_code apps grid_view account_tree database dns cloud laptop
    smartphone print image photo_camera videocam music_note palette brush edit
    checklist task inbox archive trophy card_giftcard handshake restaurant coffee
    pets sports_soccer translate search
`
    .trim()
    .split(/\s+/);

const CHOICES = SPACE_ICONS.map((icon) => ({
    value: icon,
    label: icon.replace(/_/g, ' '),
}));

/** Searchable grid of icons, showing the one picked with its name. */
export class IconPicker extends Component {
    static template = 'muk_ai.IconPicker';
    static components = { SelectMenu };
    props = useProps({
        value: t.string().optional(''),
        onSelect: t.function(),
        boxed: t.boolean().optional(false),
        required: t.boolean().optional(false),
        placeholder: t.string().optional(),
    });
    choices = CHOICES;
    searchPlaceholder = _t('Search an icon...');
}

/** Char field picking a Material Symbol from a searchable icon grid. */
export class IconSelectorField extends Component {
    static template = 'muk_ai.IconSelectorField';
    static components = { IconPicker };
    props = useProps({
        ...standardFieldProps,
        placeholder: t.string().optional(),
        required: t.boolean().optional(false),
    });
    get icon() {
        return this.props.record.data[this.props.name] || '';
    }
    onSelect(icon) {
        this.props.record.update({ [this.props.name]: icon || false });
    }
}

registry.category('fields').add('icon_selector', {
    component: IconSelectorField,
    displayName: _t('Icon Selector'),
    supportedTypes: ['char'],
    extractProps: ({ attrs }, dynamicInfo) => ({
        placeholder: attrs.placeholder,
        required: dynamicInfo.required,
    }),
});
