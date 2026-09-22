// @odoo-module

import { Component, useState } from '@odoo/owl';

import { registry } from '@web/core/registry';

import { ChatWindow } from '@muk_ai/chat/window/chat_window';

// Mounted from `main_components`, which the web test helpers CLONE while they
// CLEAR the `services` registry - so this container is mounted in suites that
// never started our service. `useService` throws there and the error escapes
// into the owl lifecycle, taking down every test that mounts a webclient.
// Read the service the way the rest of muk_ai does and render nothing without
// it; core mail's container is lazy for the same reason.
const NO_WINDOWS = { windows: [] };

/** Root container rendering all open chat windows from the chat-window service. */
export class ChatWindowContainer extends Component {
    static template = 'muk_ai.ChatWindowContainer';
    static components = { ChatWindow };
    static props = {};
    setup() {
        this.cw = this.env.services['muk_ai.chat_window'];
        this.state = useState(this.cw ? this.cw.state : NO_WINDOWS);
    }
}

registry.category('main_components').add('muk_ai.ChatWindowContainer', {
    Component: ChatWindowContainer,
});
