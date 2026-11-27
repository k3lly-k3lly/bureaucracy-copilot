// Talking to the Python API. The types mirror AskResponse / CitationOut in src/copilot/main.py:
// if you change the API's response, change these too.

export type Citation = {
  number: number; // the [n] used in the answer text
  url: string;
  section: string; // heading of the passage on the source page
  text: string; // the passage itself
};

export type AskResponse = {
  answer: string;
  refused: boolean;
  citations: Citation[];
  reason: string;
};

// Why a question failed, so the page can show a helpful message in the right language.
export type AskErrorKind = "busy" | "unreachable" | "invalid" | "failed";

export class AskError extends Error {
  constructor(public kind: AskErrorKind) {
    super(kind);
  }
}

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function ask(question: string): Promise<AskResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    // No response at all: the API is not running, or (once deployed) still waking up.
    throw new AskError("unreachable");
  }
  if (response.status === 503) throw new AskError("busy"); // e.g. Groq rate limit
  if (response.status === 422) throw new AskError("invalid"); // too short / too long
  if (!response.ok) throw new AskError("failed");
  return (await response.json()) as AskResponse;
}
