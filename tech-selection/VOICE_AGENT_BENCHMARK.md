# Voice Agent Benchmark

This benchmark compares Aliyun Qwen-Omni Realtime and Volcengine Doubao end-to-end realtime speech for the parking-lot gatekeeper scenario.

## What It Tests

1. First response latency and total completion time.
2. Visitor information extraction.
3. Human-friendly gatekeeper wording.
4. WeChat/WeCom-style structured payload generation.
5. Correction handling as an automated approximation of interruption recovery.

True barge-in still needs a real phone or browser audio loop test because it depends on playback, microphone capture, VAD, and whether the provider stops speaking when interrupted.

## Setup

Edit `voice-agent-benchmark.local.mjs` and fill:

```js
const DASHSCOPE_API_KEY = "your aliyun key";
const VOLC_API_KEY = "your volc key";
```

The script is gitignored. Do not commit real keys.

## Run

Run both providers and all tests:

```bash
node voice-agent-benchmark.local.mjs
```

Run one provider:

```bash
node voice-agent-benchmark.local.mjs --provider aliyun
node voice-agent-benchmark.local.mjs --provider volc
```

Run one test:

```bash
node voice-agent-benchmark.local.mjs --test extraction_json
```

Upload generated audio as fast as possible instead of pacing it like a real call:

```bash
node voice-agent-benchmark.local.mjs --fast-audio true
```

## Outputs

Each run writes:

- `benchmark-results/<run-id>/results.jsonl`
- `benchmark-results/<run-id>/summary.md`

The most important timing fields are:

- `first_text_after_audio_done_ms`: time from the end of user speech upload to first model text.
- `total_after_audio_done_ms`: time from the end of user speech upload to completed model response.

For your requirement, separately measure real phone flow as:

`agent starts speaking -> WeChat/WeCom message sent`

That is the only number that directly maps to the 25-second acceptance requirement.
