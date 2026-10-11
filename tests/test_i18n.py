import string

import pytest
from helpers import HTML

from bookmark_organization.bookmarks import parse
from bookmark_organization.i18n import CATALOGS, locale, translate


@pytest.mark.parametrize(
    "preference,header,expected",
    [
        (None, "ja-JP, en;q=0.8", "ja"),
        (None, "en-US,ja;q=.5", "en"),
        (None, "fr-FR,ja;q=.8", "en"),
        (None, None, "ja"),
        (None, "garbage!", "ja"),
        (None, "en;q=.1,ja;q=.9", "ja"),
        (None, "ja;q=0,en;q=.8", "en"),
        ("ja", "en-US", "ja"),
        ("en", "ja-JP", "en"),
        ("bad", "en-US", "en"),
        (None, "*", "ja"),
        (None, "ja;q=bad,en;q=.9", "en"),
    ],
)
def test_language(preference, header, expected):
    assert locale(preference, header) == expected


def test_catalog_parity_and_bookmark_data_invariance():
    assert CATALOGS["en"].keys() == CATALOGS["ja"].keys()
    parser = string.Formatter()

    def fields(text):
        return {field for _, field, _, _ in parser.parse(text) if field}

    for key in CATALOGS["en"]:
        assert fields(CATALOGS["en"][key]) == fields(CATALOGS["ja"][key])
    tree = parse(HTML)
    before = repr(tree)
    translate("en", "selected", count=6)
    translate("ja", "selected", count=6)
    assert repr(tree) == before
