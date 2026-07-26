import { appMenuService } from '@muk_web_appsbar/webclient/menus/app_menu_service';

export function makeMenuTree(apps) {
    return {
        id: null,
        appID: null,
        actionID: null,
        name: 'root',
        childrenTree: apps.map((app) => ({
            id: app.id,
            appID: app.id,
            name: app.name,
            xmlid: app.xmlid,
            actionID: app.actionID,
            actionPath: `action-${app.actionID}`,
            webIconData: app.webIconData,
            childrenTree: [],
        })),
    };
}

export function makeMenuService({ tree, currentApp = null, onSelectMenu = () => {} }) {
    return {
        getCurrentApp: () => currentApp,
        getMenuAsTree: () => tree,
        selectMenu: onSelectMenu,
    };
}

export function startAppMenuService(options) {
    return appMenuService.start({}, { menu: makeMenuService(options) });
}
