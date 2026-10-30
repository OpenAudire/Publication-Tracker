"""Generate a fake OpenAlex-format dataset (seeded) for testing the pipeline offline.

The mock includes hand-built edge cases whose expected outcome is asserted in
test_pipeline.py, plus ~600 random works so the dashboard has something to show.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

UCT_ROR = "https://ror.org/03p74gp79"
UCT_INST = {"id": "https://openalex.org/I1", "ror": UCT_ROR, "country_code": "ZA",
            "display_name": "University of Cape Town"}
OTHER_INST = {"id": "https://openalex.org/I2", "ror": "https://ror.org/00cvxb145",
              "country_code": "US", "display_name": "University of Washington"}
HOSPITAL_INST = {"id": "https://openalex.org/I3", "ror": "https://ror.org/01abc2d3e",
                 "country_code": "ZA", "display_name": "Groote Schuur Hospital"}

CORE_JOURNALS = ["Medical Education", "BMC Medical Education", "Medical Teacher",
                 "African Journal of Health Professions Education", "Academic Medicine"]
GENERAL_JOURNALS = ["The Lancet", "PLoS ONE", "South African Medical Journal", "BMJ Global Health",
                    "Nature Communications", "Journal of the International AIDS Society",
                    "International Journal of Tuberculosis and Lung Disease", "Scientific Reports"]
COUNTRIES = ["US", "GB", "ZA", "ZA", "ZA", "UG", "KE", "NL", "AU", "CA", "ZW", "NG", "BR", "DE"]
FHS_AFF = ["Department of Medicine, Groote Schuur Hospital, University of Cape Town, South Africa",
           "Faculty of Health Sciences, University of Cape Town, Cape Town, South Africa",
           "School of Public Health and Family Medicine, University of Cape Town",
           "Division of Neurology, Department of Medicine, UCT, Cape Town"]
NON_FHS_AFF = ["Department of Chemistry, University of Cape Town, Rondebosch",
               "Department of Economics, University of Cape Town"]
HPE_TITLES = ["Decolonising the medical curriculum: a student perspective",
              "Assessment of clinical competence in undergraduate medical students",
              "Interprofessional education in a South African health sciences faculty",
              "Simulation-based education for rural nursing students",
              "Medical student wellbeing during emergency remote teaching",
              "Community-based education and social accountability in health professions training"]
CLIN_TITLES = ["Outcomes of drug-resistant tuberculosis treatment in Cape Town",
               "HIV viral suppression among adolescents on dolutegravir",
               "Neonatal sepsis incidence at a tertiary referral hospital",
               "Genomic surveillance of SARS-CoV-2 variants",
               "Stroke rehabilitation outcomes in a low-resource setting"]
ABSTRACTS_NEUTRAL = "We conducted a cohort study of patients treated at a tertiary hospital and measured mortality."
ABSTRACT_CANDIDATE = ("This study explored how students experience teaching and learning, and how "
                      "assessment of competence shapes curriculum choices among medical students in a clinical rotation.")


def inverted(text: str) -> dict:
    inv: dict[str, list[int]] = {}
    for i, w in enumerate(text.split()):
        inv.setdefault(w, []).append(i)
    return inv


def authorship(position: str, inst: dict, raw: str, country: str | None = None) -> dict:
    inst = dict(inst)
    if country:
        inst["country_code"] = country
    return {"author_position": position, "institutions": [inst] if inst else [],
            "countries": [inst["country_code"]], "raw_affiliation_strings": [raw]}


def work(wid: int, title: str, year: int, journal: str, authors: list[dict], *, doi: str | None = None,
         abstract: str = ABSTRACTS_NEUTRAL, cited: int = 0, domain: str = "Health Sciences",
         oa: str = "closed", wtype: str = "article", retracted: bool = False) -> dict:
    return {
        "id": f"https://openalex.org/W{wid}",
        "doi": f"https://doi.org/{doi}" if doi else None,
        "title": title, "publication_year": year, "type": wtype,
        "cited_by_count": cited, "fwci": round(cited / 8, 2), "is_retracted": retracted,
        "open_access": {"oa_status": oa, "is_oa": oa != "closed"},
        "primary_location": {"source": {"display_name": journal}},
        "primary_topic": {"display_name": "Medical Education and Admissions" if "ducation" in journal else "Infectious disease",
                          "field": {"display_name": "Medicine"}, "domain": {"display_name": domain}},
        "authorships": authors,
        "abstract_inverted_index": inverted(abstract),
    }


def edge_cases() -> list[dict]:
    uct_fhs = FHS_AFF[0]
    return [
        # W1: HPE by core journal, FHS by affiliation
        work(1, "Reflections on feedback practices", 2021, "Medical Education",
             [authorship("first", UCT_INST, uct_fhs), authorship("last", OTHER_INST, "University of Washington")],
             doi="10.1/w1", cited=12, oa="gold"),
        # W2: HPE by title keyword in a general journal
        work(2, "Interprofessional education in a South African health sciences faculty", 2019, "PLoS ONE",
             [authorship("first", UCT_INST, FHS_AFF[1])], doi="10.1/w2", cited=3, oa="green"),
        # W3: clinical paper, FHS, not HPE
        work(3, "Outcomes of drug-resistant tuberculosis treatment", 2020, "The Lancet",
             [authorship("first", UCT_INST, FHS_AFF[2])], doi="10.1/w3", cited=40),
        # W4: only a hospital affiliation, NO mention of UCT -> must be dropped
        work(4, "Neonatal outcomes at Groote Schuur", 2022, "South African Medical Journal",
             [authorship("first", HOSPITAL_INST, "Groote Schuur Hospital, Cape Town")], doi="10.1/w4"),
        # W5: UCT mentioned only in raw string, ROR missing
        work(5, "Medical student selection and throughput", 2018, "BMJ Global Health",
             [{"author_position": "first", "institutions": [], "countries": [],
               "raw_affiliation_strings": ["Faculty of Health Sciences, University of Cape Town"]}],
             doi="10.1/w5", cited=1),
        # W6: UCT chemistry, non-health topic -> out of scope
        work(6, "Catalytic hydrogenation on nickel surfaces", 2020, "Nature Communications",
             [authorship("first", UCT_INST, NON_FHS_AFF[0])], doi="10.1/w6", domain="Physical Sciences"),
        # W7: candidate (abstract only)
        work(7, "Experiences of the final-year rotation", 2023, "South African Medical Journal",
             [authorship("first", UCT_INST, FHS_AFF[0])], doi="10.1/w7", abstract=ABSTRACT_CANDIDATE),
        # W8: retracted -> excluded
        work(8, "A retracted study", 2017, "PLoS ONE",
             [authorship("first", UCT_INST, FHS_AFF[0])], doi="10.1/w8", retracted=True),
        # W9: duplicate DOI of W3 with fewer citations -> deduped
        work(9, "Outcomes of drug-resistant tuberculosis treatment (preprint)", 2019, "medRxiv",
             [authorship("first", UCT_INST, FHS_AFF[2])], doi="10.1/w3", cited=2, wtype="preprint"),
        # W10: HPE in a core journal, UCT author outside FHS (still in scope as HPE)
        work(10, "Writing across the curriculum", 2022, "Medical Teacher",
             [authorship("first", UCT_INST, "Centre for Higher Education Development, University of Cape Town")],
             doi="10.1/w10", domain="Social Sciences", cited=5),
        # W11: found only via a Scopus export (not in OpenAlex harvest)
        # lives in extra_by_doi, see below
    ]


def extra_by_doi() -> list[dict]:
    return [work(11, "Curriculum transformation and decolonisation in medical schools", 2024,
                 "Advances in Health Sciences Education",
                 [authorship("first", UCT_INST, FHS_AFF[1])], doi="10.1/w11", cited=7, oa="hybrid")]


def random_works(n: int, seed: int = 7, start_id: int = 1000) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        year = rng.choices(range(2006, 2027), weights=[1 + (y - 2006) * 0.3 for y in range(2006, 2027)])[0]
        is_hpe = rng.random() < 0.09
        if is_hpe:
            title = rng.choice(HPE_TITLES)
            journal = rng.choice(CORE_JOURNALS) if rng.random() < 0.6 else rng.choice(GENERAL_JOURNALS)
        else:
            title = rng.choice(CLIN_TITLES) + f" ({i})"
            journal = rng.choice(GENERAL_JOURNALS)
        fhs = rng.random() < 0.85
        aff = rng.choice(FHS_AFF if fhs else NON_FHS_AFF)
        authors = [authorship("first" if rng.random() < .6 else "middle", UCT_INST, aff)]
        for j in range(rng.randint(0, 4)):
            c = rng.choice(COUNTRIES)
            inst = dict(OTHER_INST, country_code=c)
            authors.append(authorship("last" if j == 0 and rng.random() < .5 else "middle", inst, f"Univ {c}", c))
        cited = int(rng.expovariate(1 / 12) * (2027 - year) / 6)
        out.append(work(start_id + i, title, year, journal, authors, doi=f"10.9/{start_id + i}", cited=cited,
                        oa=rng.choices(["closed", "gold", "green", "hybrid", "bronze"], [4, 3, 3, 1, 1])[0],
                        domain="Health Sciences" if fhs else "Physical Sciences",
                        abstract=ABSTRACT_CANDIDATE if rng.random() < 0.02 else ABSTRACTS_NEUTRAL))
    return out


def build(n_random: int = 600) -> dict:
    return {"works": edge_cases() + random_works(n_random), "extra_by_doi": extra_by_doi()}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("mock_openalex.json")
    target.write_text(json.dumps(build()), encoding="utf-8")
    print(f"wrote {target}")
