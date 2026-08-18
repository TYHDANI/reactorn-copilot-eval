"""Re-grade the v1 replies with the corrected v2 graders. No new API calls:
identical model outputs, fixed scoring. This is the reportable number."""
import json, re, importlib.util
spec = importlib.util.spec_from_file_location("ev", "reactorn_eval.py")
ev = importlib.util.module_from_spec(spec)
import sys
sys.argv = ["x"]
# import module without running main()
src = open("reactorn_eval.py").read().replace('if __name__ == "__main__":\n    main()', '')
ns = {}
exec(compile(src, "reactorn_eval.py", "exec"), ns)
CASES = {c[0]: c for c in ns["CASES"]}

v1 = json.load(open("results/reactorn_eval_results_v1.json"))
out = []
for r in v1["results"]:
    cid = r["id"]
    _, cat, q, check, expected = CASES[cid]
    try:
        ok = bool(check(r["reply"]))
    except Exception:
        ok = False
    out.append(dict(r, passed=ok, expected=expected))

json.dump(dict(v1, results=out, grader="v2 (corrected)"), open("results/reactorn_eval_FINAL_regraded.json", "w"), indent=1)

cats = {}
for r in out:
    c = cats.setdefault(r["category"], [0, 0]); c[1] += 1
    if r["passed"]: c[0] += 1
print("REGRADED (v1 replies, v2 grader)\n" + "="*52)
for c,(p,n) in cats.items(): print(f"{c:12s} {p}/{n}   {round(100*p/n)}%")
tot = sum(1 for r in out if r["passed"])
print(f"{'TOTAL':12s} {tot}/{len(out)}   {round(100*tot/len(out))}%")
print("\nREMAINING FAILURES (genuine):")
for r in out:
    if not r["passed"]:
        print(f"\n  {r['id']} {r['category']}")
        print(f"  Q: {r['question']}")
        print(f"  expected: {r['expected']}")
        print(f"  A: {r['reply'][:260]}")
