// @odoo-module

import { _t } from '@muk_ai/core/compat/translation';
import { registry } from '@web/core/registry';
import { useDynamicPlaceholder } from '@web/views/fields/dynamicplaceholder_hook';
import { TextField } from '@web/views/fields/text/text_field';

/** Prompt template whose Insert Field button writes a placeholder of a variable. */
export class PromptField extends TextField {
    setup() {
        super.setup();
        this.fieldPicker = useDynamicPlaceholder();
        this.selectionStart = (this.props.value || '').length;
    }
    get resModel() {
        return this.props.resModel || this.props.record.data[this.props.resModelField];
    }
    onBlur() {
        this.selectionStart = this.textareaRef.el.selectionStart;
    }
    async onDynamicPlaceholderOpen(ev) {
        await this.fieldPicker.open(ev.currentTarget, this.resModel, {
            validateCallback: this.onPromptFieldValidate.bind(this),
        });
    }
    onPromptFieldValidate(chain, defaultValue) {
        if (!chain || !chain.length) {
            return;
        }
        const path = [this.props.variable, ...chain].filter(Boolean).join('.');
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

PromptField.template = 'muk_ai.PromptField';
PromptField.props = {
    ...TextField.props,
    variable: { type: String, optional: true },
    resModel: { type: String, optional: true },
    resModelField: { type: String, optional: true },
};
PromptField.defaultProps = {
    ...TextField.defaultProps,
    variable: '',
    resModel: '',
    resModelField: '',
};
PromptField.extractProps = ({ field, attrs }) => ({
    ...TextField.extractProps({ field, attrs }),
    variable: attrs.options.variable || '',
    resModel: attrs.options.res_model || '',
    resModelField: attrs.options.res_model_field || '',
});
PromptField.supportedTypes = ['text'];
PromptField.additionalClasses = ['o_field_text', 'w-100'];
PromptField.displayName = _t('Prompt');

registry.category('fields').add('prompt', PromptField);
