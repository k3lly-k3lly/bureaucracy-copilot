# Evaluation report

Run: 2026-11-27 13:10 · model: openai/gpt-oss-120b · top-k: 5

| Metric | Score |
| --- | --- |
| Questions | 74 scored (59 answerable, 15 should refuse) |
| Retrieval hit@5 | 88% (52/59) |
| Retrieval MRR | 0.80 |
| Answer correct (facts + citation + language) | 63% (37/59) |
| Answered (not refused) | 80% (47/59) |
| Cites an expected source | 85% (40/47) |
| Contains all key facts | 94% (44/47) |
| Correct refusals | 100% (15/15) |

## Failures

- **rent-01** How much can my landlord ask for a deposit? - refused (the model said the passages do not contain the answer)
- **health-01** Do I need health insurance to enrol at a German university? - did not cite an expected source
- **anm-11** Can someone else go to the Bürgeramt to register my address for me if I have a lecture? - refused (the model said the passages do not contain the answer)
- **anm-12** Do I need to deregister (Abmeldung) when I finish my exchange semester and leave Germany? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **anm-15** Can I book an Anmeldung appointment at any Bürgeramt in Berlin, or only the one in my district? - did not cite an expected source
- **rent-03** Can my landlord demand the entire security deposit in one lump sum before I even get the keys? - expected source not retrieved; did not cite an expected source
- **rent-05** My landlord says I have to pay a 500 euro broker fee (Provision) to sign the contract. Is that legal? - did not cite an expected source
- **rent-07** What is a Schufa credit check and how am I supposed to have one if I just arrived in Germany? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **rent-09** How soon after moving out does my landlord have to give back my Kaution? - missing facts: months|Monate|Nebenkosten|operating costs
- **rent-11** What is a Mietpreisbremse and does it apply to furnished student rooms in Berlin? - expected source not retrieved; did not cite an expected source
- **rent-12** What is a Wohnungsübergabeprotokoll and why should I fill one out on move-in day? - refused (the model said the passages do not contain the answer)
- **bank-05** Do I need a regular German current account (Girokonto) in addition to my Sperrkonto? - refused (the model said the passages do not contain the answer)
- **bank-07** Was passiert mit dem Restgeld auf meinem Sperrkonto, wenn ich mein Studium abbreche und Deutschland verlasse? - refused (the model said the passages do not contain the answer)
- **bank-08** What is the difference between a Girocard (EC-Karte) and a debit Visa or Mastercard in Germany? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **bank-09** Are there alternatives to a Sperrkonto to prove financial means for my student visa? - missing facts: scholarship|Stipendium|Verpflichtungserklärung|declaration of commitment|income
- **health-02** I am from an EU country and have a European Health Insurance Card (EHIC). Do I still need German student health insurance? - did not cite an expected source
- **health-06** I am doing a preparatory language course (Studienkolleg) before my degree. Can I get the cheap public student rate? - refused (the model said the passages do not contain the answer)
- **health-10** What is the electronic student notification procedure (M10) for health insurance? - refused (the model said the passages do not contain the answer)
- **res-03** My national entry visa expires in two weeks, and my LEA appointment isn't for three months. Will I be here illegally? - expected source not retrieved; did not cite an expected source
- **res-07** Can I work as a freelancer or self-employed tutor on a student residence permit? - missing facts: permission|approval|Erlaubnis|self-employed|selbstständig
- **res-10** Do I need to show proof of German language skills if my Master's program in Berlin is taught 100% in English? - expected source not retrieved; refused (the model said the passages do not contain the answer)
- **other-01** I got a letter from ARD ZDF Deutschlandradio Beitragsservice asking for money, even though I don't own a TV. Is this a scam? - refused (the model said the passages do not contain the answer)
