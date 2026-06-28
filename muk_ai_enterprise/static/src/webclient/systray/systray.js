import { registry } from '@web/core/registry';
import { patch } from '@web/core/utils/patch';
import { useService } from '@web/core/utils/hooks';
import { useHotkey } from '@web/core/hotkeys/hotkey_hook';
import { isMacOS } from '@web/core/browser/feature_detection';

import { MukAISystray } from '@muk_ai/webclient/systray/systray';

const ODOO_AI_HOTKEY = 'alt+shift+r';

registry.category('systray').remove('ai.systray_action');

patch(MukAISystray.prototype, {
    setup() {
        super.setup();
        this.aiChatLauncher = useService('aiChatLauncher');
        useHotkey(ODOO_AI_HOTKEY, () => this.onOpenOdooAI(), {
            global: true,
            bypassEditableProtection: true,
        });
    },
    get odooAIHotkeyLabel() {
        return isMacOS() ? 'Ctrl+Shift+R' : 'Alt+Shift+R';
    },
    /** Launch the Odoo Enterprise AI chat, mirroring the native systray action. */
    onOpenOdooAI() {
        const currentController = this.action.currentController;
        if (currentController?.view?.type === 'form') {
            this.env.bus.trigger('AI:OPEN_AI_CHAT', { origin: 'chatter_ai_button' });
            return;
        }
        this.aiChatLauncher.launchAIChat({
            callerComponentName: 'systray_ai_button',
        });
    },
});
