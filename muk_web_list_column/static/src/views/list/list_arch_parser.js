import { patch } from '@web/core/utils/patch';

import { getColumnWidth } from '@muk_web_list_column/views/list/list_view_storage';

import { ListArchParser } from '@web/views/list/list_arch_parser';

/** Apply persisted column widths to labelled columns while parsing the list arch. */
patch(ListArchParser.prototype, {
    parse(xmlDoc, models, modelName) {
        const res = super.parse(...arguments);
        for (const column of res.columns) {
            const width = getColumnWidth(modelName, column.name);
            if (column.hasLabel && width) {
                column.attrs.width = width;
            }
        }
        return res;
    },
});
