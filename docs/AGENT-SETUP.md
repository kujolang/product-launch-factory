# Set up a launch factory

Give this guide to your agent with a product brief and permission to use your model account. The factory prepares local artifacts for review. It does not publish a campaign.

## Install

Use macOS or Linux with Git, Python 3.10 or newer, Node 26.12.1, npm and FFmpeg (including ffprobe). Chromium needs its usual Linux system libraries. Use the package manager for your operating system to install missing prerequisites; do not claim that cloning the repository installs them.

```sh
git clone https://github.com/kujolang/product-launch-factory.git
cd product-launch-factory
npm ci
npm run setup
npm run login
npm run doctor
```

Setup fetches the four factory revisions in `sources.lock.json` and their pinned tools. It does not generate content. Login uses Codex authentication; `npm run login -- --reuse-existing` copies an existing login into the private factory home without copying hooks, tools or instructions. Model access and sufficient account allowance remain necessary for live campaigns.

## Run the supplied example

```sh
npm run factory -- run examples/webops-launch.json
npm start
```

Open `http://127.0.0.1:4384`. The supplied brief produces a silent video by default. See [video configuration](VIDEO.md) to add explicitly authorized narration. Runtime files, credentials and intermediate work stay under `.runtime`.

The controller prints a run ID. Use it to inspect or resume that campaign:

```sh
npm run factory -- status
npm run factory -- resume RUN_ID
npm run factory -- verify RUN_ID
```

A blocked stage is not a successful campaign. Read its error and `.runtime/runs/RUN_ID/logs`. Resume preserves completed handoffs after checking their hashes. If inputs change, create a new run. Never edit a frozen snapshot or remove a failed review to force the next stage.

## Adapt it to your product

Use the [brief schema](../schemas/launch-brief.json). Copy the example brief and replace its local sources, evidence and visuals. Keep all referenced paths inside the brief's directory. Sources must be captured UTF-8 text with a public HTTPS provenance URL. Use an exported Software Factory evidence package (`software-export`) or a retained WebOps package (`webops-package`). The source station verifies existing evidence; it does not build a new product.

Set the audience, objective, voice and constraints. The controller stays the same. Keep performance claims tied to observations and state the limits of the source evidence. Supply up to three PNG or JPEG product images with provenance and reuse rights. WebOps adds a screenshot of the generated landing page.

Publishing House creates reviewed article and adaptation drafts. WebOps checks the static landing page. VideoOps compiles a bounded composition using registered assets. Models propose data; they do not receive a general shell for your source material.

## Review

Inspect every deliverable, source claim and check result. Play the whole video with sound, including the ending. Technical checks do not establish pronunciation, pacing or editorial quality.

After review, record the exact package hash printed by `verify`:

```sh
npm run factory -- approve RUN_ID --package-sha256 EXACT_HASH --reviewer 'YOUR NAME' --video-reviewed
```

This records local approval only. Changed, added or deleted package files invalidate the reviewed version. Deployment requires a separate workflow and explicit permission.
