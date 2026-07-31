// @odoo-module

import { Component } from '@odoo/owl';

import { _t } from '@muk_ai/core/compat/translation';
import { registry } from '@web/core/registry';
import { evalDomain } from '@web/views/utils';
import { SelectMenu } from '@muk_ai/core/compat/select_menu';
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
        requiredModifier: { optional: true },
    };
    setup() {
        this.choices = fontAwesomeIcons().map((icon) => ({
            value: icon,
            label: icon.slice(3).replace(/-/g, ' '),
        }));
    }
    get icon() {
        return this.props.value;
    }
    /**
     * Whether the view marks the field as required, so it cannot be cleared.
     * Odoo 16 hands ``extractProps`` only the arch, and the modifier may be a
     * domain, so it is evaluated here where the record is at hand — 17.0 does
     * this upstream and passes the answer in.
     * @returns {boolean}
     */
    get isRequired() {
        return evalDomain(this.props.requiredModifier, this.props.record.evalContext);
    }
    get searchPlaceholder() {
        return _t('Search an icon...');
    }
    onSelect(icon) {
        this.props.update(icon || false);
    }
}

// Odoo 16 reads these as statics on the component and calls extractProps with a
// single ``{field, attrs}`` argument; the field descriptor object and the
// ``(staticInfo, dynamicInfo)`` signature both arrived in 17.0.
IconSelectorField.extractProps = ({ attrs }) => ({
    placeholder: attrs.placeholder,
    requiredModifier: attrs.modifiers.required,
});
IconSelectorField.supportedTypes = ['char'];
IconSelectorField.displayName = _t('Icon Selector');

registry.category('fields').add('icon_selector', IconSelectorField);
