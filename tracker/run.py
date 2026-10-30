"""Run the whole pipeline:  python -m tracker.run  [--mock-file FILE] [--config FILE]"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import config as config_mod
from .external import load_external
from .model import to_record
from .tag import load_overrides, tag

log = logging.getLogger("run")


def compact(rec: dict) -> dict:
    """The slim record published to the dashboard (no abstracts, no licensed metadata)."""
    return {
        "i": rec["id"], "d": rec["doi"], "t": rec["title"], "y": rec["year"],
        "ty": rec["type"], "j": rec["journal"], "c": rec["cited_by"],
        "f": None if rec["fwci"] is None else round(rec["fwci"], 2),
        "o": rec["oa"], "tp": rec["topic"], "cn": rec["countries"],
        "fa": int(rec["uct_first"]), "la": int(rec["uct_last"]),
        "h": int(rec["hpe"]), "hs": rec["hpe_status"], "th": rec["themes"],
        "fb": rec["fhs_basis"], "s": rec["sources"],
    }


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def update_history(path: Path, row: dict) -> list[dict]:
    rows: list[dict] = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh) if r["date"] != row["date"]]
    rows.append({k: str(v) for k, v in row.items()})
    rows.sort(key=lambda r: r["date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def run(cfg: dict, mock_file: str | None = None) -> dict:
    root = Path(cfg["_root"])
    out = cfg["outputs"]

    # 1. Harvest -------------------------------------------------------------
    extra_by_doi: dict[str, dict] = {}
    if mock_file:
        mock = json.loads(Path(mock_file).read_text(encoding="utf-8"))
        raw = {w["id"]: {**w, "_found_by": {"ror"}} for w in mock["works"]}
        extra_by_doi = {config_mod.normalize_doi(w["doi"]): w for w in mock.get("extra_by_doi", [])}
    else:
        from .harvest import harvest
        raw = harvest(cfg)
    log.info("harvested %d works", len(raw))

    # 2. Flatten; keep only papers that mention the institution ---------------
    records: dict[str, dict] = {}
    dropped_no_uct = 0
    for wid, w in raw.items():
        rec = to_record(w, cfg)
        if not (rec["ror_match"] or rec["raw_match"]):
            dropped_no_uct += 1
            continue
        records[rec["id"]] = rec

    # 3. Merge Scopus / WoS DOI lists ---------------------------------------
    ext = load_external(cfg)
    by_doi = {r["doi"]: r for r in records.values() if r["doi"]}
    missing = sorted(d for d in ext if d not in by_doi)
    fetched: dict[str, dict] = {}
    if missing:
        if mock_file:
            fetched = {d: extra_by_doi[d] for d in missing if d in extra_by_doi}
        else:
            from .harvest import fetch_by_dois
            fetched = fetch_by_dois(cfg, missing)
    unresolved = [d for d in missing if d not in fetched]
    for doi, w in fetched.items():
        rec = to_record(w, cfg)
        rec["doi"] = rec["doi"] or doi
        rec["external_only"] = True
        records[rec["id"]] = rec
        by_doi[rec["doi"]] = rec
    for doi, info in ext.items():
        rec = by_doi.get(doi)
        if not rec:
            continue
        for s in sorted(info["sources"]):
            if s not in rec["sources"]:
                rec["sources"].append(s)
        rec["fhs_aff"] = rec["fhs_aff"] or info["fhs_aff"]

    # 4. Tag ------------------------------------------------------------------
    overrides = load_overrides(root / out["overrides_csv"])
    for rec in records.values():
        tag(rec, cfg, overrides)

    # 5. Scope, retractions, duplicate DOIs ------------------------------------
    retracted = sum(1 for r in records.values() if r["retracted"] and r["in_scope"])
    kept: dict[str, dict] = {}
    for rec in records.values():
        if not rec["in_scope"] or rec["retracted"]:
            continue
        key = rec["doi"] or rec["id"]
        if key not in kept or rec["cited_by"] > kept[key]["cited_by"]:
            kept[key] = rec
    final = sorted(kept.values(), key=lambda r: (-(r["year"] or 0), r["title"].lower()))

    # 6. Write outputs ------------------------------------------------------------
    works_path = root / out["works_json"]
    works_path.parent.mkdir(parents=True, exist_ok=True)
    works_path.write_text(
        json.dumps([compact(r) for r in final], ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    candidates = [r for r in records.values()
                  if r["hpe_status"] == "candidate" and r["fhs"] and not r["retracted"]]
    candidates.sort(key=lambda r: -r["cited_by"])
    write_csv(root / out["review_queue_csv"],
              ["doi", "openalex_id", "year", "journal", "title", "decision(yes/no)"],
              [[r["doi"], r["id"], r["year"], r["journal"], r["title"], ""] for r in candidates])
    write_csv(root / out["unresolved_csv"], ["doi"], [[d] for d in unresolved])

    today = datetime.now(timezone.utc).date().isoformat()
    counts = {
        "date": today,
        "in_scope": len(final),
        "fhs": sum(1 for r in final if r["fhs"]),
        "hpe": sum(1 for r in final if r["hpe"]),
        "review_candidates": len(candidates),
        "scopus": sum(1 for r in final if "scopus" in r["sources"]),
        "wos": sum(1 for r in final if "wos" in r["sources"]),
    }
    history = update_history(root / out["history_csv"], counts)

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "demo_data": bool(mock_file),
        "institution": cfg["institution"]["name"],
        "short_name": cfg["institution"]["short_name"],
        "lens": cfg["lens"]["name"],
        "from_year": cfg["harvest"]["from_year"],
        "counts": {**counts, "harvested": len(raw), "dropped_no_institution_mention": dropped_no_uct,
                   "retracted_excluded": retracted, "unresolved_external_dois": len(unresolved)},
        "fhs_rule": cfg["fhs"]["rule"],
        "core_journals": cfg["lens"]["core_journals"],
        "themes": list(cfg["lens"]["themes"].keys()),
        "external_sources_present": sorted({s for r in final for s in r["sources"] if s != "openalex"}),
        "history": history,
    }
    (root / out["meta_json"]).write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("done: %s", counts)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--mock-file", help="Use a saved OpenAlex-format JSON file instead of the live API")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    run(config_mod.load(args.config), args.mock_file)


if __name__ == "__main__":
    main()
