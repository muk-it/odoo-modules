import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';

/**
 * Build a debug-menu item opening the reports bound to the current model.
 * @param {object} context debug context with the active ``action``
 * @returns {object|null} the menu item descriptor, or null when no model is set
 */
function manageReports({ action }) {
    const actionService = useService('action');
    if (!action.res_model) {
        return null;
    }
    const description = _t('Reports');
    return {
        type: 'item',
        description,
        callback: () => {
            actionService.doAction({
                res_model: 'ir.actions.report',
                name: description,
                views: [
                    [false, 'list'],
                    [false, 'form'],
                ],
                type: 'ir.actions.act_window',
                domain: [['model', '=', action.res_model]],
            });
        },
        sequence: 265,
        section: 'ui',
    };
}

registry.category('debug').category('action').add('manageReports', manageReports);
