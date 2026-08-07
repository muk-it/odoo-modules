import { describe, expect, test } from '@odoo/hoot';

import { wordDiff } from '@muk_ai_chatter/composer/word_diff';

describe.current.tags('muk_ai_chatter');

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

test('identical texts are one unchanged part', () => {
    const parts = wordDiff('the same words', 'the same words');
    expect(parts).toHaveLength(1);
    expect(parts[0].type).toBe('same');
});

test('a replaced word is marked on both sides', () => {
    const parts = wordDiff('ship it today', 'ship it tomorrow');
    expect(
        parts.some((part) => part.type === 'removed' && part.value === 'today'),
    ).toBe(true);
    expect(
        parts.some((part) => part.type === 'added' && part.value === 'tomorrow'),
    ).toBe(true);
});

test('both texts are rebuilt exactly from the diff', () => {
    const before = 'Dear customer, thanks for you order.';
    const after = 'Dear customer, thank you for your order.';
    const parts = wordDiff(before, after);
    expect(rebuild(parts, 'before')).toBe(before);
    expect(rebuild(parts, 'after')).toBe(after);
});

test('an untouched sentence around an edit stays untouched', () => {
    const parts = wordDiff('one two three', 'one TWO three');
    expect(parts[0].type).toBe('same');
    expect(parts[parts.length - 1].type).toBe('same');
});

test('writing into an empty draft is all added', () => {
    const parts = wordDiff('', 'brand new text');
    expect(parts).toHaveLength(1);
    expect(parts[0].type).toBe('added');
    expect(parts[0].value).toBe('brand new text');
});

test('clearing a draft is all removed', () => {
    const parts = wordDiff('gone now', '');
    expect(parts).toHaveLength(1);
    expect(parts[0].type).toBe('removed');
});

test('a change of spacing alone does not reword the sentence', () => {
    const parts = wordDiff('a  b', 'a b');
    expect(rebuild(parts, 'before')).toBe('a  b');
    expect(rebuild(parts, 'after')).toBe('a b');
    expect(parts.some((part) => part.type === 'same' && part.value.includes('a'))).toBe(
        true,
    );
});

test('a text past the cap falls back to a wholesale replacement', () => {
    const before = 'word '.repeat(40);
    const after = 'other '.repeat(40);
    const parts = wordDiff(before, after, 4);
    expect(parts.map((part) => part.type)).toEqual(['removed', 'added']);
});
