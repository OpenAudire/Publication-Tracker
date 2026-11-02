"""Offline end-to-end test: mock OpenAlex data -> pipeline -> outputs.

Run:  python -m tests.test_pipeline     (or: pytest)
"""
from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from tests import make_mock
from tracker import config as config_mod
from tracker.run import run


def _setup(tmp: Path) -> tuple[dict, Path]:
    ext = tmp / "data" / "external"
    ext.mkdir(parents=True)
    # Scopus export: W1 (already in OpenAlex), W11 (only here), an unresolvable DOI,
    # and a row that does not mention UCT (must be ignored).
    with (ext / "scopus.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["DOI", "Affiliations", "Title"])
        w.writerow(["10.1/w1", "Department of Medicine, University of Cape Town", "x"])
        w.writerow(["https://doi.org/10.1/w11", "Faculty of Health Sciences, University of Cape Town", "x"])
        w.writerow(["10.1/zzz", "Faculty of Health Sciences, University of Cape Town", "x"])
        w.writerow(["10.1/other", "Department of Medicine, University of Oslo", "x"])
    with (ext / "wos.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["DOI", "Addresses"])
        w.writerow(["10.1/w1", "Univ Cape Town, Dept Med, Cape Town, South Africa"])
    # Manual decision: reject W2 as HPE, accept the candidate W7.
    with (tmp / "data" / "overrides.csv").open("w", encoding="utf-8", newline="") as fh:
        fh.write("doi,openalex_id,hpe\n10.1/w2,,no\n10.1/w7,,yes\n,W15,yes\n")
    mock = tmp / "mock.json"
    mock.write_text(json.dumps(make_mock.build(600)), encoding="utf-8")
    return config_mod.load(root=tmp), mock


def test_pipeline() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        cfg, mock = _setup(tmp)
        meta = run(cfg, str(mock))
        works = {w["i"]: w for w in json.loads((tmp / cfg["outputs"]["works_json"]).read_text())}
        by_doi = {w["d"]: w for w in works.values()}

        # W1: core journal => HPE; FHS by affiliation; indexed in OpenAlex, Scopus, WoS
        w1 = by_doi["10.1/w1"]
        assert w1["h"] == 1 and w1["hs"] == "core_journal" and w1["fb"] == "affiliation"
        assert sorted(w1["s"]) == ["openalex", "scopus", "wos"], w1["s"]
        assert w1["fa"] == 1 and w1["la"] == 0
        assert "Assessment and feedback" in w1["th"]

        # W2: title keyword would make it HPE, but the manual override says no
        assert by_doi["10.1/w2"]["h"] == 0 and by_doi["10.1/w2"]["hs"] == "manual_no"

        # W3/W9: duplicate DOI, the more-cited record is kept, only once
        assert sum(1 for w in works.values() if w["d"] == "10.1/w3") == 1
        assert by_doi["10.1/w3"]["c"] == 40 and by_doi["10.1/w3"]["h"] == 0

        # W4: hospital only, no UCT mention => dropped
        assert "10.1/w4" not in by_doi
        assert meta["counts"]["dropped_no_institution_mention"] >= 1

        # W5: UCT only in the raw affiliation string => kept, HPE by title keyword
        assert by_doi["10.1/w5"]["h"] == 1 and by_doi["10.1/w5"]["hs"] == "title_keyword"

        # W6: UCT chemistry, non-health => out of scope
        assert "10.1/w6" not in by_doi

        # W7: abstract-only candidate, accepted via override => HPE
        assert by_doi["10.1/w7"]["hs"] == "manual_yes" and by_doi["10.1/w7"]["h"] == 1

        # W8: retracted => excluded
        assert "10.1/w8" not in by_doi and meta["counts"]["retracted_excluded"] == 1

        # W10: HPE core journal, author outside FHS => still in scope
        assert by_doi["10.1/w10"]["h"] == 1 and by_doi["10.1/w10"]["fb"] == ""

        # W11: found only through the Scopus export, resolved via OpenAlex by DOI
        w11 = by_doi["10.1/w11"]
        assert w11["h"] == 1 and "scopus" in w11["s"] and "openalex" in w11["s"]

        # W12: HPE-sounding title with no health context => not counted at all
        assert "10.1/w12" not in by_doi
        # W13: supplementary-file record => excluded
        assert "10.1/w13" not in by_doi
        # W14: no FHS affiliation but "occupational therapy" in the title => HPE
        assert by_doi["10.1/w14"]["h"] == 1 and by_doi["10.1/w14"]["hs"] == "title_keyword"

        # W15: no DOI, accepted by OpenAlex id in overrides.csv => HPE
        assert works["W15"]["h"] == 1 and works["W15"]["hs"] == "manual_yes"

        # Unresolvable external DOI is reported, and the non-UCT row never appears
        unresolved = (tmp / cfg["outputs"]["unresolved_csv"]).read_text()
        assert "10.1/zzz" in unresolved and "10.1/other" not in unresolved

        # Review queue: W7 was overridden, so it is still listed as a candidate
        # only if its status is "candidate" - it is not, so the queue must not list it.
        queue = (tmp / cfg["outputs"]["review_queue_csv"]).read_text()
        assert "10.1/w7" not in queue

        # Outputs exist and are consistent
        assert meta["counts"]["in_scope"] == len(works)
        assert meta["counts"]["hpe"] == sum(w["h"] for w in works.values())
        assert (tmp / cfg["outputs"]["history_csv"]).exists()

        # Re-running the same day replaces the history row instead of duplicating it
        run(cfg, str(mock))
        rows = list(csv.DictReader((tmp / cfg["outputs"]["history_csv"]).open()))
        assert len(rows) == 1, rows

        print("pipeline test OK:", meta["counts"])


def test_config_regexes() -> None:
    cfg = config_mod.load()
    assert cfg["institution"]["_re"].search("Univ. of Cape Town, Rondebosch")
    assert cfg["institution"]["_re"].search("Dept of Surgery, UCT, Cape Town, South Africa")
    assert not cfg["institution"]["_re"].search("Facultad de Medicina, UCT, Temuco, Chile")
    assert not cfg["institution"]["_re"].search("Groote Schuur Hospital, Cape Town")
    assert cfg["fhs"]["_re"].search("Division of Neurology, University of Cape Town")
    assert not cfg["fhs"]["_re"].search("Department of Economics, University of Cape Town")
    assert cfg["institution"]["_re"].search("Univ Cape Town, Dept Med")          # WoS style
    assert cfg["fhs"]["_re"].search("Univ Cape Town, Dept Med, Cape Town")        # WoS style
    assert cfg["lens"]["_strong"].search("Decolonising the medical curriculum")
    assert not cfg["lens"]["_strong"].search("Outcomes of drug-resistant tuberculosis treatment")
    print("config regex test OK")


def test_themes() -> None:
    """Sub-themes: phrase-based, with broad words allowed only in the title."""
    T = config_mod.load()["lens"]["_themes"]

    def hit(theme: str, title: str, abstract: str = "") -> bool:
        return T[theme].search(f"{title} {abstract}", title)

    assert hit("Assessment and feedback", "Reflections on feedback practices")
    assert hit("Examinations and psychometrics", "An OSCE standard-setting study")
    assert hit("Workplace-based and competency-based assessment", "Entrustable professional activities for registrars")
    # a passing word in an abstract must not tag a paper...
    assert not hit("Assessment and feedback", "Cohort study",
                   "We made an assessment of patients and gave feedback to the team.")
    # ...and neither must look-alike words
    assert not hit("Postgraduate training and CPD", "An international, multicentre study")   # "intern" in "international"
    assert not hit("Examinations and psychometrics", "Examples of good practice")            # "exam" in "examples"
    assert not hit("Teaching and learning methods", "Outcomes at Tamale Teaching Hospital")
    # typographic hyphens are folded
    assert hit("Social accountability and workforce", "Experiences of non\u2010practising health professionals")
    # a theme can be matched by an abstract phrase even if the title has none
    assert hit("Artificial intelligence in education", "A pilot study", "We used large language models to draft cases.")
    print("theme test OK")


if __name__ == "__main__":
    test_pipeline()
    test_config_regexes()
    test_themes()
