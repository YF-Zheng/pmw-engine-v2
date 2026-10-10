# PMW Gameplay v0.4 Compatibility Report

Status: **PASS**

Baseline: `a98ff51561760f87689093c815508fa93120807d`.

The implementation is confined to
`experiments/generative_mechanics/next_tracks_v06/`. PMW Core, old Generative
Mechanics source/assets, pilots, preregistration, and formal protocol files are
unchanged.

## Protected tree

The protected manifest is the sorted `git ls-tree -r` output for `src/pmw` and
`experiments/generative_mechanics`, excluding `next_tracks_v06`. Both baseline
and final trees contain 381 entries with SHA-256:

```text
a20fd763cad342ac357a08d94ee96ca42075f215efcbff93c4017b65a8ddd669
```

`git diff a98ff515... --` over those protected paths is empty.

## Final suites

```text
Core       254/254  25.821s  log SHA 4c41ad2e8462722b0326658e2d28727b1d562281282c1b6f4b1f24c542cd8b49
Old GM     345/345  67.812s  log SHA a966a47256eb311ad63bd14de367a9cbae3515aeb610578ba3d5da97e9ccc15d
v0.6       170/170  25.722s  log SHA 64ae892dc995c17d6221ca2839f0474d7bba5c320091e00f04a414ddd102bc21
Gameplay   107/107  22.361s  log SHA f2d2fbd05ae5f29b2dab0f7448b2f6423eb8e894b5fcd779b105216364176422
```

No suite reported a failure, error, skip, or expected failure. No formal model
request, generated model result, new preregistration, or TODO2 benchmark asset
was created. `git diff --check` passes.
