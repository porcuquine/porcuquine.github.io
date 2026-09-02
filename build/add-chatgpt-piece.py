#!/usr/bin/env python3
"""Add a site piece from a ChatGPT share URL.

This wraps make-chatgpt-behind-scenes.py with the repo-specific bookkeeping:
it infers the title/slug, writes the Org essay and transcript page, and updates
Makefile plus index.html.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pathlib
import re
import types
import unicodedata


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER_PATH = pathlib.Path(__file__).with_name("make-chatgpt-behind-scenes.py")


def env_path(name: str, default: pathlib.Path) -> pathlib.Path:
    value = os.environ.get(name)
    path = pathlib.Path(value) if value else default
    return path if path.is_absolute() else ROOT / path


SRC_DIR = env_path("SRC_DIR", pathlib.Path("src"))
ESSAY_DIR = env_path("ESSAY_DIR", SRC_DIR / "essays")
BEHIND_DIR = env_path("BEHIND_DIR", SRC_DIR / "behind-the-scenes")
INDEX_PATH = env_path("INDEX_PATH", SRC_DIR / "static" / "index.html")


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error

    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an Org essay and transcript page from a ChatGPT share URL."
    )
    parser.add_argument("url", help="ChatGPT share URL.")
    parser.add_argument("--title", help="Override inferred title.")
    parser.add_argument("--slug", help="Override inferred filename slug.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated essay/transcript files.",
    )
    parser.add_argument(
        "--literal-writing-math",
        action="append",
        default=[],
        metavar="N",
        type=positive_int,
        help=(
            "Preserve raw math markup in 1-based writing block N. Repeat for "
            "multiple blocks when mirroring a known source rendering failure."
        ),
    )
    parser.add_argument(
        "--subtitle",
        help="Optional Org subtitle to add below the essay title.",
    )
    return parser.parse_args()


def load_helper():
    spec = importlib.util.spec_from_file_location("chatgpt_bts_helper", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load helper from {HELPER_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_title.lower()).strip("-")
    if not slug:
        raise ValueError(f"Could not derive a slug from title: {title!r}")
    return slug


def last_assistant_text(helper, document: str) -> tuple[str | None, str]:
    compact_share = helper.extract_compact_share(document)
    if not compact_share:
        raise ValueError("Could not extract compact ChatGPT conversation data.")

    extracted_title, messages = compact_share
    message = next(
        (
            message
            for message in reversed(messages)
            if message["role"] == "assistant" and isinstance(message.get("text"), str)
        ),
        None,
    )
    if message is None:
        raise ValueError("Could not find an assistant turn to export.")

    text = str(message["text"])
    citation_replacements = message.get("citation_replacements")
    if not isinstance(citation_replacements, dict):
        citation_replacements = {}
    text = helper.replace_chatgpt_citations(text, citation_replacements)
    return extracted_title, text


def final_piece_text(helper, text: str, title: str | None) -> str:
    return helper.extract_final_piece_text(text, title)


def append_makefile_item(path: pathlib.Path, variable: str, item: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.startswith(f"{variable} :=")),
        None,
    )
    if start is None:
        raise ValueError(f"Could not find {variable} in {path}")

    end = start + 1
    while end < len(lines) and (lines[end].startswith("\t") or lines[end].startswith(" ")):
        end += 1

    block = lines[start + 1 : end]
    if any(line.strip().rstrip("\\").strip() == item for line in block):
        return

    if block:
        last_index = end - 1
        if not lines[last_index].rstrip().endswith("\\"):
            lines[last_index] = lines[last_index].rstrip() + " \\"

    lines.insert(end, f"\t{item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_index_item(path: pathlib.Path, href: str, title: str) -> None:
    document = path.read_text(encoding="utf-8")
    if href in document:
        return

    entry = f"      <li><a href='{href}'>{title}</a></li>\n"
    marker = "    </ul>"
    if marker not in document:
        raise ValueError(f"Could not find index list marker in {path}")

    document = document.replace(marker, entry + marker, 1)
    path.write_text(document, encoding="utf-8")


def ensure_new_paths(paths: list[pathlib.Path], force: bool) -> None:
    if force:
        return

    existing = [str(path.relative_to(ROOT)) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing file(s): " + ", ".join(existing)
        )


def main() -> int:
    args = parse_args()
    helper = load_helper()
    ESSAY_DIR.mkdir(parents=True, exist_ok=True)
    BEHIND_DIR.mkdir(parents=True, exist_ok=True)

    fetch_args = types.SimpleNamespace(input=None, url=args.url)
    document = helper.read_document(fetch_args)
    extracted_title, assistant_text = last_assistant_text(helper, document)
    essay_text = final_piece_text(helper, assistant_text, args.title)

    title = args.title or helper.infer_markdown_title(essay_text, extracted_title)
    slug = args.slug or slugify(title)

    org_name = f"{slug}.org"
    html_name = f"{slug}.html"
    transcript_name = f"{slug}-behind-the-scenes.html"
    org_path = ESSAY_DIR / org_name
    transcript_path = BEHIND_DIR / transcript_name
    ensure_new_paths([org_path, transcript_path], args.force)

    org_path.write_text(
        helper.render_org_essay(essay_text, title, transcript_name, args.subtitle),
        encoding="utf-8",
    )

    render_args = types.SimpleNamespace(
        url=args.url,
        source_url=None,
        back_href=html_name,
        back_text=title,
        title=f"{title} - Behind the Scenes",
        literal_writing_math=args.literal_writing_math,
    )
    transcript_path.write_text(
        helper.render_document(document, render_args),
        encoding="utf-8",
    )

    append_makefile_item(ROOT / "Makefile", "ORG_FILES", org_name)
    append_makefile_item(ROOT / "Makefile", "BEHIND_SCENES_HTML", transcript_name)
    append_index_item(INDEX_PATH, html_name, title)

    print(f"Added {title}")
    print(f"  essay: {org_name}")
    print(f"  transcript: {transcript_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
