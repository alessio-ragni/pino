---
name: release
description: Cuts a Pino release — changelog and docs, tests, version bump everywhere, one commit, push to main, tag vX.Y.Z, a GitHub release with the Android APK attached, the server updated, the app installed on the tablet. Use it when the user asks to release, ship or publish a version ("fai una release", "cut a release", "rilascia la v2", "pubblica"). Do not use it for a plain commit or push: that is the changelog skill alone.
---

# Cutting a release

A release is what the family's tablet and server run, and what the public sees on GitHub. The order
matters and the last steps are public.

## Before anything

```bash
git rev-parse --git-dir; git rev-parse --git-common-dir   # different → this is a worktree: close it first
git branch --show-current
git status --porcelain
git fetch -q origin && git log origin/main..HEAD --oneline
gh auth status
```

Releases go out from `main`. On another branch: commit what is there, `git switch main`,
`git merge --no-ff <branch>`, then carry on from `main`. Stop and ask only for a conflict that is not
obvious, or a detached HEAD.

## The way out

1. **Changelog and documentation**: follow `.claude/skills/changelog/SKILL.md`.
2. **Choose the number** from what is under `## [Unreleased]`: a change in how Pino behaves or
   in the protocol between tablet and server that an old app cannot follow is a major; new
   behaviour is a minor; fixes only are a patch. Say which and why in one line.
3. **Bump the version in the three places** (they must agree, `server/tests/test_version.py`
   checks):
   - `server/pino/__init__.py` → `__version__`
   - `server/pyproject.toml` → `version`
   - `android/app/build.gradle.kts` → `versionName`, and `versionCode` = major×10000 + minor×100 + patch
4. **Close the changelog**: `## [Unreleased]` becomes `## [x.y.z] - YYYY-MM-DD` with a short opening
   paragraph; add a fresh empty `## [Unreleased]` above it and the link
   `[x.y.z]: https://github.com/alessio-ragni/pino/releases/tag/vx.y.z` at the bottom.
5. **Tests, all of them**:
   ```bash
   cd server && .venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/ruff format --check .
   cd ../android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew assembleDebug testDebugUnitTest lintDebug
   ```
6. **One commit** `release: vx.y.z`, then `git push origin main`.
7. **Tag and GitHub release**, with the APK and the version's changelog section as notes:
   ```bash
   git tag -a vx.y.z -m "Pino vx.y.z" && git push origin vx.y.z
   cp android/app/build/outputs/apk/debug/app-debug.apk /tmp/pino-vx.y.z.apk
   awk '/^## \[x.y.z\]/{f=1;next} /^## \[/{f=0} f' CHANGELOG.md > /tmp/notes.md
   gh release create vx.y.z /tmp/pino-vx.y.z.apk --title "Pino vx.y.z" --notes-file /tmp/notes.md
   ```
   The APK is the debug build (signed with the debug key): fine for a personal tablet, say so in
   the notes if anyone else may install it.
8. **Watch CI**: `gh run list --limit 3`, then `gh run watch <id> --exit-status`. Report the verdict,
   not the hope.
9. **Update the server** (it follows `main`):
   ```bash
   ssh alessio@vps-alessio 'bash ~/pino/deploy/vps/installa.sh'
   ssh alessio@vps-alessio 'journalctl --user -u pino -n 20 --no-pager'
   ```
10. **Install on the tablet**: `adb install -r android/app/build/outputs/apk/debug/app-debug.apk`,
    open the app, and check with one harmless written question
    (`adb shell am start -a dev.pino.app.ASCOLTA --es text "'Pino, che ore sono?'"`) and
    the journal on the server (`ssh alessio@vps-alessio 'cd pino/server && .venv/bin/python -m
    pino.journal --db ~/.local/share/pino/pino.db --hours 1'`) that the answer arrived.

## Reporting back

The version and why that number; the commit and where it went; what CI said; the release address
(`https://github.com/alessio-ragni/pino/releases/tag/vx.y.z`); whether the server and the tablet
run it; anything skipped and why.
