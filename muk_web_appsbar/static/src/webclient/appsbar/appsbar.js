/** @odoo-module **/

import { url } from "@web/core/utils/urls";
import { useService } from "@web/core/utils/hooks";

import { Component } from "@odoo/owl";

export class AppsBar extends Component {
	setup() {
		this.companyService = useService('company');
    	if (this.companyService.currentCompany.has_appsbar_image) {
            this.sidebarImageUrl = url('/web/image', {
                model: 'res.company',
                field: 'appbar_image',
                id: this.companyService.currentCompany.id,
            });
    	}
    }
}

Object.assign(AppsBar, {
    template: 'muk_web_appsbar.AppsBar',
    props: {
    	apps: Array,
    },
});

