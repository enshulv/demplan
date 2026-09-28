#!/bin/bash
# Run pequod-cljs's csvgen.clj on one input file inside the image built from ./Dockerfile, the
# way bin/bigger_csv.sh runs it: `lein run -m pequod-cljs.csvgen exNN`. The CSV goes to stdout,
# diagnostics to stderr.
#
# Usage: run_csvgen.sh NN [CSVGEN]
#   NN      the repository's experiment number, 61 to 65
#   CSVGEN  a csvgen.clj to run in place of the committed one: run.py writes one per edit set in
#           edits/. Without it, csvgen.clj runs exactly as committed. Either way the script prints
#           the file's diff against the commit.
#
# Expects /data/dep1exNN.clj (the input with its first-line namespace set to pequod-cljs.dep1exNN)
# and this directory at /work.
set -euo pipefail

experiment="$1"
replacement="${2:-}"
src=src/clj/pequod_cljs
target_ns="pequod-cljs.dep1ex${experiment}"
cd /pequod-cljs

# The input must be the file the repository's LFS pointer names.
pointer="/evidence/dep1ex${experiment}.clj.pointer"
want_oid="$(sed -n 's/^oid sha256://p' "$pointer")"
want_size="$(sed -n 's/^size //p' "$pointer")"
have_oid="$(sha256sum "/data/dep1ex${experiment}.clj" | cut -d' ' -f1)"
have_size="$(stat -c %s "/data/dep1ex${experiment}.clj")"
echo "input: sha256 ${have_oid} size ${have_size}; LFS pointer at $(cat "/evidence/dep1ex${experiment}.clj.pointer-commit"): sha256 ${want_oid} size ${want_size}" >&2
if [ "$have_oid" != "$want_oid" ] || [ "$have_size" != "$want_size" ]; then
  echo "input does not match the LFS pointer; stopping" >&2
  exit 3
fi

# csvgen.clj's ns form requires 101 data namespaces. At this commit the tree holds only
# dep1ex01 ... dep1ex50, a smaller, earlier data set; dep1ex51 ... dep1ex100 and ex081 are not
# in it, so the program as committed cannot load. Every required namespace other than the one
# under test is replaced by a stub that defines ccs and wcs as nil. setup's `case` reads only
# the namespace named on the command line, so the stubs are never read. csvgen.clj itself is
# not changed for this.
required="$(sed -n '1,/^))/p' "$src/csvgen.clj" | grep -o '\[pequod-cljs\.[A-Za-z0-9_-]*' | tr -d '[')"
stubbed=0
for ns in $required; do
  [ "$ns" = "$target_ns" ] && continue
  printf '(ns %s)\n(def ccs nil)\n(def wcs nil)\n' "$ns" > "$src/${ns#pequod-cljs.}.clj"
  stubbed=$((stubbed + 1))
done
echo "stubbed ${stubbed} of $(echo "$required" | wc -w) required namespaces; ${target_ns} is the input" >&2
cp "/data/dep1ex${experiment}.clj" "$src/"

if [ -n "$replacement" ]; then
  cp "$replacement" "$src/csvgen.clj"
fi
echo "csvgen.clj: git blob $(git hash-object "$src/csvgen.clj"); changes against $(git rev-parse --short HEAD):" >&2
git --no-pager diff --no-color -- "$src/csvgen.clj" >&2
echo "java: $(java -version 2>&1 | head -1); lein: $(lein version 2>/dev/null | tail -1); JVM_OPTS=${JVM_OPTS:-}" >&2

echo "starting: lein run -m pequod-cljs.csvgen ex${experiment}" >&2
exec lein run -m pequod-cljs.csvgen "ex${experiment}"
