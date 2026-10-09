/** @odoo-module */

import { wordDiff } from '@muk_ai_chatter/composer/word_diff/word_diff';

QUnit.module('word_diff');

/**
 * Rebuild each side of a diff, to prove nothing was invented or lost.
 * @param {{type: string, value: string}[]} parts the diff
 * @param {'before'|'after'} side which text to rebuild
 * @returns {string} the rebuilt text
 */
function rebuild(parts, side) {
    const skip = side === 'before' ? 'added' : 'removed';
    return parts
        .filter((part) => part.type !== skip)
        .map((part) => part.value)
        .join('');
}

QUnit.test('identical texts are one unchanged part', (assert) => {
    assert.deepEqual(wordDiff('the same words', 'the same words'), [
        { type: 'same', value: 'the same words' },
    ]);
});

QUnit.test('a replaced word is marked on both sides', (assert) => {
    const parts = wordDiff('ship it today', 'ship it tomorrow');
    assert.ok(parts.some((part) => part.type === 'removed' && part.value === 'today'));
    assert.ok(parts.some((part) => part.type === 'added' && part.value === 'tomorrow'));
});

QUnit.test('both texts are rebuilt exactly from the diff', (assert) => {
    for (const [before, after] of [
        [
            'Dear customer, thanks for you order.',
            'Dear customer, thank you for your order.',
        ],
        ['a  b', 'a b'],
    ]) {
        const parts = wordDiff(before, after);
        assert.strictEqual(rebuild(parts, 'before'), before);
        assert.strictEqual(rebuild(parts, 'after'), after);
    }
    assert.strictEqual(wordDiff('a  b', 'a b')[0].value, 'a');
});

QUnit.test('an untouched sentence around an edit stays untouched', (assert) => {
    const parts = wordDiff('one two three', 'one TWO three');
    assert.strictEqual(parts[0].type, 'same');
    assert.strictEqual(parts[parts.length - 1].type, 'same');
});

QUnit.test('an empty side is one part, and a long text one replacement', (assert) => {
    assert.deepEqual(wordDiff('', 'brand new text'), [
        { type: 'added', value: 'brand new text' },
    ]);
    assert.deepEqual(wordDiff('gone now', ''), [
        { type: 'removed', value: 'gone now' },
    ]);
    const parts = wordDiff('word '.repeat(40), 'other '.repeat(40), 4);
    assert.deepEqual(
        parts.map((part) => part.type),
        ['removed', 'added'],
    );
});
