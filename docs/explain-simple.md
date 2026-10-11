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

---

## Step 2, slice 1 — Uploading and checking the file safely (done)

**What this slice does:** lets you upload an app file through a web page, and makes sure
it's a real, safe app file before keeping it.

Think of it as the **mailroom** checking a parcel before it's allowed inside:

- **It won't trust the label.** A file called `something.apk` means nothing — we check
  the actual contents. An APK is really a **ZIP** archive, so we look inside and require
  the tell-tale `AndroidManifest.xml` to be there. (Checking content, not extension.)
- **It weighs the parcel as it arrives.** The upload is written to a **quarantine** temp
  folder in chunks, counting bytes as they come. If it goes over the size limit, we stop
  and throw it away immediately — a giant file can't fill the disk.
- **It refuses booby-trapped parcels.** Two classic attacks are blocked:
  - a **zip bomb** — a tiny file that unpacks into something huge to exhaust the disk; we
    add up the unpacked sizes first and reject if they're too big.
  - a **path-traversal** entry — a file inside the ZIP named like `../../etc/evil` that
    tries to escape and overwrite things elsewhere; any such entry gets the whole upload
    rejected.
- **It fingerprints what it keeps.** For a good file we compute a **SHA-256** (a unique
  fingerprint of the exact bytes) and store the file under *that* name, not its original
  one. Same file uploaded twice = stored once (**deduplication**). The original filename
  is kept only as a note in the database.
- **Rejected files are never stored.** If it fails any check, we record *that it was
  rejected and why*, and delete the bytes. We don't keep hostile files around.

**How I proved it:** I uploaded three files — a proper app-shaped one, one with a
`../../etc/evil` booby-trap entry, and one that was just text pretending to be an app.
The good one was accepted and stored (as a single fingerprint-named file); the other two
were both rejected and left nothing on disk. Six automated tests cover these cases, plus
the zip-bomb and empty-file ones.

---

## Step 2, slice 2 — Taking the app apart, safely (done)

**What this slice does:** sends an uploaded app into the **sealed room** (the sandbox),
takes it apart there, and brings back a list of what's inside — without the sealed room
ever being able to reach our real data or the internet.

The hand-off is the interesting part. The sealed room and the main office have
**separate filing cabinets** (two databases) that can't see each other. So how does a job
cross safely? Like a **drop box between two locked rooms** (this pattern is called an
**outbox**):

1. The main office writes a work ticket into the sealed room's drop box.
2. The demolition guy (`sandbox-worker`) picks it up, takes the app apart with a tool
   called **androguard**, and puts the results back in the drop box. He never touches our
   real cabinet — he *can't*, it's on a different network he can't even see.
3. The main office collects the results from the drop box, **double-checks they're the
   right shape** (treats them as untrusted), and only then files them in the real cabinet.

**What androguard pulls out** (the app's "ingredients label", the **manifest**): the app's
package name, what **permissions** it asks for, which screens are **exported** (openable by
other apps), and risky flags like **debuggable**. Each finding is saved with **provenance**
— where it was found (`AndroidManifest.xml`) and how (`androguard`). Important: these are
**observations, not verdicts**. "This app can use the internet" is a fact, not a
vulnerability.

**A detail I'm a little proud of:** to test this without a real phone app, I hand-built a
tiny but *genuine* Android app file, including the manifest in Android's real **binary**
format (not plain text) — and androguard read it correctly. So the test exercises the real
tool, not a fake.

**Two real bugs this slice caught (good interview stories):**
- A one-line Python import (`import app.tasks`) silently **overwrote** the name of our
  task-runner object with the name of a code folder, so the worker "couldn't find" itself.
  The fix was a different import style. Lesson: name collisions can hide in plain sight.
- A safety setting in a startup script (`set -e`, "stop on any error") was killing the
  script on a line that was *deliberately* signalling "schema not set up yet." Fixed by
  catching that one signal. Lesson: "fail on any error" needs care around intentional
  non-zero signals.

**How I proved it:** uploaded the real sample app, triggered analysis, and watched the job
travel to the sealed room and the results come back into the real cabinet with three
tagged findings. Re-running analysis did **not** pile up duplicates. Confirmed the sealed
room cannot even find the main cabinet's address. 12 automated tests now pass.

---

## Step 2, slice 3 — Reading inside the app (done)

**What this slice does:** so far we only read the app's "label" (the manifest). This slice
reads *inside* the app's bundled files — its text resources and config — hunting for the
things that actually matter, and recording where each was found.

What it looks for, with the **file and line number** it came from:
- **Backend URLs** — especially a Supabase address like `abcd1234test.supabase.co`.
- **Keys** — and this is the important bit: it **classifies** them instead of screaming
  "secret!" at everything. A `sb_publishable_…` key is labelled **"public client key —
  not a secret"** (it's *meant* to be in the app). A `sb_secret_…` key would be flagged
  as genuinely sensitive. This is the core idea of the whole project: a public key is not
  a vulnerability by itself.
- **Which SDKs** the app uses (Supabase, Firebase, …).
- **Cleartext HTTP** links (unencrypted, a real weakness).
- **Table and bucket references** — e.g. `from("trips")`, `storage.from("receipts")` —
  hints at what data the backend holds.

**Redaction happens in the sealed room.** Any value that *is* sensitive gets masked
(shown as a short prefix plus a fingerprint) *before* it ever leaves the sandbox, so a
real secret is never written into our database or logs. I verified this: the stored key
is the redacted form, and a check for any un-redacted key came back zero.

**One honest deferral:** to read the app's *compiled program code* (not just its text
files) you need a Java tool called **JADX** and a genuinely compiled app to test against.
My hand-built test app has only a stub for the code part, so verifying JADX now would be
theatre. I've deferred it to step 3, where the real lab app exists. It matters less than
it sounds: apps built with web tech (Capacitor/React Native — like the client app) keep
their logic in those **text/asset** files we already scan.

**Important framing:** everything found here is an **observation with provenance**, never
a verdict. "There's a Supabase URL and a public key, and the app reads a `trips` table"
is a *lead*. Whether the backend actually leaks that table is what the agent will test
safely later. 13 automated tests pass.
