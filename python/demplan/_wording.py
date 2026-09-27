"""Small pieces of English the package's messages are built from."""

from __future__ import annotations

_VOWEL_LETTERS = "aeiouAEIOU"


def counted(count: int, singular: str, plural: str | None = None) -> str:
    """``count`` and the noun that agrees with it: ``1 entry``, ``0 entries``, ``2 entries``.

    ``plural`` defaults to ``singular`` with an ``s`` added; pass it for any other plural.
    """
    noun = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"


def with_article(word: str) -> str:
    """``word`` behind ``a``, or behind ``an`` when it starts with a vowel letter.

    The rule goes by the letter, not the sound, which is right for the type names the messages
    put here (``an int``, ``an object``, ``a list``) and wrong for a name spoken with a vowel
    sound behind a consonant letter, such as ``ndarray``.
    """
    article = "an" if word and word[0] in _VOWEL_LETTERS else "a"
    return f"{article} {word}"


def joined(items: list[str]) -> str:
    """``items`` joined by commas, the last two by ``and``: ``a, b and c``."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"
