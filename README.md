# Reactor N copilot eval. 23 of 24, and my grader was wrong before my model was.

An evaluation harness for the copilot on [Reactor N Intelligence](https://reactorn.com/intelligence), a free site I built that publishes US nuclear power purchase agreement pricing. You can ask the copilot about the Q2 2026 deal ledger (17 deals) and it answers from that ledger. This repo is the whole eval, including the raw responses and the part where I got the number wrong on the first pass.

**Score. 23 of 24 (96%).** One real defect (aggregation over the ledger). Three of the first run's five "failures" were my grader, not the model.

| Behavior | What the system prompt says | Score |
|---|---|---|
| Grounded retrieval | Be concrete, quote deals and $/MWh from the ledger | 7/8 |
| Refuses to invent deals | If a deal is not in the ledger, say so | 5/5 |
| Never sells anything | Never quote a price for access, no demos, no calls | 4/4 |
| Refuses legal advice | Recommend counsel | 3/3 |
| Handles undisclosed pricing | Say it is undisclosed, cite third party ranges | 4/4 |
| **Total** | | **23/24** |

## What was tested

Target is the live endpoint `POST https://reactorn.com/api/intel/chat`. Model behind it is Llama 3.3 70B on Groq with the deal ledger injected into the system prompt. That system prompt states five rules, listed in the table above. Every case asserts one of those rules, so nothing is graded on tone or taste. A failure is a real defect.

24 cases, five behaviors. Ground truth for the factual half comes straight from `deals.json`, the same file the site serves publicly, so anyone can check the expected answers.

## Files

| File | What it is |
|---|---|
| `reactorn_eval.py` | The harness. 24 cases, graders, pacing at 8 requests per minute |
| `regrade.py` | Re-scores saved replies with the corrected grader, no new API calls |
| `grader_calibration.py` | Scores the v1 grader against the v2 verdicts. Generates the confusion matrix and kappa below |
| `deals.json` | Snapshot of the public ledger the copilot is grounded on (ground truth) |
| `results/reactorn_eval_results_v1.json` | First run. Every question, every full reply, v1 grader verdicts (19/24) |
| `results/reactorn_eval_FINAL_regraded.json` | Same replies, corrected grader (23/24). This is the reported number |

## The one real failure

Asked for the largest deal by megawatts, the copilot answered Meta and Vistra at 2,609 MW. The largest is Switch and Oklo at 12,000 MW. Under the charitable reading (exclude watch list entries) it is Meta and TerraPower at 2,760 MW. Either way, not 2,609.

Point retrieval is strong. Ask about a named deal and it returns the deal ID, counterparty, MW, price band and term. Aggregation is weak. A superlative that requires comparing all 17 records at once gets answered from whatever is most salient. That is not a model problem to prompt around. Superlatives should be computed from the ledger in code and handed to the model. That fix is queued and, as of this writing, not yet deployed.

## The part worth writing down

The first run scored 79%, not 96%. Five cases failed. I read all five before reporting anything, and three of the five were the grader.

The refusal check looked for phrases like "not in the ledger." The model said "There is no Apple nuclear PPA in the Q2 2026 NPPI deal ledger." Correct refusal, scored as a failure because the regex did not cover that phrasing. Same for undisclosed pricing. The model said "no public strike price disclosed" and the pattern wanted "not disclosed."

A fourth case was graded too strictly. Asked what the AWS Susquehanna deal is priced at, I expected the $85 to $95 band. The model back calculated roughly $89.50 per MWh from the disclosed $1.4B annual payment and showed its work. That is inside the band and arguably a better answer than the one I wanted. The v2 grader accepts any figure inside the band.

Keyword graders fail in one direction. They under count correct refusals, because there are many ways to say no and only a few of them are in your regex. Had I trusted the harness and shipped the first number, I would have published 79% for a system doing its job and gone off to fix three things that were not broken.

The grader needs an eval as much as the model does. Every failing case gets read by a person before it counts.

## Putting a number on how wrong the grader was

Reading the failures by hand is what caught it. But "read everything by hand" does not scale past
24 cases, so the useful question is which metric would have caught it without me. Both graders'
verdicts on the same 24 replies are committed in `results/`, so that is checkable. Run
`python3 grader_calibration.py`.

Scoring the v1 grader against the hand adjudicated verdicts, with "this case is a real failure" as
the positive class, because that is the only judgement the grader exists to make.

|                    | grader said FAIL | grader said PASS |
|---|---|---|
| **really a failure** | 1 | 0 |
| **really fine**      | 4 | 19 |

| Metric | Value | |
|---|---|---|
| raw agreement | 83.3% | the number that looks acceptable |
| precision | 20.0% | of everything it called a failure, this much was real |
| recall | 100.0% | |
| Cohen's kappa | 0.284 | corrects for the unbalanced classes |

Raw agreement says the grader is broadly fine. It is not. Of the five cases it called failures,
four were fabricated. Accuracy hides this because the classes are lopsided, 23 of 24 cases really
do pass, so a grader can agree with the truth 83% of the time while being wrong about almost
everything it actually flags. Kappa corrects for that and lands at 0.284, which is poor.

Precision and kappa would have caught this. Accuracy would not. That is the whole argument for
validating a grader against human labels before trusting a single number it produces, and it is
the reason the headline here is 96% and not 79%.

Worth saying plainly. n is 24, I was the only person labelling, kappa on 24 cases is noisy, and I
am the one who both wrote the bad grader and adjudicated it. A second labeller would make this
stronger. The direction of the finding is not in doubt though, because the four disagreements are
all the same failure mode and each one is reproducible from the committed replies.


## One more piece of honesty

I tried to re run the whole suite with the corrected grader for a clean fresh number. It failed. 23 of 24 calls came back as upstream errors because I had pushed about fifty queries through a free tier in a few minutes and hit the rate limit. So the reported number is the first run's replies, re scored with the corrected grader. Same model outputs, fixed scoring, no new calls. `regrade.py` is that step and it is reproducible from the files here.

## Reproduce

```
python3 grader_calibration.py # score the grader itself against the hand adjudicated verdicts
python3 regrade.py            # re-score the saved v1 replies with the v2 grader, no network
python3 reactorn_eval.py      # fresh run against the live endpoint, ~4 minutes, paced to 8 req/min
```

Do not run the live suite twice in one sitting. The endpoint sits on a free tier and rate limits.

## Related

I did the same thing earlier this year with a cryptographic inventory scanner I built, benchmarked against a free open source tool. [It came second.](https://ciphermnews.substack.com/p/i-built-a-benchmark-for-cryptographic) An AI product with no published accuracy number is asking you to take its word for it. Here is mine.

Tyh McLean, Brooklyn. [cipherm.io](https://cipherm.io) · [linkedin.com/in/tyh-mclean-91b611199](https://www.linkedin.com/in/tyh-mclean-91b611199/)
