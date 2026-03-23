# ask-testudo — Full-Stack Website Plan

## Project overview

A student-facing RAG chat tool for UMD students to query academic policies,
course requirements, and registration procedures. ChatGPT-style full-page
interface with UMD branding. FastAPI backend on Railway, Next.js frontend
on Vercel.

---

## Color palette

| Token | Hex | Usage |
|---|---|---|
| `--bg-primary` | `#EED9B9` | Main page background |
| `--bg-secondary` | `#F7EDD9` | Chat bubbles, cards, inputs |
| `--accent-dark` | `#5E0006` | Primary buttons, active states |
| `--accent-mid` | `#9B0F06` | Hover states, borders |
| `--accent-light` | `#D53E0F` | Badges, confidence pills, highlights |
| `--text-primary` | `#1a0a00` | Body text |
| `--text-secondary` | `#6b3a2a` | Muted text, placeholders |
| `--border` | `rgba(94,0,6,0.15)` | Subtle borders |

Dark mode inverts: `--bg-primary` becomes `#1a0a00`, accents flip to warm
light tones, `--text-primary` becomes `#EED9B9`.

---

## Repository structure

### Backend — `ask-testudo/` (existing, deploy to Railway)

```
ask-testudo/
├── query.py              ← add CORS, history param, /ping endpoint
├── query_prompts.py
├── requirements.txt
├── Procfile              ← NEW: web: uvicorn query:app --host 0.0.0.0 --port $PORT
└── store/
    ├── parent_chunks/
    └── bm25_encoder.json
```

### Frontend — `ask-testudo-frontend/` (new repo, deploy to Vercel)

```
ask-testudo-frontend/
├── app/
│   ├── layout.tsx              ← root layout, fonts, ThemeProvider
│   ├── page.tsx                ← redirects to /chat
│   ├── chat/
│   │   └── page.tsx            ← main chat page
│   └── globals.css             ← CSS variables, color tokens, base styles
├── components/
│   ├── ui/                     ← shadcn + custom primitives
│   │   ├── button.tsx          ← shadcn Button (copy-paste provided)
│   │   ├── prompt-input.tsx    ← shadcn PromptInput
│   │   └── prompt-suggestion.tsx ← copy-paste from spec
│   ├── ChatThread.tsx          ← scrollable message list
│   ├── MessageBubble.tsx       ← single message (user or assistant)
│   ├── SourceCard.tsx          ← citation card below answer
│   ├── ConfidenceBadge.tsx     ← high / medium / low pill
│   ├── InputBar.tsx            ← wraps PromptInput + PromptSuggestion
│   ├── ExampleQuestions.tsx    ← suggestion chips on empty state
│   ├── Navbar.tsx              ← top bar: logo + title + theme toggle
│   └── ThemeToggle.tsx         ← dark mode switch
├── hooks/
│   └── useChat.ts              ← all chat state and API logic
├── lib/
│   ├── api.ts                  ← fetch calls to FastAPI
│   └── types.ts                ← TypeScript interfaces
├── .env.local                  ← NEXT_PUBLIC_API_URL=http://localhost:8002
├── next.config.js
├── tailwind.config.ts
└── package.json
```

---

## Part 1 — Backend changes (3 additions to query.py)

### 1. CORS middleware

Add immediately after `app = FastAPI(...)`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://ask-testudo.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

### 2. Conversation history on /ask

Update the request model:

```python
class Message(BaseModel):
    role: str       # "user" or "assistant"
    content: str

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    stream: bool = False
    history: list[Message] = []    # new — defaults to empty list
```

Update `generate_answer()` to inject history:

```python
def generate_answer(parents, question, history=[]):
    history_messages = [
        {"role": m.role, "content": m.content}
        for m in history[-6:]    # last 3 turns (6 messages) max
    ]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history_messages,
        {"role": "user", "content": build_context_prompt(parents, question)}
    ]
    # rest of function unchanged
```

### 3. /ping endpoint for cold-start warming

