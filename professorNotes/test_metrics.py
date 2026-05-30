"""
Tests for GradeWise metrics. Run:  python test_metrics.py

Includes a hand-computed QWK example (worked out by hand to 0.6875) so the kappa
math is verifiable without any external dependency. If scikit-learn is installed,
an extra cross-check asserts equivalence with sklearn's quadratic-weighted kappa.
"""

from metrics import (
    cohen_kappa,
    per_criterion_accuracy,
    percentile,
    quadratic_weighted_kappa,
    qwk,
    score_to_rating,
)


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_qwk_perfect_agreement():
    y = [0, 1, 2, 3, 4, 2, 1]
    assert approx(qwk(y, y), 1.0), "identical ratings must give QWK 1.0"


def test_qwk_hand_computed():
    # Worked by hand: O, weights, expected matrix -> kappa = 1 - 0.5/1.6 = 0.6875
    y_true = [0, 1, 2, 2, 1]
    y_pred = [0, 1, 1, 2, 0]
    val = quadratic_weighted_kappa(y_true, y_pred, min_rating=0, max_rating=2)
    assert approx(val, 0.6875, tol=1e-9), f"expected 0.6875, got {val}"


def test_qwk_single_class():
    # Everyone gets the same rating -> defined as perfect agreement.
    assert approx(qwk([3, 3, 3], [3, 3, 3]), 1.0)


def test_qwk_symmetry():
    a = [0, 1, 2, 2, 1]
    b = [0, 1, 1, 2, 0]
    assert approx(qwk(a, b, 0, 2), qwk(b, a, 0, 2)), "QWK must be symmetric"


def test_cohen_kappa_perfect_and_chance():
    assert approx(cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]), 1.0)
    # Total disagreement on a balanced binary set -> negative kappa
    assert cohen_kappa([1, 1, 0, 0], [0, 0, 1, 1]) < 0


def test_score_to_rating():
    assert score_to_rating(0, 10, 11) == 0
    assert score_to_rating(10, 10, 11) == 10
    assert score_to_rating(7.5, 10, 11) == 8
    # clamping
    assert score_to_rating(-5, 10, 11) == 0
    assert score_to_rating(99, 10, 11) == 10


def test_per_criterion_accuracy():
    pred = [{"c1": 5.0, "c2": 3.0}, {"c1": 4.0, "c2": 2.0}]
    gold = [{"c1": 5.0, "c2": 4.0}, {"c1": 4.0, "c2": 2.0}]
    res = per_criterion_accuracy(pred, gold, tolerance=0.0)
    assert res["c1"]["mae"] == 0.0
    assert res["c1"]["within_tol"] == 1.0
    assert res["c2"]["mae"] == 0.5            # errors 1.0 and 0.0 -> mean 0.5
    assert res["c2"]["within_tol"] == 0.5     # one exact, one off


def test_percentile():
    data = [10, 20, 30, 40, 50]
    assert approx(percentile(data, 50), 30)
    assert approx(percentile(data, 0), 10)
    assert approx(percentile(data, 100), 50)


def test_sklearn_equivalence_if_available():
    try:
        from sklearn.metrics import cohen_kappa_score
    except ImportError:
        print("  (sklearn not installed -- skipping cross-check)")
        return
    import random
    random.seed(1)
    y_true = [random.randint(0, 5) for _ in range(200)]
    y_pred = [random.randint(0, 5) for _ in range(200)]
    ours = quadratic_weighted_kappa(y_true, y_pred, 0, 5)
    theirs = cohen_kappa_score(y_true, y_pred, weights="quadratic")
    assert approx(ours, theirs, tol=1e-9), f"ours={ours} sklearn={theirs}"
    print("  (sklearn cross-check passed)")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} tests passed.")
