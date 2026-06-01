import { Component, useState } from '@odoo/owl';

import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';

import { ChatWindow } from '@muk_ai/chat/window/chat_window';

export class ChatWindowContainer extends Component {
    static template = 'muk_ai.ChatWindowContainer';
    static components = { ChatWindow };
    static props = {};
    setup() {
        this.cw = useService('muk_ai.chat_window');
        this.state = useState(this.cw.state);
    }
}

registry.category('main_components').add('muk_ai.ChatWindowContainer', {
    Component: ChatWindowContainer,
});
