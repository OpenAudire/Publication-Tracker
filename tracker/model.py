"""Turn a raw OpenAlex work into a flat record."""
from __future__ import annotations

from .config import normalize_doi, normalize_ror


def reconstruct_abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    slots: dict[int, str] = {}
    for word, positions in inverted.items():
        for p in positions:
            slots[p] = word
    return " ".join(slots[i] for i in sorted(slots))


def _raw_strings(authorship: dict) -> list[str]:
    raws = authorship.get("raw_affiliation_strings")
    if not raws:
        raws = [a.get("raw_affiliation_string") for a in authorship.get("affiliations", [])]
    return [r for r in raws if r]


def to_record(work: dict, cfg: dict) -> dict:
    inst = cfg["institution"]
    fhs_re = cfg["fhs"]["_re"]

    ror_match = raw_match = fhs_aff = False
    uct_first = uct_last = False
    countries: set[str] = set()
    authorships = work.get("authorships") or []

    for a in authorships:
        rors = {normalize_ror(i.get("ror")) for i in a.get("institutions", []) if i.get("ror")}
        raws = _raw_strings(a)
        by_ror = inst["ror_id"] in rors
        by_raw = any(inst["_re"].search(r) for r in raws)
        for c in a.get("countries") or [i.get("country_code") for i in a.get("institutions", [])]:
            if c:
                countries.add(c)
        if by_ror or by_raw:
            ror_match |= by_ror
            raw_match |= by_raw
            if any(fhs_re.search(r) for r in raws):
                fhs_aff = True
            pos = a.get("author_position")
            uct_first |= pos == "first"
            uct_last |= pos == "last"

    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    topic = work.get("primary_topic") or {}
    oa = work.get("open_access") or {}

    return {
        "id": (work.get("id") or "").rsplit("/", 1)[-1],
        "doi": normalize_doi(work.get("doi")),
        "title": (work.get("title") or "").strip(),
        "year": work.get("publication_year"),
        "type": work.get("type") or "",
        "journal": source.get("display_name") or "",
        "cited_by": work.get("cited_by_count") or 0,
        "fwci": work.get("fwci"),
        "oa": oa.get("oa_status") or "closed",
        "is_oa": bool(oa.get("is_oa")),
        "retracted": bool(work.get("is_retracted")),
        "topic": topic.get("display_name") or "",
        "field": (topic.get("field") or {}).get("display_name") or "",
        "domain": (topic.get("domain") or {}).get("display_name") or "",
        "countries": sorted(countries),
        "n_authors": len(authorships),
        "uct_first": uct_first,
        "uct_last": uct_last,
        "ror_match": ror_match,
        "raw_match": raw_match,
        "fhs_aff": fhs_aff,
        "sources": ["openalex"],
        "found_by": sorted(work.get("_found_by", [])),
        "_abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
    }
