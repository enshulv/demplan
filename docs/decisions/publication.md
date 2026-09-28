# Publication

## 2026-09-29

### The README keeps what the library is, its findings and the entry points; details move to the wiki, and wiki pages put conclusions before evidence

**Decision**:

- The README runs in this order: a one-sentence description → Why → what reproducing the published experiments found → install → one example → a documentation table by kind of reader → status → contributing → how to cite → references → licence
- The reproduction section states four findings: the round counts come back; they come back only with the program's price rule; four printed cells differ from the program's output; the order of magnitude of a round's time. Each links to its wiki entry. The full 40-experiment table and the timing setup sit in `<details>` sections
- Moved out of the README: the `Economy` and `Plan` field tables, the difference reports, WIOD, writing your own coordination method, the run configuration document, the first comparison of two mechanisms (the 1.80 ratio), what the library is answerable for, the wiki's full contents and the list of limitations. Each is on its wiki page; the full list of limitations is the Status section of the wiki's home page. The references sit in a `<details>` section
- Wiki pages: a long page opens with an index table; each section starts with one sentence of conclusion, then why it matters, keeping only the number the conclusion rests on; quotations, line numbers, commits, full script output and derivations go into `<details>` sections, followed by one line linking to the check or the next step. The steps a tutorial reader must run and their expected output, the signatures and parameter tables of a reference page, and the qualifications a conclusion depends on are not collapsed
- Mathematics is rendered with LaTeX, never pasted in code format
- A rewrite moves content between layers and removes no fact: the numbers, commit hashes, quotations, code blocks, headings and links of the old and new versions are compared by script and must be the same sets
- Sentences that answer a view nobody raised, and run-ups with no content, are removed, such as the "Why these gaps exist" paragraph of the limitations page

**Why**: The maintainer found the README and the wiki piled up and hard to read. The README had 848 lines and was a tutorial, an API reference, a research report and a roadmap at once, all of which the wiki already covers. Wiki entries laid conclusion, evidence and qualifications side by side in one paragraph, with exact figures and code line numbers inside the main sentence. Most readers want the conclusion; the evidence is for those who check it. Layered by need, neither kind of reader carries what the other needs.

**Alternatives rejected**:
- Keeping the field tables and the feature examples in the README — two copies to maintain with the wiki, and they drift apart without an error
- Moving the evidence to separate subpages — a reader clicks once more, and one entry's conclusion and evidence end up on two pages; the maintainer chose collapsed sections
- Cutting the evidence — the checks depend on those numbers and line numbers, so they move and stay
- Keeping the wiki's full contents in the README — the wiki's sidebar provides them; the README keeps the table by kind of reader

