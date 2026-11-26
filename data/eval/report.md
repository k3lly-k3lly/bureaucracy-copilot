# Evaluation report

Run: 2026-11-26 11:53 · model: openai/gpt-oss-120b · top-k: 5

| Metric | Score |
| --- | --- |
| Questions | 11 scored (8 answerable, 3 should refuse) |
| Retrieval hit@5 | 50% (4/8) |
| Retrieval MRR | 0.50 |
| Answer correct (facts + citation + language) | 50% (4/8) |
| Answered (not refused) | 50% (4/8) |
| Cites an expected source | 100% (4/4) |
| Contains all key facts | 100% (4/4) |
| Correct refusals | 100% (3/3) |

## Failures

- **rent-04** What is the difference between Kaltmiete and Warmmiete? - expected source not retrieved; refused (best passage similarity 0.23 is below 0.35)
- **rent-07** What is a Schufa credit check and how am I supposed to have one if I just arrived in Germany? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **rent-08** Can I sublet my dorm room or apartment while I go home for the summer break? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **rent-11** What is a Mietpreisbremse and does it apply to furnished student rooms in Berlin? - expected source not retrieved; refused (the model said the passages do not contain the answer)
