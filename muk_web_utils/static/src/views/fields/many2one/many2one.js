import { session } from '@web/session';
import { patch } from '@web/core/utils/patch';
import { registry } from '@web/core/registry';

import * as M2OField from '@web/views/fields/many2one/many2one_field';

const originalExtractM2OFieldProps = M2OField.extractM2OFieldProps;
const originalbuildM2OFieldDescription = M2OField.buildM2OFieldDescription;

/**
 * Wrap the core extractor to disable quick-create when the session flag is set
 * and the field does not explicitly opt out.
 * @param {object} staticInfo static field metadata
 * @param {object} dynamicInfo dynamic field metadata
 * @returns {object} the resulting field props
 */
const patchedExtractM2OFieldProps = function (staticInfo, dynamicInfo) {
    const result = originalExtractM2OFieldProps(staticInfo, dynamicInfo);
    if (session.disable_quick_create && staticInfo.options.no_quick_create == null) {
        result.canQuickCreate = false;
    }
    return result;
};

/**
 * Rebuild the field description so it uses the patched props extractor.
 * @param {object} component the many2one field component
 * @returns {object} the patched field description
 */
const patchedbuildM2OFieldDescription = function (component) {
    const result = originalbuildM2OFieldDescription(component);
    result.extractProps = patchedExtractM2OFieldProps;
    return result;
};

// eslint-disable-next-line no-import-assign -- patch the core field extractor in place
M2OField.extractM2OFieldProps = patchedExtractM2OFieldProps;
// eslint-disable-next-line no-import-assign -- patch the core field description in place
M2OField.buildM2OFieldDescription = patchedbuildM2OFieldDescription;

/** Disable quick-create on the registered many2one field when the session flag is set. */
patch(registry.category('fields').get('many2one'), {
    extractProps({ options }) {
        const result = super.extractProps(...arguments);
        if (session.disable_quick_create && options.no_quick_create == null) {
            result.canQuickCreate = false;
        }
        return result;
    },
});
