# How to Publish `agentsentinel-cli` to PyPI

Step-by-step guide for every release. Run all commands from the repo root
(`/Users/jaydenaung/claude/agentsentinel`) unless otherwise noted.

---

## One-time setup (do this once, never again)

### Step 1 — Create a PyPI account

Go to https://pypi.org/account/register/ and create an account if you don't have one.

### Step 2 — Create an API token

1. Log in to https://pypi.org
2. Go to **Account Settings → API tokens → Add API token**
3. Name it `agentsentinel-cli`
4. Scope: select **Entire account** (or restrict to this project after first upload)
5. Copy the token — it starts with `pypi-` and is shown only once

### Step 3 — Save the token to `~/.pypirc`

Create the file `~/.pypirc` with this content (replace the placeholder):

```ini
[distutils]
index-servers = pypi

[pypi]
username = __token__
password = pypi-YOUR_ACTUAL_TOKEN_HERE
```

Lock the file so only you can read it:

```bash
chmod 600 ~/.pypirc
```

Verify it's set up:

```bash
cat ~/.pypirc   # should show your token
```

### Step 4 — Verify tools are installed

```bash
twine --version      # should print twine version 6.x
/opt/homebrew/bin/python3.11 -m pip show build   # if missing, run next line
/opt/homebrew/bin/python3.11 -m pip install build twine
```

---

## Every release — the full checklist

Follow these steps in order for every new version.

---

### Step 1 — Make sure all changes are committed

```bash
git status
git log --oneline -5
```

There should be no uncommitted changes to `cli/`. If there are, commit them first.

---

### Step 2 — Bump the version number

Open `cli/pyproject.toml` and update the `version` field:

```toml
version = "0.3.0"   ← change this
```

**Version numbering convention:**
- `0.X.0` — new command or major feature (e.g. added `sentinel mcp scan`)
- `0.X.Y` — bug fix or small enhancement to an existing command

Current version history:
| Version | What changed |
|---------|-------------|
| `0.1.0` | `sentinel scan` — static posture scanner |
| `0.2.0` | `sentinel discover` — process/network/docker/subnet discovery |
| `0.3.0` | `sentinel mcp scan` — MCP server security audit |

---

### Step 3 — Update the CLI README if needed

File: `cli/README.md`

Add the new command to the Commands section and the What it detects table.
This README becomes the PyPI project description page.

---

### Step 4 — Clean the dist directory

```bash
rm -rf cli/dist/
```

Never upload leftover artifacts from a previous build.

---

### Step 5 — Build the package

```bash
cd cli
/opt/homebrew/bin/python3.11 -m build
cd ..
```

This creates two files in `cli/dist/`:
- `agentsentinel_cli-X.Y.Z-py3-none-any.whl` — the wheel (fast install)
- `agentsentinel_cli-X.Y.Z.tar.gz` — the source distribution

---

### Step 6 — Validate the build

```bash
twine check cli/dist/*
```

Both files must show `PASSED`. If either fails, fix the error before uploading.

Common failures:
- Missing or malformed README
- `description` field in `pyproject.toml` contains special characters

---

### Step 7 — (Optional) Test on TestPyPI first

If this is a major release or you're unsure, upload to TestPyPI first:

```bash
twine upload --repository testpypi cli/dist/*
```

Then install from TestPyPI to verify it works:

```bash
pip install --index-url https://test.pypi.org/simple/ agentsentinel-cli==X.Y.Z
sentinel --version
sentinel scan --help
sentinel mcp scan --help
```

If it looks good, continue to Step 8.

---

### Step 8 — Upload to PyPI

```bash
twine upload cli/dist/*
```

Expected output:
```
Uploading distributions to https://upload.pypi.org/legacy/
Uploading agentsentinel_cli-0.3.0-py3-none-any.whl
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 34.0 kB
Uploading agentsentinel_cli-0.3.0.tar.gz
100% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 27.0 kB

View at: https://pypi.org/project/agentsentinel-cli/0.3.0/
```

---

### Step 9 — Verify the live package

```bash
pip install --upgrade agentsentinel-cli
sentinel --version    # should print 0.3.0
sentinel scan --help
sentinel mcp scan --help
sentinel discover --help
```

---

### Step 10 — Commit the version bump

```bash
git add cli/pyproject.toml cli/README.md
git commit -m "chore: bump cli to vX.Y.Z"
git tag cli-vX.Y.Z
git push && git push --tags
```

---

## Quick reference — the 4 commands you actually run each time

```bash
# 1. Clean
rm -rf cli/dist/

# 2. Build
cd cli && /opt/homebrew/bin/python3.11 -m build && cd ..

# 3. Check
twine check cli/dist/*

# 4. Upload
twine upload cli/dist/*
```

---

## Troubleshooting

### `HTTPError: 400 File already exists`
You cannot upload the same version twice to PyPI. Bump the version number and rebuild.

### `HTTPError: 403 Forbidden`
Your API token is wrong or expired. Check `~/.pypirc` and regenerate the token at
https://pypi.org/manage/account/token/ if needed.

### `twine check FAILED — long description has syntax errors`
The `cli/README.md` contains something PyPI's RST/Markdown renderer can't parse.
Run `twine check cli/dist/*` to see the exact error line.

### `ModuleNotFoundError: No module named 'build'`
```bash
/opt/homebrew/bin/python3.11 -m pip install build
```

### Version not updating after `pip install --upgrade`
PyPI CDN can take 1–2 minutes to propagate. Wait and retry.

---

## Current state (as of 2026-06-01)

- Live on PyPI: `0.3.0`
- PyPI project page: https://pypi.org/project/agentsentinel-cli/
- Build tools: `twine 6.2.0`, `python 3.11.9`, `hatchling` (build backend)
- Dist artifacts after build: `cli/dist/`
- Token stored in: `~/.pypirc` (you need to create this — see one-time setup above)
