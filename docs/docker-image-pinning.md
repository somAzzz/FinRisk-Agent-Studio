# Docker Image Pinning

This project pins base images to a specific **minor version**
(`neo4j:5.26.0`, `lmsysorg/sglang:v0.5.14-cu130-runtime`) rather
than to a digest or to a floating `latest` tag. This document
explains the choice and how to bump.

## Why minor-version pinning, not digest pinning

- **Layer caching**: Docker layer hashes depend on the resolved
  base image. A digest-pinned image changes hashes on every base
  image rebuild, which busts the layer cache. Minor-version
  pinning only invalidates the cache when we explicitly bump.
- **Cross-registry promotion**: We may pull the same base image
  from `docker.io`, a mirror, or an internal registry. Digest
  pinning ties us to one registry's content-addressable scheme.
- **Auditability**: A reviewer can `docker pull` the same image
  that CI uses without copying a 64-character digest.
- **Trade-off**: A base image update can ship silently between
  the pinned version and the next bump. We accept this because
  the audit's priority is "reproducible builds now" and the
  alternative (digest pinning) is operationally costly.

## Bump cadence

Quarterly. The owner of this repository reviews the upstream
release notes for each pinned image and opens a PR that bumps
the minor version. The PR must include:

- A note in the commit message summarising upstream release
  highlights / CVEs.
- A successful CI run (lint + test).
- A manual smoke test (`docker compose up -d <service>` and a
  trivial `docker exec` check).

## Pinned images (2026-06-27 baseline)

| Service | Image | Pinned version | Upstream |
|---|---|---|---|
| `sglang` | `lmsysorg/sglang` | `v0.5.14-cu130-runtime` | <https://github.com/sgl-project/sglang/releases> |
| `neo4j` | `neo4j` | `5.26.0` | <https://neo4j.com/release-notes/> |
