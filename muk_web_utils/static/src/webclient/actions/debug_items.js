import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

const debugRegistry = registry.category('debug');

/**
 * Build a debug-menu item opening the reports bound to the current model.
 * @param {object} context debug context with the active ``action`` and ``env``
 * @returns {object|null} the menu item descriptor, or null when no model is set
 */
function manageReports({ action, env }) {
    if (!action.res_model) {
        return null;
    }
    return {
        type: 'item',
        description: _t('Reports'),
        callback: () => {
            env.services.action.doAction({
                res_model: 'ir.actions.report',
                name: _t('Reports'),
                views: [
                    [false, 'list'],
                    [false, 'form'],
                ],
                type: 'ir.actions.act_window',
                domain: [['model', '=', action.res_model]],
            });
        },
        sequence: 260,
        section: 'ui',
    };
}

debugRegistry.category('action').add('manageReports', manageReports);
