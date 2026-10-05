# Result provenance

`fixture_240/` and `phase2_smoke.json` are historical protocol v0.1 replay
artifacts. They are retained for reproducibility, not migrated in place and not
valid evidence for protocol v0.2 or for an LLM result.

New v0.2 runs must use a new output directory, retain `source_kind`, and report
the two Oracle targets separately. A genuine-model pilot requires 135 provider
responses (15 per baseline/band cell) and exact contextual evaluation.
