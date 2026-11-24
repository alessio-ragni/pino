---
name: changelog
description: Writes the CHANGELOG.md entry for the work just done, for someone who uses Pino and does not read code, and brings README.md and the docs/ guides up to date in the same pass. Use it whenever the user wants to commit, push or release in this repository, in whatever words or language ("commit this", "push it", "committa", "pusha", "fai una release"). Do not use it when the user only asks what changed, or when the change touches nothing but .claude/.
---

# The changelog

`CHANGELOG.md`, at the root of the repository, is where someone who uses Pino and does not read
code finds out what is different for them. It is not a list of commits.

## When it does not run

- The user is only asking what changed.
- The change touches only `.claude/`.
- The work is half finished: an entry describes something done.

## In this order

1. **Look at the work, not the commit messages.**
   ```bash
   git status --porcelain
   git diff --stat
   git log origin/main..HEAD --oneline --no-merges
   date +%F
   ```
   Read enough of the diff to answer: what is different for the person using Pino?
2. **Bring the documentation up to date first**, in the same change:
   - `README.md` for anything a person can see or that changes how the project is laid out;
   - `docs/how-it-works.md` for behaviour, states, cards, tools, what is kept, speed;
   - `docs/protocol.md` for any message between tablet and server (the code and this file move
     together);
   - `docs/deployment.md` for setting up or updating the server and the tablet.
   If none needed touching, say so in one line.
3. **Write the entry under `## [Unreleased]`**, Keep a Changelog sections in this order when used:
   Added, Changed, Deprecated, Removed, Fixed, Security. If a bullet about the same thing is
   already there, improve it instead of adding a second one.
4. **Run the tests**: `cd server && .venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/ruff
   format --check .`, and for Android changes
   `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew testDebugUnitTest lintDebug`.
   Never skip or weaken a test to get green.
5. **Show the CHANGELOG diff**, then commit only if the user asked.

## How an entry reads

```markdown
- **«Prossimo passo» moves the recipe on**, on the same card: the step you are on is at the top,
  large, and the ones already done are ticked.
```

- English, complete sentences, opening with the claim in bold.
- Say what the person will notice: what Pino does, says or shows, how long it takes.
- No file, function, table or path names, and no jargon (endpoint, schema, hook, refactor, deploy).
- Say whether it was tried on the real tablet or only in tests.
- What was removed or switched off is said as plainly as what was added.
- No emoji, no superlatives. Past entries are never rewritten; a correction is a new entry.
- Work nobody can see still gets a short line that says so, and why it was worth doing.

## Cutting a version

Only when the user asks for a release; then follow `.claude/skills/release/SKILL.md`, which turns
`## [Unreleased]` into `## [x.y.z] - YYYY-MM-DD` with a two or three sentence opening paragraph and
a fresh empty `## [Unreleased]` above it.
