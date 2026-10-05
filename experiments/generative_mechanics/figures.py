"""Publication-oriented deterministic figure rendering for the experiment tables."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

FIGURE_VERSION = "gm-figures-v0.1"
COLORS = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
          "red": "#D55E00", "purple": "#CC79A7", "gray": "#666666"}


def _matplotlib():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("render-figures requires the optional matplotlib dependency") from exc
    matplotlib.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 9, "axes.labelsize": 9,
        "axes.titlesize": 10, "legend.fontsize": 8, "svg.hashsalt": "pmw-gml-v0.1",
        "pdf.compression": 9,
    })
    return plt


def _save(fig, stem: Path) -> list[Path]:
    paths = []
    for extension in ("pdf", "svg", "png"):
        path = stem.with_suffix(f".{extension}")
        metadata = ({"Creator": "PMW Generative Mechanics Lab", "CreationDate": None, "ModDate": None}
                    if extension == "pdf" else
                    {"Creator": "PMW Generative Mechanics Lab", "Date": None}
                    if extension == "svg" else {"Software": "PMW Generative Mechanics Lab"})
        fig.savefig(path, dpi=300 if extension == "png" else None, bbox_inches="tight", metadata=metadata)
        paths.append(path)
    return paths


def render_figures(batch: dict[str, Any], analysis: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    plt = _matplotlib()
    output = Path(output_dir); output.mkdir(parents=True, exist_ok=True)
    records = [row for row in batch.get("records", ()) if row.get("status") == "ok"]
    artifacts: list[Path] = []

    fig, ax = plt.subplots(figsize=(7.2, 2.2))
    ax.axis("off")
    labels = ("Generated\nMechanic", "Strict\nContract", "PMW\nExecution", "World\nLaws", "Emergent\nConsequences")
    xs = [0.08, .29, .50, .71, .92]
    for index, (x, label) in enumerate(zip(xs, labels)):
        color = COLORS["orange"] if index == 0 else COLORS["blue"] if index < 3 else COLORS["green"]
        ax.text(x, .5, label, ha="center", va="center", color="white", fontweight="bold",
                transform=ax.transAxes, bbox={"boxstyle": "round,pad=.45", "facecolor": color, "edgecolor": "none"})
        if index:
            ax.annotate("", xy=(x-.08, .5), xytext=(xs[index-1]+.08, .5), xycoords=ax.transAxes,
                        arrowprops={"arrowstyle": "->", "color": COLORS["gray"], "lw": 1.4})
    ax.set_title("Executable mechanic evaluation pipeline", pad=10)
    artifacts += _save(fig, output / "fig1_pipeline"); plt.close(fig)

    env_rows = analysis.get("cross_environment", [])
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    environments = ("mine", "wetland", "industrial_yard", "fragile_bridge")
    values = [sum(row["environments"][env]["downstream_count"] for row in env_rows) / len(env_rows)
              if env_rows else 0 for env in environments]
    ax.bar(range(4), values, color=[COLORS["blue"], COLORS["green"], COLORS["orange"], COLORS["purple"]])
    ax.set_xticks(range(4), ["Mine", "Wetland", "Industrial Yard", "Fragile Bridge"])
    ax.set_ylabel("Mean additional world laws")
    ax.set_title("Same unchanged mechanics across environments")
    ax.spines[["top", "right"]].set_visible(False)
    artifacts += _save(fig, output / "fig2_cross_environment"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    target_mid = {"Low": 25, "Mid": 45, "High": 65}
    for baseline, color, marker in (("direct_effect", COLORS["orange"], "o"),
                                     ("world_substrate", COLORS["blue"], "s")):
        rows = [row for row in records if row["baseline"] == baseline]
        ax.scatter([target_mid[row["target_band"]] for row in rows],
                   [row["evaluators"]["pmw_standard_simulation"]["score"] for row in rows],
                   facecolors="none", edgecolors=color, marker=marker, alpha=.7,
                   label=baseline.replace("_", " ") + " one-shot")
        ax.scatter([target_mid[row["target_band"]] for row in rows],
                   [row["guided_score"] for row in rows], color=color, marker="x", alpha=.65,
                   label=baseline.replace("_", " ") + " guided")
    ax.plot([15, 75], [15, 75], color=COLORS["gray"], linestyle="--", linewidth=1)
    ax.set(xlabel="Requested target midpoint", ylabel="Held-out realized power",
           title="Requested versus realized power")
    ax.legend(frameon=False); ax.spines[["top", "right"]].set_visible(False)
    artifacts += _save(fig, output / "fig3_target_vs_realized"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.2, 3.5)); ax.axis("off")
    comparison = analysis.get("evaluator_comparison", {})
    if not comparison.get("available"):
        ax.text(.5, .56, "Evaluator accuracy unavailable", ha="center", va="center",
                fontsize=13, fontweight="bold", transform=ax.transAxes)
        ax.text(.5, .40, "No independent ground truth supplied.\nFixture scores are not substituted.",
                ha="center", va="center", color=COLORS["gray"], transform=ax.transAxes)
    else:
        available = [
            (name, item) for name, item in comparison["evaluators"].items()
            if item.get("mae") is not None
        ]
        if available:
            names, metrics = zip(*available)
            ax.axis("on"); ax.bar(range(len(names)), [item["mae"] for item in metrics], color=COLORS["blue"])
            ax.set_xticks(range(len(names)), [name.replace("_", "\n") for name in names]); ax.set_ylabel("MAE")
        else:
            ax.text(.5, .5, "Insufficient paired evaluator data", ha="center", va="center",
                    transform=ax.transAxes)
    ax.set_title("Evaluator comparison (fixture protocol)")
    artifacts += _save(fig, output / "fig4_evaluator_comparison"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    global_scores = [row["evaluators"]["pmw_standard_simulation"]["score"] for row in records]
    deltas = [row["evaluators"]["pmw_contextual_search"]["score"] for row in records]
    colors = [COLORS["orange"] if row["baseline"] == "direct_effect" else COLORS["blue"] for row in records]
    ax.scatter(global_scores, deltas, c=colors, alpha=.65)
    ax.axhline(0, color=COLORS["gray"], linewidth=1)
    ax.set(xlabel="Global held-out power", ylabel="Personalized build delta",
           title="Global power versus contextual value")
    ax.spines[["top", "right"]].set_visible(False)
    artifacts += _save(fig, output / "fig5_global_vs_personalized"); plt.close(fig)

    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(artifacts)}
    manifest = {
        "schema_version": FIGURE_VERSION,
        "fixture_disclaimer": "Figures rendered from deterministic fixtures are pipeline artifacts, not paper findings.",
        "artifacts": hashes,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
