# Evaluation report

Run: 2026-11-26 12:34 · model: openai/gpt-oss-120b · top-k: 5

| Metric | Score |
| --- | --- |
| Questions | 42 scored (39 answerable, 3 should refuse) |
| Retrieval hit@5 | 87% (34/39) |
| Retrieval MRR | 0.77 |
| Answer correct (facts + citation + language) | 64% (25/39) |
| Answered (not refused) | 72% (28/39) |
| Cites an expected source | 93% (26/28) |
| Contains all key facts | 96% (27/28) |
| Correct refusals | 100% (3/3) |

## Failures

- **rent-01** How much can my landlord ask for a deposit? - refused (the model said the passages do not contain the answer)
- **anm-11** Can someone else go to the Bürgeramt to register my address for me if I have a lecture? - refused (the model said the passages do not contain the answer)
- **anm-12** Do I need to deregister (Abmeldung) when I finish my exchange semester and leave Germany? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **anm-15** Can I book an Anmeldung appointment at any Bürgeramt in Berlin, or only the one in my district? - did not cite an expected source
- **rent-03** Can my landlord demand the entire security deposit in one lump sum before I even get the keys? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **rent-05** My landlord says I have to pay a 500 euro broker fee (Provision) to sign the contract. Is that legal? - did not cite an expected source
- **rent-07** What is a Schufa credit check and how am I supposed to have one if I just arrived in Germany? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **rent-09** How soon after moving out does my landlord have to give back my Kaution? - refused (the model said the passages do not contain the answer)
- **rent-11** What is a Mietpreisbremse and does it apply to furnished student rooms in Berlin? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **rent-12** What is a Wohnungsübergabeprotokoll and why should I fill one out on move-in day? - refused (the model said the passages do not contain the answer)
- **bank-05** Do I need a regular German current account (Girokonto) in addition to my Sperrkonto? - refused (the model said the passages do not contain the answer)
- **bank-07** Was passiert mit dem Restgeld auf meinem Sperrkonto, wenn ich mein Studium abbreche und Deutschland verlasse? - refused (the model said the passages do not contain the answer)
- **bank-08** What is the difference between a Girocard (EC-Karte) and a debit Visa or Mastercard in Germany? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **bank-09** Are there alternatives to a Sperrkonto to prove financial means for my student visa? - missing facts: scholarship|Stipendium|Verpflichtungserklärung|declaration of commitment|income
