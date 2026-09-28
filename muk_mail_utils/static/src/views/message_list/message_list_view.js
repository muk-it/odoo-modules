import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';

import { MessageListRenderer } from '@muk_mail_utils/views/message_list/message_list_renderer';
import { MessageListController } from '@muk_mail_utils/views/message_list/message_list_controller';

export const MessageListView = {
    ...listView,
    Renderer: MessageListRenderer,
    Controller: MessageListController,
};

registry.category('views').add('message_list', MessageListView);
