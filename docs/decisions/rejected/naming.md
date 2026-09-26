# Rejected: Project Naming

## 2026-08-28

Each candidate below was checked individually against actual name availability on crates.io, PyPI, and GitHub.

### Use the original project's name, cybersyn

**Rejected.**

**Proposal**: use the name of Project Cybersyn directly.

**Why it was considered**: highest name recognition, and structurally the closest fit to this project's own positioning — Cybersyn
itself was an umbrella over CHECO, Cyberstride, Cybernet, and Opsroom, and this project is likewise an umbrella over
"comparison + computational optimization + packaging for social scientists."
The package name is still free on both crates.io and PyPI.

**Why rejected**: the package name is free, but the name is already taken twice in adjacent spaces. The top GitHub search results
are `project-cybersyn/cybersyn2` and similar Factorio train-logistics mods, plus a `cybersyn-data` organization — an economic-data
company that was acquired by Snowflake. The latter collides with this project in the same subject-matter niche.

**Revival condition**: if those two occupied spaces free up. In practice this will not happen, so there is no point waiting for it.

---

### Use checo

**Rejected.**

**Proposal**: take CHECO (CHilean ECOnomy), Cybersyn's economic-simulation component. Both crates.io and PyPI are free.

**Why it was considered**: the closest functional analogy of any candidate. CHECO was itself an economic simulator — given an
economy and a policy, it produced a trajectory — which maps one-to-one onto what this library does. Five letters, easy to type and
say.

**Why rejected**: generic searches collide with two high-frequency terms — the Spanish word for "Czech," and F1 driver Sergio
"Checo" Pérez. The name also does not read as infrastructure.

**Revival condition**: none. Already superseded by `cyberstride`; the mismatch in the functional analogy is recorded as a known
cost in [naming.md](../naming.md).

---

### Other candidates from the same lineage: synco and opsroom

**Rejected.**

