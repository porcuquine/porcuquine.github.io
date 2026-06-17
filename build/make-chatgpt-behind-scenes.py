#!/usr/bin/env python3
"""Create a local behind-the-scenes page from ChatGPT share HTML.

Older rendered share pages are preserved and wrapped with the site's small
navigation block. Newer app-shell share pages are converted into a static
transcript from their embedded conversation data.
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re
import sys
import urllib.request


BODY_RE = re.compile(r"(<body\b[^>]*>\s*)", re.IGNORECASE)
RENDERED_TRANSCRIPT_RE = re.compile(r'data-testid="conversation-turn-\d+"')
STREAM_ENQUEUE_RE = re.compile(
    r"window\.__reactRouterContext\.streamController\.enqueue\((.*?)\);",
    re.DOTALL,
)
LOCAL_NAV_RE = re.compile(
    r"(<body\b[^>]*>\s*)"
    r"<center>\s*\[<a href=(['\"]).*?\2>.*?</a>\]\s*<br>\s*"
    r"\[blank space \(modulo truth\)\]\s*<br>\s*"
    r"\[(?:<a href=(['\"]).*?\3>ChatGPT Source</a>|ChatGPT Source pending)\]"
    r"\s*</center>\s*",
    re.IGNORECASE | re.DOTALL,
)
TITLE_RE = re.compile(r"(<title>)(.*?)(</title>)", re.IGNORECASE | re.DOTALL)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
ORDERED_LIST_RE = re.compile(r"^\d+[.)]\s+(.+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Wrap a ChatGPT share page as a site behind-the-scenes page."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="ChatGPT share URL to fetch.")
    source.add_argument("--input", help="Saved ChatGPT share HTML to wrap.")
    parser.add_argument("--output", required=True, help="Destination HTML path.")
    parser.add_argument("--back-href", required=True, help="Essay page href.")
    parser.add_argument("--back-text", required=True, help="Essay page link text.")
    parser.add_argument("--title", help="Optional replacement HTML title.")
    parser.add_argument(
        "--source-url",
        help="Source URL for the ChatGPT Source link. Defaults to --url.",
    )
    parser.add_argument(
        "--essay-output",
        help="Optional Org file to create from the final assistant turn.",
    )
    parser.add_argument(
        "--essay-title",
        help="Optional title for --essay-output. Defaults to the final H1.",
    )
    parser.add_argument(
        "--essay-behind-href",
        help="Optional behind-the-scenes link to append to --essay-output.",
    )
    return parser.parse_args()


def read_document(args: argparse.Namespace) -> str:
    if args.input:
        return pathlib.Path(args.input).read_text(encoding="utf-8")

    request = urllib.request.Request(
        args.url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; porcuquine-site-builder/1.0)"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def replace_title(document: str, title: str | None) -> str:
    if not title:
        return document

    escaped_title = html.escape(title, quote=False)
    if TITLE_RE.search(document):
        return TITLE_RE.sub(rf"\1{escaped_title}\3", document, count=1)

    head_re = re.compile(r"(<head\b[^>]*>\s*)", re.IGNORECASE)
    return head_re.sub(rf"\1<title>{escaped_title}</title>\n", document, count=1)


def build_nav(args: argparse.Namespace) -> str:
    source_url = args.source_url or args.url
    source_link = "ChatGPT Source pending"
    if source_url:
        source_link = (
            f'<a href="{html.escape(source_url, quote=True)}">ChatGPT Source</a>'
        )

    return (
        f'<center>[<a href="{html.escape(args.back_href, quote=True)}">'
        f"{html.escape(args.back_text, quote=False)}</a>]<br>"
        f"[blank space (modulo truth)]<br>"
        f"[{source_link}]</center>"
    )


def inject_nav(document: str, nav: str) -> str:
    if LOCAL_NAV_RE.search(document):
        return LOCAL_NAV_RE.sub(rf"\1{nav}\n  ", document, count=1)

    if not BODY_RE.search(document):
        raise ValueError("Could not find opening <body> tag in source HTML.")

    return BODY_RE.sub(rf"\1{nav}\n  ", document, count=1)


def extract_stream_array(document: str) -> list | None:
    for match in STREAM_ENQUEUE_RE.finditer(document):
        try:
            decoded = json_loads(match.group(1))
        except ValueError:
            continue

        first_line = decoded.strip().splitlines()[0] if decoded.strip() else ""
        if not first_line.startswith("["):
            continue

        try:
            return json_loads(first_line)
        except ValueError:
            continue

    return None


def json_loads(value: str):
    import json

    return json.loads(value)


def render_inline_markdown(text: str) -> str:
    code_spans: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        code_spans.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00CODE{len(code_spans) - 1}\x00"

    rendered = INLINE_CODE_RE.sub(stash_code, text)
    rendered = html.escape(rendered, quote=False)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", rendered)

    for index, code_span in enumerate(code_spans):
        rendered = rendered.replace(f"\x00CODE{index}\x00", code_span)

    return rendered


def render_blockquote(lines: list[str]) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush_quote_paragraph() -> None:
        if not paragraph:
            return

        text = "\n".join(paragraph).strip()
        paragraph.clear()
        if text:
            blocks.append(
                f"<p>{render_inline_markdown(text).replace(chr(10), '<br>')}</p>"
            )

    for line in lines:
        quote_line = line[1:]
        if quote_line.startswith(" "):
            quote_line = quote_line[1:]

        if quote_line.strip():
            paragraph.append(quote_line)
        else:
            flush_quote_paragraph()

    flush_quote_paragraph()
    return f"<blockquote>\n{chr(10).join(blocks)}\n</blockquote>"


def extract_chatgpt_writing_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith(":::writing"):
            current = []
            continue

        if current is not None and line.strip() == ":::":
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)
            current = None
            continue

        if current is not None:
            current.append(line)

    return blocks


def strip_chatgpt_writing_markers(text: str) -> str:
    lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith(":::writing") or line.strip() == ":::":
            continue
        lines.append(line)

    return "\n".join(lines).strip()


def infer_markdown_title(text: str, fallback: str | None = None) -> str:
    for line in text.splitlines():
        match = re.match(r"#\s+(.+)$", line.strip())
        if match:
            return match.group(1).strip()

    return fallback or "Untitled"


def markdown_inline_to_org(text: str) -> str:
    code_spans: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        code_spans.append(f"~{match.group(1)}~")
        return f"\x00CODE{len(code_spans) - 1}\x00"

    rendered = INLINE_CODE_RE.sub(stash_code, text)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"*\1*", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"/\1/", rendered)

    for index, code_span in enumerate(code_spans):
        rendered = rendered.replace(f"\x00CODE{index}\x00", code_span)

    return rendered


def markdown_to_org_body(text: str, title: str) -> str:
    lines = strip_chatgpt_writing_markers(text).splitlines()
    body: list[str] = []
    in_code = False
    in_quote = False
    skipped_title = False

    def close_quote() -> None:
        nonlocal in_quote
        if in_quote:
            body.append("#+end_quote")
            in_quote = False

    for line in lines:
        if line.startswith("```"):
            close_quote()
            body.append("#+end_example" if in_code else "#+begin_example")
            in_code = not in_code
            continue

        if in_code:
            body.append(line)
            continue

        heading = re.match(r"(#{1,6})\s+(.+)$", line)
        if heading:
            close_quote()
            heading_text = heading.group(2).strip()
            if not skipped_title and len(heading.group(1)) == 1 and heading_text == title:
                skipped_title = True
                continue

            level = "*" * len(heading.group(1))
            body.append(f"{level} {markdown_inline_to_org(heading_text)}")
            continue

        if line.startswith(">"):
            if not in_quote:
                body.append("#+begin_quote")
                in_quote = True

            quote_line = line[1:]
            if quote_line.startswith(" "):
                quote_line = quote_line[1:]
            body.append(markdown_inline_to_org(quote_line))
            continue

        close_quote()
        body.append(markdown_inline_to_org(line))

    if in_code:
        body.append("#+end_example")
    close_quote()
    return "\n".join(body).strip()


def render_org_essay(
    text: str,
    title: str,
    behind_href: str | None,
) -> str:
    body = markdown_to_org_body(text, title)
    parts = [
        f"#+TITLE: {title}",
        (
            "#+HTML_HEAD_EXTRA: "
            "<style>.site-nav{position:fixed;top:0.5rem;left:0.5rem;z-index:1000;}</style>"
        ),
        "",
        "#+begin_export html",
        '<div class="site-nav">[<a href="index.html">Disordered List</a>]</div>',
        "#+end_export",
        "",
        body,
    ]

    if behind_href:
        parts.extend(
            [
                "",
                "#+begin_export html",
                f'<center>[<a href="{behind_href}">Behind the scenes</a>]</center>',
                "#+end_export",
            ]
        )

    return "\n".join(parts).rstrip() + "\n"


def compact_ref(table: list, ref):
    if isinstance(ref, int) and 0 <= ref < len(table):
        return table[ref]
    if isinstance(ref, int) and ref < 0:
        return None
    return ref


def compact_key(table: list, key):
    if isinstance(key, str) and key.startswith("_") and key[1:].isdigit():
        return compact_ref(table, int(key[1:]))
    return key


def compact_get(table: list, obj, key: str, default=None):
    if not isinstance(obj, dict):
        return default

    for raw_key, raw_value in obj.items():
        if compact_key(table, raw_key) == key:
            return compact_ref(table, raw_value)

    return default


def extract_compact_share(document: str) -> tuple[str | None, list[dict[str, str]]] | None:
    table = extract_stream_array(document)
    if not table:
        return None

    root = table[0]
    loader = compact_get(table, root, "loaderData")
    route = None
    if isinstance(loader, dict):
        for raw_key, raw_value in loader.items():
            key = compact_key(table, raw_key)
            if isinstance(key, str) and key.startswith("routes/share."):
                route = compact_ref(table, raw_value)
                break
    if route is None:
        return None

    server = compact_get(table, route, "serverResponse")
    conversation = compact_get(table, server, "data")
    if not isinstance(conversation, dict):
        return None

    title = compact_get(table, conversation, "title")
    linear = compact_get(table, conversation, "linear_conversation") or []
    messages: list[dict[str, str]] = []

    for item_ref in linear:
        item = compact_ref(table, item_ref)
        message = compact_get(table, item, "message")
        if not isinstance(message, dict):
            continue

        metadata = compact_get(table, message, "metadata") or {}
        if compact_get(table, metadata, "is_visually_hidden_from_conversation"):
            continue

        author = compact_get(table, message, "author") or {}
        role = compact_get(table, author, "role")
        if role not in {"user", "assistant"}:
            continue

        content = compact_get(table, message, "content") or {}
        if compact_get(table, content, "content_type") != "text":
            continue

        parts = compact_get(table, content, "parts") or []
        text = "\n\n".join(
            part for part in (compact_ref(table, part_ref) for part_ref in parts)
            if isinstance(part, str) and part.strip()
        )
        if text.strip():
            messages.append({"role": role, "text": text})

    return (title if isinstance(title, str) else None), messages


def render_message_text(text: str) -> str:
    text = strip_chatgpt_writing_markers(text)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    code: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if not paragraph:
            return

        block = "\n".join(paragraph).strip()
        paragraph.clear()
        if not block:
            return

        if block.startswith("# "):
            blocks.append(f"<h2>{render_inline_markdown(block[2:].strip())}</h2>")
            return
        if block.startswith("## "):
            blocks.append(f"<h3>{render_inline_markdown(block[3:].strip())}</h3>")
            return
        if block.startswith("### "):
            blocks.append(f"<h4>{render_inline_markdown(block[4:].strip())}</h4>")
            return

        block_lines = block.splitlines()
        if block_lines and all(line.startswith(">") for line in block_lines):
            blocks.append(render_blockquote(block_lines))
            return

        if block_lines and all(line.startswith("- ") for line in block_lines):
            items = "".join(
                f"<li>{render_inline_markdown(line[2:].strip())}</li>"
                for line in block_lines
            )
            blocks.append(f"<ul>{items}</ul>")
            return

        ordered_matches = [ORDERED_LIST_RE.match(line) for line in block_lines]
        if ordered_matches and all(ordered_matches):
            items = "".join(
                f"<li>{render_inline_markdown(match.group(1).strip())}</li>"
                for match in ordered_matches
                if match is not None
            )
            blocks.append(f"<ol>{items}</ol>")
            return

        rendered = render_inline_markdown(block).replace("\n", "<br>")
        blocks.append(f"<p>{rendered}</p>")

    def flush_code() -> None:
        blocks.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
        code.clear()

    for line in lines:
        if line.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            continue

        if in_code:
            code.append(line)
        elif line.strip():
            paragraph.append(line)
        else:
            flush_paragraph()

    if in_code:
        flush_code()
    flush_paragraph()
    return "\n".join(blocks)


def render_static_transcript(
    title: str,
    nav: str,
    messages: list[dict[str, str]],
) -> str:
    escaped_title = html.escape(title, quote=False)
    turns = []
    for message in messages:
        role = message["role"]
        label = "You said:" if role == "user" else "ChatGPT said:"
        turns.append(
            "\n".join(
                [
                    f'<section class="turn {role}">',
                    f"  <h2>{label}</h2>",
                    '  <div class="message">',
                    render_message_text(message["text"]),
                    "  </div>",
                    "</section>",
                ]
            )
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

    .turn {{
      border-top: 1px solid var(--line);
      padding: 1.4rem 0;
    }}

    .turn h2 {{
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
  </style>
</head>
<body>
  {nav}
  <main>
{chr(10).join(turns)}
  </main>
</body>
</html>
"""


