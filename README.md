# porcuquine.github.io

This repository is the source for the site. It is not published directly.
GitHub Pages publishes the artifact built from `public/` by the Pages workflow.

## Layout

- `src/*.org`: source essays written in Org Mode
- `src/*.html`: hand-authored static pages that are copied into the published site
- `src/*-codex-transcript.txt`: raw Codex transcript sources for reconstructed process pages
- `build/export-org.el`: batch Org-to-HTML exporter with minimal site defaults
- `Makefile`: builds the publishable site into `public/`
- `public/`: generated site artifact; ignored locally and rebuilt as needed
- `zips/`: generated zip archives; ignored locally and rebuilt as needed
- `.github/workflows/pages.yml`: GitHub Pages build/deploy workflow

## Build

Rebuild the published site locally:

```sh
make
```

This does two things:

1. exports the Org files listed in `Makefile` from `src/` to same-named `*.html` in `public/`
2. copies the hand-authored HTML pages listed in `Makefile` from `src/` into `public/`

To remove generated output:

```sh
make clean
```

## Zip Archive

Generate a zip archive from the current built site:

```sh
make zip
```

This rebuilds `public/` as needed and writes a date-stamped archive to
`zips/porcuquine-site-YYYY-MM-DD.zip`. The `zips/` directory is ignored by git.
`make latest-zip` is an alias for the same task.

## Local Preview

Build the site and serve `public/` locally:

```sh
make
python3 -m http.server --directory public 8000
```

Then open:

```text
http://localhost:8000/
```

This is the reliable preview path. It uses the same generated files that the
GitHub Pages workflow deploys. Do not preview by opening `src/index.html`
directly; generated Org pages such as `committee.html` exist under `public/`,
not beside the source `src/index.html`.

## GitHub Pages

The site is intended to publish through GitHub Actions, not from the repository
root and not from `/docs`.

Repository setting to use:

- Pages source: `GitHub Actions`

The workflow installs Emacs on the runner, runs `make`, and deploys `public/`.

## Writing A New Org Essay

1. Add a new `src/name.org` file.
2. Keep the Org source minimal unless you need custom HTML.
3. Add the source and any companion HTML page to `Makefile`.
4. Add the rendered page to `src/index.html` when it should appear on the site.
5. Run `make`.
6. Preview from `public/`.
7. Commit the source changes. Do not commit `public/`.

## Behind-The-Scenes Link Pattern

Pieces with an associated ChatGPT transcript use this pattern:

- the rendered essay links to a separate “Behind the scenes” page
- the behind-the-scenes page links back to the rendered essay
- the behind-the-scenes page also links to the original ChatGPT conversation

### Transcript Helper

Use the helper to generate a behind-the-scenes page from a ChatGPT share URL:

```sh
python3 build/make-chatgpt-behind-scenes.py \
  --url "https://chatgpt.com/share/..." \
  --output src/name-behind-the-scenes.html \
  --back-href name.html \
  --back-text "Essay Title" \
  --title "Essay Title - Behind the Scenes"
```

If the share page has already been saved locally, use `--input saved.html`
instead of `--url` and pass `--source-url` with the original ChatGPT share URL.
The helper preserves older rendered ChatGPT share HTML when available; for newer
ChatGPT share pages, it extracts the embedded conversation data and emits a
self-contained static transcript. The static transcript renderer handles the
small Markdown subset commonly emitted by ChatGPT, including emphasis, inline
code, lists, and blockquotes.

If the final assistant turn contains the essay text, the helper can also create
the Org source file:

```sh
python3 build/make-chatgpt-behind-scenes.py \
  --url "https://chatgpt.com/share/..." \
  --output src/name-behind-the-scenes.html \
  --back-href name.html \
  --back-text "Essay Title" \
  --title "Essay Title - Behind the Scenes" \
  --essay-output src/name.org \
  --essay-behind-href name-behind-the-scenes.html
```

The Org exporter uses the final ChatGPT writing block when one is present,
infers the title from its top-level Markdown heading, adds the site nav, and
appends the behind-the-scenes link.

After generating the files, add any generated Org essay to `ORG_FILES` and the
transcript page to `STATIC_HTML` in `Makefile` so they are built into `public/`.

For the common case where the title and slug can be inferred, use the
repo-specific wrapper:

```sh
make add-chatgpt-piece URL="https://chatgpt.com/share/..."
```

This creates `src/slug.org` and `src/slug-behind-the-scenes.html`, updates
`Makefile`, and adds the entry to `src/index.html`. The wrapper accepts the same
URL directly:

```sh
python3 build/add-chatgpt-piece.py "https://chatgpt.com/share/..."
```

Use `--title`, `--slug`, or `--force` with the Python wrapper when inference or
overwrite behavior needs to be controlled.

### Codex Transcript Helper

Some pieces use a reconstructed Codex transcript instead of a shared ChatGPT
conversation. Keep the raw transcript as `src/name-codex-transcript.txt`; it is
source material, not a public page by itself.

The transcript source should contain a fenced `text` block whose turns use exact
labels:

```text
User said:

...

Assistant said:

Piece Title

Finished piece body...
```

The publishable piece must appear as an assistant turn whose first nonblank line
is exactly the piece title. Add it with:

```sh
make add-codex-piece \
  TRANSCRIPT=src/name-codex-transcript.txt \
  TITLE="Piece Title" \
  SLUG=name
```

This creates `src/name.org` and `src/name-behind-the-scenes.html`, updates
`Makefile`, and adds the entry to `src/index.html`. The behind-the-scenes page
marks the provenance as a Codex transcript reconstruction rather than a
ChatGPT-source link.

## Notes

- Root-level generated Org exports are no longer kept in the repository.
- If GitHub Pages ever drifts from local output, first compare the local build
  with the workflow logs, especially the Emacs version on the runner.
