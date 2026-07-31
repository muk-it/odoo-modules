import { Component } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { SelectMenu } from '@web/core/select_menu/select_menu';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

const ICON_RULE = /^\.(fa-[\w-]+)::?before$/;

let icons = null;

/**
 * Collect every Font Awesome class the loaded stylesheets define.
 *
 * @returns {string[]} bare classes such as `fa-folder-o`
 */
export function fontAwesomeIcons() {
    if (icons) {
        return icons;
    }
    const found = new Set();
    for (const sheet of document.styleSheets) {
        let rules;
        try {
            rules = sheet.cssRules;
        } catch {
            continue;
        }
        for (const rule of rules) {
            for (const selector of rule.selectorText?.split(',') ?? []) {
                const match = selector.trim().match(ICON_RULE);
                if (match) {
                    found.add(match[1]);
                }
            }
        }
    }
    icons = [...found].sort();
    return icons;
}

/** Char field picking a Font Awesome class from a searchable icon grid. */
export class IconSelectorField extends Component {
    static template = 'muk_ai.IconSelectorField';
    static components = { SelectMenu };
    static props = {
        ...standardFieldProps,
        placeholder: { type: String, optional: true },
        required: { type: Boolean, optional: true },
    };
    setup() {
        this.choices = fontAwesomeIcons().map((icon) => ({
            value: icon,
            label: icon.slice(3).replace(/-/g, ' '),
        }));
    }
    get icon() {
        return this.props.record.data[this.props.name];
    }
    get searchPlaceholder() {
        return _t('Search an icon...');
    }
    onSelect(icon) {
        this.props.record.update({ [this.props.name]: icon || false });
    }
}

export const iconSelectorField = {
    component: IconSelectorField,
    displayName: _t('Icon Selector'),
    supportedTypes: ['char'],
    extractProps: ({ attrs }, dynamicInfo) => ({
        placeholder: attrs.placeholder,
        required: dynamicInfo.required,
    }),
};

registry.category('fields').add('icon_selector', iconSelectorField);
