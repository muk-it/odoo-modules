import { onWillStart, useState } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { useService } from '@web/core/utils/hooks';
import { FormLabelHighlightText } from '@web/webclient/settings_form_view/highlight_text/form_label_highlight_text';

import { moduleLinkField } from '@muk_web_utils/views/fields/module_link/module_link';
import { probeModuleAvailable } from '@muk_web_utils/views/module_availability';

/** Reveal the module-link addon hint on settings labels whose module is unavailable. */
patch(FormLabelHighlightText.prototype, {
    setup() {
        super.setup();
        this.addonState = useState({ show: false });
        const fieldInfo = this.props.fieldInfo;
        if (!fieldInfo || fieldInfo.field !== moduleLinkField) {
            return;
        }
        const moduleName = fieldInfo.options && fieldInfo.options.module;
        if (!moduleName) {
            return;
        }
        const orm = useService('orm');
        onWillStart(async () => {
            const available = await probeModuleAvailable(orm, moduleName);
            this.addonState.show = !available;
        });
    },
});
