# Frontend: the chat page

Next.js + TypeScript, exported as a static site (plain HTML/CSS/JS in `out/`) so it can be
hosted for free on GitHub Pages. It calls the Python API in the folder above.

## Run it locally

You need Node.js (LTS) and the API running (`uv run uvicorn copilot.main:app --reload` in
the project root, with Docker's database up).

```bash
cd frontend
cp .env.example .env.local   # where the API runs; the default is http://localhost:8000
npm install                  # first time only
npm run dev                  # open http://localhost:3000
```

## Checks

```bash
npm run lint        # code style and common React mistakes
npm run typecheck   # TypeScript types
npm run build       # the static site, into out/
```

## Where things are

| File | What it does |
| --- | --- |
| `src/app/page.tsx` | The chat page: input, example questions, language toggle, answers |
| `src/components/AnswerView.tsx` | One answer: `[n]` markers become links, sources become chips |
| `src/lib/api.ts` | Calls `POST /ask`; types that mirror the API's response |
| `src/lib/texts.ts` | All interface text in English and German |
