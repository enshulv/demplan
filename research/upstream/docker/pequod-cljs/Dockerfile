# pequod-cljs (https://github.com/msszczep/pequod-cljs) at 71e44d3. Its csvgen.clj is the same
# Git blob as at df6dc57, the commit that adds the output files dep1ex51.csv ... dep1ex100.csv.
#
# Java 11 and Leiningen 2.9: project.clj declares Clojure 1.9.0 and Leiningen >= 2.5.0, and the
# README shows "Leiningen 2.8.1 on Java 11.0.7" as example output. This is the official
# Clojure image with the nearest versions that has a digest: OpenJDK 11.0.16, Leiningen 2.9.8.
FROM clojure:openjdk-11-lein-2.9.8-bullseye@sha256:b9611359a8d7f26249a77b9936cbf1b7abb5c0aefa01fa8abb30aafe8d9ba7c9

ARG REPO=https://github.com/msszczep/pequod-cljs.git
# csvgen.clj as committed on 2020-06-23 ("Adding bigger CSV and gen scripts").
ARG PROGRAM_COMMIT=71e44d39a36a22b1acf9355baa7e96c20ad18273
# The commit that adds the output files ("Adding results of scaled-up experiments").
ARG OUTPUT_COMMIT=df6dc57743d2ebb4eb2f9e255472cc87e1f22a23
# The commits that add the Git LFS pointers of the input files dep1ex61.clj ... dep1ex65.clj.
# None of these inputs is in the tree of PROGRAM_COMMIT.
ARG POINTER_COMMITS="61:ab9a6084090842374a79bc88d51bab2edc36445c 62:b36c1258d6dd6967cb81002bb13e39ef15add0d4 63:0de3b87c5e31f6184eb86057523ffe586eb03cbf 64:36bbdbd0ae01ed44dcf77f21b941169674cf1d72 65:4f7fc9061d3ca6491642b7369c26c136750ff1a1"

# The inputs are Git LFS objects of 160 MB each; only their pointer files are fetched.
ENV GIT_LFS_SKIP_SMUDGE=1

WORKDIR /pequod-cljs

# A blob-less clone fetches commits and trees; checkout then fetches only the blobs of
# PROGRAM_COMMIT, and `git show` only the blobs it prints.
RUN git clone --quiet --filter=blob:none --no-checkout "$REPO" . \
 && git checkout --quiet --detach "$PROGRAM_COMMIT" \
 && test "$(git rev-parse HEAD)" = "$PROGRAM_COMMIT"

# What the run script and run.py read back: the commit checked out, the csvgen.clj blob at
# the program and output commits, the output files' blob ids, and the input pointers.
RUN mkdir /evidence \
 && git rev-parse HEAD > /evidence/program-commit \
 && for c in "$PROGRAM_COMMIT" "$OUTPUT_COMMIT"; do \
      echo "$c $(git rev-parse "$c:src/clj/pequod_cljs/csvgen.clj")" >> /evidence/csvgen-blobs; \
    done \
 && for pair in $POINTER_COMMITS; do \
      n="${pair%%:*}"; c="${pair#*:}"; \
      git ls-tree "$OUTPUT_COMMIT" "src/clj/pequod_cljs/dep1ex$n.csv" >> /evidence/output-csv-blobs; \
      echo "$c" > "/evidence/dep1ex$n.clj.pointer-commit"; \
      git show "$c:src/clj/pequod_cljs/dep1ex$n.clj" > "/evidence/dep1ex$n.clj.pointer"; \
    done

# Fetch the dependencies and plugins project.clj declares, so a run needs no network.
RUN lein deps > /dev/null
