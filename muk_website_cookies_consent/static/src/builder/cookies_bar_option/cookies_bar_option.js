import { BuilderAction } from '@html_builder/core/builder_action';
import { Plugin } from '@html_editor/plugin';
import { registry } from '@web/core/registry';

/**
 * Store one banner setting on the website and render the result from it.
 *
 * Core's layout action rebuilds `.modal-content` from a client template and
 * lets the editor save the markup. This banner is rendered from the registry on
 * every request, so freezing it would detach the disclosure from the hash
 * consent is checked against. Reloading instead of swapping classes in place is
 * what keeps the sidebar honest: the editor shows what a visitor will get,
 * because it is the same server render. Reloading also turns the preview off,
 * so a setting is written when the editor picks it rather than when they hover
 * past it.
 */
class SelectCookieSettingAction extends BuilderAction {
    setup() {
        this.reload = {};
        this.value = undefined;
    }
    async prepare() {
        const [values] = await this.services.orm.read(
            'website',
            [this.services.website.currentWebsite.id],
            [this.constructor.field],
        );
        this.value = values[this.constructor.field];
    }
    getValue() {
        return this.value;
    }
    isApplied({ value }) {
        return this.value === value;
    }
    async apply({ value }) {
        await this.services.orm.write(
            'website',
            [this.services.website.currentWebsite.id],
            { [this.constructor.field]: value },
        );
        this.value = value;
    }
}

/** Choose where the banner sits and how much room it takes. */
export class SelectCookieLayoutAction extends SelectCookieSettingAction {
    static id = 'selectCookieLayout';
    static field = 'cookie_layout';
}

/** Choose how much of the notice is shown before the visitor asks for more. */
export class SelectCookieDensityAction extends SelectCookieSettingAction {
    static id = 'selectCookieDensity';
    static field = 'cookie_density';
}

/** Choose which corner carries the button that reopens the choice. */
export class SelectCookieFloatAction extends SelectCookieSettingAction {
    static id = 'selectCookieFloat';
    static field = 'cookie_reopen_float';
}

class CookiesBarSettingPlugin extends Plugin {
    static id = 'mukCookiesBarSettingPlugin';
    resources = {
        builder_actions: {
            SelectCookieLayoutAction,
            SelectCookieDensityAction,
            SelectCookieFloatAction,
        },
    };
}

registry
    .category('website-plugins')
    .add(CookiesBarSettingPlugin.id, CookiesBarSettingPlugin);
