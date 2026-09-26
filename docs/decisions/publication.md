# Publication

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