**How to apply**: Write or rewrite README and wiki pages to this structure. The README's code blocks are still run by `tests/test_readme_examples.py`, which now covers the "Example" section only; look at that test when changing the section's heading or code. When wiki pages are added or removed, update the README's documentation table and the wiki's sidebar.
This entry supersedes 2026-09-26 "The README opens with the purpose, and shows the reproduction comparison and the limitations", and partly supersedes 2026-09-28 "The README opens with entry points" (the table by kind of reader stays, the wiki's contents go, and the entry points move after the example).

**Human in the loop**:
- Decided by: enshulv (the README keeps the key points and what makes the library worth using, evidence goes into collapsed sections, formulas use LaTeX)
- AI assistance: Claude Code rewrote the README and the limitations page; subagents rewrote the other wiki pages to the same specification
- Verified by me: the maintainer looked at the rendered README and limitations page in a browser
- Not verified: the other wiki pages are spot-checked by the maintainer, not reviewed page by page

## 2026-09-28

### The README opens with entry points: a table by kind of reader and the wiki's contents

(⚠ Partially superseded: since 2026-09-29 the README no longer lists the wiki's contents, and the
table by kind of reader comes after the example; see 2026-09-29 "The README keeps what the library
is, its findings and the entry points".)

**Decision**: The README gains a "Where to start" section after the subtitle and before the
purpose. It has three parts: two sentences on what the wiki and the README each cover; a table
that points each kind of reader to a page; and the contents of the wiki, in four groups
(tutorial, mechanisms, reference, guides), shown in full. The kinds of reader are: a researcher
who has never used Python, a researcher who wants a one-page overview, someone looking for the
model and formulas of a mechanism, a researcher with a mechanism of their own, someone comparing
with the published experiments, someone looking up a function or an error, someone asking how
far to trust the results, and a contributor. A researcher with a mechanism of their own is asked
to open an issue with the paper, pseudocode or code that states it, and the maintainer adds it to
the library; one who wants to write it themselves is pointed to tutorial page 9.

**Why**: On 2026-09-28 the README and the wiki were each read from the point of view of a
researcher with no prior context. The wiki's tutorial starts from zero and is enough for a
researcher who does not program. The README, however, reaches the lag and the floor of the
price-update rule in the second point of its purpose, then Rust, maturin and the field tables,
and its links to the wiki sit in the middle; the readers the tutorial is written for left before
they reached a link. With the entry points at the top, every kind of reader sees on the first
screen where to go. A researcher with a mechanism of their own is the most typical "next person
in the field" of the first principle, and the table had no row for them.

**Alternatives rejected**:
- One or two sentences above the table stating the reproduction result — the maintainer declined:
  a reader who scrolls down reaches the reproduction section
- Folding the wiki contents into a `<details>` block — done and then reverted (`1726d92`,
  `d1d1004`); the maintainer chose to show them in full

**How to apply**: When a wiki page is added or removed, update the README's contents list and
table with it. This entry partially supersedes the order in 2026-09-26 "The README opens with the
purpose": an entry-point section now comes before the purpose, and the rest of the order is
unchanged.

### The wiki gains a Mechanisms section: one rigorous statement per mechanism that ships with the library

**Decision**: The wiki gains a Mechanisms section, an index page and one page per mechanism that
ships with the library, starting with Hahnel (2021). Each page gives the participants, the model
each solves, the closed-form solutions and their derivation, the price-adjustment and stopping
rules, a table from symbols to `Economy` and `Plan` fields, the parameters of a published data set
(with a script to rerun and its output), the properties that follow mathematically from the
functional forms, and the sources. It states the mechanism and nothing else: it does not answer
particular questions, list real-world counterexamples or draw inferences the literature does not.

**Why**: The maintainer's requirement (2026-09-28). The reference pages say how to call the code;
nothing gave a reader without context a statement of the mechanism precise enough to reimplement
and to check formula by formula. The formulas were spread over the paper, the book and the code,
and the price rule printed in the book differs from the program that produced its tables. A
statement written in the terms of an earlier discussion (for example, arguing that effort is not
a split of labour) reads to a reader without that discussion as an answer to a question nobody
asked.

**Alternatives rejected**:
- Put the formulas into the reference pages — the reference is organised by API and the statement
  by model; mixing them makes both harder to find
- Include the discussion material as well (a comparison with effective labour, a table of
  real-world counterexamples, an inference about how hard convergence would be) — that is
  discussion, not the mechanism, and it presets the reader's questions

**How to apply**: When a mechanism is added to the library, add a page in the same structure and
list it on the index page and in the sidebar. Every claim attributed to a source on the page is
checked against the original under the citation rule; the numbers in the parameter table come with
the script and its output.

### `release.yml` can also publish when run by hand, only on a `v*` tag and only when ticked

**Decision**: The `workflow_dispatch` trigger of `release.yml` gains a boolean input `publish`
(off by default). The upload step runs in two cases: a GitHub release is published; or the
workflow is run by hand with `publish` ticked on a `v*` tag. Any other run, including a manual
run with `publish` ticked on a branch, builds without uploading.

**Why**: Since September 2026, pushes to this repository have not started CI runs (GitHub receives
the event and the workflow is active, but no run is created; the cause is not known), and the two
pushes after the repository became public on 2026-09-28 behaved the same. If a published release
also failed to start the workflow, the release would be up and PyPI would stay empty. (That day the v0.1.0 release event did not start the workflow; after the repository's Actions were turned off and on again, pushes started runs again.) The trusted
publisher is bound to the workflow file and the environment, not to the event, so a manual run can
upload as well. Limiting it to tags means every uploaded package corresponds to a fixed, versioned
commit.

**Alternatives rejected**:
- Find out why events do not start runs before releasing — the investigation so far found
  nothing, and the release does not need to wait for it
- Let every manual run upload — one mistaken run on a branch would use up a version number, and
  PyPI never lets a version number be reused, even after deletion

**How to apply**: To release, publish a GitHub release first; if no run triggered by the `release`
event appears under Actions within a minute, run the workflow by hand on that tag with `publish`
ticked. Partially supersedes the sentence "`workflow_dispatch` does not upload" in the 2026-09-26
entry on publishing through GitHub Actions.

### Go public after opening the kinds, Stage 2 and the WIOD loader

**Decision**: The repository becomes public once three pieces of work are merged and the full test suite and CI pass: opening up the commodity and technology kinds, Stage 2 (residual and indicator tools), and the WIOD loader.

**Why**: Decided by the maintainer: the published library should do more than reproduce Hahnel; it should load real input-output tables and show residuals.
This narrows the 2026-09-26 "publish early" decision: the reason (a public repository establishes the date) still holds; only the moment of publication moves to after these three pieces.

**Rejected alternatives**:
- Publish as soon as the reviewed Hahnel reproduction is complete and release later work as versions — not chosen by the maintainer

---

### The wiki follows documentation-site conventions, with a from-zero tutorial and a full configuration reference

**Decision**: The wiki is organised like a documentation site, one Markdown file per page, so it can later move into a documentation website unchanged.
It gains two parts: a tutorial for social scientists that assumes the reader has never used the library and goes step by step from installation to using the shipped models and then to building their own economy; and a complete configuration reference listing every parameter of every public function and class, with its type, default and errors.

**Why**: Decided by the maintainer. Researchers are the first users, and the existing researcher guide covers everything on one page, which is too fast for someone starting from zero.

**How to apply**: Every code snippet in the tutorial is run and its output pasted from the run; the configuration reference is checked item by item against the code, never written from memory.
The three audiences of 2026-09-26 "The wiki has researcher, contributor and quality-assurance pages" stay; the researcher part expands into several pages.

---

## 2026-09-26

### Publish early; the public repository and a DOI establish the date

**Decision**: v1 is published before it is feature-complete. The public repository establishes
the date and the authorship, and the first release gets a DOI through Zenodo. The README says
that a DOI will be registered and that citations and mentions are welcome.

**Why**: The project had been under way for a month and the maintainer was concerned about
being pre-empted. What counts academically is a public, timestamped record, not how many
features exist, so establishing priority and finishing a minimum viable product are separate
steps and the first does not need to wait for the second. The charter's "a better fork also
counts as success" is about the field's progress; authorship and citation are a separate matter,
and the two do not conflict.

**Alternatives rejected**:
- Wait for the minimum viable product (real input-output tables, an output format, prebuilt
  wheels) before publishing — several more weeks, and publication needs none of these

**How to apply**: Changes to the data model that break existing code (open commodity kinds,
stable identifiers, joint products) happen before 1.0. The README's limitations section says so,
so breaking changes during 0.x are announced in advance.

---

### The README opens with the purpose, and shows the reproduction comparison and the limitations

(⚠ Superseded, see 2026-09-29 "The README keeps what the library is, its findings and the entry
points". Before that, from 2026-09-28, a "Where to start" section came before the purpose.)

**Decision**: The README runs in this order: purpose → what it does → results of reproducing the
published experiments → the first comparison between two mechanisms and why it cannot be quoted
yet → limitations and open work → installation and usage → contributing and the AI policy →
how to cite → references → license.

The purpose section says four things: the field lacks shared infrastructure, while the
neighbouring field of social simulation has it (Mesa, Concordia, AgentSociety); implementations
of democratic planning are scattered and published results are hard to reproduce; this is not a
failing of the researchers, because research and engineering are best divided, economists should
not spend their effort writing code, and AI does not substitute for sound engineering structure;
and people with the skills and interest are invited to take part. It also states that the
maintainer is an independent developer, with no funding from any organisation and no commercial
purpose, who will maintain the library for the long term.

**Why**: The purpose is what the maintainer wants readers to know first: why the library is
worth using and why it is worth contributing to. The reproduction comparison comes before usage
because it is the direct evidence for why the library exists, and it is what a reader uses to
judge whether to trust it. The limitations are placed prominently because academic transparency
requires it: a reader needs to know, before using the library, what it cannot do yet and which
numbers cannot be quoted yet.

Statements about the upstream authors' work stay factual: measured numbers and differences,
without evaluative adjectives. The README says explicitly that the reproduction problems come
from researchers having to be software engineers as well, not from any individual's failing.

**How to apply**: Every number in the README must be traceable to `docs/research/` and must come
from a run. The README's code blocks are executed by `tests/test_readme_examples.py`; changing a
heading or a code block means checking that test too.

---

### The wiki has three guides: researchers, contributors, quality assurance

**Decision**: The GitHub wiki has a home page and three guides. For Researchers: installation,
the first run, the data structures, writing a coordination procedure, the reproducibility tools,
comparing with the reference solution and its caveats, and what the library does not promise.
For Contributors: where help is most useful, the five design rules, the architecture, how
changes are checked, how the documentation is divided, and the AI policy. Quality Assurance: see
[quality-assurance.md](quality-assurance.md).

**Why**: The README is already long, and the two audiences want different things. Researchers
want to know how to use the library and how far to trust its results; developers want the design
constraints and the rules. Written separately, neither has to skip past the other's material.

**How to apply**: Example code and output in the wiki must have been run. The wiki is a separate
git repository that the test suite does not cover, so an API change means checking the wiki's
examples by hand.

---

### Authorship: Enrique Mark; license: MIT

**Decision**: The author is credited as Enrique Mark (given name Enrique, family name Mark), with
the GitHub handle `enshulv` as an alias. The author's ORCID iD is 0009-0004-2013-3270. `CITATION.cff` uses this name and ORCID iD, and the copyright holder
in `LICENSE` is `Enrique Mark`. Once outside contributions are merged, it becomes
`Enrique Mark and demplan contributors`.

**Why**: Academic citation needs a real name. The MIT license requires the copyright notice to be
kept, so the holder cannot be left blank. Under GitHub's terms of service, a contribution to an
MIT-licensed repository is licensed under MIT, so no separate agreement is needed.

---

### Every citation needs evidence from the original source

**Decision**: Every citation in the public documentation (README, wiki, `CONTRIBUTING.md`,
`docs/`), and every specific claim attached to a citation (a page, a number, a quotation), has to
be checked against the original source. Before publication, an independent reviewer with no
access to how the documents were written checks each one and has to give evidence: where in the
original, and a quotation. When the original cannot be found, it is requested from the
maintainer; when the maintainer cannot provide it either, the citation is removed.

**Why**: This is an academic library, and a wrong citation is worse than none: readers follow the
wrong source, or take an unsupported claim as supported. Citations written from a title or from
memory all read as genuine; only a check against the original tells them apart.

**How to apply**: Find the original before writing a new citation. A claim without a located
source does not get a citation number.

---

### Releases go through GitHub Actions: prebuilt wheels and trusted publishing

**Decision**: `.github/workflows/release.yml` builds wheels and an sdist and uploads them to PyPI
when a GitHub release is published. The wheels cover five targets: Linux x86_64 and aarch64
(manylinux), macOS arm64 and x86_64, and Windows x64. The extension module uses the stable ABI
(`abi3-py310`), so one wheel per platform covers every Python version from 3.10 on. Uploads use
PyPI trusted publishing: the trusted publisher registered on PyPI is `release.yml` in the
`enshulv/demplan` repository with the environment `pypi`, and no token is stored anywhere.

`.github/workflows/ci.yml` runs pytest and `cargo test -p demplan-core` on Linux, Windows and
macOS on every push and pull request. CI does not download the dep1ex data, so the tests that
need it skip themselves; the reproduction targets are still checked locally against the
published data.

**Why**: Social scientists cannot be expected to install a Rust toolchain, so without prebuilt
wheels the library is effectively unusable for its intended users (the charter's third part, a
low-barrier interface). Trusted publishing needs no secret to guard, so there is nothing to leak.
CI lets outside contributors see test results when they submit, without waiting for the
maintainer to run them locally.

Only `demplan-core` is tested on the Rust side: all Rust tests live in that crate, and the
Python binding crate has the `extension-module` feature, which can leave its test binary unable
to find libpython's symbols when linking on Linux and macOS.

**Alternatives rejected**:
- Generate a PyPI API token and store it as a repository secret — one more secret to guard and
  possibly leak, when trusted publishing does the same job
- Build one wheel per Python version — the bindings already use the stable ABI, so per-version
  builds would only produce duplicate files

**How to apply**: Neither workflow has run yet, because the repository did not exist when they
were written; check the logs of the first runs. Before releasing `v0.1.0`, trigger `release.yml`
by hand once (`workflow_dispatch` does not upload) and confirm that all five wheels build. (Since 2026-09-28 a manual run uploads when `publish` is ticked and it runs on a
`v*` tag; see 2026-09-28.)
