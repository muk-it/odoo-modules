import { Component, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { CheckBox } from '@web/core/checkbox/checkbox';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { useRecordObserver } from '@web/model/relational_model/utils';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

import { probeModuleAvailable } from '@muk_web_utils/views/module_availability';

const DEFAULT_APPS_BASE = 'https://apps.odoo.com/apps/modules/19.0';

/**
 * Boolean field that renders an Apps-store link and a checkbox, shown only when
 * the linked Odoo module is available on the instance.
 */
export class ModuleLinkField extends Component {
    static template = 'muk_web_utils.ModuleLinkField';
    static components = { CheckBox };
    static props = {
        ...standardFieldProps,
        appstoreUrl: { type: String, optional: true },
    };
    static defaultProps = {
        appstoreUrl: '',
    };
    setup() {
        this.orm = useService('orm');
        this.state = useState({ value: false, available: false });
        useRecordObserver((record) => {
            this.state.value = !!record.data[this.props.name];
        });
        if (this.moduleName) {
            probeModuleAvailable(this.orm, this.moduleName).then((available) => {
                this.state.available = available;
            });
        }
    }
    get moduleName() {
        return this.props.name.startsWith('module_') ? this.props.name.slice(7) : '';
    }
    get appstoreLink() {
        return this.props.appstoreUrl || `${DEFAULT_APPS_BASE}/${this.moduleName}`;
    }
    onChange(newValue) {
        this.state.value = newValue;
        this.props.record.update({ [this.props.name]: newValue });
    }
}

export const moduleLinkField = {
    component: ModuleLinkField,
    displayName: _t('Module Link'),
    supportedTypes: ['boolean'],
    supportedOptions: [
        { label: _t('Apps store URL override'), name: 'url', type: 'string' },
    ],
    isEmpty: () => false,
    extractProps: ({ options }) => ({
        appstoreUrl: options.url || '',
    }),
};

registry.category('fields').add('module_link', moduleLinkField);