```python
@app.get("/ping")
def ping():
    return {"status": "warm"}
```

### 4. Procfile (new file in repo root)

```
web: uvicorn query:app --host 0.0.0.0 --port $PORT
```

---

## Part 2 — Frontend: project setup

### Scaffold with shadcn (run once)

```bash
npx create-next-app@latest ask-testudo-frontend \
  --typescript --tailwind --app --src-dir=false \
  --import-alias="@/*"

cd ask-testudo-frontend
npx shadcn@latest init
```

When shadcn init prompts:
- Style: Default
- Base color: pick any (will be overridden by custom palette)
- CSS variables: Yes

### Install dependencies

```bash
# shadcn components used by PromptSuggestion
npx shadcn@latest add button

# PromptInput component (install separately — not in default registry)
# Copy-paste prompt-input.tsx to components/ui/ manually

# Additional packages
npm install class-variance-authority @radix-ui/react-slot
npm install react-markdown
npm install lucide-react        # already included with shadcn
```

### Copy-paste components into components/ui/

The following files must be manually placed at `components/ui/`:

1. `prompt-suggestion.tsx` — from the spec provided
2. `button.tsx` — from the spec provided (shadcn generates this but
   verify it matches the spec version)
3. `prompt-input.tsx` — from shadcn extended components registry

**Why components/ui/ matters:** shadcn resolves imports from
`@/components/ui/`. If files are placed elsewhere, all `import` paths
across the codebase will break. The `@/*` alias maps to your project root.

---

## Part 3 — TypeScript types

```typescript
// lib/types.ts

export interface Source {
  filename: string
  page: number
  section: string
  doc_type: string
}

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: Source[]
  confidence?: "high" | "medium" | "low"
  rerank_score?: number
  fallback?: boolean
  loading?: boolean     // true while waiting for API response
}

export interface AskResponse {
  answer: string
  sources: Source[]
  confidence: "high" | "medium" | "low"
  rerank_score: number
  fallback: boolean
}

export interface HistoryMessage {
  role: "user" | "assistant"
  content: string
}
```

---

## Part 4 — API layer

```typescript
// lib/api.ts

import { AskResponse, HistoryMessage } from "./types"

const API_URL = process.env.NEXT_PUBLIC_API_URL

export async function askQuestion(
  question: string,
  history: HistoryMessage[]
): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history, stream: false }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `API error: ${res.status}`)
  }
  return res.json()
}

// Fire-and-forget — warms Railway server on page load
export function pingBackend(): void {
  fetch(`${API_URL}/ping`).catch(() => {})
}
```

---

## Part 5 — useChat hook

All chat state lives here. Components stay pure UI.

```typescript
// hooks/useChat.ts
"use client"

import { useState, useCallback } from "react"
import { ChatMessage, HistoryMessage } from "@/lib/types"
import { askQuestion } from "@/lib/api"
import { v4 as uuidv4 } from "uuid"

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)

  // Build history array from current messages (exclude loading placeholders)
  const buildHistory = (msgs: ChatMessage[]): HistoryMessage[] =>
    msgs
      .filter((m) => !m.loading && m.content)
      .map((m) => ({ role: m.role, content: m.content }))

  const sendMessage = useCallback(
    async (question: string) => {
      if (!question.trim() || isLoading) return

      // Add user message immediately
      const userMsg: ChatMessage = {
        id: uuidv4(),
        role: "user",
        content: question,
      }

      // Add loading placeholder for assistant
      const loadingMsg: ChatMessage = {
        id: uuidv4(),
        role: "assistant",
        content: "",
        loading: true,
      }

      setMessages((prev) => [...prev, userMsg, loadingMsg])
      setIsLoading(true)

      try {
        const history = buildHistory(messages)
        const response = await askQuestion(question, history)

        // Replace loading placeholder with real response
        setMessages((prev) =>
          prev.map((m) =>
            m.loading
              ? {
                  ...m,
                  loading: false,
                  content: response.answer,
                  sources: response.sources,
                  confidence: response.confidence,
                  rerank_score: response.rerank_score,
                  fallback: response.fallback,
                }
              : m
          )
        )
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.loading
              ? {
                  ...m,
                  loading: false,
                  content:
                    "Something went wrong. Please try again in a moment.",
                  fallback: true,
                }
              : m
          )
        )
      } finally {
        setIsLoading(false)
      }
    },
    [messages, isLoading]
  )

  const clearHistory = useCallback(() => setMessages([]), [])

  return { messages, isLoading, sendMessage, clearHistory }
}
```

