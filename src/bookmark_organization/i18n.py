import json
from pathlib import Path

CATALOGS = {
    code: json.loads((Path(__file__).parent / "locales" / f"{code}.json").read_text())
    for code in ("en", "ja")
}


def locale(preference: str | None, header: str | None) -> str:
    if preference in CATALOGS:
        return preference
    choices = []
    for index, part in enumerate((header or "").split(",")):
        bits = part.strip().split(";")
        language = bits[0].strip().lower()
        if (
            not language
            or language == "*"
            or not all(
                chunk.isalpha() or chunk.isdigit() for chunk in language.split("-")
            )
        ):
            continue
        quality = 1.0
        try:
            for option in bits[1:]:
                name, value = option.strip().split("=", 1)
                if name == "q":
                    quality = float(value)
            if not 0 < quality <= 1:
                continue
        except ValueError:
            continue
        choices.append((-quality, index, language))
    if not choices:
        return "ja"
    return "ja" if sorted(choices)[0][2].split("-")[0] == "ja" else "en"


def translate(code: str, key: str, **values) -> str:
    return (
        CATALOGS.get(code, CATALOGS["en"])
        .get(key, CATALOGS["en"].get(key, key))
        .format(**values)
    )
