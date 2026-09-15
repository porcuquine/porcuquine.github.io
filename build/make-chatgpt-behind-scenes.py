#!/usr/bin/env python3
"""Create a local behind-the-scenes page from ChatGPT share HTML.

Older rendered share pages are preserved and wrapped with the site's small
navigation block. Newer app-shell share pages are converted into a static
transcript from their embedded conversation data.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request


BODY_RE = re.compile(r"(<body\b[^>]*>\s*)", re.IGNORECASE)
RENDERED_TRANSCRIPT_RE = re.compile(r'data-testid="conversation-turn-\d+"')
STREAM_ENQUEUE_MARKER = "window.__reactRouterContext.streamController.enqueue("
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
CODE_PLACEHOLDER_RE = re.compile(r"\x00CODE(\d+)\x00")
INLINE_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
INLINE_MATH_RE = re.compile(r"\\\((.+?)\\\)")
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
ORDERED_LIST_RE = re.compile(r"^\d+[.)]\s+(.+)$")
CONTEXT_MARKER_RE = re.compile(r"^<context(?:\.\.\.|\s+[^<>]+)?>$", re.IGNORECASE)
ORG_EMPHASIS_PRE_CHARS = set(" \t\r\n([{'\"")
ORG_EMPHASIS_POST_CHARS = set(" \t\r\n-.,:!?;'\"") | set(")}]")
CHATGPT_CITATION_RE = re.compile(r"cite[^]+")
RAW_MATH_DELIMITER_RE = re.compile(r"\\[\[\]()]")
LITERAL_WRITING_BLOCK_RE = re.compile(
    r'<div class="writing-block literal-math">.*?</div>', re.DOTALL
)
CODE_BLOCK_RE = re.compile(r"<pre\b[^>]*>.*?</pre>", re.DOTALL)
CODE_SPAN_RE = re.compile(r"<code\b[^>]*>.*?</code>", re.DOTALL)
LATEX_REPLACEMENTS = (
    (r"\longrightarrow", "\u2192"),
    (r"\rightarrow", "\u2192"),
    (r"\Downarrow", "\u21d3"),
    (r"\Rightarrow", "\u21d2"),
    (r"\Leftarrow", "\u21d0"),
    (r"\Delta", "\u0394"),
    (r"\qquad", " "),
    (r"\quad", " "),
    (r"\geq", "\u2265"),
    (r"\leq", "\u2264"),
    (r"\ge", "\u2265"),
    (r"\le", "\u2264"),
    (r"\gg", "\u226b"),
    (r"\ll", "\u226a"),
    (r"\iff", "\u21d4"),
    (r"\mid", " | "),
    (r"\to", "\u2192"),
    (r"\,", " "),
)


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
        "--essay-subtitle",
        help="Optional Org subtitle to add below the essay title.",
    )
    parser.add_argument(
        "--essay-behind-href",
        help="Optional behind-the-scenes link to append to --essay-output.",
    )
    parser.add_argument(
        "--literal-writing-math",
        action="append",
        default=[],
        metavar="N",
        type=positive_int,
        help=(
            "Preserve raw math markup in 1-based writing block N. Repeat for "
            "multiple blocks. Use only to mirror a known source rendering failure."
        ),
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


def iter_stream_payloads(document: str):
    decoder = json.JSONDecoder()
    pos = 0

    while True:
        marker_pos = document.find(STREAM_ENQUEUE_MARKER, pos)
        if marker_pos == -1:
            return

        arg_pos = marker_pos + len(STREAM_ENQUEUE_MARKER)
        try:
            payload, end = decoder.raw_decode(document[arg_pos:])
        except ValueError:
            pos = arg_pos + 1
            continue

        if isinstance(payload, str):
            yield payload

        pos = arg_pos + end


def extract_stream_array(document: str) -> list | None:
    for decoded in iter_stream_payloads(document):
        first_line = decoded.strip().splitlines()[0] if decoded.strip() else ""
        if not first_line.startswith("["):
            continue

        try:
            return json_loads(first_line)
        except ValueError:
            continue

    return None


def json_loads(value: str):
    return json.loads(value)


def latex_to_text(source: str) -> str:
    rendered = source
    rendered = rendered.replace(r"\\", "\n")
    rendered = re.sub(r"\\begin\{[^{}]+\}", "", rendered)
    rendered = re.sub(r"\\end\{[^{}]+\}", "", rendered)

    previous = None
    while previous != rendered:
        previous = rendered
        rendered = re.sub(r"\\text\{([^{}]*)\}", r"\1", rendered)

    for latex, replacement in LATEX_REPLACEMENTS:
        rendered = rendered.replace(latex, replacement)

    unsupported = sorted(set(re.findall(r"\\[A-Za-z]+|\\.", rendered)))
    if unsupported:
        commands = ", ".join(unsupported)
        raise ValueError(
            "Unsupported LaTeX command(s) in math expression "
            f"{source!r}: {commands}"
        )

    rendered = rendered.replace("&", "")
    rendered = re.sub(r"_\{([^{}]+)\}", r"_\1", rendered)
    rendered = re.sub(r"\^\{([^{}]+)\}", r"^\1", rendered)
    rendered = rendered.replace("{", "").replace("}", "")
    rendered = re.sub(r"\s*([⇔⇒⇐→≥≤≫≪=<>+|])\s*", r" \1 ", rendered)
    rendered = re.sub(r"([(\[])\s+", r"\1", rendered)
    rendered = re.sub(r"[ \t]+", " ", rendered)
    rendered = re.sub(r" *\n *", "\n", rendered)
    rendered = re.sub(r"\s+([)\],.;:?])", r"\1", rendered)
    return rendered.strip()


def render_inline_math(source: str) -> str:
    rendered = html.escape(latex_to_text(source), quote=False)
    return f'<span class="math math-inline">{rendered}</span>'


def render_display_math(block_lines: list[str], render_math: bool = True) -> str | None:
    if not render_math:
        return None

    block = "\n".join(block_lines).strip()
    if not block.startswith(r"\[") or not block.endswith(r"\]"):
        return None

    rendered = latex_to_text(block[2:-2].strip())
    if not rendered:
        return None

    lines = [
        f'<span class="math-line">{html.escape(line, quote=False)}</span>'
        for line in rendered.splitlines()
        if line.strip()
    ]
    return f'<div class="math math-display">{"".join(lines)}</div>'


def render_context_marker(text: str) -> str:
    return f'<div class="context-marker">{html.escape(text, quote=False)}</div>'


def render_inline_markdown(text: str, render_math: bool = True) -> str:
    code_spans: list[str] = []
    link_spans: list[str] = []
    math_spans: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        code_spans.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00CODE{len(code_spans) - 1}\x00"

    def stash_link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1), quote=False)
        href = html.escape(match.group(2), quote=True)
        link_spans.append(f'<a href="{href}">{label}</a>')
        return f"\x00LINK{len(link_spans) - 1}\x00"

    def stash_inline_math(match: re.Match[str]) -> str:
        math_spans.append(render_inline_math(match.group(1)))
        return f"\x00MATH{len(math_spans) - 1}\x00"

    rendered = INLINE_CODE_RE.sub(stash_code, text)
    rendered = INLINE_LINK_RE.sub(stash_link, rendered)
    if render_math:
        rendered = INLINE_MATH_RE.sub(stash_inline_math, rendered)
    rendered = html.escape(rendered, quote=False)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<em>\1</em>", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", rendered)

    for index, code_span in enumerate(code_spans):
        rendered = rendered.replace(f"\x00CODE{index}\x00", code_span)
    for index, link_span in enumerate(link_spans):
        rendered = rendered.replace(f"\x00LINK{index}\x00", link_span)
    for index, math_span in enumerate(math_spans):
        rendered = rendered.replace(f"\x00MATH{index}\x00", math_span)

    return rendered


def render_blockquote(lines: list[str], render_math: bool = True) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush_quote_paragraph() -> None:
        if not paragraph:
            return

        text = "\n".join(paragraph).strip()
        paragraph.clear()
        if text:
            blocks.append(
                f"<p>{render_inline_markdown(text, render_math).replace(chr(10), '<br>')}</p>"
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


def split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if "|" not in stripped:
        return []

    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    return [cell.strip() for cell in stripped.split("|")]


def is_markdown_table_separator(line: str) -> bool:
    cells = split_markdown_table_row(line)
    return bool(cells) and all(
        re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells
    )


def render_markdown_table(lines: list[str], render_math: bool = True) -> str | None:
    if len(lines) < 2 or not is_markdown_table_separator(lines[1]):
        return None

    header = split_markdown_table_row(lines[0])
    rows = [split_markdown_table_row(line) for line in lines[2:]]
    if not header or any(len(row) != len(header) for row in rows):
        return None

    header_html = "".join(
        f"<th>{render_inline_markdown(cell, render_math)}</th>" for cell in header
    )
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{render_inline_markdown(cell, render_math)}</td>" for cell in row
        )
        body_rows.append(f"<tr>{cells}</tr>")

    body = "\n".join(body_rows)
    return (
        "<table>\n"
        f"<thead><tr>{header_html}</tr></thead>\n"
        f"<tbody>\n{body}\n</tbody>\n"
        "</table>"
    )


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
        match = MARKDOWN_HEADING_RE.match(line.strip())
        if match:
            return match.group(2).strip()

    return fallback or "Untitled"


def extract_final_piece_text(text: str, title: str | None = None) -> str:
    writing_blocks = extract_chatgpt_writing_blocks(text)
    if writing_blocks:
        return strip_chatgpt_writing_markers(writing_blocks[-1])

    cleaned_text = strip_chatgpt_writing_markers(text)
    lines = cleaned_text.splitlines()
    heading_indexes: list[int] = []

    for index, line in enumerate(lines):
        match = MARKDOWN_HEADING_RE.match(line.strip())
        if not match:
            continue

        heading_indexes.append(index)
        if title and match.group(2).strip() == title:
            return "\n".join(lines[index:]).strip()

    for index in heading_indexes:
        if any(line.strip() for line in lines[index + 1 :]):
            return "\n".join(lines[index:]).strip()

    if heading_indexes:
        return "\n".join(lines[heading_indexes[0] :]).strip()

    return cleaned_text


def markdown_inline_to_org(text: str) -> str:
    code_spans: list[str] = []
    hard_break = bool(re.search(r" {2,}$", text))
    text = re.sub(r" {2,}$", "", text)

    def stash_code(match: re.Match[str]) -> str:
        code_spans.append(match.group(1))
        return f"\x00CODE{len(code_spans) - 1}\x00"

    def render_html_inline(tag: str, value: str) -> str:
        pieces: list[str] = []
        pos = 0
        for match in CODE_PLACEHOLDER_RE.finditer(value):
            pieces.append(html.escape(value[pos : match.start()], quote=False))
            pieces.append(
                f"<code>{html.escape(code_spans[int(match.group(1))])}</code>"
            )
            pos = match.end()

        pieces.append(html.escape(value[pos:], quote=False))
        rendered = "".join(pieces).replace("@@", "&#64;&#64;")
        return f"@@html:<{tag}>{rendered}</{tag}>@@"

    def org_markup_is_safe(source: str, start: int, end: int) -> bool:
        before = source[start - 1] if start > 0 else ""
        after = source[end] if end < len(source) else ""
        return (
            (not before or before in ORG_EMPHASIS_PRE_CHARS)
            and (not after or after in ORG_EMPHASIS_POST_CHARS)
        )

    emphasis_spans: list[str] = []

    def stash_emphasis(match: re.Match[str], marker: str, tag: str) -> str:
        content = match.group(1)
        if org_markup_is_safe(rendered, match.start(), match.end()):
            replacement = f"{marker}{content}{marker}"
        else:
            replacement = render_html_inline(tag, content)

        emphasis_spans.append(replacement)
        return f"\x00EMPH{len(emphasis_spans) - 1}\x00"

    rendered = INLINE_CODE_RE.sub(stash_code, text)
    rendered = re.sub(
        r"\*\*([^*\n]+?)\*\*",
        lambda match: stash_emphasis(match, "*", "strong"),
        rendered,
    )
    rendered = re.sub(
        r"(?<!\*)\*([^*\n]+)\*(?!\*)",
        lambda match: stash_emphasis(match, "/", "em"),
        rendered,
    )

    for index, emphasis_span in enumerate(emphasis_spans):
        rendered = rendered.replace(f"\x00EMPH{index}\x00", emphasis_span)

    for index, code_span in enumerate(code_spans):
        rendered = rendered.replace(f"\x00CODE{index}\x00", f"~{code_span}~")

    if hard_break:
        rendered = rendered.rstrip() + r"\\"

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
            if not skipped_title and heading_text == title:
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
    subtitle: str | None = None,
) -> str:
    body = markdown_to_org_body(text, title)
    parts = [
        f"#+TITLE: {title}",
    ]
    if subtitle:
        parts.append(f"#+SUBTITLE: {subtitle}")

    parts.extend(
        [
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
    )

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


def clean_source_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.startswith("utm_")
    ]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


def citation_label_for_url(url: str, attribution: str | None = None) -> str:
    if attribution and attribution.strip():
        return attribution.strip()

    host = urllib.parse.urlsplit(url).netloc
    return host.removeprefix("www.") or "source"


def collect_citation_replacements(table: list, metadata: dict) -> dict[str, str]:
    replacements: dict[str, str] = {}
    references = compact_get(table, metadata, "content_references") or []

    for reference_ref in references:
        reference = compact_ref(table, reference_ref)
        matched_text = compact_get(table, reference, "matched_text")
        if not isinstance(matched_text, str) or not CHATGPT_CITATION_RE.fullmatch(
            matched_text
        ):
            continue

        links: list[tuple[str, str]] = []
        seen_urls: set[str] = set()
        items = compact_get(table, reference, "items") or []
        for item_ref in items:
            item = compact_ref(table, item_ref)
            url = compact_get(table, item, "url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                continue

            cleaned_url = clean_source_url(url)
            if cleaned_url in seen_urls:
                continue

            seen_urls.add(cleaned_url)
            attribution = compact_get(table, item, "attribution")
            links.append(
                (
                    citation_label_for_url(
                        cleaned_url, attribution if isinstance(attribution, str) else None
                    ),
                    cleaned_url,
                )
            )

        if not links:
            safe_urls = compact_get(table, reference, "safe_urls") or []
            for url_ref in safe_urls:
                url = compact_ref(table, url_ref)
                if not isinstance(url, str) or not url.startswith(
                    ("http://", "https://")
                ):
                    continue

                cleaned_url = clean_source_url(url)
                if cleaned_url in seen_urls:
                    continue

                seen_urls.add(cleaned_url)
                links.append((citation_label_for_url(cleaned_url), cleaned_url))

        if not links:
            replacements[matched_text] = ""
            continue

        rendered_links = ", ".join(f"[{label}]({url})" for label, url in links)
        replacements[matched_text] = f"({rendered_links})"

    return replacements


def replace_chatgpt_citations(text: str, replacements: dict[str, str]) -> str:
    for marker, replacement in replacements.items():
        text = text.replace(marker, replacement)

    return CHATGPT_CITATION_RE.sub("", text)


def extract_compact_share(document: str) -> tuple[str | None, list[dict[str, object]]] | None:
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
    messages: list[dict[str, object]] = []

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
            messages.append(
                {
                    "role": role,
                    "text": text,
                    "citation_replacements": collect_citation_replacements(
                        table, metadata
                    ),
                }
            )

    return (title if isinstance(title, str) else None), messages


def render_message_text(
    text: str,
    citation_replacements: dict[str, str] | None = None,
    literal_writing_math_blocks: set[int] | None = None,
    writing_block_counter: list[int] | None = None,
) -> str:
    if citation_replacements:
        text = replace_chatgpt_citations(text, citation_replacements)
    else:
        text = replace_chatgpt_citations(text, {})

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    code: list[str] = []
    in_code = False
    in_writing = False
    writing_render_math = True
    paragraph_render_math = True
    literal_writing_math_blocks = literal_writing_math_blocks or set()
    if writing_block_counter is None:
        writing_block_counter = [0]

    def flush_paragraph() -> None:
        nonlocal paragraph_render_math
        if not paragraph:
            return

        block = "\n".join(paragraph).strip()
        paragraph.clear()
        render_math = paragraph_render_math
        paragraph_render_math = True
        if not block:
            return

        if CONTEXT_MARKER_RE.fullmatch(block):
            blocks.append(render_context_marker(block))
            return

        if block.startswith("# "):
            blocks.append(
                f"<h2>{render_inline_markdown(block[2:].strip(), render_math)}</h2>"
            )
            return
        if block.startswith("## "):
            blocks.append(
                f"<h3>{render_inline_markdown(block[3:].strip(), render_math)}</h3>"
            )
            return
        if block.startswith("### "):
            blocks.append(
                f"<h4>{render_inline_markdown(block[4:].strip(), render_math)}</h4>"
            )
            return

        block_lines = block.splitlines()
        display_math = render_display_math(block_lines, render_math)
        if display_math:
            blocks.append(display_math)
            return

        table = render_markdown_table(block_lines, render_math)
        if table:
            blocks.append(table)
            return

        if block_lines and all(line.startswith(">") for line in block_lines):
            blocks.append(render_blockquote(block_lines, render_math))
            return

        if block_lines and all(line.startswith("- ") for line in block_lines):
            items = "".join(
                f"<li>{render_inline_markdown(line[2:].strip(), render_math)}</li>"
                for line in block_lines
            )
            blocks.append(f"<ul>{items}</ul>")
            return

        ordered_matches = [ORDERED_LIST_RE.match(line) for line in block_lines]
        if ordered_matches and all(ordered_matches):
            items = "".join(
                f"<li>{render_inline_markdown(match.group(1).strip(), render_math)}</li>"
                for match in ordered_matches
                if match is not None
            )
            blocks.append(f"<ol>{items}</ol>")
            return

        rendered = render_inline_markdown(block, render_math).replace("\n", "<br>")
        blocks.append(f"<p>{rendered}</p>")

    def flush_code() -> None:
        blocks.append(f"<pre><code>{html.escape(chr(10).join(code))}</code></pre>")
        code.clear()

    def append_paragraph(line: str) -> None:
        nonlocal paragraph_render_math
        if not paragraph:
            paragraph_render_math = writing_render_math if in_writing else True
        paragraph.append(line)

    for line in lines:
        if not in_code and line.startswith(":::writing"):
            flush_paragraph()
            writing_block_counter[0] += 1
            writing_render_math = (
                writing_block_counter[0] not in literal_writing_math_blocks
            )
            class_name = (
                "writing-block" if writing_render_math else "writing-block literal-math"
            )
            blocks.append(f'<div class="{class_name}">')
            in_writing = True
            continue

        if not in_code and in_writing and line.strip() == ":::":
            flush_paragraph()
            blocks.append("</div>")
            in_writing = False
            writing_render_math = True
            continue

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
            append_paragraph(line)
        else:
            flush_paragraph()

    if in_code:
        flush_code()
    flush_paragraph()
    if in_writing:
        blocks.append("</div>")
    return "\n".join(blocks)


def find_unconverted_math(document: str) -> list[str]:
    stripped = LITERAL_WRITING_BLOCK_RE.sub("", document)
    stripped = CODE_BLOCK_RE.sub("", stripped)
    stripped = CODE_SPAN_RE.sub("", stripped)

    contexts: list[str] = []
    for match in RAW_MATH_DELIMITER_RE.finditer(stripped):
        start = max(0, match.start() - 45)
        end = min(len(stripped), match.end() + 45)
        context = re.sub(r"\s+", " ", stripped[start:end]).strip()
        contexts.append(context)

    return contexts


def validate_rendered_math(document: str) -> None:
    contexts = find_unconverted_math(document)
    if not contexts:
        return

    preview = "; ".join(contexts[:3])
    if len(contexts) > 3:
        preview += f"; ... and {len(contexts) - 3} more"
    raise ValueError(
        "Unconverted math delimiter(s) remain in rendered transcript. "
        "Add converter support or mark a known source-rendering failure with "
        f"--literal-writing-math. Context: {preview}"
    )


def render_static_transcript(
    title: str,
    nav: str,
    messages: list[dict[str, object]],
    literal_writing_math_blocks: set[int] | None = None,
) -> str:
    escaped_title = html.escape(title, quote=False)
    turns = []
    writing_block_counter = [0]
    for message in messages:
        role = str(message["role"])
        text = message["text"]
        if not isinstance(text, str):
            continue

        citation_replacements = message.get("citation_replacements")
        if not isinstance(citation_replacements, dict):
            citation_replacements = {}

        label = "You said:" if role == "user" else "ChatGPT said:"
        turns.append(
            "\n".join(
                [
                    f'<section class="turn {role}">',
                    f"  <h2>{label}</h2>",
                    '  <div class="message">',
                    render_message_text(
                        text,
                        citation_replacements,
                        literal_writing_math_blocks,
                        writing_block_counter,
                    ),
                    "  </div>",
                    "</section>",
                ]
            )
        )

    document = f"""<!doctype html>
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

    .writing-block {{
      margin: 1rem 0;
      border: 1px solid var(--line);
      border-left: 0.25rem solid #b8b8b8;
      background: #fbfbfb;
      padding: 1rem 1.1rem;
    }}

    .writing-block > :last-child {{
      margin-bottom: 0;
    }}

    .context-marker {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin: 0.15rem 0 1rem;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
      font-size: 0.85rem;
    }}

    .context-marker::before,
    .context-marker::after {{
      content: "";
      flex: 1;
      border-top: 1px solid var(--line);
    }}

    .user .message {{
      margin-left: auto;
      border-radius: 1rem;
      background: var(--user);
      padding: 0.9rem 1rem;
    }}

    p, ul, ol, blockquote, pre, table, .math-display {{
      margin: 0 0 1rem;
    }}

    p:last-child, ul:last-child, ol:last-child, blockquote:last-child, pre:last-child, table:last-child, .math-display:last-child, .context-marker:last-child {{
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

    .math {{
      font-family: ui-serif, Georgia, "Times New Roman", Times, serif;
    }}

    .math-display {{
      text-align: center;
      line-height: 1.7;
    }}

    .math-line {{
      display: block;
    }}

    .math-inline {{
      white-space: nowrap;
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
{chr(10).join(turns)}
  </main>
</body>
</html>
"""
    validate_rendered_math(document)
    return document


def render_document(document: str, args: argparse.Namespace) -> str:
    nav = build_nav(args)
    compact_share = extract_compact_share(document)
    if compact_share and not RENDERED_TRANSCRIPT_RE.search(document):
        extracted_title, messages = compact_share
        title = args.title or extracted_title or "Behind the Scenes"
        literal_writing_math_blocks = set(
            getattr(args, "literal_writing_math", []) or []
        )
        return render_static_transcript(
            title,
            nav,
            messages,
            literal_writing_math_blocks,
        )

    document = replace_title(document, args.title)
    return inject_nav(document, nav)


def write_essay_output(document: str, args: argparse.Namespace) -> None:
    if not args.essay_output:
        return

    compact_share = extract_compact_share(document)
    if not compact_share:
        raise ValueError("Could not extract compact ChatGPT conversation data.")

    extracted_title, messages = compact_share
    last_assistant_message = next(
        (
            message
            for message in reversed(messages)
            if message["role"] == "assistant" and isinstance(message.get("text"), str)
        ),
        None,
    )
    if last_assistant_message is None:
        raise ValueError("Could not find an assistant turn to export.")

    last_assistant = str(last_assistant_message["text"])
    citation_replacements = last_assistant_message.get("citation_replacements")
    if not isinstance(citation_replacements, dict):
        citation_replacements = {}
    last_assistant = replace_chatgpt_citations(last_assistant, citation_replacements)
    cleaned_text = extract_final_piece_text(last_assistant, args.essay_title)
    title = args.essay_title or infer_markdown_title(cleaned_text, extracted_title)
    essay = render_org_essay(
        cleaned_text,
        title,
        args.essay_behind_href,
        args.essay_subtitle,
    )
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
