from typing import Optional, List
import unicodedata
import re

PRIVATE_CHAR = "\ue000"  # Private-use Unicode character
# Apostrophes  Needed for historical luxembourgish texts that use the apostrophe as a letter, see REAME.md
APOSTROPHES = "’'`"

# Quotes and general punctuation
QUOTES_PUNCT = '„•<>!"#%&'

# Basic ASCII punctuation
ASCII_PUNCT = "()*,./:;?"

# Brackets and special characters
BRACKETS_SPECIAL = "[]\\~_{}"

# Unicode punctuation (¡«·»¿)
UNICODE_PUNCT = "\xa1\xab\xb7\xbb\xbf"

# Em dash, caret
DASH_CARET = "—^"

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
            APOSTROPHES
            + QUOTES_PUNCT
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


def normalize_text(
    s: str, language: str = None, unicode_normalize: Optional[str] = "NFKC"
) -> str:
    """
    Normalize text by replacing punctuation with spaces and digits with '0'.

    >>> normalize_text("Hello, World! 123")
    'Hello  World  000'
    >>> normalize_text("Luxembourg's finest", language="lb")
    'Luxembourg s finest'
    >>> normalize_text("Price: £100")
    'Price   000'
    >>> normalize_text("ge'nt", language="lb")
    "ge'nt"
    >>> normalize_text("ge'f", language="lb")
    "ge'f"
    >>> normalize_text("kre'en", language="lb")
    "kre'en"
    >>> normalize_text("ere'scht", language="lb")
    "ere'scht"
    >>> normalize_text("ne'deg", language="lb")
    "ne'deg"
    >>> normalize_text("le'sst", language="lb")
    "le'sst"
    >>> normalize_text("go'f", language="lb")
    "go'f"
    >>> normalize_text("go'w", language="lb")
    "go'w"
    >>> normalize_text("o'ni", language="lb")
    "o'ni"
    >>> normalize_text("gro'ss", language="lb")
    "gro'ss"
    >>> normalize_text("ge'nt")
    'ge nt'
    >>> normalize_text("ge'f")
    'ge f'
    >>> normalize_text("kre'en")
    'kre en'
    >>> normalize_text("ere'scht")
    'ere scht'
    >>> normalize_text("ne'deg")
    'ne deg'
    >>> normalize_text("le'sst")
    'le sst'
    >>> normalize_text("go'f")
    'go f'
    >>> normalize_text("go'w")
    'go w'
    >>> normalize_text("o'ni")
    'o ni'
    >>> normalize_text("gro'ss")
    'gro ss'
    """
    if unicode_normalize:
        s = unicodedata.normalize(unicode_normalize, s)

    # Luxembourgish specific treatment of the word-internal apostrophe (modulo OCR
    # variants)
    # we temporarily map apostrophes to a private UNICODE character to avoid
    # conflicts with the following normalization

    if language == "lb":
        s = re.sub(rf"(?<=[oe])[{APOSTROPHES}](?=\S)", PRIVATE_CHAR, s)
    s = s.translate(NORMALIZATION_TABLE)
    if language == "lb":
        s = s.replace(PRIVATE_CHAR, "'")
    return s


def subtokens(
    w: str,
    language: str = None,
    unicode_normalize: Optional[str] = "NFKC",
    min_length: int = 1,
) -> List[str]:
    """Normalize and tokenize a word."""
    w = normalize_text(
        w, language, unicode_normalize
    )  # Apply punctuation and digit normalization
    tokens = w.split()
    if min_length <= 1:
        return tokens
    return [tok for tok in tokens if len(tok) >= min_length]
