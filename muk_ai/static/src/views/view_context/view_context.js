import { onMounted, onPatched, onWillUnmount, usePlugin } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { FormController } from '@web/views/form/form_controller';
import { KanbanController } from '@web/views/kanban/kanban_controller';
import { ListController } from '@web/views/list/list_controller';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';

/**
 * Add the active search domain to a view context.
 * @param {object} payload the view context
 * @param {object} controller the view controller
 * @returns {object} the view context with its domain
 */
export function withDomain(payload, controller) {
    const domain = controller.env.searchModel?.domain || [];
    return domain.length ? { ...payload, domain } : payload;
}

/**
 * Build the view context of a controller, by view type, as
 * `(controller) => payload|null`.
 */
export const viewContextBuilders = {
    form(controller) {
        const root = controller.model.root;
        if (!root?.resModel) {
            return null;
        }
        if (!root.resId) {
            return { kind: 'list', model: root.resModel, view_type: 'form' };
        }
        const name = root.data.display_name || root.data.name || '';
        return {
            kind: 'record',
            model: root.resModel,
            id: root.resId,
            display_name: String(name),
        };
    },
    list(controller) {
        return withDomain(
            { kind: 'list', model: controller.props.resModel, view_type: 'list' },
            controller,
        );
    },
    kanban(controller) {
        return withDomain(
            { kind: 'list', model: controller.props.resModel, view_type: 'kanban' },
            controller,
        );
    },
};

/**
 * Keep the chats open in a window pinned to the view this controller shows
 * each time it renders, and offer it to the `adjust_search` client tool,
 * whose `rendered()` resolves at its next render. Views in a dialog are a
 * passing picker, not what the user talks about, and stay out.
 * @param {object} controller the view controller
 * @param {string} viewType its view type
 */
export function useViewContext(controller, viewType) {
    if (controller.env.inDialog) {
        return;
    }
    const chat = usePlugin(AIChatPlugin);
    const waiting = [];
    const target = {
        controller,
        viewType,
        build: () => viewContextBuilders[viewType](controller),
        rendered: () => new Promise((resolve) => waiting.push(resolve)),
    };
    const dispatch = () => {
        if (chat.windows.length) {
            chat.pushContext(target.build());
        }
        waiting.splice(0).forEach((resolve) => resolve());
    };
    let unregister = null;
    onMounted(() => {
        unregister = chat.registerTarget(target);
        dispatch();
    });
    onPatched(dispatch);
    onWillUnmount(() => unregister());
}

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        useViewContext(this, 'form');
    },
});

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        useViewContext(this, 'list');
    },
});

patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        useViewContext(this, 'kanban');
    },
});
