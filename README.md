# porcuquine.github.io

This repository is the source for the site. It is not published directly.
GitHub Pages publishes the artifact built from `public/` by the Pages workflow.

## Layout

- `*.org`: source essays written in Org Mode
- `*.html` in the repo root: hand-authored static pages that are copied into the published site
- `build/export-org.el`: batch Org-to-HTML exporter with minimal site defaults
- `Makefile`: builds the publishable site into `public/`
- `public/`: generated site artifact; ignored locally and rebuilt as needed
- `.github/workflows/pages.yml`: GitHub Pages build/deploy workflow

## Build

Rebuild the published site locally:

```sh
make
```

This does two things:

1. exports the Org files listed in `Makefile` to same-named `*.html` in `public/`
2. copies the hand-authored HTML pages listed in `Makefile` into `public/`

To remove generated output:

```sh
make clean
```

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
GitHub Pages workflow deploys. Do not preview by opening the repository-root
`index.html` directly; generated Org pages such as `committee.html` exist under
`public/`, not beside the source `index.html`.

## GitHub Pages

The site is intended to publish through GitHub Actions, not from the repository
root and not from `/docs`.

Repository setting to use:

- Pages source: `GitHub Actions`

The workflow installs Emacs on the runner, runs `make`, and deploys `public/`.

## Writing A New Org Essay

1. Add a new `name.org` file in the repo root.
2. Keep the Org source minimal unless you need custom HTML.
3. Add the source and any companion HTML page to `Makefile`.
4. Add the rendered page to `index.html` when it should appear on the site.
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
  --output name-behind-the-scenes.html \
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
  --output name-behind-the-scenes.html \
  --back-href name.html \
  --back-text "Essay Title" \
  --title "Essay Title - Behind the Scenes" \
  --essay-output name.org \
  --essay-behind-href name-behind-the-scenes.html
```

The Org exporter uses the final ChatGPT writing block when one is present,
infers the title from its top-level Markdown heading, adds the site nav, and
appends the behind-the-scenes link.

After generating the files, add any generated Org essay to `ORG_FILES` and the
transcript page to `STATIC_HTML` in `Makefile` so they are built into `public/`.

## Notes

- Root-level generated Org exports are no longer kept in the repository.
- If GitHub Pages ever drifts from local output, first compare the local build
  with the workflow logs, especially the Emacs version on the runner.
