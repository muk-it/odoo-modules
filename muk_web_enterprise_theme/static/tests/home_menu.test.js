import { user } from '@web/core/user';
import { cookie } from '@web/core/browser/cookie';
import { expect, test } from '@odoo/hoot';

import { patchWithCleanup } from '@web/../tests/web_test_helpers';

import { getCompanyBackgroundImageUrl } from '@muk_web_enterprise_theme/webclient/home_menu/home_menu';

function patchActiveCompany(values) {
    const company = { ...user.activeCompany, id: 3, ...values };
    patchWithCleanup(user, {
        get activeCompany() {
            return company;
        },
    });
    return company;
}

test.tags('muk_web_enterprise_theme');
test('dark color scheme uses the dark company background image', async () => {
    const company = patchActiveCompany({
        has_background_image_dark: true,
        has_background_image_light: true,
    });
    const url = getCompanyBackgroundImageUrl(company, 'dark');
    expect(url).toInclude('/web/image');
    expect(url).toInclude('background_image_dark');
    expect(url).toInclude('id=3');
});

test.tags('muk_web_enterprise_theme');
test('light color scheme uses the light company background image', async () => {
    const company = patchActiveCompany({
        has_background_image_dark: true,
        has_background_image_light: true,
    });
    const url = getCompanyBackgroundImageUrl(company, 'light');
    expect(url).toInclude('background_image_light');
    expect(url).not.toInclude('background_image_dark');
});

test.tags('muk_web_enterprise_theme');
test('an unset color scheme is treated as light', async () => {
    const company = patchActiveCompany({
        has_background_image_dark: true,
        has_background_image_light: true,
    });
    expect(getCompanyBackgroundImageUrl(company, undefined)).toInclude(
        'background_image_light',
    );
});

test.tags('muk_web_enterprise_theme');
test('dark scheme without a dark image falls back to no image', async () => {
    const company = patchActiveCompany({
        has_background_image_dark: false,
        has_background_image_light: true,
    });
    expect(getCompanyBackgroundImageUrl(company, 'dark')).toBe(null);
});

test.tags('muk_web_enterprise_theme');
test('light scheme without a light image falls back to no image', async () => {
    const company = patchActiveCompany({
        has_background_image_dark: true,
        has_background_image_light: false,
    });
    expect(getCompanyBackgroundImageUrl(company, 'light')).toBe(null);
});

test.tags('muk_web_enterprise_theme');
test('a company without any background image yields no url', async () => {
    const company = patchActiveCompany({
        has_background_image_dark: false,
        has_background_image_light: false,
    });
    expect(getCompanyBackgroundImageUrl(company, 'dark')).toBe(null);
    expect(getCompanyBackgroundImageUrl(company, 'light')).toBe(null);
});

test.tags('muk_web_enterprise_theme');
test('a missing company yields no url', async () => {
    expect(getCompanyBackgroundImageUrl(undefined, 'dark')).toBe(null);
    expect(getCompanyBackgroundImageUrl(null, 'light')).toBe(null);
});

test.tags('muk_web_enterprise_theme');
test('the color scheme cookie drives which image is picked', async () => {
    const company = patchActiveCompany({
        has_background_image_dark: true,
        has_background_image_light: true,
    });
    const realScheme = cookie.get('color_scheme');
    try {
        cookie.set('color_scheme', 'dark');
        expect(
            getCompanyBackgroundImageUrl(company, cookie.get('color_scheme')),
        ).toInclude('background_image_dark');
        cookie.set('color_scheme', 'light');
        expect(
            getCompanyBackgroundImageUrl(company, cookie.get('color_scheme')),
        ).toInclude('background_image_light');
    } finally {
        if (realScheme) {
            cookie.set('color_scheme', realScheme);
        } else {
            cookie.delete('color_scheme');
        }
    }
});
