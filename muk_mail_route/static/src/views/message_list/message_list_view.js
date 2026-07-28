// @odoo-module

import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';

import { MessageListRenderer } from '@muk_mail_route/views/message_list/message_list_renderer';
import { MessageListController } from '@muk_mail_route/views/message_list/message_list_controller';

export const MessageListView = {
    ...listView,
    Renderer: MessageListRenderer,
    Controller: MessageListController,
};

registry.category('views').add('muk_mail_route.message_list', MessageListView);
