"""Declarative model of every objdump option.

Each :class:`OptSpec` knows how to render itself (kind + choices) and how to turn
a UI value into argv tokens (``build``). The options panel is generated entirely
from :data:`GROUPS`, and the command builder just concatenates ``build`` results,
so adding/removing an option is a one-line change here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class OptSpec:
    key: str
    label: str
    kind: str                       # flag | text | int | choice | sections | dwarf
    help: str = ""
    build: Callable[[object], list[str]] = lambda v: []
    choices: list[tuple[str, str]] = field(default_factory=list)  # (display, data)
    placeholder: str = ""
    default: object = None


# ---- build helpers ---------------------------------------------------------

def _flag(f: str) -> Callable[[object], list[str]]:
    return lambda v: [f] if v else []


def _kv(f: str, sep: str = "=") -> Callable[[object], list[str]]:
    def b(v):
        v = ("" if v is None else str(v)).strip()
        if not v:
            return []
        return [f + sep + v] if sep == "=" else [f, v]
    return b


def _choice(f: str) -> Callable[[object], list[str]]:
    """Combo where the selected data is appended as ``--flag=DATA`` (empty omits)."""
    def b(v):
        v = "" if v is None else str(v)
        return [f + "=" + v] if v else []
    return b


def _csv_repeat(f: str) -> Callable[[object], list[str]]:
    """Comma/space separated value -> repeated ``f VALUE`` pairs (e.g. -j, -I)."""
    def b(v):
        v = ("" if v is None else str(v)).strip()
        if not v:
            return []
        out: list[str] = []
        for item in re.split(r"[,\s]+", v):
            if item:
                out += [f, item]
        return out
    return b


def _build_endian(v):
    return {"little": ["-EL"], "big": ["-EB"]}.get(v or "", [])


def _build_show_raw(v):
    return {"show": ["--show-raw-insn"], "no": ["--no-show-raw-insn"]}.get(v or "", [])


def _build_recurse(v):
    return {"limit": ["--recurse-limit"], "no": ["--no-recurse-limit"]}.get(v or "", [])


def _build_demangle(v):
    if not v:
        return []
    return ["-C"] if v == "default" else ["--demangle=" + v]


def _build_visualize(v):
    if not v:
        return []
    return ["--visualize-jumps"] if v == "on" else ["--visualize-jumps=" + v]


def _build_followlinks(v):
    return {
        "follow": ["--dwarf=follow-links"],
        "no": ["--dwarf=no-follow-links"],
    }.get(v or "", [])


def _build_dwarf(v):
    """v is a list of selected dwarf section names; 'all' means bare -W."""
    if not v:
        return []
    if "all" in v:
        return ["-W"]
    return ["--dwarf=" + ",".join(v)]


def _build_msyntax(v):
    return ["-M", v] if v else []


# ---- the option catalogue --------------------------------------------------

DWARF_SECTIONS = [
    "all", "abbrev", "addr", "aranges", "cu_index", "decodedline", "frames",
    "frames-interp", "gdb_index", "info", "loc", "macro", "pubnames",
    "pubtypes", "Ranges", "rawline", "str", "str-offsets", "trace_abbrev",
    "trace_aranges", "trace_info", "links",
]


def build_groups(caps) -> list[tuple[str, list[OptSpec]]]:
    """Build the grouped option catalogue, injecting probed target/arch lists."""

    arch_choices = [("(auto)", "")] + [(a, a) for a in caps.architectures]
    target_choices = [("(auto)", "")] + [(t, t) for t in caps.targets]
    demangle_choices = [("(off)", ""), ("default (-C)", "default")] + [
        (s, s) for s in caps.demangle_styles
    ]

    headers = [
        OptSpec("d", "Disassemble executable sections (-d)", "flag",
                "Display assembler contents of executable sections.",
                _flag("-d"), default=True),
        OptSpec("D", "Disassemble all sections (-D)", "flag",
                "Display assembler contents of all sections.", _flag("-D")),
        OptSpec("disassemble_sym", "Disassemble symbol (--disassemble=)", "text",
                "Display assembler contents starting from the given symbol.",
                _kv("--disassemble"), placeholder="main"),
        OptSpec("S", "Intermix source (-S)", "flag",
                "Intermix source code with disassembly (needs debug info).",
                _flag("-S")),
        OptSpec("l", "Line numbers (-l)", "flag",
                "Include line numbers and filenames in output.", _flag("-l")),
        OptSpec("inlines", "Show inlines (--inlines)", "flag",
                "Print all inlines for a source line (with -l).", _flag("--inlines")),
    ]

    info_group = [
        OptSpec("f", "File headers (-f)", "flag",
                "Display the contents of the overall file header.", _flag("-f")),
        OptSpec("p", "Private headers (-p)", "flag",
                "Display object-format-specific file header contents.", _flag("-p")),
        OptSpec("h", "Section headers (-h)", "flag",
                "Display the contents of the section headers.", _flag("-h"),
                default=True),
        OptSpec("x", "All headers (-x)", "flag",
                "Display the contents of all headers.", _flag("-x")),
        OptSpec("a", "Archive headers (-a)", "flag",
                "Display archive header information.", _flag("-a")),
        OptSpec("t", "Symbol table (-t)", "flag",
                "Display the contents of the symbol table(s).", _flag("-t")),
        OptSpec("T", "Dynamic symbols (-T)", "flag",
                "Display the contents of the dynamic symbol table.", _flag("-T")),
        OptSpec("r", "Relocations (-r)", "flag",
                "Display the relocation entries in the file.", _flag("-r")),
        OptSpec("R", "Dynamic relocations (-R)", "flag",
                "Display the dynamic relocation entries.", _flag("-R")),
        OptSpec("special_syms", "Special symbols (--special-syms)", "flag",
                "Include special symbols in symbol dumps.", _flag("--special-syms")),
        OptSpec("private", "Private options (--private=)", "text",
                "Object-format-specific contents, e.g. 'header,sections' for PE.",
                _kv("--private"), placeholder="header,sections"),
    ]

    contents = [
        OptSpec("s", "Full contents (-s)", "flag",
                "Display the full contents of all requested sections (hex).",
                _flag("-s")),
        OptSpec("Z", "Decompress (-Z)", "flag",
                "Decompress sections before displaying their contents.",
                _flag("-Z")),
        OptSpec("g", "Debugging info (-g)", "flag",
                "Display debug information in object file.", _flag("-g")),
        OptSpec("e", "Debugging tags (-e)", "flag",
                "Display debug information using ctags style.", _flag("-e")),
        OptSpec("G", "STABS (-G)", "flag",
                "Display (in raw form) any STABS info in the file.", _flag("-G")),
        OptSpec("L", "Process links (-L)", "flag",
                "Display non-debug sections in separate debuginfo files.",
                _flag("-L")),
        OptSpec("map_global_vars", "Map global vars (--map-global-vars)", "flag",
                "Display memory mapping of global variables.",
                _flag("--map-global-vars")),
    ]

    disasm_fmt = [
        OptSpec("m", "Architecture (-m)", "choice",
                "Specify the target architecture.", _kv("-m", sep=" "),
                choices=arch_choices),
        OptSpec("b", "Target format (-b)", "choice",
                "Specify the target object format (BFD name).", _kv("-b", sep=" "),
                choices=target_choices),
        OptSpec("endian", "Endianness", "choice",
                "Assume big/little endian when disassembling.", _build_endian,
                choices=[("(default)", ""), ("little (-EL)", "little"),
                         ("big (-EB)", "big")]),
        OptSpec("msyntax", "Assembler syntax", "choice",
                "x86: AT&T vs Intel mnemonic syntax (-M).", _build_msyntax,
                choices=[("(default)", ""), ("intel", "intel"), ("att", "att")]),
        OptSpec("M", "Disassembler options (-M)", "text",
                "Comma-separated -M options (see Disassembler Options dock).",
                _kv("-M", sep=" "), placeholder="intel,addr64"),
        OptSpec("j", "Limit to sections (-j)", "sections",
                "Only display information for the named section(s).",
                _csv_repeat("-j"), placeholder=".text,.data"),
        OptSpec("show_raw", "Raw instruction bytes", "choice",
                "Show/hide hex bytes alongside disassembly.", _build_show_raw,
                choices=[("(default)", ""), ("show", "show"), ("hide", "no")]),
        OptSpec("insn_width", "Instruction width (--insn-width)", "int",
                "Bytes shown on a single line for -d.", _kv("--insn-width"),
                placeholder="7"),
        OptSpec("prefix_addresses", "Prefix addresses (--prefix-addresses)", "flag",
                "Print complete address alongside disassembly.",
                _flag("--prefix-addresses")),
        OptSpec("no_addresses", "No addresses (--no-addresses)", "flag",
                "Do not print address alongside disassembly.",
                _flag("--no-addresses")),
        OptSpec("F", "File offsets (-F)", "flag",
                "Include file offsets when displaying information.", _flag("-F")),
        OptSpec("adjust_vma", "Adjust VMA (--adjust-vma=)", "text",
                "Add OFFSET to all displayed section addresses.",
                _kv("--adjust-vma"), placeholder="0x1000"),
        OptSpec("start_address", "Start address (--start-address=)", "text",
                "Only process data whose address is >= ADDR.",
                _kv("--start-address"), placeholder="0x401000"),
        OptSpec("stop_address", "Stop address (--stop-address=)", "text",
                "Only process data whose address is < ADDR.",
                _kv("--stop-address"), placeholder="0x402000"),
        OptSpec("z", "Disassemble zeroes (-z)", "flag",
                "Do not skip blocks of zeroes when disassembling.", _flag("-z")),
        OptSpec("show_all_symbols", "Show all symbols (--show-all-symbols)", "flag",
                "Display all symbols at a given address.",
                _flag("--show-all-symbols")),
        OptSpec("visualize", "Visualize jumps (--visualize-jumps)", "choice",
                "Draw ASCII-art lines for local jumps.", _build_visualize,
                choices=[("(off)", ""), ("on", "on"), ("color", "color"),
                         ("extended-color", "extended-color"), ("off", "off")]),
        OptSpec("disasm_color", "Disassembler color (--disassembler-color)", "choice",
                "Color output (ANSI is stripped for display in this GUI).",
                _choice("--disassembler-color"),
                choices=[("(off)", ""), ("terminal", "terminal"), ("on", "on"),
                         ("extended", "extended")]),
    ]

    source = [
        OptSpec("I", "Source include dirs (-I)", "text",
                "Add directory to search list for source files.",
                _csv_repeat("-I"), placeholder="/path/to/src"),
        OptSpec("file_start_context", "File start context (--file-start-context)",
                "flag", "Include context from start of file (with -S).",
                _flag("--file-start-context")),
        OptSpec("source_comment", "Source comment prefix (--source-comment=)", "text",
                "Prefix lines of source code with this text.",
                _kv("--source-comment"), placeholder="// "),
        OptSpec("prefix", "Path prefix (--prefix=)", "text",
                "Add PREFIX to absolute paths for -S.", _kv("--prefix")),
        OptSpec("prefix_strip", "Prefix strip levels (--prefix-strip=)", "int",
                "Strip initial directory names for -S.", _kv("--prefix-strip"),
                placeholder="2"),
    ]

    demangle = [
        OptSpec("demangle", "Demangle symbols (-C)", "choice",
                "Decode mangled/processed C++/Rust/etc. symbol names.",
                _build_demangle, choices=demangle_choices),
        OptSpec("recurse_limit", "Recursion limit", "choice",
                "Limit recursion while demangling.", _build_recurse,
                choices=[("(default)", ""), ("limit", "limit"),
                         ("no-limit", "no")]),
    ]

    dwarf = [
        OptSpec("dwarf", "DWARF sections (-W / --dwarf=)", "dwarf",
                "Select which DWARF debug sections to display.", _build_dwarf,
                choices=[(n, n) for n in DWARF_SECTIONS]),
        OptSpec("follow_links", "Follow debug links", "choice",
                "Follow links to separate debug info files.", _build_followlinks,
                choices=[("(default)", ""), ("follow", "follow"),
                         ("no-follow", "no")]),
        OptSpec("dwarf_depth", "DWARF depth (--dwarf-depth=)", "int",
                "Do not display DIEs at depth N or greater.", _kv("--dwarf-depth")),
        OptSpec("dwarf_start", "DWARF start (--dwarf-start=)", "int",
                "Display DIEs starting at offset N.", _kv("--dwarf-start")),
        OptSpec("dwarf_check", "DWARF consistency check (--dwarf-check)", "flag",
                "Make additional DWARF consistency checks.", _flag("--dwarf-check")),
        OptSpec("debug_dir", "Debug dir (--debug-dir=)", "text",
                "Search DIR for separate debug info files.", _kv("--debug-dir")),
    ]

    ctf = [
        OptSpec("ctf", "CTF info (--ctf)", "flag",
                "Display CTF info from the default .ctf section.", _flag("--ctf")),
        OptSpec("ctf_section", "CTF section (--ctf=)", "text",
                "Display CTF info from a named section.", _kv("--ctf")),
        OptSpec("ctf_parent", "CTF parent (--ctf-parent=)", "text",
                "Use CTF archive member NAME as the CTF parent.",
                _kv("--ctf-parent")),
        OptSpec("sframe", "SFrame info (--sframe)", "flag",
                "Display SFrame info from the default .sframe section.",
                _flag("--sframe")),
        OptSpec("sframe_section", "SFrame section (--sframe=)", "text",
                "Display SFrame info from a named section.", _kv("--sframe")),
    ]

    display = [
        OptSpec("w", "Wide output (-w)", "flag",
                "Format output for more than 80 columns.", _flag("-w")),
        OptSpec("unicode", "Unicode handling (-U)", "choice",
                "Control display of UTF-8 unicode characters.", _choice("--unicode"),
                choices=[("(default)", ""), ("locale", "locale"),
                         ("invalid", "invalid"), ("hex", "hex"),
                         ("escape", "escape"), ("highlight", "highlight")]),
    ]

    return [
        ("Disassembly", headers),
        ("Headers, Symbols & Relocations", info_group),
        ("Section Contents & Debug", contents),
        ("Disassembly Formatting", disasm_fmt),
        ("Source Correlation", source),
        ("Demangling", demangle),
        ("DWARF", dwarf),
        ("CTF / SFrame", ctf),
        ("Display", display),
    ]
