# App Sentinel, explained simply

A running, plain-language companion to the build. One section per step. Plain words,
but the real technical terms are kept so the vocabulary sticks. This is for me to re-read
before explaining the project to someone.

---

## The whole idea in one picture

Think of the tool as a **small security firm inside one computer**. You hand it an
Android app file (an **APK**). Its staff take the app apart, work out what it talks to,
safely test whether that backend leaks data it shouldn't, and hand back a report.

The one rule that shapes everything:

> **The advisor (the AI) suggests. The plain code decides.**

The AI is a smart consultant. It can say "you should check that table." But a separate
piece of boring, testable code — the **scope gate** — checks every suggested action
against what you actually authorized. The AI can't give itself permission, and it can't
be tricked into it, because the permission check never reads the AI's opinion. And when a
check runs, another piece of plain code (the **verifier**) looks at what actually came
back and decides if it's a real problem. The AI saying "I found a vulnerability" is never
the proof — the evidence is.

## The rooms (we keep three apart on purpose)

- **Room 1 — the sealed room (the sandbox).** Where the uploaded app gets taken apart.
  App files are treated as dangerous, like a suspicious package. So this room has **no
  internet and no passwords in it.** If something nasty were hidden in the app, there is
  nothing here to steal and no way to phone out. It has its own throwaway notepad (a
  separate database).
- **Room 2 — the main office (the orchestrator).** The brain. Keeps the real records and
  makes every real decision about what's allowed. It is the only room allowed to talk to
  both other rooms, and it double-checks anything the sealed room hands over.
- **Room 3 — the advisor's booth (the LLM gateway).** The only place the AI login lives.
  A question is slid under the door; an answer comes back. The advisor can only talk — it
  can't run commands or touch files, and it never sees the raw app file.

The rule: **passwords and dangerous files are never in the same room.**

---

## Step 1 — The foundation (done)

**What this step was about:** hiring the staff, building the rooms, and checking everyone
turns up for work. No real scanning yet — this was making the building stand up.

**One command (`docker compose up`) now starts six programs at once** (each is a
**container**):

- the **receptionist** (`api`) — serves the web page
- the **investigator** (`worker`) — will run scans later; for now just proves it can pick
  up tasks
- the **demolition guy** (`sandbox-worker`) — sits in the sealed room, idle for now
- **two filing cabinets** (`main-db`, `sandbox-db`) — the two databases
- the **advisor's booth** (`llm-gateway`) — empty booth for now, just says "I'm alive"

**What I checked, and why each matters:**

- **The health page tells the truth.** Asking the app "are you OK?" (the `/health` check)
  makes it look at the real database and the real task list before answering, instead of
  always saying "fine." We know it's honest because at one point something *was* broken
  and it correctly reported the problem instead of lying.
- **A task travels from the web page to the worker and back.** A button sends a tiny test
  task (a `ping`) into the **task queue**; the investigator picked it up and did it. That
  proves the hand-off pipe between the parts works.
- **The sealed room is actually sealed.** From inside the sandbox I tried to reach the
  internet — blocked. I tried to reach the main filing cabinet — blocked. It can only
  reach its own throwaway cabinet. That is the core safety idea working: **if a nasty app
  ever blew up in that room, it has nowhere to go and nothing to steal.**
- **The app refuses to start if it's misconfigured.** I removed a required setting (the
  database address). Instead of starting up broken and failing weirdly later, it stopped
  at once with a clear message about what was missing.
- **The front door only accepts local visitors.** A request pretending to come from
  another website was turned away. This matters because the tool runs on your own machine
  with no login, so we block anything that isn't genuinely you (this guards against
  **CSRF** and **DNS-rebinding**).

**One honest caveat:** the page styling is a small hand-written stylesheet for now, not
the proper **Tailwind** build yet. Written down in the roadmap rather than pretended done.

**A bug worth remembering (good interview story):** my first setup script hid a real
failure behind a "carry on anyway" line — the task-queue tables never got created, and
only the honest `/health` check (returning an error) exposed it. I fixed it to check
first and fail loudly. It's a live example of *why* health checks must tell the truth and
*why* hiding errors is dangerous.
