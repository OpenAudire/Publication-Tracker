"""Load config.yaml and compile the regexes once."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _join_lines(text: str) -> str:
    """Join a multi-line regex written in a YAML block scalar into one line."""
    return "".join(line.strip() for line in text.splitlines())


def _any_of(terms: list[str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{t})" for t in terms), re.I)


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
    lens["_themes"] = {name: re.compile(rx, re.I) for name, rx in lens["themes"].items()}
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
