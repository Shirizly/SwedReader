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

Open <http://127.0.0.1:8765/> in a browser. The local server shows public documents and any private documents available on this machine.

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
