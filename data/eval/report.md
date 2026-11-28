# Evaluation report

Run: 2026-11-28 11:53 · model: openai/gpt-oss-120b · top-k: 5

| Metric | Score |
| --- | --- |
| Questions | 21 scored (6 answerable, 15 should refuse) |
| Retrieval hit@5 | 100% (6/6) |
| Retrieval MRR | 0.92 |
| Answer correct (facts + citation + language) | 17% (1/6) |
| Answered (not refused) | 33% (2/6) |
| Cites an expected source | 100% (2/2) |
| Contains all key facts | 50% (1/2) |
| Correct refusals | 93% (14/15) |

## Failures

- **rent-01** How much can my landlord ask for a deposit? - refused (the model's answer cited no passage, so it could not be verified)
- **refuse-02** What is the best neighbourhood in Berlin for students to live in? - answered but should have refused
- **anm-11** Can someone else go to the Bürgeramt to register my address for me if I have a lecture? - refused (the model's answer cited no passage, so it could not be verified)
- **bank-05** Do I need a regular German current account (Girokonto) in addition to my Sperrkonto? - refused (the model's answer cited no passage, so it could not be verified)
- **bank-07** Was passiert mit dem Restgeld auf meinem Sperrkonto, wenn ich mein Studium abbreche und Deutschland verlasse? - missing facts: Sperrfreigabe|Auslandsvertretung|Ausländerbehörde|Abmeldung
- **other-01** I got a letter from ARD ZDF Deutschlandradio Beitragsservice asking for money, even though I don't own a TV. Is this a scam? - refused (the model's answer cited no passage, so it could not be verified)
