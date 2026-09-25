# Releasing

PokeClaude uses [Semantic Versioning](https://semver.org/) and [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/). The version lives in
`VERSION` at the repo root; `parser.__version__` reads it at import time.
See `CHANGELOG.md` for what counts as the public API for SemVer purposes.

## Day to day: adding changelog entries

Every PR that changes user-visible behavior (the parser's JSON output, the
`parser.sync` CLI, `config.json`/`saves/` layout, reference data, memory
files, slash commands, etc.) should add its own entry under
`## [Unreleased]` in `CHANGELOG.md`, in the relevant group (`Added`,
`Changed`, `Fixed`, `Removed`). Write it for someone using the bot, not for
another engineer reading the diff — say what changed and why it matters,
skip internal refactor detail.

Nothing else needs to happen in the PR. Versioning and dating happen at
release time, not per-PR.

## Cutting a release

1. Make sure `main` is green and `## [Unreleased]` has the entries you want
   to ship.
2. Decide the bump:
   - **patch** — bug fixes and corrections only.
   - **minor** — new capability, in a backward-compatible way (also covers
     what would be a breaking change to the public API while the project is
     still `0.x`, per SemVer's pre-1.0 rule — see `CHANGELOG.md`).
   - **major** — a breaking change to the public API, once the project is
     past `1.0.0`.
3. Run the bump script from the repo root:

   ```bash
   python3 scripts/bump_version.py minor   # or: major | patch | X.Y.Z
   ```

   Add `--dry-run` first if you want to preview the new `VERSION` and
   `CHANGELOG.md` without writing anything. Add `--allow-empty` only if you
   intend to cut a release with no changelog entries (rare — the script
   refuses by default).

   This updates `VERSION`, moves `[Unreleased]`'s contents into a new dated
   `## [X.Y.Z] - YYYY-MM-DD` section, leaves `[Unreleased]` empty, and
   rewrites the compare/tag links at the bottom of the file.

4. Commit, tag, and push — the script prints the exact commands, which are:

   ```bash
   git add VERSION CHANGELOG.md
   git commit -m "Release vX.Y.Z"
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin main --tags
   ```

5. Pushing the tag triggers `.github/workflows/release.yml`, which:
   - verifies the tag matches `v$(cat VERSION)`,
   - runs the test suite,
   - extracts that version's `CHANGELOG.md` section
     (`scripts/bump_version.py --extract-notes X.Y.Z`),
   - publishes a GitHub release from the tag with those notes, marked
     **prerelease** automatically while the major version is `0` or the tag
     has a suffix (e.g. `v1.2.3-rc.1`).

No other step is needed — the release is live once the workflow finishes.

## The one-time first release

The very first release (`0.1.0`) is a special case: its `CHANGELOG.md`
section was written directly (there was no prior release to diff against),
so there's nothing sitting in `[Unreleased]` to move. Instead of
`bump_version.py minor`, that release used:

```bash
python3 scripts/bump_version.py --release-current
```

which just replaces `## [0.1.0] - TBD` with the actual release date and
rewrites the links, without touching `[Unreleased]`. This only applies to
the very first tagged release — every release after that goes through the
normal bump flow above.

## Fixing a bad tag

If a tag was pushed by mistake (wrong version, `release.yml` failed for a
reason unrelated to the tag itself, etc.) and no one has pulled it yet:

1. Delete the GitHub release, if one was created:
   ```bash
   gh release delete vX.Y.Z --yes
   ```
2. Delete the tag, both locally and on the remote:
   ```bash
   git tag -d vX.Y.Z
   git push origin :refs/tags/vX.Y.Z
   ```
3. Fix whatever was wrong (VERSION, CHANGELOG.md, or the code itself) in a
   new commit on `main`.
4. Re-tag and push again, following the normal flow above.

Never force-push over a tag that anyone may have already fetched — delete
and recreate it instead, as above, so there's no ambiguity about what
`vX.Y.Z` pointed to.
