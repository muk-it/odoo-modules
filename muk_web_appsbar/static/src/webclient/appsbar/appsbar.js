import { url } from '@web/core/utils/urls';
import { useService } from '@web/core/utils/hooks';
import { user } from '@web/core/user';

import { Component } from '@odoo/owl';

/**
 * Sidebar listing the installed apps, with an optional company footer image.
 */
export class AppsBar extends Component {
    static template = 'muk_web_appsbar.AppsBar';
    setup() {
        this.appMenuService = useService('app_menu');
        if (user.activeCompany.has_appsbar_image) {
            this.sidebarImageUrl = url('/web/image', {
                model: 'res.company',
                field: 'appbar_image',
                id: user.activeCompany.id,
            });
        }
    }
    _onAppClick(app) {
        return this.appMenuService.selectApp(app);
    }
}
