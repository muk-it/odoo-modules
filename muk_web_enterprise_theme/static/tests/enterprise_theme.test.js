import { user } from "@web/core/user";
import { cookie } from "@web/core/browser/cookie";
import { expect, test } from "@odoo/hoot";

import { patchWithCleanup } from "@web/../tests/web_test_helpers";

import { getCompanyBackgroundImageUrl } from "@muk_web_enterprise_theme/webclient/home_menu/home_menu";

import "@muk_web_enterprise_theme/webclient/home_menu/home_menu";

test.tags("muk_web_enterprise_theme");
test("home menu sets custom background class based on color scheme", async () => {
    const realCompany = user.activeCompany;
    cookie.set("color_scheme", "dark");
    try {
        const patchedCompany = {
            ...realCompany,
            id: 1,
            has_background_image_dark: true,
            has_background_image_light: false,
        };
        patchWithCleanup(user, {
            get activeCompany() {
                return patchedCompany;
            },
        });
        const backgroundImageUrl = getCompanyBackgroundImageUrl(
            user.activeCompany,
            cookie.get("color_scheme")
        );
        document.body.classList.toggle(
            "o_home_menu_background_custom", !!backgroundImageUrl
        );
        expect(backgroundImageUrl.includes(
            "background_image_dark"
        )).toBe(true);
        expect(document.body.classList.contains(
            "o_home_menu_background_custom"
        )).toBe(true);
    } finally {
        cookie.delete("color_scheme");
        document.body.classList.remove(
            "o_home_menu_background_custom"
        );
    }
});
