"""Decide whether a record is FHS and/or HPE, and which themes it carries."""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .config import normalize_doi, normalize_journal

# A title match on an HPE term (e.g. "decolonis*", "curriculum development",
# "student selection") only counts as HPE if the paper also has a health
# context: an FHS affiliation or health topic, or a health word in the title.
# Without this, "Decolonising management education" would be counted.
HEALTH_WORDS = re.compile(
    r"\b(medic\w*|health\w*|clinic\w*|nurs\w*|patient\w*|dental|dentist\w*|pharmac\w*|"
    r"physiotherap\w*|occupational therap\w*|surg\w*|doctor\w*|hospital\w*|midwi\w*|"
    r"radiograph\w*|audiolog\w*|paediatric\w*|pediatric\w*|psychiatr\w*|registrars?|"
    r"general practice|HIV)\b", re.I)

# "Additional file 1 of <paper title>" records (supplementary files deposited
# on Figshare) are not publications in their own right.
SUPPLEMENT_TITLE = re.compile(
    r"^\s*(additional|supplementary|supporting)\s+(file|data|material|information)s?"
    r"\s*\d*\s+(of|for|to)\b", re.I)


def load_overrides(path: Path) -> dict[str, bool]:
    """data/overrides.csv: doi,openalex_id,hpe  with hpe = yes|no.

    Manual decisions win over every automatic rule. A paper is matched by its
    DOI, or by its OpenAlex id (W123...) when it has no DOI. Either column may
    be left empty, and an old two-column file (doi,hpe) still works.
    """
    out: dict[str, bool] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            val = (row.get("hpe") or "").strip().lower()
            if val not in ("yes", "no"):
                continue
            doi = normalize_doi(row.get("doi"))
            oid = (row.get("openalex_id") or "").strip().lower()
            for key in (doi, oid):
                if key:
                    out[key] = val == "yes"
    return out


def tag_fhs(rec: dict, cfg: dict) -> None:
    topic_hit = rec["domain"] in cfg["fhs"]["health_topic_domains"]
    use_topic = cfg["fhs"]["rule"] == "any"
    rec["fhs"] = bool(rec["fhs_aff"] or (use_topic and topic_hit))
    if rec["fhs_aff"]:
        rec["fhs_basis"] = "affiliation"
    elif rec["fhs"]:
        rec["fhs_basis"] = "topic"
    else:
        rec["fhs_basis"] = ""


def tag_hpe(rec: dict, cfg: dict, overrides: dict[str, bool]) -> None:
    lens = cfg["lens"]
    title = rec["title"]
    text = f"{title} {rec.get('_abstract', '')}"

    key = next((k for k in (rec["doi"], rec["id"].lower()) if k and k in overrides), None)
    if key:
        status = "manual_yes" if overrides[key] else "manual_no"
    elif normalize_journal(rec["journal"]) in lens["_core"]:
        status = "core_journal"
    elif lens["_strong"].search(title):
        has_health_context = rec["fhs"] or bool(HEALTH_WORDS.search(title))
        status = "title_keyword" if has_health_context else "candidate"
    elif lens["_strong"].search(rec.get("_abstract", "")) or \
            sum(1 for rx in lens["_weak"] if rx.search(text)) >= 3:
        status = "candidate"
    else:
        status = "none"

    rec["hpe_status"] = status
    rec["hpe"] = status in ("core_journal", "title_keyword", "manual_yes")
    rec["themes"] = (
        [name for name, rx in lens["_themes"].items() if rx.search(text)]
        if rec["hpe"] else []
    )


def tag(rec: dict, cfg: dict, overrides: dict[str, bool]) -> dict:
    tag_fhs(rec, cfg)
    tag_hpe(rec, cfg, overrides)
    rec["in_scope"] = bool(rec["fhs"] or rec["hpe"]) and not SUPPLEMENT_TITLE.match(rec["title"])
    return rec
