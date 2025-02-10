from typing import Optional, List
import unicodedata

# Quotes and general punctuation
QUOTES_PUNCT = "„•<>!\"#%&'"

# Basic ASCII punctuation
ASCII_PUNCT = "()*,./:;?"

# Brackets and special characters
BRACKETS_SPECIAL = "[]\\~_{}"

# Unicode punctuation (¡«·»¿)
UNICODE_PUNCT = "\xa1\xab\xb7\xbb\xbf"

# Em dash, caret, apostrophe
DASH_CARET = "—^`"

# Special symbols (broken bar, section, pound, equals)
SPECIAL_SYMBOLS = "¦§£="

# Hyphen (kept for clarity)
HYPHEN = "-"

# Digits (normalized to "0")
DIGITS = "0123456789"

# Combine all groups into a single mapping for translation
NORMALIZATION_TABLE = str.maketrans(
    {
        char: " "
        for char in (
            QUOTES_PUNCT
            + ASCII_PUNCT
            + BRACKETS_SPECIAL
            + UNICODE_PUNCT
            + DASH_CARET
            + SPECIAL_SYMBOLS
            + HYPHEN
        )
    }  # Normalize punctuation
    | {char: "0" for char in DIGITS}  # Normalize digits
)


def normalize_text(s: str, unicode_normalize: Optional[str] = "NFKC") -> str:
    """Normalize text by replacing punctuation with spaces and digits with '0'."""
    if unicode_normalize:
        s = unicodedata.normalize(unicode_normalize, s)
    return s.translate(NORMALIZATION_TABLE)


def subtokens(w: str, unicode_normalize: Optional[str] = "NFKC") -> List[str]:
    """Normalize and tokenize a word."""
    w = normalize_text(
        w, unicode_normalize
    )  # Apply punctuation and digit normalization
    return w.split()  # Tokenize by whitespace
