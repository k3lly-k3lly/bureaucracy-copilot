"use client";
// "use client": this page runs in the visitor's browser (it keeps state and calls the API),
// rather than being rendered once at build time like a plain static page.

import { FormEvent, useEffect, useRef, useState } from "react";

import AnswerView from "@/components/AnswerView";
import { ask, AskError, type AskErrorKind, type AskResponse } from "@/lib/api";
import { TEXTS, type Language } from "@/lib/texts";

// One question and what happened to it. `status` says which of the other fields are set.
type Turn =
  | { id: number; question: string; status: "loading" }
  | { id: number; question: string; status: "done"; response: AskResponse }
  | { id: number; question: string; status: "error"; error: AskErrorKind };

export default function Home() {
  const [language, setLanguage] = useState<Language>("en");
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(0); // gives each question its own id
  const t = TEXTS[language];
  const busy = turns.some((turn) => turn.status === "loading");

  // Keep the newest question in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function submit(question: string) {
    question = question.trim();
    if (!question || busy) return;
    const id = nextId.current++;
    setInput("");
    setTurns((prev) => [...prev, { id, question, status: "loading" }]);

    // Replace the "loading" turn with its result (or error) when the API replies.
    const update = (next: Turn) =>
      setTurns((prev) => prev.map((turn) => (turn.id === id ? next : turn)));
    try {
      update({ id, question, status: "done", response: await ask(question) });
    } catch (err) {
      update({ id, question, status: "error", error: err instanceof AskError ? err.kind : "failed" });
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault(); // stop the browser from reloading the page
    submit(input);
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col px-4">
      <header className="flex items-center justify-between py-5">
        <h1 className="text-lg font-semibold">{t.title}</h1>
        <div className="flex rounded-full border border-zinc-300 p-0.5 text-sm dark:border-zinc-700">
          {(["en", "de"] as const).map((lang) => (
            <button
              key={lang}
              onClick={() => setLanguage(lang)}
              aria-pressed={language === lang}
              className={`rounded-full px-3 py-1 ${
                language === lang ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : ""
              }`}
            >
              {lang.toUpperCase()}
            </button>
          ))}
        </div>
      </header>

      <main className="flex-1 pb-6">
        {turns.length === 0 ? (
          // Empty screen: explain what the copilot does and offer example questions.
          <section className="pt-10 sm:pt-16">
            <p className="max-w-xl text-2xl leading-snug font-medium">{t.tagline}</p>
            <h2 className="mt-10 mb-3 text-sm text-zinc-500">{t.examplesHeading}</h2>
            <ul className="grid gap-2 sm:grid-cols-2">
              {t.examples.map((example) => (
                <li key={example}>
                  <button
                    onClick={() => submit(example)}
                    className="h-full w-full rounded-xl border border-zinc-300 p-3 text-left text-sm hover:border-sky-500 hover:bg-sky-50 dark:border-zinc-700 dark:hover:bg-sky-950"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <ol className="space-y-8 pt-4">
            {turns.map((turn) => (
              <li key={turn.id} className="space-y-3">
                <p className="ml-auto w-fit max-w-[85%] rounded-2xl bg-zinc-100 px-4 py-2 dark:bg-zinc-800">
                  {turn.question}
                </p>
                {turn.status === "loading" && (
                  <p className="animate-pulse text-zinc-500">{t.thinking}</p>
                )}
                {turn.status === "error" && (
                  <p className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100">
                    {t.errors[turn.error]}
                  </p>
                )}
                {turn.status === "done" && (
                  <AnswerView
                    response={turn.response}
                    sourcesLabel={t.sources}
                    refusedHint={t.refusedHint}
                  />
                )}
              </li>
            ))}
          </ol>
        )}
        <div ref={bottomRef} />
      </main>

      <footer className="sticky bottom-0 bg-background pt-2 pb-4">
        <form onSubmit={onSubmit} className="flex gap-2">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={t.placeholder}
            maxLength={500}
            aria-label={t.placeholder}
            className="flex-1 rounded-xl border border-zinc-300 bg-transparent px-4 py-3 outline-none focus:border-sky-500 dark:border-zinc-700"
          />
          <button
            type="submit"
            disabled={busy || input.trim().length < 3}
            className="rounded-xl bg-sky-700 px-5 font-medium text-white hover:bg-sky-800 disabled:opacity-40"
          >
            {t.send}
          </button>
        </form>
        <p className="mt-2 text-center text-xs text-zinc-500">{t.disclaimer}</p>
      </footer>
    </div>
  );
}
