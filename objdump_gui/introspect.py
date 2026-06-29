"""Discover the capabilities of the local objdump binary at runtime.

Everything the UI offers for target/architecture/disassembler selection is
derived from the actual installed binutils, never hard-coded, so the GUI stays
correct across binutils versions and cross toolchains.
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class Capabilities:
    path: str
    version: str = ""
    targets: list[str] = field(default_factory=list)
    architectures: list[str] = field(default_factory=list)
    # Architecture-specific -M disassembler options, e.g. intel/att for x86.
    disasm_options: list[str] = field(default_factory=list)
    demangle_styles: list[str] = field(default_factory=list)


# Demangle styles are a fixed binutils enum; objdump --help lists them inline.
_DEFAULT_DEMANGLE = ["auto", "gnu-v3", "java", "gnat", "dlang", "rust"]


def find_objdump(preferred: str | None = None) -> str | None:
    """Locate an objdump binary (honouring an explicit override / $OBJDUMP)."""
    for cand in (preferred, ):
        if cand and (shutil.which(cand) or _is_exec(cand)):
            return cand
    import os
    env = os.environ.get("OBJDUMP")
    if env and (shutil.which(env) or _is_exec(env)):
        return env
    return shutil.which("objdump")


def _is_exec(path: str) -> bool:
    import os
    return os.path.isfile(path) and os.access(path, os.X_OK)


def arch_family(caps: "Capabilities") -> str:
    """Classify the probed objdump's target family for syntax highlighting."""
    arches = caps.architectures
    if any(a.startswith("avr") for a in arches):
        return "avr"
    joined = " ".join(arches).lower()
    if "riscv" in joined:
        return "riscv"
    if "aarch64" in joined or "arm" in joined:
        return "arm"
    if any(k in joined for k in ("i386", "x86", "i8086")):
        return "x86"
    return "generic"


def discover_objdumps() -> list[str]:
    """Find GNU objdump binaries on PATH (plus ~/.local/bin).

    Returns full paths to ``objdump`` / ``*-objdump`` executables whose
    ``--version`` identifies them as GNU objdump, so cross toolchains
    (avr-objdump, arm-none-eabi-objdump, …) appear in the Toolchain menu while
    incompatible variants (llvm-objdump, eu-objdump) are excluded — this GUI is
    built around GNU objdump's option set and output format.
    """
    import os

    dirs = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    extra = os.path.expanduser("~/.local/bin")
    if extra not in dirs:
        dirs.append(extra)

    by_name: dict[str, str] = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for name in entries:
            if name != "objdump" and not name.endswith("-objdump"):
                continue
            full = os.path.join(d, name)
            if name not in by_name and os.path.isfile(full) and os.access(full, os.X_OK):
                by_name[name] = full

    out: list[str] = []
    for name in sorted(by_name):
        if "GNU objdump" in _run(by_name[name], "--version"):
            out.append(by_name[name])
    return out


def _run(path: str, *args: str) -> str:
    try:
        cp = subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return (cp.stdout or "") + "\n" + (cp.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return ""


@functools.lru_cache(maxsize=8)
def probe(path: str) -> Capabilities:
    """Probe an objdump binary; results cached per path for the session."""
    caps = Capabilities(path=path, demangle_styles=list(_DEFAULT_DEMANGLE))

    ver = _run(path, "--version")
    if ver:
        caps.version = ver.strip().splitlines()[0] if ver.strip() else ""

    help_txt = _run(path, "--help")

    m = re.search(r"supported targets:\s*(.+)", help_txt)
    if m:
        caps.targets = m.group(1).split()
    else:
        info = _run(path, "--info")
        caps.targets = [
            ln.strip()
            for ln in info.splitlines()
            if ln and not ln.startswith(" ") and "header" not in ln
            and not ln.lower().startswith("bfd")
        ]

    m = re.search(r"supported architectures:\s*(.+)", help_txt)
    if m:
        caps.architectures = m.group(1).split()

    caps.disasm_options = _parse_disasm_options(help_txt)

    m = re.search(r'STYLE can be\s+(.+)', help_txt)
    if m:
        styles = re.findall(r'"([^"]+)"', m.group(1))
        styles += re.findall(r'"([^"]+)"', help_txt.split("STYLE can be", 1)[-1][:200])
        styles = [s for s in dict.fromkeys(styles) if s != "none"]
        if styles:
            caps.demangle_styles = styles
    return caps


def _parse_disasm_options(help_txt: str) -> list[str]:
    """Extract the architecture-specific -M option tokens from --help."""
    start = help_txt.find("disassembler options are supported")
    if start == -1:
        return []
    block = help_txt[start:]
    end = block.find("Options supported for -P")
    if end != -1:
        block = block[:end]
    opts: list[str] = []
    started = False
    for line in block.splitlines():
        if not started:
            # Skip the intro prose; option rows begin after its trailing ":".
            if line.rstrip().endswith(":"):
                started = True
            continue
        # An option row is indented exactly two spaces then the option name.
        # Wrapped description lines are indented far more, so requiring a
        # non-space at column 2 excludes them (e.g. the "Display instruction…"
        # continuation under att-mnemonic).
        m = re.match(r"^ {2}([A-Za-z][\w-]*)(?=\s|$)", line)
        if m:
            opts.append(m.group(1))
    return list(dict.fromkeys(opts))
