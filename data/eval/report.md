# Evaluation report

Run: 2026-11-25 13:52 · model: openai/gpt-oss-120b · top-k: 5

| Metric | Score |
| --- | --- |
| Questions | 14 (11 answerable, 3 should refuse) |
| Retrieval hit@5 | 100% (11/11) |
| Retrieval MRR | 0.91 |
| Answer correct (facts + citation + language) | 91% (10/11) |
| Answered (not refused) | 100% (11/11) |
| Cites an expected source | 100% (11/11) |
| Contains all key facts | 91% (10/11) |
| Correct refusals | 100% (3/3) |

## Failures

- **anm-05** I moved to Berlin from abroad. Do I also have only 14 days to register? - missing facts: three months|3 months
