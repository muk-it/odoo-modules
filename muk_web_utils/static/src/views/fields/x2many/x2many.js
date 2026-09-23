import { t } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';

import {
    X2ManyField,
    x2ManyField,
    x2ManyFieldProps,
} from '@web/views/fields/x2many/x2many_field';

Object.assign(x2ManyFieldProps, {
    canOpen: t.boolean().optional(true),
});

/** Honour a ``no_open`` option that prevents opening records from the x2many list. */
patch(X2ManyField.prototype, {
    setup() {
        super.setup();
        if (!this.props.canOpen) {
            this.canOpenRecord = false;
        }
    },
});

patch(x2ManyField, {
    extractProps({ options }) {
        const props = super.extractProps(...arguments);
        if ('no_open' in options) {
            props.canOpen = !options.no_open;
        }
        return props;
    },
});
