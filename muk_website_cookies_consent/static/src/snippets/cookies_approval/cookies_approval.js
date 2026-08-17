/** @odoo-module **/

import publicWidget from 'web.public.widget';

import { _t } from '@web/core/l10n/translation';
import { MEDIAS_BREAKPOINTS, SIZES } from '@web/core/ui/ui_service';
import { sprintf } from '@web/core/utils/strings';

/**
 * Put a named placeholder where a blocked embed was stripped.
 *
 * This branch of Odoo strips nothing and offers no placeholder, so the module
 * brings its own. The server stamps which service was removed and which
 * purpose would release it, which is what lets the placeholder name the
 * provider and offer that one embed instead of asking for "optional cookies"
 * in the abstract.
 */
const CookiesApproval = publicWidget.Widget.extend({
    selector: '[data-need-cookies-approval]',

    /**
     * @override
     */
    start() {
        this.iframeEl =
            this.el.tagName === 'IFRAME' ? this.el : this.el.querySelector('iframe');
        // A container is watchlisted by class alone, whatever per-service
        // consent says, so an untouched source is the proof that nothing was
        // blocked and the embed must be left alone.
        if (this.iframeEl?.dataset.nocookieSrc && !this._getWarningEl()) {
            this._addWarning();
        }
        return this._super(...arguments);
    },
    /**
     * @override
     */
    destroy() {
        if (this.__onConsent) {
            document.removeEventListener('optionalCookiesAccepted', this.__onConsent);
        }
        this._super(...arguments);
    },

    //--------------------------------------------------------------------------
    // Private
    //--------------------------------------------------------------------------

    /**
     * Return the placeholder already standing next to the embed, if any.
     *
     * @private
     * @returns {HTMLElement|null}
     */
    _getWarningEl() {
        const nextEl = this.iframeEl.nextElementSibling;
        return nextEl?.classList.contains('o_no_optional_cookie') ? nextEl : null;
    },
    /**
     * Hide the blocked embed and offer the choice that would bring it back.
     *
     * @private
     */
    _addWarning() {
        const data = { ...this.el.dataset, ...this.iframeEl.dataset };
        const label = data.mukCookieLabel || _t('a third party');
        this.warningEl = document.createElement('div');
        this.warningEl.className = 'o_no_optional_cookie mk_cookies_placeholder';
        this.warningEl.setAttribute('role', 'group');
        this.warningEl.setAttribute(
            'aria-label',
            sprintf(_t('Blocked content from %s'), label),
        );
        if (this.iframeEl.parentElement.classList.contains('media_iframe_video')) {
            this.warningEl.style.aspectRatio = '16/9';
            this.warningEl.style.maxWidth = `${
                MEDIAS_BREAKPOINTS[SIZES.SM].maxWidth
            }px`;
        }
        if (getComputedStyle(this.iframeEl.parentElement).position !== 'absolute') {
            this.warningEl.classList.add('my-3');
        }
        const textEl = document.createElement('p');
        textEl.className = 'mb-0 small';
        textEl.textContent =
            data.mukCookiePlaceholder ||
            sprintf(
                _t(
                    'This content is provided by %s and is not loaded until you allow it.',
                ),
                label,
            );
        this.warningEl.appendChild(textEl);
        if (data.mukCookieService) {
            const allowEl = document.createElement('button');
            allowEl.type = 'button';
            allowEl.className = 'btn btn-primary btn-sm mk_cookies_allow_embed';
            allowEl.dataset.mukCookieService = data.mukCookieService;
            allowEl.dataset.mukCookieCategory = data.mukCookieCategory || '';
            allowEl.textContent = sprintf(_t('Allow %s'), label);
            this.warningEl.appendChild(allowEl);
        }
        const reviewEl = document.createElement('button');
        reviewEl.type = 'button';
        reviewEl.className = 'btn btn-link btn-sm mk_cookies_reopen';
        reviewEl.textContent = _t('Review all cookie choices');
        this.warningEl.appendChild(reviewEl);
        this.iframeEl.insertAdjacentElement('afterend', this.warningEl);
        this.iframeEl.classList.add('d-none');
        this.__onConsent = this._removeWarning.bind(this);
        document.addEventListener('optionalCookiesAccepted', this.__onConsent, {
            once: true,
        });
    },
    /**
     * Load the embed that was blocked and take the placeholder away.
     *
     * @private
     */
    _removeWarning() {
        this.iframeEl.src = this.iframeEl.dataset.nocookieSrc;
        this.iframeEl.classList.remove('d-none');
        delete this.iframeEl.dataset.nocookieSrc;
        delete this.iframeEl.dataset.needCookiesApproval;
        delete this.iframeEl.closest(':not(iframe)[data-need-cookies-approval]')
            ?.dataset.needCookiesApproval;
        this.warningEl.remove();
    },
});

publicWidget.registry.MukCookiesApproval = CookiesApproval;

export default CookiesApproval;
