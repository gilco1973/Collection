/** Chat modes and the page context a turn can carry (see `POST /api/chat`). */
export type ChatMode = "ask" | "explain" | "elaborate" | "quiz";

/** The page the reader is on and, when they selected some of its text, that passage. */
export interface ChatContext {
  path: string;
  title: string;
  selection?: string;
}

/** One multiple-choice question of a `quiz` answer; `answer` is the index of the correct option. */
export interface QuizQuestion {
  q: string;
  options: string[];
  answer: number;
  why: string;
}
