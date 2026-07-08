# Bug Report: test_unicode_sanitizer fails on emoji sequences

**Reported by:** dev@unicode-lib  
**Date:** 2026-08-01  
**Severity:** High  
**Taskboard ticket:** BUG-421

## Summary

The unit test `test_unicode_sanitizer` located in `tests/test_sanitizer.py` is failing consistently when the input string contains emoji sequences—especially those built with Zero-Width Joiners (ZWJ) and skin-tone modifiers. The full failure output is captured in `test_failure.log`.

## Steps to Reproduce

Run the test suite with:

```bash
pytest tests/test_sanitizer.py::test_unicode_sanitizer
```

Input example that triggers the failure:

```python
"👨‍👩‍👧‍👦 ✅👍🏿"
# Family emoji (man + ZWJ + woman + ZWJ + girl + ZWJ + boy)
# White heavy check mark + Thumbs up with dark skin tone
```

## Expected Behavior

The sanitizer should preserve well-formed emoji sequences intact, keeping all necessary combining characters (ZWJ, variation selectors, skin-tone modifiers) as valid Unicode output.

## Actual Behavior

The sanitizer strips U+200D (ZWJ) and variation selectors (U+FE0F), which breaks the emoji clusters. For example, the family emoji becomes four separate characters instead of a single combined glyph. The assertion error in the log shows:

```
AssertionError: sanitized result != expected valid sequence
```

## Initial Observations

- The character whitelist used by the sanitizer may not include U+200D (Zero-Width Joiner) or U+FE0F (Variation Selector-16).
- The Unicode normalization step (NFKC/NFKD) might be remapping or removing the ZWJ before the validation stage.
- Previous debugging session (see notebook note NOTE-202) looked at this area; the failure might be related to how the library handles non-printable but contextually required joiners.

## Suggested Next Steps

1. Review the previous investigation notes in NOTE-202 for any pending clues.
2. Update the taskboard task BUG-421 with a concrete fix plan (e.g., updating the whitelist, adjusting normalization order, or adding a ZWJ-preserving pass).
3. No source file modifications should be made yet—only diagnosis and a plan update.

## Environment

- Python 3.11
- Unicode Sanitizer Lib v0.3.2
