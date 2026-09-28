# pequod-plus (https://github.com/msszczep/pequod-plus) at one pinned commit, built with its own
# project.clj, plus the probe namespaces of this directory under src/clj/probe/.
#
# Build argument:
#   PEQUOD_COMMIT  full commit hash to check out (required)
#
# No file of pequod-plus is changed: the probes are added as new files, and
# /opt/source-info/changes.txt records `git diff` of the checkout, which is empty.
# edited.Dockerfile builds on an image of this file to replace lines of pequod-plus.
#
# Both base images are pinned by digest. The Clojure image has Leiningen on Eclipse Temurin
# JDK 21. The author's run log (docs/notes.txt) shows an OpenJDK of version 13 or later and does
# not record which; 21 is a long-term-support release that runs Clojure 1.11.1 and
# sqlite-jdbc 3.51.3.0. git comes from a separate image so that the build needs no package
# mirror.
ARG GIT_IMAGE=alpine/git@sha256:832b1cd1a271509f3d5272a1a62d4cb2ab1a53426ebde1f6c2cb7349f907dc6f
ARG CLOJURE_IMAGE=clojure:temurin-21-lein-bookworm@sha256:99636c48fe24ab35ea03e8708639296656da9297a3441bade3b07c35190ad774

# The dependencies of 44a6d08 (the same project.clj as the head of branch db, 44d8c15). Resolving
# them in their own stage lets every commit reuse one download.
FROM ${GIT_IMAGE} AS dependency-source
ARG DEPENDENCY_COMMIT=44a6d08be631b57e1638d39555d1f6089f0ca68b
RUN for attempt in 1 2 3 4 5; do \
      git clone --quiet https://github.com/msszczep/pequod-plus.git /pequod-plus && break; \
      rm -rf /pequod-plus; sleep 10; \
    done \
 && git -C /pequod-plus checkout --quiet --detach "$DEPENDENCY_COMMIT"

FROM ${GIT_IMAGE} AS source
ARG PEQUOD_COMMIT
COPY --from=dependency-source /pequod-plus /pequod-plus
RUN test -n "$PEQUOD_COMMIT" \
 && cd /pequod-plus \
 && git checkout --quiet --detach "$PEQUOD_COMMIT" \
 && test "$(git rev-parse HEAD)" = "$PEQUOD_COMMIT" \
 && mkdir /source-info \
 && git log -1 --format="commit %H %cI %s" > /source-info/commit.txt \
 && git diff --stat > /source-info/changes.txt \
 && { git diff --unified=0 --word-diff=porcelain | grep -E '^(@@|[-+][^-+])' >> /source-info/changes.txt || true; }

FROM ${CLOJURE_IMAGE}
ENV LEIN_ROOT=1
COPY --from=dependency-source /pequod-plus/project.clj /opt/dependencies/project.clj
RUN cd /opt/dependencies && lein deps
COPY --from=source /pequod-plus /opt/pequod-plus
COPY --from=source /source-info /opt/source-info
WORKDIR /opt/pequod-plus
RUN lein deps
COPY probe/src/probe/ /opt/pequod-plus/src/clj/probe/
