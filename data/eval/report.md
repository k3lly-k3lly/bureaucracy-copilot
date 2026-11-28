# Evaluation report

Run: 2026-11-28 12:02 · model: openai/gpt-oss-120b · top-k: 5

| Metric | Score |
| --- | --- |
| Questions | 6 scored (2 answerable, 4 should refuse) |
| Retrieval hit@5 | 100% (2/2) |
| Retrieval MRR | 0.75 |
| Answer correct (facts + citation + language) | 0% (0/2) |
| Answered (not refused) | 0% (0/2) |
| Cites an expected source | n/a |
| Contains all key facts | n/a |
| Correct refusals | 100% (4/4) |

## Failures

- **bank-07** Was passiert mit dem Restgeld auf meinem Sperrkonto, wenn ich mein Studium abbreche und Deutschland verlasse? - refused (the model said the passages do not contain the answer)
- **other-01** I got a letter from ARD ZDF Deutschlandradio Beitragsservice asking for money, even though I don't own a TV. Is this a scam? - refused (the model said the passages do not contain the answer)
