// Shows one answer: the text with clickable [n] markers, then a chip for every source.

import type { AskResponse, Citation } from "@/lib/api";

// "https://service.berlin.de/dienstleistung/120686/" -> "service.berlin.de"
function siteName(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// Split "Within 14 days [1]. Bring your passport [2]." into text pieces and citation numbers,
// so each [n] can become a link to its source.
export function splitCitations(text: string): (string | number)[] {
  return text
    .replace(/\s+(?=\[\d+\])/g, "") // "moving in [1]" -> "moving in[1]": the chip has its own margin
    .split(/(\[\d+\])/)
    .filter((part) => part !== "")
    .map((part) => {
      const match = part.match(/^\[(\d+)\]$/);
      return match ? Number(match[1]) : part;
    });
}

function CitationMark({ citation, n }: { citation?: Citation; n: number }) {
  if (!citation) return <sup>[{n}]</sup>; // the API only returns valid ones; this is a safety net
  return (
    <a
      href={citation.url}
      target="_blank"
      rel="noopener noreferrer"
      title={citation.section || siteName(citation.url)}
      className="mx-0.5 inline-flex h-5 min-w-5 -translate-y-0.5 items-center justify-center rounded-full bg-sky-100 px-1 text-xs font-semibold text-sky-800 no-underline hover:bg-sky-200 dark:bg-sky-900 dark:text-sky-100"
    >
      {n}
    </a>
  );
}

export default function AnswerView({
  response,
  sourcesLabel,
  refusedHint,
}: {
  response: AskResponse;
  sourcesLabel: string;
  refusedHint: string;
}) {
  const byNumber = new Map(response.citations.map((c) => [c.number, c]));

  if (response.refused) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
        <p>{response.answer}</p>
        <p className="mt-2 text-sm opacity-80">{refusedHint}</p>
      </div>
    );
  }

  return (
    <div>
      <p className="leading-7 whitespace-pre-wrap">
        {splitCitations(response.answer).map((part, i) =>
          typeof part === "number" ? (
            <CitationMark key={i} n={part} citation={byNumber.get(part)} />
          ) : (
            <span key={i}>{part}</span>
          ),
        )}
      </p>

      {response.citations.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-zinc-500 uppercase">
            {sourcesLabel}
          </h3>
          <ul className="flex flex-wrap gap-2">
            {response.citations.map((c) => (
              <li key={c.number}>
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex max-w-xs items-center gap-2 rounded-full border border-zinc-300 px-3 py-1 text-sm hover:border-sky-500 hover:bg-sky-50 dark:border-zinc-700 dark:hover:bg-sky-950"
                >
                  <span className="font-semibold text-sky-700 dark:text-sky-300">{c.number}</span>
                  <span className="truncate">
                    {siteName(c.url)}
                    {c.section && <span className="text-zinc-500"> · {c.section}</span>}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
