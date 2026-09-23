import { session } from '@web/session';
import { patch } from '@web/core/utils/patch';
import { registry } from '@web/core/registry';

import * as M2OField from '@web/views/fields/many2one/many2one_field';
import {
    buildM2OFieldDescription,
    extractM2OFieldProps,
} from '@web/views/fields/many2one/many2one_field';

/**
 * Extract the many2one props, disabling quick-create when the session flag is
 * set and the field does not configure ``no_quick_create`` itself.
 * @param {object} staticInfo static field metadata
 * @param {object} dynamicInfo dynamic field metadata
 * @returns {object} the field props
 */
function extractProps(staticInfo, dynamicInfo) {
    const props = extractM2OFieldProps(staticInfo, dynamicInfo);
    if (session.disable_quick_create && staticInfo.options.no_quick_create == null) {
        props.canQuickCreate = false;
    }
    return props;
}

// eslint-disable-next-line no-import-assign -- reach every widget built on the core extractor
M2OField.extractM2OFieldProps = extractProps;
// eslint-disable-next-line no-import-assign -- reach every widget built on the core description
M2OField.buildM2OFieldDescription = (component) => ({
    ...buildM2OFieldDescription(component),
    extractProps,
});

/** Apply the quick-create switch to the many2one field registered by core. */
patch(registry.category('fields').get('many2one'), { extractProps });
