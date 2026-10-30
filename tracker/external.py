"""Read Scopus / Web of Science CSV exports.

Only DOIs and an "indexed in" flag are kept. If the export has an affiliation
column, rows that do not mention the institution are ignored, so the rule
"must mention UCT" holds for these sources too.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from .config import normalize_doi

log = logging.getLogger("external")


def load_external(cfg: dict) -> dict[str, dict]:
    """Return {doi: {"sources": set[str], "fhs_aff": bool}}."""
    out: dict[str, dict] = {}
    uct_re = cfg["institution"]["_re"]
    fhs_re = cfg["fhs"]["_re"]
    for src in cfg.get("external") or []:
        path = Path(cfg["_root"]) / src["path"]
        if not path.exists():
            log.info("no %s export at %s - skipping", src["name"], src["path"])
            continue
        kept = skipped = 0
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                doi = normalize_doi(row.get(src["doi_column"]))
                if not doi:
                    continue
                aff = row.get(src.get("affiliation_column", ""), "") or ""
                if aff and not uct_re.search(aff):
                    skipped += 1
                    continue
                entry = out.setdefault(doi, {"sources": set(), "fhs_aff": False})
                entry["sources"].add(src["name"])
                # Only count FHS text that sits in a UCT address.
                for chunk in aff.replace("\n", ";").split(";"):
                    if uct_re.search(chunk) and fhs_re.search(chunk):
                        entry["fhs_aff"] = True
                kept += 1
        log.info("%s: %d rows kept, %d skipped (no UCT mention)", src["name"], kept, skipped)
    return out
