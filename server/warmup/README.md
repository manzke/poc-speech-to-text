# Warmup audio

`de_warmup.wav` is a short (~2 s) 16 kHz mono German utterance used to warm the
model at container startup. WhisperLiveKit's `--warmup-file` runs one inference
before the server reports ready, so the Kubernetes readiness probe (see
`helm/stt`) only passes once the model is loaded and the first (slow) decode is
out of the way (§10).

This file is **not** committed as binary here (the repo keeps the tree text-only
for review). Generate or drop in a real clip before building the image:

```bash
# Any 16 kHz mono German wav works. Example using ffmpeg + a source clip:
ffmpeg -i source.(mp3|wav) -ac 1 -ar 16000 -t 2 server/warmup/de_warmup.wav

# Or synthesize silence as a no-op placeholder (warmup still loads the model):
ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 2 server/warmup/de_warmup.wav
```

The Dockerfile fails the build if `de_warmup.wav` is missing, so this is a
required build input. If you prefer no warmup, set `STT_WARMUP_FILE=` empty and
remove `--warmup-file` (the readiness probe will then gate only on the port).