**Proposal**: `synco` (from the project's original Spanish name, Proyecto Synco) or `opsroom` (operations room).

**Why it was considered**: `synco` is the project's own name and is two syllables, easy to say; `opsroom` echoes directly with the
already-settled "TS/wasm for visualization and human-in-the-loop frontends" in [technology-choices.md](../technology-choices.md).

**Why rejected**: `synco`'s PyPI package name is already taken, and GitHub search results are drowned out by the `syncora-ai`
family of repositories. `opsroom` is free on all three, but to anyone unfamiliar with this lineage it just reads as a generic
DevOps war room, flattening the meaning; it also only covers the frontend layer, which skews it away from the core library.

**Revival condition**: none.

---

### Use parecon

**Rejected.**

**Proposal**: use the standard abbreviation for participatory economics directly. Both crates.io and PyPI are free.

**Why it was considered**: highest recognition within the movement itself, immediately signaling the field.

**Why rejected**: it would make the project sound smaller than it is. Under [scope-and-purpose.md](../scope-and-purpose.md), this
library covers the field of democratic economic planning as a whole, and participatory planning is only one school within it;
naming it after that school would make same-field alternatives such as Cockshott's labor-time accounting or Kantorovich's linear
programming look like outsiders.

**Revival condition**: none. This conflicts directly with the already-settled scope and purpose.

---

### Use a Greek or Latin abstract-noun family

**Rejected.**

**Proposal**: `koinon` (a league of Greek city-states, held in common), `isegoria` (equal right to speak), `oikonomia` (the
etymological root of "economy"), `consilium` (deliberation, council, plan).

**Why it was considered**: in the same family as `mesa` and `Concordia` — a single word, abstract, not self-explanatory, and
leaving room to grow into. `isegoria` maps semantically right onto the core of participatory planning (every participant's
proposal enters the iteration on equal footing), and it is the cleanest of all on availability: only 15 same-named repositories on
all of GitHub, none with more than one star. `consilium` has the fullest semantics, being deliberation, council, and plan all in
one word.

**Why rejected**: once the Cybersyn lineage was settled on, this family lost its footing — each of these is a good name on its own,
but none of them carries this field's history. Two also have their own specific flaws: `consilium`'s PyPI package name is already
taken by an LLM-debate CLI, colliding in the same semantic space; `isegoria` is five syllables, which is a real handicap when
citing it out loud in a meeting.

**Revival condition**: if the Cybersyn lineage is abandoned.

---

## 2026-09-26

Before the first public release the maintainer reconsidered the name against three criteria:
distinctive, academic in tone, and not overused. The candidates below were checked for actual use
on PyPI, crates.io and GitHub. The choice was `demplan`; see [naming.md](../naming.md), 2026-09-26.

### Keep cyberstride

**Rejected**.

**Proposal**: Keep the name `cyberstride`.

**Why it was considered**: It was already in use, and a rename touches the package, the crates,
the module and every document.

**Why rejected**: The `cyber-` prefix reads first as cybersecurity today, sounds less academic, and
carries a science-fiction tone that does not suit research infrastructure. Renaming before
publication costs one mechanical replacement; renaming after publication would drag every
downstream user along.

**Revival condition**: None.

---

### neurath

**Rejected**.

**Proposal**: Name the library after Otto Neurath. In 1919 he proposed calculation in kind, which
set off the socialist calculation debate; he argued that plans cannot be compared on a single
scale, which matches the library's refusal to fix a metric; and his Isotype pictorial statistics
were meant for readers without statistical training, which matches the charter's low-barrier
interface. The name was free on all three registries, with only a few scattered GitHub
repositories.

**Why it was considered**: One name matched all three parts of the library, with an academic
reference and no overuse.

**Why rejected**: The maintainer chose a plain descriptive name over one that needs a piece of
intellectual history before it makes sense. It also has weaknesses of its own: Neurath's 1919
proposal leans towards central planning, so a critical reader could say it stands for central
rather than democratic planning; and naming a package after a person can read as hanging the
project on one individual.

**Revival condition**: None.

---

### anarres, algedonic, tatonnement, kantorovich

**Rejected**.

**Proposal**: `anarres` (the planet in Le Guin's *The Dispossessed* whose production and
distribution are coordinated by computer, without a centre), `algedonic` (the pain-pleasure
signal of Stafford Beer's cybernetics, used by Cybersyn for alerts), `tatonnement` (Walras's
"groping", the classic term for iterative price adjustment), `kantorovich` (the founder of linear
programming and of optimal planning theory). All four were unregistered on PyPI and crates.io.

**Why it was considered**: Each has a reference behind it and none is overused.

**Why rejected**: `anarres` is a literary reference and less academic than a person's name;
`algedonic` is obscure, hard to spell, and means an alarm rather than a plan; `tatonnement` is a
term of market mechanisms and conflicts with the comparison boundary that excludes markets;
`kantorovich` is long and matches only the reference solution. Once the plain descriptive route was
chosen, this family as a whole was dropped.

**Revival condition**: None.

---

### SocietyPlanning and PlanningSociety

**Rejected**.

**Proposal**: `SocietyPlanning`, the maintainer's plain descriptive proposal, abbreviated and with
a Core suffix; and `PlanningSociety`, mirroring `AgentSociety`.

**Why it was considered**: Simple and plain, in the same family as `AgentSociety`.

**Why rejected**:
- It is not an established English phrase. Native speakers read it as "social planning" or
  "societal planning", and "social planning" in English is another field (social policy and
  community planning)
- It drops the field's most important qualifier, democratic. "Planning society" easily suggests
  top-down social engineering in English, the very image democratic planning has long worked to
  distance itself from
- The abbreviation `SP` collides with SharePoint, stored procedures and signal processing, and a
  signal-processing library named `spcore` already exists on GitHub; the `-core` suffix usually
  names an internal subpackage in the Rust and Python ecosystems, so a project called XCore
  suggests a larger X outside it

The maintainer accepted the suggestion to keep the idea and change the root: the abbreviation plus
core structure became `demplan` and `demplan-core`.

**Revival condition**: None.

---

### eco_demplan

**Rejected**.

**Proposal**: Prefix `demplan` with `eco` to put "economic" in the name. Free on all three
registries.

**Why it was considered**: `demplan` alone does not say "economic".

**Why rejected**:
- `eco` reads first as ecology (eco-friendly, ecosystem). One strand of planning research is
  precisely ecological planning and eco-socialism, so readers would take this for that strand's
  library: the field is read too narrowly, and the reader believes they read it correctly
- Underscores follow different conventions in each ecosystem: the Python import `eco_demplan`,
  the PyPI name normalised to `eco-demplan`, the Rust convention `eco-demplan-core`. One name with
  three spellings scatters citations and searches

`econ` avoids the ecological reading, but `econdemplan` is awkward to say. The "economic" part of
the meaning is left to the subtitle.

**Revival condition**: None.
