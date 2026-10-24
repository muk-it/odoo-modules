// @odoo-module

import { _t } from '@web/core/l10n/translation';
import { usePopover } from '@web/core/popover/popover_hook';
import { registry } from '@web/core/registry';
import { DynamicPlaceholderPopover } from '@web/views/fields/dynamic_placeholder_popover';
import { TextField, textField } from '@web/views/fields/text/text_field';

/** Prompt template whose Insert Field button writes a placeholder of a variable. */
export class PromptField extends TextField {
    static template = 'muk_ai.PromptField';
    static props = {
        ...TextField.props,
        variable: { type: String, optional: true },
        resModel: { type: String, optional: true },
        resModelField: { type: String, optional: true },
    };
    static defaultProps = {
        ...TextField.defaultProps,
        variable: '',
        resModel: '',
        resModelField: '',
    };
    setup() {
        super.setup();
        this.fieldPopover = usePopover(DynamicPlaceholderPopover);
        this.selectionStart = this.props.record.data[this.props.name]?.length || 0;
    }
    get resModel() {
        return this.props.resModel || this.props.record.data[this.props.resModelField];
    }
    onBlur() {
        this.selectionStart = this.textareaRef.el.selectionStart;
    }
    onDynamicPlaceholderOpen(ev) {
        this.fieldPopover.open(ev.currentTarget, {
            resModel: this.resModel,
            validate: this.onDynamicPlaceholderValidate.bind(this),
        });
    }
    onDynamicPlaceholderValidate(chain, defaultValue) {
        if (!chain) {
            return;
        }
        const path = [this.props.variable, chain].filter(Boolean).join('.');
        const fallback = defaultValue ? ` ||| ${defaultValue}` : '';
        const textarea = this.textareaRef.el;
        textarea.focus();
        textarea.setRangeText(
            `{{${path}${fallback}}}`,
            this.selectionStart,
            this.selectionStart,
            'end',
        );
        textarea.dispatchEvent(new InputEvent('input'));
    }
}

registry.category('fields').add('prompt', {
    ...textField,
    component: PromptField,
    displayName: _t('Prompt'),
    supportedOptions: [
        { label: _t('Variable'), name: 'variable', type: 'string' },
        { label: _t('Model'), name: 'res_model', type: 'string' },
        { label: _t('Model field'), name: 'res_model_field', type: 'string' },
    ],
    supportedTypes: ['text'],
    additionalClasses: ['o_field_text'],
    extractProps: (fieldInfo, dynamicInfo) => ({
        ...textField.extractProps(fieldInfo, dynamicInfo),
        variable: fieldInfo.options.variable || '',
        resModel: fieldInfo.options.res_model || '',
        resModelField: fieldInfo.options.res_model_field || '',
    }),
    fieldDependencies: ({ options }) =>
        options.res_model_field
            ? [{ name: options.res_model_field, type: 'char' }]
            : [],
});
