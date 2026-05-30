"""
GradeWise evaluation harness.

Runs a grader over a held-out dataset and produces an EvalReport: QWK against the
human-consensus score, the human-vs-human QWK ceiling, per-criterion accuracy,
tier distribution, latency percentiles, and cost. `compare()` prints an ablation
table across named variants so architecture changes are decided by numbers, not taste.

The grader is injected, so the same harness evaluates the current system, a stub, or
any tier of the new routing ladder.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol, Sequence

from metrics import (
    cohen_kappa,
    percentile,
    per_criterion_accuracy,
    qwk,
    score_to_rating,
)


# --------------------------------------------------------------------------- #
# Data contracts
# --------------------------------------------------------------------------- #

@dataclass
class EvalItem:
    """One held-out grading case with trusted human scores."""
    submission_id: str
    assignment_id: str
    submission_path: str          # path the grader will ingest
    max_score: float
    human_scores: list[float]     # >=2 graders enables the human-vs-human ceiling
    gold_per_criterion: dict[str, float] = field(default_factory=dict)
    reference_text: str | None = None   # optional, for feedback-faithfulness


@dataclass
class GraderOutput:
    """What a grader must return. Maps onto GradingResult in the main app."""
    score: float
    per_criterion: Mapping[str, float] = field(default_factory=dict)
    feedback: str = ""
    tier_used: str = "unknown"
    cost_usd: float = 0.0


class Grader(Protocol):
    def __call__(self, item: EvalItem) -> GraderOutput: ...


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

@dataclass
class EvalReport:
    name: str
    n_items: int
    n_levels: int
    qwk_ai_vs_human: float
    qwk_human_ceiling: float | None      # None if <2 graders per item
    cohen_kappa_ai_vs_human: float
    per_criterion: dict[str, dict[str, float]]
    tier_distribution: dict[str, int]
    latency_p50_ms: float
    latency_p95_ms: float
    avg_cost_usd: float
    total_cost_usd: float
    faithfulness: float | None = None    # filled separately if a judge is run

    def summary(self) -> str:
        lines = [
            f"=== Eval Report: {self.name} ===",
            f"  items                 : {self.n_items}  (rating levels: {self.n_levels})",
            f"  QWK (AI vs human)     : {self.qwk_ai_vs_human:.4f}",
        ]
        if self.qwk_human_ceiling is not None:
            gap = self.qwk_human_ceiling - self.qwk_ai_vs_human
            lines.append(
                f"  QWK human ceiling     : {self.qwk_human_ceiling:.4f}  "
                f"(gap to ceiling: {gap:+.4f})"
            )
        lines += [
            f"  Cohen kappa (AI/human): {self.cohen_kappa_ai_vs_human:.4f}",
            f"  latency p50 / p95     : {self.latency_p50_ms:.0f} ms / {self.latency_p95_ms:.0f} ms",
            f"  cost avg / total      : ${self.avg_cost_usd:.4f} / ${self.total_cost_usd:.4f}",
            f"  tier distribution     : {dict(self.tier_distribution)}",
        ]
        if self.faithfulness is not None:
            lines.append(f"  feedback faithfulness : {self.faithfulness:.3f}")
        if self.per_criterion:
            lines.append("  per-criterion (mae / within_tol / n):")
            for cid, m in sorted(self.per_criterion.items()):
                lines.append(
                    f"    - {cid:<24} mae={m['mae']:.3f}  "
                    f"within_tol={m['within_tol']:.2f}  n={int(m['n'])}"
                )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Core runner
# --------------------------------------------------------------------------- #

def _consensus_rating(human_scores: Sequence[float], max_score: float, n_levels: int) -> int:
    """Human-consensus = rounded mean of grader scores, binned to a rating."""
    mean = sum(human_scores) / len(human_scores)
    return score_to_rating(mean, max_score, n_levels)


def _human_ceiling_qwk(
    items: Sequence[EvalItem], n_levels: int
) -> float | None:
    """
    QWK between the first two human graders across items that have >=2 graders.
    This is the realistic upper bound: the AI should not be expected to beat the
    agreement two humans achieve with each other.
    """
    pairs = [it for it in items if len(it.human_scores) >= 2]
    if not pairs:
        return None
    g1 = [score_to_rating(it.human_scores[0], it.max_score, n_levels) for it in pairs]
    g2 = [score_to_rating(it.human_scores[1], it.max_score, n_levels) for it in pairs]
    return qwk(g1, g2, min_rating=0, max_rating=n_levels - 1)


def run_eval(
    grader: Grader,
    dataset: Sequence[EvalItem],
    name: str = "variant",
    n_levels: int = 11,
) -> EvalReport:
    """
    Run `grader` over `dataset` and produce an EvalReport.

    `n_levels` is the number of ordinal rating bins used for QWK (default 11 -> a
    0..10 scale). Pick the granularity that matches how your rubrics actually score.
    """
    if not dataset:
        raise ValueError("dataset is empty")

    ai_ratings: list[int] = []
    human_ratings: list[int] = []
    pred_criteria: list[dict[str, float]] = []
    gold_criteria: list[dict[str, float]] = []
    latencies_ms: list[float] = []
    costs: list[float] = []
    tier_counts: dict[str, int] = {}

    for item in dataset:
        t0 = time.perf_counter()
        out = grader(item)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        ai_ratings.append(score_to_rating(out.score, item.max_score, n_levels))
        human_ratings.append(_consensus_rating(item.human_scores, item.max_score, n_levels))

        pred_criteria.append(dict(out.per_criterion))
        gold_criteria.append(dict(item.gold_per_criterion))

        costs.append(out.cost_usd)
        tier_counts[out.tier_used] = tier_counts.get(out.tier_used, 0) + 1

    report = EvalReport(
        name=name,
        n_items=len(dataset),
        n_levels=n_levels,
        qwk_ai_vs_human=qwk(human_ratings, ai_ratings, min_rating=0, max_rating=n_levels - 1),
        qwk_human_ceiling=_human_ceiling_qwk(dataset, n_levels),
        cohen_kappa_ai_vs_human=cohen_kappa(human_ratings, ai_ratings),
        per_criterion=per_criterion_accuracy(pred_criteria, gold_criteria),
        tier_distribution=tier_counts,
        latency_p50_ms=percentile(latencies_ms, 50),
        latency_p95_ms=percentile(latencies_ms, 95),
        avg_cost_usd=sum(costs) / len(costs) if costs else 0.0,
        total_cost_usd=sum(costs),
    )
    return report


# --------------------------------------------------------------------------- #
# Ablation comparison
# --------------------------------------------------------------------------- #

def compare(reports: Mapping[str, EvalReport]) -> str:
    """
    Print an ablation table across named variants. Use this to decide whether a
    change ships: a change is accepted only if QWK improves, or holds while
    improving latency/cost.
    """
    header = (
        f"{'variant':<22} {'QWK':>8} {'ceiling':>9} {'p50ms':>8} "
        f"{'p95ms':>8} {'$avg':>9}"
    )
    sep = "-" * len(header)
    rows = [header, sep]
    for name, r in reports.items():
        ceiling = f"{r.qwk_human_ceiling:.4f}" if r.qwk_human_ceiling is not None else "  n/a "
        rows.append(
            f"{name:<22} {r.qwk_ai_vs_human:>8.4f} {ceiling:>9} "
            f"{r.latency_p50_ms:>8.0f} {r.latency_p95_ms:>8.0f} {r.avg_cost_usd:>9.4f}"
        )
    return "\n".join(rows)


# --------------------------------------------------------------------------- #
# Demo / smoke test: proves the plumbing with a random-score stub grader.
# Run:  python harness.py
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import random

    random.seed(7)

    # Synthetic held-out set: 40 submissions, scored out of 10 by 2 human graders.
    demo: list[EvalItem] = []
    for i in range(40):
        true_quality = random.uniform(0, 10)
        # Two humans who mostly agree (small noise)
        h1 = max(0, min(10, true_quality + random.uniform(-1, 1)))
        h2 = max(0, min(10, true_quality + random.uniform(-1, 1)))
        demo.append(
            EvalItem(
                submission_id=f"sub_{i}",
                assignment_id="assign_demo",
                submission_path=f"/fake/sub_{i}.pdf",
                max_score=10.0,
                human_scores=[h1, h2],
                gold_per_criterion={"c1": round(true_quality / 2, 1),
                                    "c2": round(true_quality / 2, 1)},
            )
        )

    def stub_grader(item: EvalItem) -> GraderOutput:
        """Stand-in grader: noisy approximation of the human consensus."""
        consensus = sum(item.human_scores) / len(item.human_scores)
        noisy = max(0, min(10, consensus + random.uniform(-2, 2)))
        return GraderOutput(
            score=noisy,
            per_criterion={"c1": round(noisy / 2, 1), "c2": round(noisy / 2, 1)},
            feedback="stub feedback",
            tier_used=random.choice(["tier0_context", "tier1_tree", "tier2_vector"]),
            cost_usd=random.uniform(0.001, 0.01),
        )

    def random_grader(item: EvalItem) -> GraderOutput:
        """Pure-random baseline: should land near QWK 0 (chance)."""
        s = random.uniform(0, 10)
        return GraderOutput(score=s, tier_used="tier0_context", cost_usd=0.002)

    r_stub = run_eval(stub_grader, demo, name="stub_grader", n_levels=11)
    r_rand = run_eval(random_grader, demo, name="random_baseline", n_levels=11)

    print(r_stub.summary())
    print()
    print(r_rand.summary())
    print()
    print(compare({"stub_grader": r_stub, "random_baseline": r_rand}))
