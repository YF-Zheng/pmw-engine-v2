# Paper Output Plan

No formal values are entered before collection and unblinding. Empty cells
remain empty rather than being filled from the DEV pilot.

## Main Text

### Table 1 - Validity And Participation

Rows are models; columns show requested N, schema/compile/execution validity
with 95% CIs, activation-rate mean/distribution, and behavioral inertness.
Conditional columns display eligible N. The caption states that mechanisms,
not arms, are independent.

### Figure 1 - Capability Profiles

Aligned point-and-interval panels show P4 abstract collision probability, P3
median realized depth, P5 outcome differentiation, and P6 path differentiation
for each model. Use common meaningful axes within endpoint; do not use a radar
chart, composite area, total score, or rank ordering selected by significance.

### Figure 2 - Dynamic Reach

Mechanism-level distributions compare median realized and median
necessity-backed depth, with maximum-depth sensitivity in a secondary panel.
Arm-level distributions may appear as a lightly weighted descriptive layer but
receive no independent-sample CI or test.

### Figure 3 - Semantic Versus Abstract Structure

Show semantic and abstract collision probabilities with 95% CIs, plus unique
fractions and eligible N. Raw unique counts are annotated only as descriptive
and are never the headline comparison.

### Figure 4 - Environmental Conditionality

Panel A shows mechanism-level outcome- and path-differentiation fractions.
Panel B shows the four-quadrant composition based on each mechanism's six
contexts. Zero off-diagonal cells remain visible as zeros.

## Supplement

- model matrix, exact versions/configurations, availability, and collection windows;
- validity/failure cascade including transport, provider, refusal, empty,
  malformed, schema, compile, and execution failures;
- primary omnibus and pairwise test table with raw and Holm-adjusted p-values;
- all effect sizes and CIs, including non-significant effects;
- secondary endpoint table with BH q-values and explicit `exploratory` label;
- exact/near-copy/recombination table with frozen definitions and limitation text;
- S1-S5 sensitivity outputs;
- collection incidents, retry logs, alias/returned-ID limitations, and missingness;
- lineage and artifact manifests sufficient to reproduce each paper row.

## Reporting Rules

Models are first presented as capability profiles, not a leaderboard. Figure
order, endpoint inclusion, and primary/secondary labels do not change based on
significance. Saturated or all-zero metrics are reported. Missing is shown as
NA with reason, never plotted as zero. Captions distinguish requested,
execution-valid, structurally eligible, and activated populations.
