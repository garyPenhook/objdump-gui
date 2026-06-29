"""Reformat objdump disassembly into aligned, human-readable columns.

This is a pure display transform applied to the raw text of a run — it never
re-invokes objdump. It is deliberately conservative: only lines it positively
recognizes as a disassembly label or instruction are reformatted; everything
else (section banners, file headers, symbol tables, ``-S`` source lines, blank
lines) is passed through verbatim. That makes it safe to apply to *any* objdump
output, not just ``-d``.

objdump separates an instruction's fields with real TAB characters
(``addr:\\tbytes\\tmnemonic operands``), which is what makes reliable parsing
possible without guessing per-architecture comment syntax.
"""

from __future__ import annotations

import re

_LABEL_RE = re.compile(r"^[0-9a-fA-F]+\s+<(.+)>:$")
_ADDR_RE = re.compile(r"^\s*([0-9a-fA-F]+):$")
# A raw-bytes field is one or more whole-byte hex groups separated by single
# spaces. Different targets group bytes differently: x86/AVR space-separate byte
# pairs ("48 89 e5", "80 91 00 00") while ARM/AArch64 emit a contiguous opcode
# word ("4408", "0b010000"). Each group must therefore be an EVEN number of hex
# digits — which also disambiguates bytes from odd-length all-hex mnemonics such
# as "add"/"adc"/"dec" when raw bytes are disabled.
_BYTES_RE = re.compile(r"^(?:[0-9a-fA-F]{2})+(?: (?:[0-9a-fA-F]{2})+)*$")


def _split_insn(addr: str, bytestr: str, insn: str) -> dict:
    insn = insn.rstrip()
    parts = insn.split(None, 1)
    return {
        "addr": addr,
        "bytes": bytestr,
        "mnemonic": parts[0] if parts else "",
        "operands": parts[1].strip() if len(parts) > 1 else "",
    }


def _parse(line: str):
    """Classify one line -> (kind, fields).

    objdump separates fields with TABs, but how many fields an instruction has
    is architecture-dependent: x86 emits ``addr:<TAB>bytes<TAB>mnemonic operands``
    (operands and any ``# comment`` space-separated in one field) while AVR emits
    ``addr:<TAB>bytes<TAB>mnemonic<TAB>operands<TAB>; comment``. Splitting on all
    TABs and rejoining the instruction fields with single spaces normalizes both
    (and removes the embedded tabs AVR would otherwise leave in the operands).
    """
    if line.startswith("Disassembly of section"):
        return ("banner", {})
    m = _LABEL_RE.match(line)
    if m:
        return ("label", {"name": m.group(1)})
    if "\t" not in line:
        return ("other", {})
    parts = line.split("\t")
    am = _ADDR_RE.match(parts[0])
    if not am:
        return ("other", {})
    addr = am.group(1)
    fields = [f for f in parts[1:]]
    bytestr = ""
    if fields and _BYTES_RE.fullmatch(fields[0].strip()):
        bytestr = fields[0].strip()
        fields = fields[1:]
    insn = " ".join(f.strip() for f in fields if f.strip())
    if not insn:
        # Bytes-only continuation line (a long instruction's wrapped bytes).
        return ("byte_cont", {"addr": addr, "bytes": bytestr})
    return ("insn", _split_insn(addr, bytestr, insn))


def _space_commas(ops: str) -> str:
    # Cosmetic: "%rsp,%rbp" -> "%rsp, %rbp"; harmless on memory operands like
    # "(%rax,%rbx,4)" -> "(%rax, %rbx, 4)".
    return re.sub(r",(?!\s)", ", ", ops)


def format_disassembly(
    text: str,
    show_bytes: bool = False,
    space_operands: bool = True,
) -> str:
    """Return ``text`` with recognized disassembly reformatted into columns."""
    lines = text.split("\n")
    parsed = [_parse(ln) for ln in lines]

    addr_w = mnem_w = bytes_w = 0
    for kind, f in parsed:
        if kind == "insn":
            addr_w = max(addr_w, len(f["addr"]))
            mnem_w = max(mnem_w, len(f["mnemonic"]))
            bytes_w = max(bytes_w, len(f["bytes"]))
        elif kind == "byte_cont":
            addr_w = max(addr_w, len(f["addr"]))
            bytes_w = max(bytes_w, len(f["bytes"]))
    mnem_w = min(max(mnem_w, 4), 9)
    bytes_w = min(bytes_w, 30)

    out: list[str] = []
    seen_label = False
    for raw, (kind, f) in zip(lines, parsed):
        if kind == "label":
            # Blank line between functions, but don't stack blanks when a
            # section banner already left one.
            if seen_label and out and out[-1] != "":
                out.append("")
            seen_label = True
            out.append(f"{f['name']}:")
        elif kind == "insn":
            line = "  " + f["addr"].rjust(addr_w) + ":  "
            if show_bytes:
                line += f["bytes"].ljust(bytes_w) + "  "
            line += f["mnemonic"].ljust(mnem_w)
            ops = f["operands"]
            if ops:
                if space_operands:
                    ops = _space_commas(ops)
                line += " " + ops
            out.append(line.rstrip())
        elif kind == "byte_cont":
            # Continuation bytes carry no instruction; keep them only when the
            # byte column is shown, otherwise drop for a cleaner read.
            if show_bytes:
                out.append("  " + f["addr"].rjust(addr_w) + ":  " + f["bytes"])
        else:
            out.append(raw)
    return "\n".join(out)
