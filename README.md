# Publication Tracker

An auto-updating dashboard of publications by an institution's staff, starting with
**University of Cape Town, Faculty of Health Sciences, with Health Professions
Education (HPE) as the first lens**. Free to run and fully hosted on GitHub.

Every Monday a GitHub Action pulls the latest records from OpenAlex, merges your
Scopus / Web of Science DOI exports, tags each paper, and republishes the dashboard.

## What counts

| Question | Rule |
|---|---|
| **Which institution?** | The paper must show UCT as an affiliation: an OpenAlex institution match, or affiliation text naming UCT. Hospital-only affiliations do not count. Scopus / WoS rows count only if their address text names UCT. |
| **Faculty of Health Sciences?** | An author's UCT address names an FHS unit (`fhs.affiliation_regex`), or OpenAlex classes the paper under Health Sciences (`fhs.rule: any`). |
| **HPE?** | Published in an HPE journal, **or** an HPE term in the title, **or** confirmed in `data/overrides.csv`. Papers with an HPE term only in the abstract go to `data/review_queue.csv` and are **not** counted until you decide. |
| **Sub-themes** | Decolonisation, community-based learning, assessment and so on, assigned only to papers already counted as HPE (so health sciences education is always central). |
| **Years** | 2006 to now (`harvest.from_year`). |
| **Excluded** | Retracted papers. Duplicate DOIs are merged. |

HPE papers by UCT authors outside the Faculty are kept. All rules live in `config.yaml`.

## Set up (about 15 minutes)

1. Create a GitHub repository and upload everything in this folder.
2. Get a free OpenAlex key at <https://openalex.org/settings/api> (create a free account first).
   In the repo: **Settings > Secrets and variables > Actions > New repository secret**,
   name `OPENALEX_API_KEY`.
3. **Settings > Pages**: source = *Deploy from a branch*, branch `main`, folder `/docs`.
4. **Actions > Update publications > Run workflow** to do the first build.
   After it finishes, your dashboard is at `https://<your-username>.github.io/<repo>/`.

From then on it refreshes itself weekly. To change the schedule, edit the `cron` line in
`.github/workflows/update.yml`.

## Adding Scopus and Web of Science

Export the UCT records as CSV with the DOI and affiliation columns, and save them as
`data/external/scopus.csv` and `data/external/wos.csv`. Re-export every few months.
Only the DOI and an "indexed in" flag are published; titles, citations and abstracts always
come from OpenAlex, so licensed metadata is not republished.

The raw exports are git-ignored because they contain licensed metadata and your repo may be
public. To let the weekly job use them, trim each file to just the `DOI` and affiliation
column (`Affiliations` for Scopus, `Addresses` for Web of Science), then add it with
`git add -f data/external/scopus.csv`. Check UCT Libraries' licence terms if unsure.

DOIs that OpenAlex cannot resolve are listed in `data/unresolved_external.csv`.

## Your weekly 5-minute job

Open `data/review_queue.csv`. For each candidate, add a line to `data/overrides.csv`:

```
doi,hpe
10.1234/abcd,yes
10.1234/efgh,no
```

A decision is remembered permanently and wins over every automatic rule.

## Files

| Path | What it is |
|---|---|
| `config.yaml` | Institution, rules, journal list, themes. The only file you normally edit. |
| `tracker/` | Python pipeline: `harvest.py` (OpenAlex), `model.py`, `tag.py`, `external.py`, `run.py` |
| `docs/index.html` | The dashboard (one static page, no build step) |
| `docs/data/` | Generated: `works.json`, `meta.json` |
| `data/history.csv` | One row per update, for the "records tracked" chart |
| `tests/` | Offline test using a mock dataset: `python -m tests.test_pipeline` |

## Reusing it for another institution or field

Change `institution` (name, ROR id, affiliation regex), the `fhs` block, and the `lens`
block (journals, terms, themes). No code changes needed.

## How the sub-themes work

Each theme in `config.yaml` has two lists of patterns:

- `terms`: specific phrases, looked for in the title **and** the abstract
  (for example "workplace-based assessment", "feedback practices").
- `title_terms`: broader words, looked for in the **title only** (for example "feedback",
  "curriculum"). A broad word in a title is usually what the paper is about; the same word
  in an abstract usually is not.

A paper gets a theme when either list matches, and can have several themes. Themes are only
given to papers already counted as HPE. To tighten a theme, make its phrases longer; to
widen it, add a phrase. To check a change, run `python -m tests.test_pipeline`.

## Known limits to keep in mind

- **OpenAlex coverage is imperfect.** Affiliations can be missing or split between a
  hospital and its university. Scopus / WoS merging and the raw-affiliation query exist to
  reduce this, but counts will differ from Scopus or Web of Science.
- **Unverified against the live API.** The pipeline was tested on mock data because the
  build environment could not reach OpenAlex. Before relying on numbers, check that the
  first run's `meta.json` counts are plausible, and confirm `harvest.raw_affiliation_filter`
  in `config.yaml` against the current OpenAlex docs (if rejected, the run logs a warning and
  continues with the institution query).
- **Keyword rules are a first pass.** Review the candidate queue for the first few weeks and
  tighten `strong_terms` / `weak_terms` where the rules over- or under-count.
- **Counts for the current year are year to date**, and recent papers pick up citations
  and affiliation fixes over time.
