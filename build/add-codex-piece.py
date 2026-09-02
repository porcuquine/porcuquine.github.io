#!/usr/bin/env python3
"""Add a site piece from a Codex transcript source."""

from __future__ import annotations

import argparse
import html
import importlib.util
import os
import pathlib
import re
import types


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER_PATH = pathlib.Path(__file__).with_name("make-chatgpt-behind-scenes.py")
TURN_RE = re.compile(r"^(User|Assistant) said:\s*$")


def env_path(name: str, default: pathlib.Path) -> pathlib.Path:
    value = os.environ.get(name)
    path = pathlib.Path(value) if value else default
    return path if path.is_absolute() else ROOT / path


SRC_DIR = env_path("SRC_DIR", pathlib.Path("src"))
ESSAY_DIR = env_path("ESSAY_DIR", SRC_DIR / "essays")
BEHIND_DIR = env_path("BEHIND_DIR", SRC_DIR / "behind-the-scenes")
INDEX_PATH = env_path("INDEX_PATH", SRC_DIR / "static" / "index.html")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an Org essay and transcript page from a Codex transcript."
    )
    parser.add_argument("transcript", help="Path to the Codex transcript source.")
    parser.add_argument("--title", required=True, help="Exact piece title.")
    parser.add_argument("--slug", required=True, help="Exact filename slug.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated essay/transcript files.",
    )
    return parser.parse_args()


