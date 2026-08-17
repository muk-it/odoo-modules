/** @odoo-module **/

import publicWidget from 'web.public.widget';

/**
 * Report cookies, storage keys and third-party hosts the registry misses.
 *
 * Only rendered for editors, and only ever reports: the server decides what is
 * new, and a captured key gates nothing until somebody classifies it.
 */
const CookiesObserver = publicWidget.Widget.extend({
    selector: '#muk_cookies_observer',

    /**
     * @override
     */
    start() {
        this.reported = false;
        this.timeout = setTimeout(() => this._report(), 2000);
        return this._super(...arguments);
    },
    /**
     * @override
     */
    destroy() {
        clearTimeout(this.timeout);
        this._super(...arguments);
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Send what the page holds, once, after scripts further down have run.
     *
     * @private
     */
    async _report() {
        if (this.reported) {
            return;
        }
        this.reported = true;
        const keys = [
            ...this._collectCookies(),
            ...this._collectStorage('local', window.localStorage),
            ...this._collectStorage('session', window.sessionStorage),
            ...this._collectHosts(),
        ];
        if (keys.length) {
            await this._rpc({
                route: '/muk_website_cookies_consent/observe',
                params: { keys: keys },
            });
        }
    },
    /**
     * @private
     * @returns {object[]}
     */
    _collectCookies() {
        return document.cookie
            .split(';')
            .map((part) => part.split('=')[0].trim())
            .filter(Boolean)
            .map((name) => this._entry(name, 'http'));
    },
    /**
     * @private
     * @param {string} type
     * @param {Storage} storage
     * @returns {object[]}
     */
    _collectStorage(type, storage) {
        try {
            return Object.keys(storage).map((name) => this._entry(name, type));
        } catch {
            return [];
        }
    },
    /**
     * @private
     * @returns {object[]}
     */
    _collectHosts() {
        const hosts = new Set();
        for (const el of document.querySelectorAll(
            'script[src], iframe[src], img[src]',
        )) {
            const src = el.getAttribute('src') || '';
            if (!/^https?:\/\//.test(src) && !src.startsWith('//')) {
                continue;
            }
            try {
                const host = new URL(src, window.location.href).hostname.replace(
                    /^www\./,
                    '',
                );
                if (host && host !== window.location.hostname.replace(/^www\./, '')) {
                    hosts.add(host);
                }
            } catch {
                continue;
            }
        }
        return [...hosts].map((host) => this._entry(host, 'host'));
    },
    /**
     * @private
     * @param {string} name
     * @param {string} type
     * @returns {object}
     */
    _entry(name, type) {
        return { name: name, type: type, url: window.location.pathname };
    },
});

publicWidget.registry.MukCookiesObserver = CookiesObserver;

export default CookiesObserver;
