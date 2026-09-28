# check=skip=InvalidDefaultArgInFrom
# An image built from ./Dockerfile with files of pequod-plus replaced by edited copies.
#
# Build argument:
#   BASE  the image to start from, one built from ./Dockerfile (required)
#
# Build context, written by run_all.py from an edit set in edits/:
#   source/      the edited files, at their paths within the repository
#   changes.txt  the diff of the edited files against the files of BASE
#
# The diff replaces /opt/source-info/changes.txt, which run_all.py prints for every image.
#
# BASE has no default, so that a build without it fails instead of starting from some other
# image; the check directive on the first line silences BuildKit's warning about that.
ARG BASE
FROM ${BASE}
COPY source/ /opt/pequod-plus/
COPY changes.txt /opt/source-info/changes.txt
