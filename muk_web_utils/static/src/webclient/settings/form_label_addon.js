import { signal, usePlugin } from '@odoo/owl';

import { ORM } from '@web/core/orm_plugin';
import { patch } from '@web/core/utils/patch';
import { FormLabelHighlightText } from '@web/webclient/settings_form_view/highlight_text/form_label_highlight_text';

import { moduleLinkField } from '@muk_web_utils/views/fields/module_link/module_link';
import {
    moduleNameFromField,
    probeModuleAvailable,
} from '@muk_web_utils/views/module_availability/module_availability';

/** Mark settings labels with an add-on badge when their linked module is unavailable. */
patch(FormLabelHighlightText.prototype, {
    setup() {
        super.setup();
        this.showAddonBadge = signal(false);
        const fieldInfo = this.props.fieldInfo;
        if (fieldInfo?.field !== moduleLinkField) {
            return;
        }
        const moduleName = moduleNameFromField(fieldInfo.name);
        probeModuleAvailable(usePlugin(ORM), moduleName).then((available) =>
            this.showAddonBadge.set(!available),
        );
    },
});
