// Every piece of text on the page, in English and German. The answers themselves come from
// the API, which replies in the language of the question.

import type { AskErrorKind } from "./api";

export type Language = "en" | "de";

type Texts = {
  title: string;
  tagline: string;
  placeholder: string;
  send: string;
  examplesHeading: string;
  examples: string[];
  thinking: string;
  sources: string;
  refusedHint: string;
  errors: Record<AskErrorKind, string>;
  disclaimer: string;
  feedback: {
    question: string;
    yes: string;
    no: string;
    privacy: string; // shown next to the buttons: says exactly what a click sends
    thanks: string;
    failed: string;
  };
};

export const TEXTS: Record<Language, Texts> = {
  en: {
    title: "Bureaucracy Copilot",
    tagline:
      "Questions about Anmeldung, residence permits, health insurance, renting or bank " +
      "accounts in Berlin, answered from official sources.",
    placeholder: "Ask a question…",
    send: "Ask",
    examplesHeading: "Try one of these",
    examples: [
      "How long do I have to register my address after moving in?",
      "Which documents do I need for a student residence permit?",
      "Do I need German health insurance as a student?",
      "How much can a landlord ask for as a deposit?",
    ],
    thinking: "Searching the official sources…",
    sources: "Sources",
    refusedHint: "The copilot only answers when the official sources it has cover the question.",
    errors: {
      busy: "Too many questions right now. Please wait a minute and try again.",
      unreachable:
        "Can't reach the server. It may be waking up, which takes about a minute. Please try again.",
      invalid: "Please write a question between 3 and 500 characters.",
      failed: "Something went wrong. Please try again.",
    },
    disclaimer:
      "Not legal advice. Answers can be incomplete or out of date: always check the linked " +
      "official source before you act.",
    feedback: {
      question: "Was this helpful?",
      yes: "Yes",
      no: "No",
      privacy: "Clicking sends your question and this answer, nothing else.",
      thanks: "Thanks for your feedback!",
      failed: "Couldn't send your feedback. Please try again later.",
    },
  },
  de: {
    title: "Bureaucracy Copilot",
    tagline:
      "Fragen zu Anmeldung, Aufenthaltstitel, Krankenversicherung, Miete oder Bankkonto in " +
      "Berlin, beantwortet aus offiziellen Quellen.",
    placeholder: "Stelle eine Frage…",
    send: "Fragen",
    examplesHeading: "Probier eine dieser Fragen",
    examples: [
      "Wie lange habe ich Zeit, mich nach dem Einzug anzumelden?",
      "Welche Unterlagen brauche ich für eine Aufenthaltserlaubnis zum Studium?",
      "Muss ich mich als Student in Deutschland krankenversichern?",
      "Wie hoch darf die Mietkaution sein?",
    ],
    thinking: "Durchsuche die offiziellen Quellen…",
    sources: "Quellen",
    refusedHint:
      "Der Copilot antwortet nur, wenn seine offiziellen Quellen die Frage abdecken.",
    errors: {
      busy: "Gerade kommen zu viele Fragen an. Bitte warte eine Minute und versuche es erneut.",
      unreachable:
        "Der Server ist nicht erreichbar. Vielleicht startet er gerade, das dauert etwa eine " +
        "Minute. Bitte versuche es erneut.",
      invalid: "Bitte schreibe eine Frage mit 3 bis 500 Zeichen.",
      failed: "Etwas ist schiefgelaufen. Bitte versuche es erneut.",
    },
    disclaimer:
      "Keine Rechtsberatung. Antworten können unvollständig oder veraltet sein: Prüfe immer " +
      "die verlinkte offizielle Quelle, bevor du handelst.",
    feedback: {
      question: "War das hilfreich?",
      yes: "Ja",
      no: "Nein",
      privacy: "Ein Klick sendet deine Frage und diese Antwort, sonst nichts.",
      thanks: "Danke für dein Feedback!",
      failed: "Feedback konnte nicht gesendet werden. Bitte versuche es später erneut.",
    },
  },
};
