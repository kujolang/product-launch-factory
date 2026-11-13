# Video adapter

The launch coordinator calls the existing VideoOps Factory in a private job directory. It supplies the campaign facts and verified product screenshots. Producer, Creative Director, Asset Scout, Editor and Critic make real provider calls through the pinned factory. The factory renders the screenshots and Kujo bumper through its trusted HTML template.

The job copies tracked source and registered assets. It shares installed dependencies through read-only-in-practice links; these are trusted tools, not a security sandbox. It copies the existing provider login into a private runtime directory. No provider keys belong in the repo or campaign export.

One small template overlay removes the original zoom and opacity entrance effects so evidence and the bumper appear on their first frame. The receipt records the pinned commit, original file hashes, and overlay hash. The modified job is never described as pristine upstream source.

## Requirements

Install and authenticate the pinned VideoOps Factory first. Its setup provides the matching Node packages, Kujo runtime, canonical VideoOps Python environment, and pinned agent/workflow contracts. FFmpeg, FFprobe and a working HyperFrames browser renderer must be available. Follow that factory's setup and login instructions; this adapter does not install global software.

Run `node src/video.mjs /absolute/request.json`. Standard output contains one JSON result. The workspace holds command logs.

```json
{
  "workspace": "/work/launch/video",
  "factoryRoot": "/work/dependencies/videoops-factory",
  "title": "A launch worth showing",
  "objective": "Show the benefit, then the actual product, then the Kujo bumper.",
  "duration": 24,
  "facts": [{"text": "The product exports a review package.", "source": "product-contract.json"}],
  "images": [{"id": "product-floor", "path": "/work/floor.png", "sha256": "REPLACE_WITH_SHA256", "source": "Actual browser capture"}],
  "narration": {"enabled": false}
}
```

Use one to four PNG/JPEG evidence images, a duration of 3–60 seconds, and facts with source references. Images are checked before any model work. New facts, image bytes or narration inputs require a new video workspace.

## Narration

Narration is optional. The upstream runner produces silent visuals. A separate, explicit adapter step adds authorized speech, then asks the canonical Media Generator and Critic to review the handoffs. It retains the original provider bytes, normalized source, final mix and receipt. The editable composition includes the same speech track as the final MP4.

For new speech, set `enabled: true`, `mediaWorkspace`, `requestPath`, `authorizationPath`, and `authorize: true`. All paths must be absolute. Prepare these files with the canonical VideoOps media workflow, including the approved asset registry, exact text hash, rights evidence and provider entitlement evidence. The adapter accepts one speech call, at most 500 text characters and 500 credits, included allowance only, with zero monetary overage. It never reads or prints the credential itself. The canonical runtime resolves the configured credential reference and enforces the exact request authorization.

For an existing recording, supply `enabled: true`, `mediaWorkspace`, `receiptPath`, and optionally `audioPath` and `sha256`. The recording must have a successful canonical speech or local import receipt and explicit usage approval in its source registry. Every original and derivative hash must match. Fixture receipts are rejected.

The first campaign uses ElevenLabs Siren with `eleven_v4`. Its closing line spells the domain for speech as “Koo-joe LANG dot A I,” where LANG rhymes with hang. Public copy keeps `kujolang.ai`. A text spelling is not proof of pronunciation: listening is still required.

Speech starts 0.2 seconds into the film. It must leave at least 0.4 seconds at the end. The adapter normalizes the track to a target of −16 LUFS and −2 dBTP and adds silence to fill the film. It never cuts spoken words to fit. To reuse a music bed, supply `music: {path, sha256, source, rights}` with an absolute path and explicit rights. The adapter checks its bytes, mixes it quietly under the voice, and fades the last 0.4 seconds. Music can also accompany a film without speech. There is no automatic music generation.

## Review and reuse

The output remains `REVIEW_INCOMPLETE`. Technical checks cover hashes, dimensions, frame rate, duration, audio presence, full media decoding and an independent text-based critic call. These checks do not prove that a viewer can read the shots or hear the closing line clearly. Full playback and listening must approve the exact candidate hash before release.

The result includes `exportRoot`, a directory containing the MP4, editable composition and public evidence. Copy this directory when sealing a launch. It also includes the child run ID, candidate hash, input hash inventory, artifact hash inventory and paths to the child state, events, review and composition. A factory floor can read `paths.state` and tail `paths.events` for actual stage status. During the initial run, the child lives beneath `workspace/factory-job/.runtime/runs/`.

A completed matching request returns its checked result without rerunning providers. An existing successful silent render can continue to narration after an interrupted adapter step. A blocked child is not silently rerolled: inspect its logs and start a new attempt. Cached speech receipts must match the request fingerprint; uncertain or failed acquisition is never retried automatically. A workspace lock prevents concurrent runs. If a process died, confirm its recorded PID is no longer running before removing `.video-lock`.

The `files` inventory contains public production evidence. The `inputs` inventory binds narration requests and authorizations by hash without exporting credentials or login files. Keep the entire `.runtime` directory private.