def render_document(document: str, args: argparse.Namespace) -> str:
    nav = build_nav(args)
    compact_share = extract_compact_share(document)
    if compact_share and not RENDERED_TRANSCRIPT_RE.search(document):
        extracted_title, messages = compact_share
        title = args.title or extracted_title or "Behind the Scenes"
        return render_static_transcript(title, nav, messages)

    document = replace_title(document, args.title)
    return inject_nav(document, nav)


def write_essay_output(document: str, args: argparse.Namespace) -> None:
    if not args.essay_output:
        return

    compact_share = extract_compact_share(document)
    if not compact_share:
        raise ValueError("Could not extract compact ChatGPT conversation data.")

    extracted_title, messages = compact_share
    last_assistant = next(
        (message["text"] for message in reversed(messages) if message["role"] == "assistant"),
        None,
    )
    if last_assistant is None:
        raise ValueError("Could not find an assistant turn to export.")

    writing_blocks = extract_chatgpt_writing_blocks(last_assistant)
    essay_text = writing_blocks[-1] if writing_blocks else last_assistant
    cleaned_text = strip_chatgpt_writing_markers(essay_text)
    title = args.essay_title or infer_markdown_title(cleaned_text, extracted_title)
    essay = render_org_essay(cleaned_text, title, args.essay_behind_href)
    pathlib.Path(args.essay_output).write_text(essay, encoding="utf-8")


def main() -> int:
    args = parse_args()
    document = read_document(args)
    write_essay_output(document, args)
    document = render_document(document, args)

    output = pathlib.Path(args.output)
    output.write_text(document, encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
