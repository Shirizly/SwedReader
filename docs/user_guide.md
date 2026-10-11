# User guide

Run commands from the project root. For Python commands, use the `translatepipe` Conda environment:

```bash
conda run -n translatepipe python ...
```

## Read stories

Start the local reader:

```bash
conda run -n translatepipe python -m pipeline serve
```

Open <http://127.0.0.1:8765/> in a browser. The local server shows public documents and any private documents available on this machine. Use this server to test audio seeking; it supports the byte-range requests needed by MP3 playback.

## Review translation and alignment flags

List the available document IDs:

```bash
conda run -n translatepipe python scripts/view_review.py --list
```

Generate and open a document's HTML review report:

```bash
conda run -n translatepipe python scripts/view_review.py runeberg-org-kristleg-0113-html
```

The script regenerates the report from the latest processed JSON and opens it in your browser. Reports are also written to `data/private/review/<document-id>.html`; the accompanying JSON file contains the same findings as structured data. These report files are private and are not published.

To regenerate a report without opening a browser, add `--no-open`. To use the existing pipeline command instead, run:

```bash
conda run -n translatepipe python -m pipeline review runeberg-org-kristleg-0113-html
```

The `review` command only regenerates the files; open the HTML report in a browser to read it. Available status categories include weak alignments, wide alignments, conflicts, and differing alignments. Review each flagged word or group in its Swedish and English sentence context.

## Generate a local Swedish speech sample

Piper and the default `sv_SE-alma-medium` voice synthesize Swedish locally. The first run downloads the voice model and its configuration into the ignored `data/private/tts/voices/` directory; later runs use that local copy. Document text and audio remain local and are not published.

Generate a sample from the first five body sentences of the hand-made fixture:

```bash
conda run -n translatepipe python scripts/generate_audio.py tests/fixtures/sample-fixture.json --sentences 5
```

The default WAV destination is `data/private/tts/samples/<document>_sv_SE-alma-medium.wav`. The sample generated during setup is [sample-fixture_sv_SE-alma-medium.wav](../data/private/tts/samples/sample-fixture_sv_SE-alma-medium.wav) (mono, 22.05 kHz). Use `--output <path>` to choose another destination or `--voice <voice-name>` to select another Piper voice.

To attach sentence-timed audio to an eligible public document, run:

```bash
conda run -n translatepipe python scripts/generate_audio.py reader/content/<document-id>.json --attach
conda run -n translatepipe python -m pipeline publish
```

`--attach` synthesizes every sentence independently, joins the audio with brief pauses, records exact sentence start/end times in the JSON, then compresses the public track to MP3. This avoids a second speech-recognition model for alignment and keeps files small enough to publish. Use `--sentences N` only when intentionally creating an excerpt. The generated public MP3 is placed directly in `reader/content/audio/`; `pipeline publish` validates the content and rebuilds its index without making another copy. The reader's sticky top player offers play/pause, stop, previous/next sentence, seek, and a compact speed button that opens a tick-marked horizontal slider from 0.5× through 2.0× in 0.1 increments, and highlights/scrolls with playback.
