import { CookiesApproval } from '@website/interactions/cookies/cookies_approval';
import { patch } from '@web/core/utils/patch';

import { MEDIAS_BREAKPOINTS, SIZES } from '@web/core/ui/ui_utils';

patch(CookiesApproval.prototype, {
    /**
     * Render the placeholder with the service the blocked element belongs to.
     *
     * The server stamps which service was stripped and which purpose would
     * release it, so the placeholder can name the provider instead of asking
     * for "optional cookies" in the abstract.
     *
     * A container can be flagged by its class while the embed inside it was
     * left alone, so an untouched src is the proof that nothing was blocked. The dataset is merged because a wrapped video
     * carries the flag on its container but the stamps on the iframe.
     */
    addOptionalCookiesWarning() {
        if (!this.iframeEl.dataset.nocookieSrc) {
            return;
        }
        const data = { ...this.el.dataset, ...this.iframeEl.dataset };
        this.renderAt(
            'website.cookiesWarning',
            {
                extraStyle: this.iframeEl.parentElement.classList.contains(
                    'media_iframe_video',
                )
                    ? `aspect-ratio: 16/9; max-width: ${
                          MEDIAS_BREAKPOINTS[SIZES.SM].maxWidth
                      }px;`
                    : '',
                extraClasses:
                    getComputedStyle(this.iframeEl.parentElement).position ===
                    'absolute'
                        ? ''
                        : 'my-3',
                serviceName: data.mukCookieService || '',
                serviceLabel: data.mukCookieLabel || '',
                categoryCode: data.mukCookieCategory || '',
                placeholderText: data.mukCookiePlaceholder || '',
            },
            this.iframeEl,
            'afterend',
        );
    },
});
