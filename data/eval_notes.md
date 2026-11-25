# Eval notes

Ideas for the Week 4 test set, collected while reviewing sources.

## Tricky questions (sources disagree or depend on the situation)
- "How long do I have to register my address?"
  - berlin.de: within 14 days of moving in
  - TU Berlin: 3 months if moving to Berlin from abroad
  - Correct answer depends on the situation -> must cite both and explain the condition

## Sources I removed and why
- Study preparation residence permit page: only relevant for Studienkolleg students
- German blocked account page: same content as the English version

## Questions the copilot should refuse
- (add questions here that the sources can't answer, e.g. "Which bank is best?")
- Residence Act (English, full law): 466 of 718 chunks -> removed, it drowned out everything else
- make-it-in-germany.com: Radware bot protection returned a challenge page with 200 OK
  -> removed the 3 pages; downloader now detects challenge pages instead of saving them
- Broken sentences and ** markers in extracted text -> added normalize_markdown()

## First AI answers (Nov 25)
- "How long do I have to register?" -> correct, cited TU Berlin, included 3-month rule from abroad
- "How much can my landlord ask for a deposit?" -> correct: max 3x monthly rent without utilities (BGB 551)
- "Wie hoch darf die Mietkaution sein?" -> answered in German, cited BGB 551
- "Which bank has the best student account?" -> correctly refused (not in sources)
- Lessons: Groq retired llama-3.3-70b (404) -> model is config + `copilot.models` lists options;
  DB tests wiped the dev table -> isolated per-run schema; gpt-oss citation styles -> stricter prompt + normalizer
- Known limit: keyword "Kaution" doesn't match compound "Mietkaution" (semantic search covers it)
