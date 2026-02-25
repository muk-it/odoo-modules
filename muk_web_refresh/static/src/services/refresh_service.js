import { registry } from '@web/core/registry';

export const refreshService = {
    dependencies: ['bus_service', 'action'],
    start(env, { bus_service, action: actionService }) {
        bus_service.subscribe(
            'muk_web_refresh.reload',
            async (payload) => {
                const controller = actionService.currentController;
                if (
                    !controller ||
                    controller.action.type !== 'ir.actions.act_window'
                ) {
                    return;
                }
                const resModel = controller.action.res_model;
                const viewType = controller.view?.type;
                const { model, view_types, rec_ids } = payload;
                if (resModel !== model) {
                    return;
                }
                if (view_types.length > 0 && !view_types.includes(viewType)) {
                    if (!(viewType === 'list' && view_types.includes('tree'))) {
                        return;
                    }
                }
                if (rec_ids.length > 0) {
                    const currentResId = controller.currentState?.resId;
                    if (currentResId && !rec_ids.includes(currentResId)) {
                        return;
                    }
                }
                await actionService.doAction('soft_reload');
            }
        );
        bus_service.start();
    },
};

registry.category('services').add(
    'muk_web_refresh.reload', refreshService
);