Install uuid: `npm install uuid @types/uuid`

---

## Part 6 — Component specifications

### Navbar.tsx

- Left: Testudo logo (SVG or `🐢` emoji fallback) + "Ask Testudo" wordmark
- Right: ThemeToggle button + optional "Clear chat" icon button
- Background: `--accent-dark` (#5E0006) with `--text-primary` white
- Height: 56px, sticky top-0, z-50

### ChatThread.tsx

- Full height minus Navbar and InputBar
- Auto-scrolls to bottom on new messages (`useEffect` + `scrollIntoView`)
- Shows `<ExampleQuestions>` when `messages.length === 0`
- Maps over messages and renders `<MessageBubble>` for each

### MessageBubble.tsx

User messages:
- Right-aligned, max-width 70%
- Background: `--accent-dark` (#5E0006), text white
- Border-radius: 18px 18px 4px 18px

Assistant messages:
- Left-aligned, max-width 85%
- Background: `--bg-secondary` (#F7EDD9)
- Border-radius: 18px 18px 18px 4px
- Loading state: three animated dots (CSS keyframe pulse)
- Renders markdown via `react-markdown`
- Shows `<ConfidenceBadge>` and `<SourceCard>` below content

### ConfidenceBadge.tsx

Pill component below each assistant message:

```
high   → green pill   "High confidence"
medium → amber pill   "Medium confidence"
low    → red pill     "Low confidence"
```

Only rendered when `fallback=false`. Tooltip on hover:
"Confidence score: 0.7237 — based on how well sources matched your question"

### SourceCard.tsx

Collapsed by default. Toggle shows sources list.

```
[Show sources (3) ▾]

Collapsed view shows nothing.

Expanded:
┌──────────────────────────────┐
│ 📄 computer-science-major.pdf│
│    Page 1 • Requirements     │
│                              │
│ 📄 computer-science-minor.pdf│
│    Page 1 •                  │
└──────────────────────────────┘
```

### ExampleQuestions.tsx

Six `<PromptSuggestion>` chips rendered in a centered flex-wrap layout.
Clicking a chip calls `sendMessage(question)` directly.

Questions:
1. "What are the prerequisites for CMSC132?"
2. "What GPA do I need to stay in good academic standing?"
3. "How do I apply for a late withdrawal?"
4. "What are the lower-level requirements for the CS major?"
5. "What courses are required for the CS major?"
6. "What is the minimum GPA to graduate with honors?"

Above the chips, show:
- Testudo logo (large, centered)
- "Ask Testudo" heading
- "Your UMD academic policy assistant" subheading

### InputBar.tsx

Wraps `PromptInput` + `PromptInputTextarea` + send `Button` from the spec.

```tsx
<PromptInput
  value={input}
  onValueChange={setInput}
  onSubmit={handleSend}
  className="border border-[--border] bg-[--bg-secondary] shadow-sm"
>
  <PromptInputTextarea
    placeholder="Ask about courses, requirements, policies..."
    className="text-[--text-primary] placeholder:text-[--text-secondary]"
  />
  <PromptInputActions className="justify-between">
    <span className="text-xs text-[--text-secondary]">
      {input.length}/500
    </span>
    <Button
      size="sm"
      className="size-9 rounded-full bg-[--accent-dark] hover:bg-[--accent-mid]"
      onClick={handleSend}
      disabled={!input.trim() || isLoading}
    >
      <ArrowUpIcon className="h-4 w-4" />
    </Button>
  </PromptInputActions>
</PromptInput>
```

Keyboard: Enter submits, Shift+Enter adds newline.

### ThemeToggle.tsx

Single icon button. Stores preference in `localStorage`.
Applies `data-theme="dark"` to `<html>` element.
Icon: `SunIcon` / `MoonIcon` from lucide-react.

---

## Part 7 — CSS variables (globals.css)

```css
/* globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg-primary: #EED9B9;
  --bg-secondary: #F7EDD9;
  --accent-dark: #5E0006;
  --accent-mid: #9B0F06;
  --accent-light: #D53E0F;
  --text-primary: #1a0a00;
  --text-secondary: #6b3a2a;
  --border: rgba(94, 0, 6, 0.15);
  --shadow: 0 2px 8px rgba(94, 0, 6, 0.08);
}

[data-theme="dark"] {
  --bg-primary: #1a0a00;
  --bg-secondary: #2a1208;
  --accent-dark: #D53E0F;
  --accent-mid: #9B0F06;
  --accent-light: #EED9B9;
  --text-primary: #EED9B9;
  --text-secondary: #c4956a;
  --border: rgba(238, 217, 185, 0.15);
  --shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
}

body {
  background-color: var(--bg-primary);
  color: var(--text-primary);
  transition: background-color 0.2s, color 0.2s;
}

/* Loading dots animation */
@keyframes dot-pulse {
  0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
  40%           { opacity: 1;   transform: scale(1);   }
}
.dot-pulse span {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--accent-light);
  animation: dot-pulse 1.4s ease-in-out infinite;
}
.dot-pulse span:nth-child(2) { animation-delay: 0.2s; }
.dot-pulse span:nth-child(3) { animation-delay: 0.4s; }
```

---

## Part 8 — Page layout (chat/page.tsx)

```
┌─────────────────────────────────────────┐  height: 100dvh
│  Navbar (sticky, 56px)                  │
├─────────────────────────────────────────┤
│                                         │
│  ChatThread (flex-1, overflow-y-auto)   │
│                                         │
│  ┌─────── empty state ─────────────┐   │
│  │   [Testudo logo]                │   │
│  │   Ask Testudo                   │   │
│  │   Your UMD academic assistant   │   │
│  │                                 │   │
│  │   [chip] [chip] [chip]          │   │
│  │   [chip] [chip] [chip]          │   │
│  └─────────────────────────────────┘   │
│                                         │
├─────────────────────────────────────────┤
│  InputBar (sticky bottom, p-4)          │
└─────────────────────────────────────────┘
```

---

## Part 9 — Deployment

### Railway (backend)

1. Push `ask-testudo` repo to GitHub
2. Railway dashboard → New Project → Deploy from GitHub
3. Add environment variables:
   - `COHERE_API_KEY`
   - `PINECONE_API_KEY`
   - `PINECONE_INDEX_NAME`
   - `XAI_API_KEY`
4. Railway auto-detects `Procfile` and runs uvicorn
5. Note your Railway URL (e.g. `https://ask-testudo-production.up.railway.app`)

**Important — store/ directory:** Commit `store/` to the backend repo.
The `parent_chunks/` directory and `bm25_encoder.json` must exist on the
Railway server. At ~150MB this is large but GitHub handles it.

Add to `.gitignore` to keep venvs out:
```
.venv/
.venv-query/
.venv-wsl/
__pycache__/
*.pyc
```

### Vercel (frontend)

1. Push `ask-testudo-frontend` to GitHub
2. Vercel dashboard → New Project → Import from GitHub
3. Framework: Next.js (auto-detected)
4. Add environment variable:
   - `NEXT_PUBLIC_API_URL` = your Railway URL
5. Deploy — auto-deploys on every push to `main`

### Local development

```bash
# .env.local (frontend root)
NEXT_PUBLIC_API_URL=http://localhost:8002

# Terminal 1 — backend
cd ask-testudo
.venv-query\Scripts\activate
uvicorn query:app --port 8002 --reload

# Terminal 2 — frontend
cd ask-testudo-frontend
npm run dev    # http://localhost:3000
```

---

## Part 10 — Build order (days timeline)

### Day 1 — Backend + scaffold

- [ ] Add CORS middleware to query.py
- [ ] Add `history` param to AskRequest + generate_answer()
- [ ] Add `/ping` endpoint
- [ ] Add `Procfile`
- [ ] Push to GitHub, deploy to Railway
- [ ] Confirm `/health` returns 200 on Railway URL
- [ ] Scaffold Next.js: `npx create-next-app@latest`
- [ ] Run `npx shadcn@latest init`
- [ ] Copy-paste `prompt-suggestion.tsx` and `button.tsx` to `components/ui/`
- [ ] Install `prompt-input` from shadcn extended registry
- [ ] Set up `globals.css` with color variables
- [ ] Build `Navbar` (static shell)

### Day 2 — Core chat loop

- [ ] Create `lib/types.ts` and `lib/api.ts`
- [ ] Build `useChat` hook
- [ ] Install `uuid`: `npm install uuid @types/uuid`
- [ ] Build `InputBar` using `PromptInput` + `PromptSuggestion`
- [ ] Build `MessageBubble` with loading dots
- [ ] Build `ChatThread` with auto-scroll
- [ ] Build `ExampleQuestions` with 6 chips
- [ ] Wire all components in `chat/page.tsx`
- [ ] Test full loop locally: question → API → answer renders

### Day 3 — Polish + deploy

- [ ] Build `SourceCard` with collapse/expand
- [ ] Build `ConfidenceBadge` with tooltip
- [ ] Build `ThemeToggle` with localStorage persistence
- [ ] Mobile responsive pass (Tailwind `sm:` breakpoints)
- [ ] Add `pingBackend()` call in `layout.tsx` useEffect
- [ ] Push frontend to GitHub
- [ ] Deploy to Vercel
- [ ] Set `NEXT_PUBLIC_API_URL` in Vercel dashboard
- [ ] Test end-to-end on production URLs
- [ ] Test dark mode, mobile view, example questions

---

## Environment variables summary

| Variable | Location | Value |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Vercel + `.env.local` | Railway backend URL |
| `COHERE_API_KEY` | Railway | Cohere production key |
| `PINECONE_API_KEY` | Railway | Pinecone key |
| `PINECONE_INDEX_NAME` | Railway | `ask-testudo` |
| `XAI_API_KEY` | Railway | xAI key |

Never place API keys in the frontend. `NEXT_PUBLIC_` prefix is safe
because it's only the Railway URL — not a secret credential.

---

## NPM dependencies summary

```bash
# Core (installed by create-next-app + shadcn)
next, react, react-dom, typescript, tailwindcss

# shadcn primitives
@radix-ui/react-slot
class-variance-authority

# Chat
react-markdown         # render markdown in assistant bubbles
uuid                   # generate message IDs
@types/uuid

# Icons (already included with shadcn)
lucide-react
```

---

## PromptInput dependency note

`prompt-input.tsx` is from the shadcn extended community registry,
not the default registry. Install via:

```bash
npx shadcn@latest add "https://v0.dev/chat/b/b_eZOhBpYAqmn"
```

Or copy-paste manually from:
https://ui.shadcn.com/blocks — search "Prompt Input"

It exports: `PromptInput`, `PromptInputTextarea`, `PromptInputActions`
which are imported in `InputBar.tsx` and the demo from the spec.

---

## Notes on streaming (v2)

v1 uses `stream: false` for simplicity. When ready to add streaming:

1. Backend: the `/ask` SSE path is already implemented in query.py
2. Frontend: replace the `askQuestion` fetch with an EventSource or
   `fetch` with `ReadableStream` parsing
3. Update `useChat` to append chunks to the loading message content
   as they arrive instead of replacing the whole message at once

This is a self-contained upgrade — no architecture changes needed.