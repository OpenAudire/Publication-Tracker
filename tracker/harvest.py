"""Harvest works from OpenAlex.

Needs a free API key in the OPENALEX_API_KEY environment variable
(OpenAlex requires one for all real use since February 2026).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Iterator

import requests

from .config import normalize_doi

log = logging.getLogger("harvest")

API = "https://api.openalex.org/works"
SELECT = ",".join([
    "id", "doi", "title", "publication_year", "type", "cited_by_count", "fwci",
    "is_retracted", "open_access", "primary_location", "authorships",
    "primary_topic", "abstract_inverted_index",
])


class OpenAlexError(RuntimeError):
    pass


class FilterRejected(OpenAlexError):
    """The API answered 400 - usually an unknown filter name."""


def _get(session: requests.Session, params: dict, retries: int = 6) -> dict:
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        params = {**params, "api_key": key}
    for attempt in range(retries):
        resp = session.get(API, params=params, timeout=90)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = min(2 ** attempt, 60)
            log.warning("OpenAlex %s, retrying in %ss", resp.status_code, wait)
            time.sleep(wait)
            continue
        if resp.status_code in (401, 403, 409):
            raise OpenAlexError(
                f"OpenAlex refused the request ({resp.status_code}). "
                "Check that OPENALEX_API_KEY is set and has budget left: "
                + resp.text[:200]
            )
        if resp.status_code == 400:
            raise FilterRejected(resp.text[:300])
        raise OpenAlexError(f"OpenAlex error {resp.status_code}: {resp.text[:300]}")
    raise OpenAlexError("OpenAlex still failing after retries")


def iter_works(session: requests.Session, filt: str, per_page: int = 100) -> Iterator[dict]:
    cursor = "*"
    while cursor:
        data = _get(session, {"filter": filt, "select": SELECT,
                              "per_page": per_page, "cursor": cursor})
        yield from data["results"]
        cursor = data["meta"].get("next_cursor")


def harvest(cfg: dict, session: requests.Session | None = None) -> dict[str, dict]:
    """Return {openalex_id: raw_work}, each tagged with `_found_by`."""
    session = session or requests.Session()
    h = cfg["harvest"]
    base = [f"from_publication_date:{h['from_year']}-01-01"]
    if h.get("include_types"):
        base.append("type:" + "|".join(h["include_types"]))

    queries = {"ror": base + [f"authorships.institutions.ror:{cfg['institution']['ror']}"]}
    for i, phrase in enumerate(h.get("raw_affiliation_phrases", [])):
        queries[f"raw{i}"] = base + [f'{h["raw_affiliation_filter"]}:"{phrase}"']

    works: dict[str, dict] = {}
    for name, parts in queries.items():
        try:
            n = 0
            for w in iter_works(session, ",".join(parts), h.get("per_page", 100)):
                entry = works.setdefault(w["id"], {**w, "_found_by": set()})
                entry["_found_by"].add(name[:3])
                n += 1
            log.info("query %s returned %d works", name, n)
        except FilterRejected as exc:
            if name == "ror":
                raise
            log.warning("query %s was rejected and is skipped: %s", name, exc)
    return works


def fetch_by_dois(cfg: dict, dois: list[str], session: requests.Session | None = None) -> dict[str, dict]:
    """Look up specific DOIs (from Scopus/WoS exports) in OpenAlex."""
    session = session or requests.Session()
    out: dict[str, dict] = {}
    for i in range(0, len(dois), 50):
        chunk = dois[i:i + 50]
        filt = "doi:" + "|".join(f"https://doi.org/{d}" for d in chunk)
        for w in iter_works(session, filt, 50):
            out[normalize_doi(w.get("doi"))] = w
    return out
