"""Load config.yaml and compile the regexes once."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _join_lines(text: str) -> str:
    """Join a multi-line regex written in a YAML block scalar into one line."""
    return "".join(line.strip() for line in text.splitlines())


def _any_of(terms: list[str], word_start: bool = False) -> re.Pattern:
    """Compile a list of regexes into one. `word_start` makes every term begin at a
    word boundary, so "leader" does not match inside "misleader"."""
    body = "|".join(f"(?:{t})" for t in terms)
    return re.compile(rf"\b(?:{body})" if word_start else body, re.I)


# Titles from PubMed/Crossref often carry typographic hyphens (U+2010, U+2011,
# en and em dashes); fold them to a plain "-" so "non-practising" still matches.
_DASHES = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2212"})


class ThemeMatcher:
    """One sub-theme: phrases for title+abstract, and words for the title only.

    `search(text)` also works with a single argument (the whole text), so code
    written for the older one-regex-per-theme layout keeps working.
    """

    def __init__(self, terms: list[str] | None = None, title_terms: list[str] | None = None):
        self._any = _any_of(terms, word_start=True) if terms else None
        self._title = _any_of(title_terms, word_start=True) if title_terms else None

    def search(self, text: str, title: str | None = None) -> bool:
        text = text.translate(_DASHES)
        title = text if title is None else title.translate(_DASHES)
        return bool((self._any and self._any.search(text))
                    or (self._title and self._title.search(title)))


def _theme(spec) -> ThemeMatcher:
    if isinstance(spec, str):                    # old layout: one regex per theme
        return ThemeMatcher(terms=[spec])
    return ThemeMatcher(spec.get("terms"), spec.get("title_terms"))


def load(path: str | Path | None = None, root: str | Path | None = None) -> dict:
    """`root` is the folder that output and external paths are relative to."""
    path = Path(path) if path else ROOT / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))

    inst = cfg["institution"]
    inst["ror_id"] = normalize_ror(inst["ror"])
    inst["_re"] = re.compile(_join_lines(inst["affiliation_regex"]), re.I)

    cfg["fhs"]["_re"] = re.compile(_join_lines(cfg["fhs"]["affiliation_regex"]), re.I)

    lens = cfg["lens"]
    lens["_core"] = {normalize_journal(j) for j in lens["core_journals"]}
    lens["_strong"] = _any_of(lens["strong_terms"])
    lens["_weak"] = [re.compile(t, re.I) for t in lens["weak_terms"]]
    lens["_themes"] = {name: _theme(spec) for name, spec in lens["themes"].items()}
    cfg["_root"] = Path(root) if root else ROOT
    return cfg


def normalize_ror(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().lower().rstrip("/").split("/")[-1]


def normalize_journal(name: str | None) -> str:
    if not name:
        return ""
    name = re.sub(r"^the\s+", "", name.strip().lower())
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value
