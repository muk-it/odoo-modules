/** @odoo-module **/

import options from '@web_editor/js/editor/snippets.options';

const SETTING_FIELDS = {
    selectCookieLayout: 'cookie_layout',
    selectCookieDensity: 'cookie_density',
    toggleCookieFooter: 'cookie_reopen_footer',
    selectCookieFloat: 'cookie_reopen_float',
};

/**
 * Store the banner settings on the website and render the result from them.
 *
 * Core's popup options swap classes on the markup and let the editor save it.
 * This banner is rendered from the registry on every request, so freezing its
 * markup would detach the disclosure from the hash consent is checked against.
 * The settings are written on the website record instead and the editor is
 * reloaded, which keeps the sidebar honest: what it shows is the same server
 * render a visitor gets. Nothing is written while the editor is only hovering,
 * because a setting the visitor never picked must not reach the database.
 */
options.registry.MukCookiesBar = options.Class.extend({
    /**
     * @override
     */
    init() {
        this._super(...arguments);
        this.orm = this.bindService('orm');
        this.settings = {};
    },
    /**
     * @override
     */
    async willStart() {
        await this._super(...arguments);
        const [values] = await this.orm.read(
            'website',
            [this._getWebsiteId()],
            Object.values(SETTING_FIELDS),
        );
        this.settings = values;
    },

    /**
     * Show the banner when the editor asks to see it.
     *
     * Core's popup option is what reveals a hidden popup, and it only attaches
     * to a popup the editor may edit. This banner is rendered from the
     * registry and deliberately not editable, so revealing it is this option's
     * job, or the entry in the invisible elements panel would toggle a flag
     * and show nothing.
     *
     * @override
     */
    onTargetShow() {
        const modalEl = this.$target[0].querySelector('.modal');
        // Shown inside the editor's page frame, the banner blocks nothing in
        // the sidebar beside it. Saying so keeps the editor honest about which
        // dialog, if any, is holding the interface.
        modalEl.classList.add('o_inactive_modal');
        this.$target[0].classList.remove('d-none');
        this._bs(modalEl).modal('show');
    },
    /**
     * Hide the banner again, the same way core's popup option does.
     *
     * @override
     */
    onTargetHide() {
        const modalEl = this.$target[0].querySelector('.modal');
        this._bs(modalEl).modal('hide');
        modalEl.classList.remove('o_inactive_modal');
        this.$target[0].classList.add('d-none');
    },

    //--------------------------------------------------------------------------
    // Options
    //--------------------------------------------------------------------------

    /**
     * Choose where the banner sits and how much room it takes.
     *
     * @see this.selectClass for parameters
     */
    async selectCookieLayout(previewMode, widgetValue) {
        await this._store(previewMode, 'cookie_layout', widgetValue);
    },
    /**
     * Choose how much of the notice is shown before the visitor asks for more.
     *
     * @see this.selectClass for parameters
     */
    async selectCookieDensity(previewMode, widgetValue) {
        await this._store(previewMode, 'cookie_density', widgetValue);
    },
    /**
     * Offer the way back to the choice in the footer of every page.
     *
     * @see this.selectClass for parameters
     */
    async toggleCookieFooter(previewMode, widgetValue) {
        await this._store(previewMode, 'cookie_reopen_footer', Boolean(widgetValue));
    },
    /**
     * Choose which corner carries the button that reopens the choice.
     *
     * @see this.selectClass for parameters
     */
    async selectCookieFloat(previewMode, widgetValue) {
        await this._store(previewMode, 'cookie_reopen_float', widgetValue);
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Return an element wrapped in the jQuery of the page it belongs to.
     *
     * The page is an iframe with its own jQuery and its own Bootstrap, and
     * only that instance may drive a dialog inside it: driving it from the
     * editor's instance moves the element into the editor's own document,
     * which empties the banner.
     *
     * @private
     * @param {HTMLElement} element
     * @returns {jQuery}
     */
    _bs(element) {
        return this.ownerDocument.defaultView.$(element);
    },
    /**
     * Return the website the editor is looking at.
     *
     * @private
     * @returns {number}
     */
    _getWebsiteId() {
        let websiteId;
        this.trigger_up('context_get', {
            callback: (context) => {
                websiteId = context['website_id'];
            },
        });
        return websiteId;
    },
    /**
     * Write one setting on the website, then re-render the banner from it.
     *
     * @private
     * @param {boolean|string} previewMode
     * @param {string} field
     * @param {boolean|string} value
     */
    async _store(previewMode, field, value) {
        if (previewMode) {
            return;
        }
        await this.orm.write('website', [this._getWebsiteId()], { [field]: value });
        this.settings[field] = value;
        this.trigger_up('request_save', { reloadEditor: true });
    },
    /**
     * @override
     */
    _computeWidgetState(methodName) {
        const field = SETTING_FIELDS[methodName];
        if (!field) {
            return this._super(...arguments);
        }
        const value = this.settings[field];
        return typeof value === 'boolean' ? (value ? 'true' : '') : value;
    },
});

export default options.registry.MukCookiesBar;
