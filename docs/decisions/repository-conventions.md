# Repository conventions

## 2026-08-28

### Code is entirely in English; Chinese is only for docs

**Decision**: Identifiers, comments, docstrings, error messages, and test names are all in English. Documentation under `docs/` and day-to-day discussion use Chinese.

**Why**: The target users are the international academic community, and the subtitle is already in English (see [naming.md](naming.md)). Chinese identifiers in the code would shut out non-Chinese readers outright, and the library's reason for existing is to lower the barrier to use.

Chinese documentation doesn't conflict with that: right now, the only reader of the documentation is the maintainer, and an English version can be produced later when needed — but code written in Chinese doesn't have that "produce another version later" option.

(The documentation-language part is partially narrowed by 2026-09-26, "Public documents are in English; the Chinese originals are kept in a private repository". The code-in-English half still holds.)

**How to apply**: In discussion, say "coordination procedure"; in code, write `Procedure`. Chinese-English term mappings are recorded in [glossary.md](../glossary.md).

---

## 2026-09-26

### Upstream literature's original text isn't distributed with the repository

**Decision**: `docs/research/literature/` keeps only the source and download address. The PDFs for the JIE 2023 paper and the 2020 conference slides, along with text extractions of both (the paper's extracted text layer, and a page-by-page transcript of the slides), are removed from the repository and from its entire history.

**Why**: The repository is being prepared for public release. Both materials were published openly by their author or the conference organizers, but redistribution rights weren't verified item by item: the JIE paper, published by Anser Press, is mostly open access, but that still needs confirming per item; the slides are conference material with no stated license terms. A full transcript amounts to redistributing the full text, carrying the same risk as the PDF itself. (Corrected 2026-09-26 after a citation check: this said the JIE paper "is mostly open access, but that still needs confirming per item"; this paper is confirmed as CC BY 4.0, which covers only the publisher's version at <https://www.anserpress.org/journal/jie/1/3/15/pdf>, not the author's version on `szcz.org`; see the license statement on page 1 of the publisher's version and the license field in Crossref.)

The download addresses are stable, and a reader gets the original with one `curl` command — the cost of not distributing them is small.

**Alternatives rejected**:

- Keep the PDF, remove only the transcript — the risk is in the PDF itself; removing the transcript alone doesn't address it
- Verify the license first, decide later — verification means contacting the publisher, and release shouldn't wait on that. Once verified, the material can be added back

**How to apply**: Going forward, archive any third-party literature by recording only its source, DOI, and download address by default. Only put the original text into the repository after confirming the license permits redistribution.

---

### Public documents are in English; the Chinese originals are kept in a private repository

**Decision**: `docs/` in the public repository contains English only. The maintainer's Chinese
originals are kept in a private repository and paired one-to-one with the English files. Chinese
is written first and the English is translated from it; the translation removes the maintainer's
personal information and renders everything else in full.

The pairing is kept in a list: each Chinese file maps to one English file, together with the
SHA-256 of the Chinese text at the time of translation. A pre-commit check blocks the commit in
three cases: a file has no pair, the two sides hold different numbers of files, or a Chinese file
changed without its English translation being updated.

**Why**: The library is for international researchers, and the design documents, decision records
and research notes are the main evidence for judging whether it can be trusted; documents a
reader cannot read are not transparent. The maintainer writes fastest and most precisely in
Chinese, so Chinese remains the original and English is the published version.

Comparing file counts alone is not enough: deleting one file and adding another leaves the count
unchanged, and so does a Chinese edit that the English never caught up with. The list therefore
records content hashes, and what it blocks is the English falling behind the Chinese.

**Alternatives rejected**:
- Both languages in the public repository — two versions side by side leave readers unsure which
  is authoritative, and the Chinese originals contain the maintainer's personal notes, which
  would have to be cleaned file by file
- English only — the maintainer would write decision records in a second language, and the
  reasoning, which is the most valuable part of a record, would be less precise
- Compare file counts only — see above

**How to apply**: To add or change a document, change the Chinese first, then update the English,
then recompute the hashes in the private repository's list. The check runs in the pre-commit hooks
of both the public and the private repository, so neither side can fall behind.

---

### Public commit messages use English Conventional Commits

**Decision**: Commit messages in the public repository are in English and follow Conventional
Commits (`feat:`, `fix:`, `docs:`, `test:`, `perf:`, `refactor:`, `build:`, `chore:`). The subject
line is imperative and at most 72 characters; the body says what changed and why. A commit
message describes the change itself; details of the development process (who reviewed it, how
many passes it took) go in the decision records and the review evidence, not in the commit
message.

**Why**: The commit history is the first-hand record through which outside readers get to know a
project, and those readers are international researchers and developers. Process details have
their full context in the decision records and `docs/reviews/`; in a commit message they would
be fragments the reader cannot judge.

**How to apply**: The same applies to outside contributors, as stated in `CONTRIBUTING.md`.
