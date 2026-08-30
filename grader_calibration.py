#!/usr/bin/env python3
"""
Scores the v1 keyword grader against the hand-adjudicated v2 verdicts.

The point of this file is that the model is not the thing under test here.
The grader is. Both graders' verdicts on the same 24 replies are committed in
results/, so every number below is derived from files in this repo rather than
typed into the README by hand. Re-run it and you get the table in the README.

    python3 grader_calibration.py

No network, no dependencies.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
V1 = os.path.join(HERE, "results", "reactorn_eval_results_v1.json")
V2 = os.path.join(HERE, "results", "reactorn_eval_FINAL_regraded.json")


def load(path):
    with open(path) as fh:
        return {c["id"]: c for c in json.load(fh)["results"]}


def main():
    v1, v2 = load(V1), load(V2)
    assert v1.keys() == v2.keys(), "the two runs must cover the same cases"
    n = len(v2)

    # Positive class is "this case is a real failure", because that is the
    # judgement the grader exists to make. A grader that never cries failure
    # scores well on accuracy and is worthless.
    tp = sum(1 for i in v2 if not v1[i]["passed"] and not v2[i]["passed"])
    fp = sum(1 for i in v2 if not v1[i]["passed"] and     v2[i]["passed"])
    fn = sum(1 for i in v2 if     v1[i]["passed"] and not v2[i]["passed"])
    tn = sum(1 for i in v2 if     v1[i]["passed"] and     v2[i]["passed"])

    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    agreement = (tp + tn) / n

    # Cohen's kappa. Chance agreement is high here because the classes are
    # so unbalanced, which is exactly why raw agreement flatters the grader.
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    kappa = (agreement - pe) / (1 - pe)

    print(f"v1 keyword grader judged against the hand-adjudicated v2 verdicts, n={n}")
    print('positive class = "this case is a real failure"\n')
    print(f"                      grader said FAIL   grader said PASS")
    print(f"  really a failure  {tp:>14}   {fn:>16}")
    print(f"  really fine       {fp:>14}   {tn:>16}\n")
    print(f"  raw agreement   {agreement:7.1%}   the number that looks acceptable")
    print(f"  precision       {precision:7.1%}   of everything it called a failure, this much was real")
    print(f"  recall          {recall:7.1%}")
    print(f"  Cohen's kappa   {kappa:7.3f}   corrects for the unbalanced classes\n")

    r1 = sum(c["passed"] for c in v1.values())
    r2 = sum(c["passed"] for c in v2.values())
    print(f"  score if v1 had been trusted   {r1}/{n} = {r1/n:.1%}")
    print(f"  score after reading every failing case by hand   {r2}/{n} = {r2/n:.1%}")
    print(f"  the gap is {abs(r2-r1)/n:.1%} and none of it was the model\n")

    flips = sorted(i for i in v2 if v1[i]["passed"] != v2[i]["passed"])
    print(f"cases where the two graders disagree ({len(flips)}):")
    for i in flips:
        print(f"  [{i}] {v2[i]['category']:<12} v1={'PASS' if v1[i]['passed'] else 'FAIL'}"
              f" -> v2={'PASS' if v2[i]['passed'] else 'FAIL'}")
        print(f"       {v2[i]['question']}")

    still = sorted(i for i in v2 if not v2[i]["passed"])
    print(f"\nstill failing after correction ({len(still)}): {', '.join(still) or 'none'}")


if __name__ == "__main__":
    main()
