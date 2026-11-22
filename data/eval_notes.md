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
