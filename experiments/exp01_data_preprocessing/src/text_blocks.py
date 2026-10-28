"""Extract ordered textual blocks without reading images or changing wording."""

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata

from lxml import html


BLOCK_TAGS = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol",
              "article", "section", "blockquote", "pre", "tr", "td", "table", "figure", "figcaption"}
EXCLUDED_TAGS = {"script", "style", "iframe", "noscript", "img", "picture", "svg", "video", "audio", "embed", "object"}


@dataclass
class TextBlock:
    block_id: str
    role: str
    text: str
    xpath: str


def inline_text(node):
    if not isinstance(node.tag, str) or node.tag.lower() in EXCLUDED_TAGS:
        return ""
    parts = [node.text or ""]
    for child in node:
        if isinstance(child.tag, str) and child.tag.lower() == "br":
            parts.append("\n")
        else:
            parts.append(inline_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def extract_blocks(fragment):
    root = html.fromstring(fragment, parser=html.HTMLParser(no_network=True))
    tree = root.getroottree()
    blocks = []

    def emit(text, role, node):
        if text.strip():
            blocks.append(TextBlock(f"B{len(blocks)+1:04d}", role, text, tree.getpath(node)))

    def visit(node, inherited_role="paragraph"):
        if not isinstance(node.tag, str) or node.tag.lower() in EXCLUDED_TAGS:
            return
        tag = node.tag.lower()
        classes = set(node.get("class", "").split())
        role = "caption" if "graph_comment" in classes or tag == "figcaption" else inherited_role
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            role = "heading"
        buffer = [node.text or ""]
        for child in node:
            child_tag = child.tag.lower() if isinstance(child.tag, str) else ""
            if child_tag in BLOCK_TAGS:
                emit("".join(buffer), role, node)
                buffer = []
                visit(child, role if role == "caption" else "paragraph")
            elif child_tag == "br":
                buffer.append("\n")
            else:
                buffer.append(inline_text(child))
            buffer.append(child.tail or "")
        emit("".join(buffer), role, node)

    visit(root)
    return blocks


def block_fingerprint(blocks):
    values = [(b.role, re.sub(r"\s+", "", unicodedata.normalize("NFC", b.text))) for b in blocks]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
