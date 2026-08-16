import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';

import { rpc } from '@web/core/network/rpc';

/**
 * Report cookies, storage keys and third-party hosts the registry misses.
 *
 * Only rendered for editors, and only ever reports: the server decides what is
 * new, and a captured key gates nothing until somebody classifies it.
 */
export class CookiesObserver extends Interaction {
    static selector = '#muk_cookies_observer';
    setup() {
        this.reported = false;
    }
    start() {
        this.waitForTimeout(() => this.report(), 2000);
    }
    /**
     * Send what the page holds, once, after scripts further down have run.
     */
    async report() {
        if (this.reported) {
            return;
        }
        this.reported = true;
        const keys = [
            ...this.collectCookies(),
            ...this.collectStorage('local', window.localStorage),
            ...this.collectStorage('session', window.sessionStorage),
            ...this.collectHosts(),
        ];
        if (keys.length) {
            await rpc('/muk_website_cookies_consent/observe', { keys });
        }
    }
    collectCookies() {
        return document.cookie
            .split(';')
            .map((part) => part.split('=')[0].trim())
            .filter(Boolean)
            .map((name) => this.entry(name, 'http'));
    }
    /**
     * @param {string} type
     * @param {Storage} storage
     * @returns {object[]}
     */
    collectStorage(type, storage) {
        try {
            return Object.keys(storage).map((name) => this.entry(name, type));
        } catch {
            return [];
        }
    }
    collectHosts() {
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
        return [...hosts].map((host) => this.entry(host, 'host'));
    }
    entry(name, type) {
        return { name: name, type: type, url: window.location.pathname };
    }
}

registry.category('public.interactions').add('muk_cookies_observer', CookiesObserver);
