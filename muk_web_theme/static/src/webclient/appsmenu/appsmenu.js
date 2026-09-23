import { user } from '@web/core/user';
import { url } from '@web/core/utils/urls';
import { useBus, useService } from '@web/core/utils/hooks';
import { GlobalBusPlugin } from '@web/core/global_bus_plugin';
import { Dropdown } from '@web/core/dropdown/dropdown';

import { useEffect, usePlugin } from '@odoo/owl';

/**
 * Apps-menu dropdown that renders the full-screen app grid over a configurable
 * background image and opens the command palette as the user types.
 */
export class AppsMenu extends Dropdown {
    setup() {
        super.setup();
        this.commandPaletteOpen = false;
        this.commandService = useService('command');
        this.globalBus = usePlugin(GlobalBusPlugin);
        if (user.activeCompany.has_background_image) {
            this.imageUrl = url('/web/image', {
                model: 'res.company',
                field: 'background_image',
                id: user.activeCompany.id,
            });
        } else {
            this.imageUrl =
                '/muk_web_theme/static/src/webclient/appsmenu/background.png';
        }
        useEffect(() => {
            if (!this.state.isOpen) {
                return;
            }
            const openMainPalette = (ev) => {
                if (
                    !this.commandPaletteOpen &&
                    ev.key.length === 1 &&
                    !ev.ctrlKey &&
                    !ev.altKey
                ) {
                    this.commandService.openMainPalette(
                        { searchValue: `/${ev.key}` },
                        () => {
                            this.commandPaletteOpen = false;
                        },
                    );
                    this.commandPaletteOpen = true;
                }
            };
            window.addEventListener('keydown', openMainPalette);
            return () => {
                window.removeEventListener('keydown', openMainPalette);
                this.commandPaletteOpen = false;
            };
        });
        useBus(this.globalBus.bus, 'ACTION_MANAGER:UI-UPDATED', () => {
            if (this.state.isOpen) {
                this.state.close();
            }
        });
    }
    onOpened() {
        super.onOpened();
        const menu = this.menuRef();
        if (menu) {
            menu.style.backgroundImage = `url('${this.imageUrl}')`;
        }
    }
}
