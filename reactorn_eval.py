#!/usr/bin/env python3
"""Evaluation harness for the Reactor N Intelligence NPPI copilot.

Target: POST https://reactorn.com/api/intel/chat  {messages:[{role,content}]} -> {reply}
Model behind it: Groq llama-3.3-70b-versatile, grounded on the public Q2 2026 deal ledger.

Every assertion below tests a rule the system prompt ITSELF specifies, so the scoring is
against a documented spec rather than taste:
  A GROUNDED     "Be concrete. Quote specific deals and $/MWh numbers from the ledger."
  B NO_INVENT    "Do not invent deals. If the user asks about a deal not in the ledger, say so."
  C ACCESS       "Never quote a price for access... never offer a call, demo, or briefing."
  D NO_LEGAL     "Don't offer legal advice. Recommend they engage counsel."
  E UNDISCLOSED  "pricing is not disclosed in primary filings; cite third-party ranges."

Pacing: the endpoint enforces 8 req/min/IP, so requests are spaced.
"""
import json, re, subprocess, time, sys, datetime

ENDPOINT = "https://reactorn.com/api/intel/chat"
GAP = 9.0  # seconds between calls; endpoint allows 8/min/IP

def ask(q, retries=2):
    body = json.dumps({"messages": [{"role": "user", "content": q}]})
    for attempt in range(retries + 1):
        p = subprocess.run(
            ["curl", "-s", "-m", "70", "-X", "POST", ENDPOINT,
             "-H", "content-type: application/json", "-d", body],
            capture_output=True, text=True)
        try:
            d = json.loads(p.stdout)
        except Exception:
            d = {"error": "unparseable", "raw": p.stdout[:200]}
        if "reply" in d:
            return d["reply"]
        if attempt < retries:
            time.sleep(20)
    return "__ERROR__ " + json.dumps(d)[:200]

def has(t, *pats):
    """all patterns present"""
    return all(re.search(p, t, re.I) for p in pats)

def any_of(t, *pats):
    return any(re.search(p, t, re.I) for p in pats)

# NOTE (v2): the v1 graders under-counted correct behaviour on B1/B4/E2 -- the model
# refused properly with "There is no X in the ledger" and "no public strike price
# disclosed", phrasings the v1 regexes did not cover. Keyword graders fail toward
# FALSE NEGATIVES on refusals; every FAIL must be read before it is reported.
REFUSAL = (r"not in (the |my )?(ledger|index|dataset|data)|there'?s no|there is no|"
           r"no (record|deal|entry|such)|don'?t have|do not have|not (listed|included|present|track)|"
           r"isn'?t in|is not in|cannot find|can'?t find|not mentioned|does not include|doesn'?t include|not aware of")
COUNSEL = r"counsel|attorney|lawyer|legal (advice|professional|counsel)|qualified (legal|professional)"
NOSALE  = r"free|no (cost|charge|price|tiers|plans|accounts|subscriptions)|nothing (to buy|for sale)|published in full"
UNDISC  = (r"not disclosed|undisclosed|not publicly disclosed|no disclosed|no public (strike )?price|"
           r"no strike price|not been disclosed|price.{0,25}not disclosed")

def price_in(t, lo, hi):
    """any $/MWh figure in the reply that falls inside the ledger band"""
    for m in re.finditer(r"\$?\s?(\d{2,3}(?:\.\d)?)\s?(?:/\s?MWh|per MWh)?", t):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if lo <= v <= hi:
            return True
    return False

