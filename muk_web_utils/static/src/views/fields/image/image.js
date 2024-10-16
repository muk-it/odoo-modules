import { registry } from "@web/core/registry";

import { imageField } from '@web/views/fields/image/image_field';

export const listImageField = {
    ...imageField,
    listViewWidth: ({ hasLabel }) => (!hasLabel ? 30 : false),
};

registry.category('fields').add('list.image', listImageField);
