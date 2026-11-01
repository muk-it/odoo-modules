import { _t } from '@web/core/l10n/translation';

import { describeToolBlock, toolBlockDecorators } from '@muk_ai/chat/session/turns';

toolBlockDecorators.add('muk_ai_product.tool_labels', (block) => {
    if (block.name === 'product_context') {
        describeToolBlock(block, {
            icon: () => 'fa-cube',
            label: () => _t('Read the product'),
        });
    }
});