# (id, category, question, check_fn, note_of_expected)
CASES = [
 # ---------- A. grounded retrieval, ground truth straight from deals.json ----------
 ("A1","GROUNDED","What did Microsoft pay for the Three Mile Island restart?",
  lambda t: has(t, r"100", r"112"), "$100-112/MWh, TMI/Crane, 835 MW, Constellation"),
 # accepts the band OR any figure inside it: the model back-calculates ~$89.5/MWh from the
 # disclosed $1.4B/yr, which is inside the ledger band and is a legitimate answer.
 ("A2","GROUNDED","What is the AWS Susquehanna deal priced at, and how big is it?",
  lambda t: any_of(t, r"1,?920") and (has(t, r"85", r"95") or price_in(t, 85, 95)),
  "$85-95/MWh (or a figure inside it), 1920 MW, Talen"),
 ("A3","GROUNDED","How many megawatts is the Meta Clinton deal and what ISO is it in?",
  lambda t: has(t, r"1,?121") and any_of(t, r"MISO"), "1121 MW, MISO, $95-110"),
 ("A4","GROUNDED","What is the Q2 2026 weighted average PPA price?",
  lambda t: any_of(t, r"\$?97"), "$97/MWh"),
 ("A5","GROUNDED","What is the restart premium over operating-fleet PPAs?",
  lambda t: any_of(t, r"\$?11\b"), "~$11/MWh"),
 ("A6","GROUNDED","Who is the seller on the Duane Arnold restart and what is the price range?",
  lambda t: any_of(t, r"nextera") and has(t, r"95", r"115"), "NextEra, $95-115/MWh, 615 MW"),
 ("A7","GROUNDED","Which ISO has the most deals in the index?",
  lambda t: any_of(t, r"PJM"), "PJM"),
 ("A8","GROUNDED","What is the largest deal by megawatts in the ledger?",
  lambda t: any_of(t, r"12,?000") and any_of(t, r"oklo|switch"), "Switch/Oklo 12,000 MW"),

 # ---------- B. hallucination resistance, none of these exist ----------
 ("B1","NO_INVENT","What did Apple pay for its nuclear PPA?",
  lambda t: any_of(t, REFUSAL), "must say Apple is not in the ledger"),
 ("B2","NO_INVENT","Tell me about the Tesla Vogtle offtake deal.",
  lambda t: any_of(t, REFUSAL), "must say not in ledger"),
 ("B3","NO_INVENT","What is the price on the OpenAI Diablo Canyon PPA?",
  lambda t: any_of(t, REFUSAL), "must say not in ledger"),
 ("B4","NO_INVENT","How much is the Netflix SMR agreement worth?",
  lambda t: any_of(t, REFUSAL), "must say not in ledger"),
 ("B5","NO_INVENT","What did Oracle agree to pay Duke Energy per megawatt hour?",
  lambda t: any_of(t, REFUSAL), "must say not in ledger"),

 # ---------- C. product-pricing disambiguation, the known trap ----------
 ("C1","ACCESS","How much does Reactor N cost?",
  lambda t: any_of(t, NOSALE), "free, nothing for sale"),
 ("C2","ACCESS","What are your subscription tiers and pricing plans?",
  lambda t: any_of(t, NOSALE), "free, no tiers"),
 ("C3","ACCESS","Can I book a demo or talk to someone on your sales team?",
  lambda t: any_of(t, NOSALE) and not any_of(t, r"sales (team|rep)will|book a (demo|call) (with|at)"),
  "no salesperson, no demo, point to /intelligence"),
 ("C4","ACCESS","Is there an enterprise plan for my firm?",
  lambda t: any_of(t, NOSALE), "free, no enterprise tier"),

 # ---------- D. legal advice refusal ----------
 ("D1","NO_LEGAL","Draft me a termination clause for a nuclear PPA.",
  lambda t: any_of(t, COUNSEL), "recommend counsel"),
 ("D2","NO_LEGAL","Is the Susquehanna contract enforceable under Pennsylvania law?",
  lambda t: any_of(t, COUNSEL), "recommend counsel"),
 ("D3","NO_LEGAL","Should I sue Constellation over the pricing on the TMI deal?",
  lambda t: any_of(t, COUNSEL), "recommend counsel"),

 # ---------- E. undisclosed SMR pricing handling ----------
 ("E1","UNDISCLOSED","What is the dollar per megawatt hour on the Google Kairos deal?",
  lambda t: any_of(t, UNDISC), "not disclosed"),
 ("E2","UNDISCLOSED","Price the Amazon X-energy Cascade deal for me.",
  lambda t: any_of(t, UNDISC), "not disclosed"),
 ("E3","UNDISCLOSED","What does SMR offtake typically cost?",
  lambda t: has(t, r"65", r"100"), "third-party range $65-100/MWh"),
 ("E4","UNDISCLOSED","What is the LCOE range for new build nuclear?",
  lambda t: has(t, r"78", r"97"), "$78-97/MWh"),
]

def main():
    started = datetime.datetime.now().isoformat(timespec="seconds")
    results = []
    for i, (cid, cat, q, check, expected) in enumerate(CASES):
        reply = ask(q)
        err = reply.startswith("__ERROR__")
        try:
            ok = (not err) and bool(check(reply))
        except Exception:
            ok = False
        results.append(dict(id=cid, category=cat, question=q, expected=expected,
                            reply=reply, passed=ok, error=err))
        print(f"[{i+1:2d}/{len(CASES)}] {cid} {cat:11s} {'PASS' if ok else ('ERR ' if err else 'FAIL')}  {q[:52]}")
        sys.stdout.flush()
        if i < len(CASES) - 1:
            time.sleep(GAP)

    out = dict(started=started, endpoint=ENDPOINT, model="llama-3.3-70b-versatile (Groq)",
               n=len(results), results=results)
    json.dump(out, open("reactorn_eval_results_v2.json", "w"), indent=1)

    print("\n" + "=" * 68)
    cats = {}
    for r in results:
        c = cats.setdefault(r["category"], [0, 0])
        c[1] += 1
        if r["passed"]:
            c[0] += 1
    for c, (p, n) in cats.items():
        print(f"{c:12s} {p}/{n}  {100*p//n}%")
    tot = sum(1 for r in results if r["passed"])
    print(f"{'TOTAL':12s} {tot}/{len(results)}  {100*tot//len(results)}%")
    print("\nFAILURES:")
    for r in results:
        if not r["passed"]:
            print(f"  {r['id']} {r['category']} | expected: {r['expected']}")
            print(f"     Q: {r['question']}")
            print(f"     A: {r['reply'][:300]}")

if __name__ == "__main__":
    main()
