/**
 * Tell whether what the user has open satisfies a skill's scope.
 *
 * Mirrors `muk_ai.skill._scope_satisfied_by`. A list, pivot or graph names a
 * model but no record, so only `kind === 'record'` counts as one; whether the
 * model carries a chatter is decided server-side and travels on the view
 * context, because the client cannot inspect the registry; a context pinned
 * before that flag existed carries none, and stays available so the server
 * gets to answer rather than the panel guessing.
 * @param {object} skill the skill descriptor from available_skill_names
 * @param {object|null} viewContext the session's pinned view context
 * @returns {boolean} true when the skill can run right now
 */
export function skillScopeSatisfied(skill, viewContext) {
    const context = viewContext || {};
    const model = context.model || '';
    const scope = skill.scope || 'any';
    if (scope !== 'any') {
        if (!model) {
            return false;
        }
        if (scope !== 'context' && context.kind !== 'record') {
            return false;
        }
        if (scope === 'chatter' && context.has_chatter === false) {
            return false;
        }
    }
    const models = skill.models || [];
    return !models.length || models.includes(model);
}
