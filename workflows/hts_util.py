"""Helpers for HTS codes and rate strings. Pure functions — no I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterator

# 0101 | 0101.21 | 0101.21.00 | 0101.21.00.10
HTS_TOKEN = re.compile(r"\b(\d{4}(?:\.\d{2}){0,3})\b")

PROVIDED_FOR = re.compile(
    r"provided\s+for\s+in\s+(?:subheadings?|headings?)?\s*"
    r"|provided\s+in\s+(?:subheadings?|headings?)?\s*"
    r"|provided\s+for\s+(?:subheadings?|headings?)\s*",
    re.IGNORECASE,
)

EXCEPT_FOR = re.compile(
    r"except\s+for\s+products\s+described\s+in\s+(?:headings?\s+)?(.+?)(?:"
    r",\s*and\s+other\s+than|,?\s*articles\b|\.\s)",
    re.IGNORECASE | re.DOTALL,
)

NOTE_REF = re.compile(
    r"(U\.?\s*S\.?\s+note\s+\d+[a-z0-9()]*(?:\s+to\s+this\s+subchapter)?)"
    r"|(statistical\s+note\s+\d+[a-z0-9()]*)"
    r"|(general\s+note\s+\d+[a-z0-9()]*)"
    r"|(note\s+\d+[a-z0-9()]*\s+to\s+this\s+subchapter)",
    re.IGNORECASE,
)

ADDITIVE = re.compile(
    r"applicable\s+subheading\s*\+\s*([\d.]+)\s*%",
    re.IGNORECASE,
)
AD_VALOREM = re.compile(r"^([\d.]+)\s*%$")
SPECIFIC = re.compile(
    r"^([\d.]+)\s*¢/([A-Za-z0-9.\s]+)$|^\$\s*([\d.]+)/([A-Za-z0-9.\s]+)$"
)
SPECIAL_FREE = re.compile(
    r"Free\s*\(([^)]+)\)",
    re.IGNORECASE,
)
SPECIAL_PCT = re.compile(
    r"([\d.]+)\s*%\s*\(([^)]+)\)",
)


def parse_hts_code(hts: str) -> tuple[int, int, int, int] | None:
    """Turn '0101.21.00.10' into (101, 21, 0, 10). Missing segments → -1."""
    hts = (hts or "").strip()
    if not hts or not re.fullmatch(r"\d{4}(?:\.\d{2}){0,3}", hts):
        return None
    parts = [int(p) for p in hts.split(".")]
    while len(parts) < 4:
        parts.append(-1)
    return parts[0], parts[1], parts[2], parts[3]


def format_hts_code(code: tuple[int, int, int, int]) -> str:
    h0, h1, h2, h3 = code
    # Preserve leading zeros on the 4-digit heading group.
    s = f"{h0:04d}"
    if h1 >= 0:
        s += f".{h1:02d}"
    if h2 >= 0:
        s += f".{h2:02d}"
    if h3 >= 0:
        s += f".{h3:02d}"
    return s


def extract_hts_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(HTS_TOKEN.findall(text or "")))


def extract_references(description: str) -> list[str]:
    """Base (or any) HTS codes named via 'provided for in …' style joins."""
    text = description or ""
    refs: list[str] = []
    for m in PROVIDED_FOR.finditer(text):
        # Take a short window after the cue and pull HTS tokens from it.
        window = text[m.end() : m.end() + 120]
        # Stop at a sentence break or parenthetical close when possible.
        stop = re.search(r"[);]|\band\b(?!\s+\d)", window)
        if stop and stop.start() > 0:
            window = window[: stop.start()]
        for tok in extract_hts_tokens(window):
            # Prefer base-schedule references (chs 1–97) for 'references' edges,
            # but keep whatever the prose named — rule_edge.target is not an FK.
            if tok not in refs:
                refs.append(tok)
    return refs


def extract_excludes(description: str) -> list[str]:
    text = description or ""
    m = EXCEPT_FOR.search(text)
    if not m:
        # Fallback: any "Except for …" opener — grab 99xx codes in the first clause.
        if not text.lower().startswith("except for"):
            return []
        clause = text.split("articles", 1)[0]
        return [t for t in extract_hts_tokens(clause) if t.startswith("99")]
    return [t for t in extract_hts_tokens(m.group(1)) if t.startswith("99")]


def extract_note_ref(description: str) -> str | None:
    m = NOTE_REF.search(description or "")
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(0)).strip()


def subchapter_for(hts: str) -> str:
    """Map 9902.x → 'II', 9903.x → 'III', etc. Falls back to the 4-digit heading."""
    code = parse_hts_code(hts)
    if not code:
        return "unknown"
    heading = code[0]  # e.g. 9903
    # Chapter 99 subchapters are numbered by the last two digits of the heading group
    # in common usage (9901→I …); keep it simple and stable.
    roman = {
        9901: "I",
        9902: "II",
        9903: "III",
        9904: "IV",
        9905: "V",
        9906: "VI",
        9907: "VII",
        9908: "VIII",
        9910: "X",
        9915: "XV",
        9917: "XVII",
        9918: "XVIII",
        9919: "XIX",
        9920: "XX",
        9921: "XXI",
        9922: "XXII",
    }
    return roman.get(heading, str(heading))


def parse_mfn_rate(general: str) -> tuple[Decimal | None, str | None]:
    """Return (mfn_rate, mfn_rate_unit) for a chapters 1-97 `general` cell."""
    g = (general or "").strip()
    if not g:
        return None, None
    if g.lower() == "free":
        return Decimal("0"), "free"
    m = AD_VALOREM.fullmatch(g)
    if m:
        return Decimal(m.group(1)), "percent"
    m = SPECIFIC.fullmatch(g)
    if m:
        if m.group(1) is not None:
            cents = Decimal(m.group(1))
            unit = m.group(2).strip()
            return cents / Decimal("100"), f"USD/{unit}"
        dollars = Decimal(m.group(3))
        unit = m.group(4).strip()
        return dollars, f"USD/{unit}"
    if "+" in g or re.search(r"\bon\b", g, re.I):
        return None, "compound"
    return None, "other"


@dataclass(frozen=True)
class _RateFrame:
    indent: int
    rate: Decimal | None
    unit: str | None


def walk_with_inherited_mfn(
    rows: list[dict],
) -> Iterator[tuple[dict, Decimal | None, str | None]]:
    """Depth-first walk of the schedule using an indent stack.

    Rows with an empty `general` inherit ``(mfn_rate, mfn_rate_unit)`` from the
    nearest parent (previous row with a smaller indent). Own rates replace the
    inherited value for that node and its descendants.
    """
    stack: list[_RateFrame] = []
    for row in rows:
        indent = int(row.get("indent") or 0)
        while stack and stack[-1].indent >= indent:
            stack.pop()

        general = (row.get("general") or "").strip()
        if general:
            rate, unit = parse_mfn_rate(general)
        elif stack:
            rate, unit = stack[-1].rate, stack[-1].unit
        else:
            rate, unit = None, None

        stack.append(_RateFrame(indent, rate, unit))
        yield row, rate, unit


def parse_rule_rate(general: str) -> tuple[str, Decimal | None, str | None]:
    """Return (rate_kind, rate_value, rate_unit) for a Chapter 99 `general` cell."""
    g = (general or "").strip()
    if not g:
        return "other", None, None
    if g.lower() == "free":
        return "free", Decimal("0"), "free"
    if re.fullmatch(r"no\s*change\.?", g, re.I):
        return "no_change", None, None
    m = ADDITIVE.search(g)
    if m:
        return "additive", Decimal(m.group(1)), "percent"
    # "The duty provided in the applicable subheading" with no add-on
    if re.search(r"applicable\s+subheading", g, re.I) and "+" not in g:
        return "no_change", None, None
    m = AD_VALOREM.fullmatch(g)
    if m:
        return "ad_valorem", Decimal(m.group(1)), "percent"
    if "¢" in g or re.search(r"\$[\d.]+/", g):
        m = SPECIFIC.fullmatch(g)
        if m and m.group(1) is not None:
            unit = m.group(2).strip()
            return "specific", Decimal(m.group(1)) / Decimal("100"), f"USD/{unit}"
        if m and m.group(3) is not None:
            unit = m.group(4).strip()
            return "specific", Decimal(m.group(3)), f"USD/{unit}"
        return "specific", None, "other"
    return "other", None, "other"


def parse_special_rates(special: str) -> list[tuple[str, Decimal, str]]:
    """Pull (tag, rate, unit) pairs from a `special` cell.

    Skips a cell that is only ``No change``. Mixed cells like
    ``No change (A) Free (CA,IL)`` still yield the Free/percent tags.
    """
    s = (special or "").strip()
    if not s or re.fullmatch(r"no\s*change\.?", s, re.I):
        return []
    out: list[tuple[str, Decimal, str]] = []
    for m in SPECIAL_FREE.finditer(s):
        for tag in _split_tags(m.group(1)):
            out.append((tag, Decimal("0"), "free"))
    for m in SPECIAL_PCT.finditer(s):
        try:
            rate = Decimal(m.group(1))
        except InvalidOperation:
            continue
        for tag in _split_tags(m.group(2)):
            out.append((tag, rate, "percent"))
    # Dedupe by (tag, unit), first wins
    seen: set[tuple[str, str]] = set()
    uniq: list[tuple[str, Decimal, str]] = []
    for tag, rate, unit in out:
        key = (tag, unit)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((tag, rate, unit))
    return uniq


def _split_tags(blob: str) -> list[str]:
    return [t.strip().rstrip("*") for t in re.split(r"[,/]", blob) if t.strip()]


def is_superior(superior: str) -> bool:
    return (superior or "").strip().lower() in ("true", "1", "t")
