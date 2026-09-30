"""Statistical significance of the difference between two runs.

Without this, the arena reports that one ranker "scored higher", which on 25–30 topics
is often indistinguishable from noise. With it, the report can say whether a difference
is real, how large it is, and how confident that claim is.

Everything operates on **paired per-topic vectors**, restricted to the topics both runs
actually scored. Comparing means taken over different topic sets is the classic invalid
comparison, so the intersection size is computed here and reported alongside every result.

Three tests are provided because they answer slightly different questions:

* **Permutation (randomization)** — the default. Makes no distributional assumption and
  is exact in the limit, which matters because average precision is bounded and skewed
  and there are only a few dozen topics.
* **Wilcoxon signed-rank** — a rank-based alternative; loses power when many topics tie,
  which happens often between two similar rankers.
* **Paired t-test** — reported because readers expect it, not leaned on at small n.

Bootstrap percentile intervals are computed separately, for the aggregate rather than for
a p-value: a confidence interval communicates the size of an effect, which a p-value does
not, and it is what the charts' error bars show.

At n ≈ 25–30 only medium-to-large effects are detectable — roughly a 15–25% relative
difference in MAP. The report states this rather than implying that an insignificant 2%
gap means the rankers are equivalent.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from irs.config import settings
from irs.logging import get_logger

log = get_logger("irs.eval.significance")


@dataclass(slots=True)
class ComparisonResult:
    """A paired comparison of two runs on one metric."""

    metric_key: str
    test: str
    #: Topics scored by *both* runs.
    sample_size: int
    mean_a: float
    mean_b: float
    mean_difference: float
    p_value: float
    #: Which two runs were compared. Without these the output is a list of anonymous
    #: numbers, which is exactly as useful as no output at all.
    label_a: str = ""
    label_b: str = ""
    statistic: float | None = None
    #: Cohen's d_z — the standardised mean of the paired differences.
    effect_size: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p_value_corrected: float | None = None
    correction: str | None = None
    #: Topics where the two runs scored identically. Many ties means little evidence.
    ties: int = 0


def paired_vectors(
    a: dict[int, dict[str, float]],
    b: dict[int, dict[str, float]],
    metric_key: str,
) -> tuple[list[float], list[float], list[int]]:
    """Align two runs' per-topic scores on the topics both evaluated."""
    shared = sorted(set(a) & set(b))
    return (
        [a[topic][metric_key] for topic in shared if metric_key in a[topic]],
        [b[topic][metric_key] for topic in shared if metric_key in b[topic]],
        shared,
    )


def permutation_test(
    a: list[float], b: list[float], samples: int | None = None, seed: int | None = None
) -> tuple[float, float]:
    """Two-sided paired permutation test on the mean difference.

    Under the null hypothesis that the two rankers are interchangeable, the sign of each
    topic's difference is arbitrary. So the differences' signs are flipped at random and
    the observed mean difference is compared against that distribution.

    Returns ``(observed_mean_difference, p_value)``. The p-value uses the
    ``(hits + 1) / (samples + 1)`` correction, which keeps it strictly positive — a
    reported ``p = 0`` would claim more certainty than a finite number of resamples can
    support.
    """
    if not a or len(a) != len(b):
        return 0.0, 1.0

    samples = samples or settings.evaluation.bootstrap_samples
    rng = random.Random(settings.evaluation.random_seed if seed is None else seed)

    differences = [x - y for x, y in zip(a, b, strict=True)]
    observed = sum(differences) / len(differences)
    target = abs(observed)

    hits = 0
    for _ in range(samples):
        total = 0.0
        for difference in differences:
            total += difference if rng.random() < 0.5 else -difference
        if abs(total / len(differences)) >= target - 1e-15:
            hits += 1

    return observed, (hits + 1) / (samples + 1)


def wilcoxon_test(a: list[float], b: list[float]) -> tuple[float | None, float]:
    """Wilcoxon signed-rank test, via SciPy.

    Zero differences are dropped (the ``wilcox`` convention). Between two similar rankers
    most topics tie, so the effective sample can be far smaller than the topic count —
    which is why the tie count is reported.
    """
    differences = [x - y for x, y in zip(a, b, strict=True) if x != y]
    if len(differences) < 6:
        # Below roughly six non-tied pairs the test has no usable power.
        return None, 1.0

    from scipy import stats

    result = stats.wilcoxon(differences, zero_method="wilcox", alternative="two-sided")
    return float(result.statistic), float(result.pvalue)