def load_helper():
    spec = importlib.util.spec_from_file_location("chatgpt_bts_helper", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load helper from {HELPER_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    entry = f"      <li><a href='{href}'>{html.escape(title)}</a></li>\n"
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


def extract_fenced_transcript(document: str) -> tuple[str, str]:
    fence = re.search(r"```text\n(?P<body>.*?)\n```", document, re.DOTALL)
    if not fence:
        return ("", document.strip())

    preface = document[: fence.start()].strip()
    transcript = fence.group("body").strip()
    return (preface, transcript)


def parse_turns(transcript: str) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    current_role: str | None = None
    current_lines: list[str] = []

    def flush_turn() -> None:
        nonlocal current_role, current_lines
        if current_role is not None:
            turns.append(
                {
                    "role": current_role,
                    "text": "\n".join(current_lines).strip(),
                }
            )
        current_role = None
        current_lines = []

    for line in transcript.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = TURN_RE.match(line)
        if match:
            flush_turn()
            current_role = match.group(1).lower()
            continue

        if current_role is not None:
            current_lines.append(line)

    flush_turn()
    if not turns:
        raise ValueError("Could not find any transcript turns.")

    return turns


def first_nonblank_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def extract_entry_text(turns: list[dict[str, str]], title: str) -> str:
    for turn in turns:
        if turn["role"] != "assistant":
            continue

        lines = turn["text"].splitlines()
        first_index = next(
            (index for index, line in enumerate(lines) if line.strip()),
            None,
        )
        if first_index is None:
            continue

        if lines[first_index].strip() == title:
            return "\n".join(lines[first_index + 1 :]).strip()

    raise ValueError(f"Could not find assistant turn beginning with {title!r}.")


def render_nav(back_href: str, back_text: str) -> str:
    return (
        f'<center>[<a href="{html.escape(back_href, quote=True)}">'
        f"{html.escape(back_text, quote=False)}</a>]<br>"
        "[blank space (modulo truth)]<br>"
        "[Codex transcript reconstruction]</center>"
    )


def render_codex_transcript(
    helper,
    title: str,
    nav: str,
    preface: str,
    turns: list[dict[str, str]],
) -> str:
    escaped_title = html.escape(f"{title} - Behind the Scenes", quote=False)
    sections = []
    for turn in turns:
        label = "User said:" if turn["role"] == "user" else "Assistant said:"
        sections.append(
            "\n".join(
                [
                    f'<section class="turn {turn["role"]}">',
                    f"  <h2>{label}</h2>",
                    '  <div class="message">',
                    helper.render_message_text(turn["text"]),
                    "  </div>",
                    "</section>",
                ]
            )
        )

    preface_html = ""
    if preface:
        preface_html = (
            '<section class="provenance">\n'
            "  <h2>Assembly note</h2>\n"
            f"  <div class=\"message\">{helper.render_message_text(preface)}</div>\n"
            "</section>\n"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      --bg: #ffffff;
      --ink: #171717;
      --muted: #6b6b6b;
      --line: #e7e7e7;
      --user: #f4f4f4;
      --code: #f7f7f7;
    }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}

    body > center {{
      padding: 1rem;
      line-height: 1.5;
    }}

    main {{
      max-width: 52rem;
      margin: 0 auto;
      padding: 1rem 1.25rem 4rem;
    }}

    .provenance, .turn {{
      border-top: 1px solid var(--line);
      padding: 1.4rem 0;
    }}

    .provenance h2, .turn h2 {{
      margin: 0 0 0.7rem;
      color: var(--muted);
      font-size: 0.95rem;
      font-weight: 600;
    }}

    .message {{
      max-width: 46rem;
    }}

    .user .message {{
      margin-left: auto;
      border-radius: 1rem;
      background: var(--user);
      padding: 0.9rem 1rem;
    }}

    p, ul, ol, blockquote, pre {{
      margin: 0 0 1rem;
    }}

    p:last-child, ul:last-child, ol:last-child, blockquote:last-child, pre:last-child {{
      margin-bottom: 0;
    }}

    h3, h4 {{
      margin: 1.1rem 0 0.6rem;
    }}

    pre {{
      overflow-x: auto;
      white-space: pre-wrap;
      border-radius: 0.5rem;
      background: var(--code);
      padding: 0.9rem 1rem;
    }}

    code {{
      border-radius: 0.25rem;
      background: var(--code);
      padding: 0.1rem 0.25rem;
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
      font-size: 0.95em;
    }}

    pre code {{
      border-radius: 0;
      background: transparent;
      padding: 0;
      font-size: 1em;
    }}

    blockquote {{
      border-left: 0.2rem solid var(--line);
      padding-left: 1rem;
      color: #333333;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
    }}

    th, td {{
      border: 1px solid var(--line);
      padding: 0.45rem 0.6rem;
      text-align: left;
      vertical-align: top;
    }}

    th {{
      background: var(--code);
      font-weight: 600;
    }}
  </style>
</head>
<body>
  {nav}
  <main>
{preface_html}{chr(10).join(sections)}
  </main>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    helper = load_helper()
    ESSAY_DIR.mkdir(parents=True, exist_ok=True)
    BEHIND_DIR.mkdir(parents=True, exist_ok=True)

    transcript_path = pathlib.Path(args.transcript)
    if not transcript_path.is_absolute():
        transcript_path = ROOT / transcript_path
    document = transcript_path.read_text(encoding="utf-8")
    preface, transcript = extract_fenced_transcript(document)
    turns = parse_turns(transcript)
    entry_text = extract_entry_text(turns, args.title)

    org_name = f"{args.slug}.org"
    html_name = f"{args.slug}.html"
    behind_name = f"{args.slug}-behind-the-scenes.html"
    org_path = ESSAY_DIR / org_name
    behind_path = BEHIND_DIR / behind_name
    ensure_new_paths([org_path, behind_path], args.force)

    org_path.write_text(
        helper.render_org_essay(
            f"# {args.title}\n\n{entry_text}",
            args.title,
            behind_name,
        ),
        encoding="utf-8",
    )

    behind_path.write_text(
        render_codex_transcript(
            helper,
            args.title,
            render_nav(html_name, args.title),
            preface,
            turns,
        ),
        encoding="utf-8",
    )

    append_makefile_item(ROOT / "Makefile", "ORG_FILES", org_name)
    append_makefile_item(ROOT / "Makefile", "BEHIND_SCENES_HTML", behind_name)
    append_index_item(INDEX_PATH, html_name, args.title)

    print(f"Added {args.title}")
    print(f"  transcript source: {transcript_path.relative_to(ROOT)}")
    print(f"  essay: {org_path.relative_to(ROOT)}")
    print(f"  behind the scenes: {behind_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
