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

1. exports every root-level `*.org` file to same-named `*.html` in `public/`
2. copies the root-level hand-authored HTML pages into `public/`

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
GitHub Pages workflow deploys.

## GitHub Pages

The site is intended to publish through GitHub Actions, not from the repository
root and not from `/docs`.

Repository setting to use:

- Pages source: `GitHub Actions`

The workflow installs Emacs on the runner, runs `make`, and deploys `public/`.

## Writing A New Org Essay

1. Add a new `name.org` file in the repo root.
2. Keep the Org source minimal unless you need custom HTML.
3. Run `make`.
4. Preview from `public/`.
5. Commit the source changes. Do not commit `public/`.

## Behind-The-Scenes Link Pattern

The older interactive essay uses this pattern:

- the rendered essay links to a separate “Behind the scenes” page
- the behind-the-scenes page links back to the rendered essay
- the behind-the-scenes page also links to the original ChatGPT conversation

The current essay follows the same pattern:

- the main essay is Org and exports to HTML
- the transcript page is a hand-authored HTML placeholder

### Current Files

- `prompting-as-essay.org`
  Adds the top `[Disordered List]` link, includes the short “first inking”
  sentence as an epigraph, and adds the bottom `[Behind the scenes]` link.

- `in-context-learning-exploration.html`
  Is the transcript page. It links back to `prompting-as-essay.html` and
  includes the original ChatGPT conversation URL.

### Placeholder To Replace

The transcript page already contains the literal transcript HTML and the current
shared conversation URL.

## Notes

- Root-level generated Org exports are no longer kept in the repository.
- If GitHub Pages ever drifts from local output, first compare the local build
  with the workflow logs, especially the Emacs version on the runner.
