# Naming

## 2026-08-28

### The project is named cyberstride (⚠️ Superseded, see 2026-09-26)

**Decision**: The project is named `cyberstride`. The crate name, Python package name, and repository name all use it. The English subtitle is fixed as "shared research infrastructure for democratic economic planning."

**This name is provisional** and can change before the first public release. The cost of renaming is close to zero while there are no downstream users, so there's no need to lock it in now — but only one name is in use at any given time, with no variant spellings running in parallel.

**Why**: The name comes from Project Cybersyn (Chile, 1971–73), specifically its statistical forecasting and early-warning component, Cyberstride. This lineage is worth claiming because the two projects share a field: Cybersyn was Chile's 1971–73 decision-support system for managing the national economy; it reached the prototype stage in 1972 and was left uncompleted after the 1973 coup. (Corrected 2026-09-26 after a citation check: this said "Cybersyn is the only attempt at democratic economic planning that ever actually ran in production"; the source supports neither "only" nor "ran in production," and says it reached the prototype stage in 1972 and was left uncompleted after the 1973 coup, see Medina (2011), *Cybernetic Revolutionaries*, MIT Press.") (Checked against Medina (2011) on 2026-09-27. The book supports 1971–73 (Introduction: "From 1971 to 1973 the transnational team worked on the creation of this new technological system"), the prototype (Introduction: "In a little over a year the team built a prototype of the system"; opening of chapter 6: "the operations room was a functioning prototype by 10 January", that is, 1973) and the end of the work after the coup (opening of chapter 7: "The military stopped work on Project Cybersyn after the coup"). Two points are not Medina's: the year 1972 for the prototype comes from the English Wikipedia article "Project Cybersyn", and "decision-support system" is how Medina reports the book *Understanding Computers and Cognition* describing Cybersyn (Epilogue: "cite Project Cybersyn as an early example of a computer-based decision-support system"); his own words are "a new computer system for economic management" (chapter 6).)

The project isn't named after Cybersyn itself because that space is already occupied nearby: a GitHub search turns up Factorio's train-logistics mod at the top, plus a `cybersyn-data` organization; an economic-data company of the same name, Cybersyn, has shut down and sold the assets of its public-domain business to Snowflake. The latter collides directly with the economic-data niche. (Corrected 2026-09-26 after a citation check: this said the `cybersyn-data` organization was "the economic-data company acquired by Snowflake"; the founder's article says the company shut down and sold the assets of its public-domain business to Snowflake, and there is no evidence linking the GitHub organization `cybersyn-data` to that company, see <https://magis.substack.com/p/lessons-from-cybersyn>.)

`cyberstride` is unregistered on both crates.io and PyPI. GitHub has 16 repositories with the same name, the highest at 2 stars, two of which are small projects rebuilding Beer's system — a name that reads correctly within the community without having formed any brand ownership. (Checked 2026-09-27: the search of 2026-08-28 cannot be rerun. A GitHub search for `cyberstride` in repository names on 2026-09-27 returns 17 repositories, one of them this project's own `enshulv/cyberstride`, created 2026-08-28, leaving 16; the highest has 2 stars; two describe themselves in terms of Cybersyn's Cyberstride or Stafford Beer's control system, `cuentadesanti/cyberstride` and `ai-forth/cyberstride`. The search matches substrings, so not every result is named exactly `cyberstride`.)

The name was chosen against a shortlist of six libraries in the "social science" category. That set splits into two families: `mesa` and `Concordia` are single words that don't explain themselves; `AgentSociety` and `AgentTorch` are descriptive compounds that are self-evident. This project picked the first family, matching Concordia, its benchmark peer named in [technology-choices.md](technology-choices.md).

**Known mismatch**: Cyberstride, in the original project, did monitoring and early warning; the economic-simulation component was a separate piece, CHECO. By functional analogy, `checo` would be the more accurate name. Choosing `cyberstride` trades analogy accuracy for name quality — see [rejected/naming.md](rejected/naming.md) for detail.

**How to apply**: The name doesn't explain itself, so every first appearance carries the subtitle. The repository description, crate description, and PyPI summary all use the same English sentence — not three separate ones.

---

## 2026-09-26

### The project is renamed demplan

**Decision**: The project is renamed `demplan`, from "democratic planning". The GitHub repository,
the Python package and the Python import name are all `demplan`; the Rust crates are
`demplan-core` and `demplan-py`, and the extension module is `demplan._core`; environment
variables use the prefix `DEMPLAN_`. The English subtitle is unchanged. The rename happens before
publication and the name does not change again.

**Why**: Before the first public release, the maintainer reconsidered the name against three
criteria: distinctive, academic in tone, and not overused. The problem with `cyberstride` is the
`cyber-` prefix: today it reads first as cybersecurity, it sounds less academic, and it carries a
science-fiction tone that does not suit research infrastructure.

The maintainer chose a plain descriptive name, in the same family as `AgentSociety` and
`AgentTorch`: the name states the field and does not require the reader to know a piece of
history first. `demplan` keeps the qualifier that matters most in the field, democratic, and has
only one spelling, so the Python import name, the PyPI package name and the GitHub repository
name agree. `demplan` and `demplan-core` were unregistered on PyPI and crates.io; GitHub had only
three unrelated repositories with demplan in the name.

**Known cost**: In geographic information systems `DEM` means digital elevation model, so a search
for "DEM plan" may bring up surveying results. The name always appears with the subtitle on first
use, which makes this acceptable. The "economic" part of the meaning is carried by the subtitle.

**Alternatives rejected**: The candidates and the reasons each was turned down are in
[rejected/naming.md](rejected/naming.md), 2026-09-26.

**Supersedes**: 2026-08-28, "The project is named cyberstride". That entry's reasoning (the
Cybersyn lineage) and its known mismatch no longer apply. Its two rules, one name at a time and
the subtitle on first appearance, still hold and carry over to this entry.
