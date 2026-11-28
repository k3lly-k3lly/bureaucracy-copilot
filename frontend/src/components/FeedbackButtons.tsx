"use client";
// "Was this helpful? Yes / No" under an answer. One vote per answer: after a click the buttons
// are replaced by a thank-you note, so the same answer can't be counted twice by accident.

import { useState } from "react";

import { sendFeedback, type AskResponse } from "@/lib/api";
import type { TEXTS } from "@/lib/texts";

type Status = "idle" | "sending" | "sent" | "failed";

export default function FeedbackButtons({
  question,
  response,
  texts,
}: {
  question: string;
  response: AskResponse;
  texts: (typeof TEXTS)["en"]["feedback"];
}) {
  const [status, setStatus] = useState<Status>("idle");

  async function vote(helpful: boolean) {
    setStatus("sending");
    const ok = await sendFeedback({
      helpful,
      question,
      answer: response.answer,
      refused: response.refused,
      cited_urls: response.citations.map((c) => c.url),
    });
    setStatus(ok ? "sent" : "failed");
  }

  if (status === "sent") return <p className="text-sm text-zinc-500">{texts.thanks}</p>;
  if (status === "failed") {
    return <p className="text-sm text-red-700 dark:text-red-300">{texts.failed}</p>;
  }

  const button =
    "rounded-full border border-zinc-300 px-3 py-0.5 hover:border-sky-500 hover:bg-sky-50 " +
    "disabled:opacity-40 dark:border-zinc-700 dark:hover:bg-sky-950";
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
      <span>{texts.question}</span>
      <button onClick={() => vote(true)} disabled={status === "sending"} className={button}>
        {texts.yes}
      </button>
      <button onClick={() => vote(false)} disabled={status === "sending"} className={button}>
        {texts.no}
      </button>
      <span className="text-xs text-zinc-500">{texts.privacy}</span>
    </div>
  );
}
