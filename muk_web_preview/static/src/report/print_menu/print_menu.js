import { useService } from '@web/core/utils/hooks';
import { patch } from '@web/core/utils/patch';

import { ActionMenus } from '@web/search/action_menus/action_menus';

/** The eye icon of a print item previews its report instead of printing it. */
patch(ActionMenus.prototype, {
    setup() {
        super.setup(...arguments);
        this.uiService = useService('ui');
    },
    /**
     * Run a selected item, with its report flagged for the preview when the eye was clicked.
     * @param {object} item
     * @param {MouseEvent} [ev]
     * @returns {Promise<void>}
     */
    async onItemSelected(item, ev) {
        if (!ev?.target.closest('.mk_report_preview')) {
            return super.onItemSelected(item);
        }
        const report = await this.actionService.loadAction(item.action.id);
        return super.onItemSelected({
            ...item,
            action: { id: { ...report, preview: true } },
        });
    },
});