def paired_t_test(a: list[float], b: list[float]) -> tuple[float | None, float]:
    """Paired t-test, via SciPy."""
    if len(a) < 3:
        return None, 1.0

    from scipy import stats

    result = stats.ttest_rel(a, b)
    p_value = float(result.pvalue)
    return float(result.statistic), 1.0 if math.isnan(p_value) else p_value


def bootstrap_interval(
    values: list[float],
    samples: int | None = None,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float]:
    """Percentile bootstrap interval for the mean of ``values``.

    Resamples topics with replacement. This is what the chart error bars show, and it
    communicates the precision of an aggregate far better than a significance star.
    """
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], values[0]

    samples = samples or settings.evaluation.bootstrap_samples
    rng = random.Random(settings.evaluation.random_seed if seed is None else seed)

    n = len(values)
    means: list[float] = []
    for _ in range(samples):
        total = 0.0
        for _ in range(n):
            total += values[rng.randrange(n)]
        means.append(total / n)

    means.sort()
    tail = (1.0 - confidence) / 2.0
    return (
        means[max(0, int(tail * samples))],
        means[min(samples - 1, int((1.0 - tail) * samples))],
    )


def cohens_dz(a: list[float], b: list[float]) -> float | None:
    """Standardised effect size for paired samples: mean(Δ) / sd(Δ).

    Reported next to every p-value, because a p-value says whether a difference is
    detectable and says nothing at all about whether it is large enough to matter.
    """
    differences = [x - y for x, y in zip(a, b, strict=True)]
    if len(differences) < 2:
        return None

    mean = sum(differences) / len(differences)
    variance = sum((d - mean) ** 2 for d in differences) / (len(differences) - 1)
    deviation = math.sqrt(variance)
    return mean / deviation if deviation > 0 else None


def compare(
    a: dict[int, dict[str, float]],
    b: dict[int, dict[str, float]],
    metric_key: str,
    test: str = "permutation",
    label_a: str = "",
    label_b: str = "",
) -> ComparisonResult:
    """Compare two runs on one metric."""
    values_a, values_b, shared = paired_vectors(a, b, metric_key)

    if not values_a:
        return ComparisonResult(
            metric_key=metric_key,
            test=test,
            sample_size=0,
            mean_a=0.0,
            mean_b=0.0,
            mean_difference=0.0,
            p_value=1.0,
            label_a=label_a,
            label_b=label_b,
        )

    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    ties = sum(1 for x, y in zip(values_a, values_b, strict=True) if x == y)

    if test == "wilcoxon":
        statistic, p_value = wilcoxon_test(values_a, values_b)
    elif test == "ttest_rel":
        statistic, p_value = paired_t_test(values_a, values_b)
    else:
        _, p_value = permutation_test(values_a, values_b)
        statistic = None

    differences = [x - y for x, y in zip(values_a, values_b, strict=True)]
    ci_low, ci_high = bootstrap_interval(differences)

    return ComparisonResult(
        metric_key=metric_key,
        test=test,
        sample_size=len(shared),
        mean_a=mean_a,
        mean_b=mean_b,
        mean_difference=mean_a - mean_b,
        p_value=p_value,
        statistic=statistic,
        effect_size=cohens_dz(values_a, values_b),
        ci_low=ci_low,
        ci_high=ci_high,
        ties=ties,
        label_a=label_a,
        label_b=label_b,
    )


def holm_bonferroni(results: list[ComparisonResult]) -> list[ComparisonResult]:
    """Control the family-wise error rate across a set of comparisons.

    Five rankers make ten pairs; at α = 0.05 the chance of at least one false positive
    among ten independent tests is about 40%. Holm–Bonferroni is uniformly more powerful
    than plain Bonferroni and needs no independence assumption.

    Both the raw and the corrected p-value are kept: the corrected one is the honest basis
    for a claim, the raw one is what a reader comparing against published figures expects.
    """
    ordered = sorted(range(len(results)), key=lambda i: results[i].p_value)
    total = len(results)

    running_max = 0.0
    for rank, index in enumerate(ordered):
        adjusted = min(1.0, (total - rank) * results[index].p_value)
        # Enforce monotonicity: a corrected p-value may never fall below one already
        # assigned to a smaller raw p-value.
        running_max = max(running_max, adjusted)
        results[index].p_value_corrected = running_max
        results[index].correction = "holm-bonferroni"

    return results
