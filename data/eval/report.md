# Evaluation report

Run: 2026-11-25 13:45 · model: openai/gpt-oss-120b · top-k: 5

| Metric | Score |
| --- | --- |
| Questions | 14 (11 answerable, 3 should refuse) |
| Retrieval hit@5 | 100% (11/11) |
| Retrieval MRR | 0.86 |
| Answer correct (facts + citation + language) | 55% (6/11) |
| Answered (not refused) | 100% (11/11) |
| Cites an expected source | 91% (10/11) |
| Contains all key facts | 73% (8/11) |
| Correct refusals | 100% (3/3) |

## Failures

- **anm-03** What is the Wohnungsgeberbestätigung and who gives it to me? - answered in the wrong language
- **anm-04** Innerhalb welcher Frist muss ich mich nach dem Einzug anmelden? - missing facts: zwei Wochen|14 Tage|14 Tagen
- **bank-02** Does a bank have to give me a basic account if I just arrived in Germany? - answered in the wrong language
- **health-01** Do I need health insurance to enrol at a German university? - missing facts: health insurance|Krankenversicherung
- **res-01** Where do I apply for a residence permit for studying in Berlin? - missing facts: Immigration Office|Landesamt|LEA|Einwanderung; did not cite an expected source
