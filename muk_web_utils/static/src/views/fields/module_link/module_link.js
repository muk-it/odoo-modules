import { Component, signal, t, usePlugin, useProps } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { CheckBox } from '@web/core/checkbox/checkbox';
import { ORM } from '@web/core/orm_plugin';
import { registry } from '@web/core/registry';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

import {
    moduleNameFromField,
    probeModuleAvailable,
} from '@muk_web_utils/views/module_availability/module_availability';

/**
 * Boolean field that renders a checkbox when the linked Odoo module is
 * available on the instance, and an Apps store link otherwise.
 */
export class ModuleLinkField extends Component {
    static template = 'muk_web_utils.ModuleLinkField';
    static components = { CheckBox };
    props = useProps({
        ...standardFieldProps,
        appstoreUrl: t.string().optional(''),
    });
    available = signal(false);
    setup() {
        const moduleName = moduleNameFromField(this.props.name);
        this.appstoreLink =
            this.props.appstoreUrl ||
            `https://apps.odoo.com/apps/modules/${moduleName}`;
        probeModuleAvailable(usePlugin(ORM), moduleName).then((available) =>
            this.available.set(available),
        );
    }
    onChange(value) {
        this.props.record.update({ [this.props.name]: value });
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
