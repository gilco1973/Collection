# Security review sheet: Chat widget, selection toolbar, quizzes, typewriter and voice input

| | |
| --- | --- |
| Module id | `web-chat-voice` |
| Kind | frontend |
| Code | `web/src/components/ChatWidget.tsx`, `ChatParts.tsx`, `QuizCard.tsx`, `SelectionToolbar.tsx`, `web/src/chatBus.ts`, `TypewriterText.tsx`, `VoiceInputButton.tsx`, `web/src/useVoiceInput.ts`, `web/src/speech.d.ts` |
| Tests | `web/src/test/chatwidget.test.tsx`, `selection.test.tsx`, `quizcard.test.tsx`, `typewriter.test.tsx`, `voice.test.tsx` |
| Depends on | `web-api-client` (`useChat`, `useRecordQuiz`, `useSignedIn`), the browser's `SpeechRecognition` and `Selection` APIs |

## Purpose

The floating "Ask the librarian" widget on every page: text or voice question, the librarian's
answer revealed with a typewriter animation and blinking caret (disabled under
`prefers-reduced-motion`), and the pages it read as source links. The mic button dictates one
utterance via the Web Speech API and is hidden where unsupported.

On a page, selecting 12–2000 characters of the article shows a small toolbar (`SelectionToolbar`)
with **Explain**, **Elaborate** and **Quiz me**. Each hands the page and the selected text to the
widget over `chatBus` (`openChat`), which opens, shows the page as a context chip ("About: …",
with the passage and an × to drop it) and sends the action at once (`mode` + `context`). A page
opened with `?quiz=1` asks for a whole-page quiz the same way. A `quiz` answer renders as a
`QuizCard`: radio options, **Check answers** graded in the browser, ✓/✗ with the model's `why`,
a score line, and "Explain what I got wrong", which sends a plain question listing the missed
questions with the same context.

## Entry points

`<ChatWidget />` (mounted by `Layout`), `<SelectionToolbar articleRef path title />` (PageView),
`openChat({mode, context?})` / `useChatRequest()` (`chatBus.ts`; a held action is sent with the
context chip as it is when the turn in flight ends — cleared chip, nothing sent),
`<VoiceInputButton onResult />` (also used by Home and Search).

## Trust boundaries

- Answers, quiz questions, options and `why` texts are model-authored: rendered **as plain
  text** (`TypewriterText` reveals a string; `QuizCard` renders text nodes; no Markdown, no HTML).
  Source links are built from the API's `{path, title}` into console routes (`/kb/page/<path>`),
  never from the answer text.
- **The selection is reader-chosen page text sent to the model** (as `context.selection`), along
  with the page path and title. It is shown back to the reader in the chip and under their turn
  (as text). A reader can only select what the page already shows them; the API refuses a context
  page they may not open.
- Quiz answers are **graded client-side**; the chosen options never leave the browser. Only the
  tally (`{path, score, total}`) is posted, and only when the reader is signed in
  (`useSignedIn`); anonymous readers see the same grading with nothing recorded.
- Voice: on browsers that implement `SpeechRecognition` with a cloud service (e.g. Chromium),
  microphone audio is sent to the **browser vendor's** recognition service, outside this system.
  The browser asks the user for microphone permission; the widget never records or stores audio.

## Data handled

The conversation (in memory, last 8 text turns sent as history; a quiz turn has no text and is
not sent back), the page context (path, title, selection ≤ 2000 chars) while the chip is shown,
transcripts of dictated speech (inserted into the input/sent as the question), `lang` when a
non-English content language is selected, the quiz tally.

## Secrets

None.

## External calls

`POST /api/chat` and `POST /api/profile/quizzes` via the client; the browser's speech service
for voice (vendor-dependent).

## Mutations

`POST /profile/quizzes` appends a tally to the signed-in reader's own profile record (see the
`profile` sheet). The chat endpoint itself is read-only.

## Controls in place

- `TypewriterText` renders text nodes only; `aria-hidden` caret; reduced-motion respected.
- History capped client-side (8) and server-side (16); input is a plain text field.
- The toolbar only reacts to a selection whose range lies inside the article element, of
  12–2000 characters (the API's `selection` limit); it shows on mouse/key release or once a
  changing selection has settled (150 ms), hides at once when the selection collapses, on
  Escape (which clears only a selection the toolbar is up for), and after an action;
  `role="toolbar"` with an accessible name.
- Requests over `chatBus` carry a sequence number; a widget mounted later never replays an
  earlier request, and a request that arrives while a turn is in flight is held (context shown
  at once) and sent when that turn ends, never dropped. The `?quiz=1` flag is handled once per
  page and removed from the URL.
- A quiz's picks and graded state live on the chat message, not in the card, so closing and
  reopening the panel never re-asks nor re-records; the "explain what I got wrong" message is
  cut to the API's 2000-character limit.
- The mic button renders only when `SpeechRecognition` exists; `interimResults=false`,
  `maxAlternatives=1`; recognition is stopped on unmount.
- Error answers are shown with fixed styling and the API's message text (no HTML).

## Residual risks and reviewer attention points

- Voice input's data flow to the browser vendor may be unacceptable for some deployments:
  managed browser policy can disable the Web Speech API, or the widget can be built with the
  mic removed — decide per data-classification policy (questions may mention Internal-tier topics).
- Conversation history and the selected passage are sent to the server each turn (not stored
  there); visible in transit only over the platform's TLS.
- The "explain what I got wrong" message quotes the missed questions and options (model text)
  back to the model as the reader's message (truncated to 2000 characters, so a very long quiz
  loses the tail of its list rather than failing).

## Reviewer checklist

- [ ] Answers and quiz text never pass through `Markdown` or any HTML path.
- [ ] Source links are derived from `sources[]`, not parsed from the answer.
- [ ] Quiz grading and the chosen options stay in the browser; only `{path, score, total}` is posted, only when signed in.
- [ ] The toolbar's selection is bounded (12–2000) and scoped to the article element.
- [ ] Voice usage documented for the deployment's data-classification policy.

## Sign-off

Submit with `kb-librarian security submit web-chat-voice`; the reviewer records the decision with
`kb-librarian security sign web-chat-voice …`, which appends a row here and to `security/signoffs/web-chat-voice.json`.
A row is valid only for the version it names; `kb-librarian security status` shows whether the module changed since.

| Version | Commit | Reviewer | Signature | Date | Decision | Notes |
| --- | --- | --- | --- | --- | --- | --- |
