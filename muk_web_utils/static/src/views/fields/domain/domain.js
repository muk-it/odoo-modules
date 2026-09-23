import { patch } from '@web/core/utils/patch';

import { DomainField } from '@web/views/fields/domain/domain_field';

/**
 * Warn about non-literal domains only when evaluating one actually fails.
 *
 * The core field warns as soon as a domain mentions anything that is not a
 * literal (`uid` in a system filter, say), and it does so before trying to
 * evaluate it. A domain whose expressions all resolve from the field context
 * therefore renders its record count correctly and still raises "evaluation
 * might fail", which is a warning about something that demonstrably did not
 * happen. Hold the notice until the result says the domain really is invalid.
 */
patch(DomainField.prototype, {
    getEvaluatedDomain(props = this.props) {
        const notification = this.notification;
        let held = null;
        this.notification = { add: (...args) => (held = args) };
        let evaluated;
        try {
            evaluated = super.getEvaluatedDomain(props);
        } finally {
            this.notification = notification;
        }
        if (held && evaluated?.isInvalid) {
            this.notification.add(...held);
        }
        return evaluated;
    },
});
