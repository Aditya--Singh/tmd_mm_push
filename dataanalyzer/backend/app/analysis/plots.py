"""The pictures of a document.

Every picture is a PNG that is written to the disk and shown in the interface. A histogram
for every number, a bar chart for every word that has few enough values, and a map of how
the numbers move with one another.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (the backend is chosen above)
import pandas as pd  # noqa: E402

from app.analysis.profiling import KIND_NUMBER, KIND_TEXT  # noqa: E402

#: The colours of the platform.
MAROON = "#a6192e"
MAROON_DARK = "#8a1426"
GOLD = "#f2b600"
GOLD_DARK = "#a87f00"
GRID = "#e2e5eb"
TEXT = "#465063"

#: How many of the pictures of one document are made.
MAX_PLOTS = 12


def _slug(name: str) -> str:
    """A name that may be used as a file name."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", str(name)).strip("-").lower()

    return cleaned[:60] or "column"


def _style(axis) -> None:
    axis.set_facecolor("white")

    for side in ("top", "right"):
        axis.spines[side].set_visible(False)

    for side in ("left", "bottom"):
        axis.spines[side].set_color(GRID)

    axis.tick_params(colors=TEXT, labelsize=9)
    axis.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.9)
    axis.set_axisbelow(True)


def _save(figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(path, dpi=110, facecolor="white")
    plt.close(figure)


def histogram_of(series: pd.Series, name: str, path: Path) -> bool:
    """The shape of a number."""
    numbers = pd.to_numeric(series, errors="coerce").dropna()

    if len(numbers) < 2:
        return False

    figure, axis = plt.subplots(figsize=(5.2, 3.1))

    values = numbers.astype(float)

    try:
        count = max(2, min(30, int(math.sqrt(len(values)))))
        axis.hist(values, bins=count, color=MAROON, edgecolor="white", linewidth=0.6)
    except Exception:
        return False

    axis.set_title(name, color=MAROON_DARK, fontsize=11, fontweight="bold")
    axis.set_ylabel("Rows", color=TEXT, fontsize=9)

    _style(axis)

    _save(figure, path)

    return True


def bar_chart_of(series: pd.Series, name: str, path: Path, limit: int = 12) -> bool:
    """How often each value occurs."""
    values = series.dropna().astype(str)

    if values.empty:
        return False

    counts = values.value_counts().head(limit)

    if len(counts) == 0 or counts.iloc[0] == 0:
        return False

    # A chart of values that never repeat says nothing: every bar is the same.
    if counts.iloc[0] < 2:
        return False

    labels = [str(label)[:22] for label in counts.index]
    heights = [int(count) for count in counts.values]

    figure, axis = plt.subplots(figsize=(5.2, 3.1))

    axis.barh(range(len(labels))[::-1], heights, color=MAROON, height=0.68)
    axis.set_yticks(range(len(labels))[::-1])
    axis.set_yticklabels(labels)

    axis.set_title(name, color=MAROON_DARK, fontsize=11, fontweight="bold")
    axis.set_xlabel("Rows", color=TEXT, fontsize=9)

    _style(axis)
    axis.grid(axis="x", color=GRID, linewidth=0.8, alpha=0.9)
    axis.grid(axis="y", visible=False)

    _save(figure, path)

    return True


def correlation_map(frame: pd.DataFrame, path: Path) -> bool:
    """How the numbers move with one another."""
    numbers = frame.select_dtypes(include="number")

    if numbers.shape[1] < 2:
        return False

    matrix = numbers.corr(numeric_only=True)

    if matrix.empty:
        return False

    figure, axis = plt.subplots(figsize=(4.6, 4.0))

    image = axis.imshow(matrix.values, cmap="RdYlGn", vmin=-1, vmax=1)

    labels = [str(name)[:16] for name in matrix.columns]

    axis.set_xticks(range(len(labels)))
    axis.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    axis.set_yticks(range(len(labels)))
    axis.set_yticklabels(labels, fontsize=8)

    axis.set_title("How the numbers move together", color=MAROON_DARK, fontsize=11, fontweight="bold")

    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)

    _save(figure, path)

    return True


def build_plots(frame: pd.DataFrame, directory: Path, limit: int = MAX_PLOTS) -> list[dict]:
    """
    The pictures of a document.

    Every picture is written to `directory` and named after the column it shows. The first
    numbers and the first words are the ones that are shown, so that the list stays short.
    """
    directory.mkdir(parents=True, exist_ok=True)

    plots: list[dict] = []

    number_names: list[str] = []
    text_names: list[str] = []

    for name in frame.columns:
        series = frame[name]

        if pd.api.types.is_numeric_dtype(series):
            number_names.append(str(name))
        elif pd.api.types.is_object_dtype(series):
            text_names.append(str(name))

    for name in number_names[: max(1, limit // 2)]:
        path = directory / f"{_slug(name)}.png"

        if histogram_of(frame[name], name, path):
            plots.append({"name": name, "kind": "histogram", "file": path.name})

    for name in text_names[: max(1, limit // 2)]:
        path = directory / f"{_slug(name)}.png"

        if bar_chart_of(frame[name], name, path):
            plots.append({"name": name, "kind": "bar", "file": path.name})

    if len(number_names) >= 2 and len(plots) < limit:
        path = directory / "correlations.png"

        if correlation_map(frame, path):
            plots.append(
                {"name": "How the numbers move together", "kind": "correlation", "file": path.name}
            )

    return plots[:limit]
