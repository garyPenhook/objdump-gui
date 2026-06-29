# objdump GUI

A professional desktop front-end for GNU binutils **`objdump`**, built with
PySide6 (Qt 6). It exposes *every* objdump option through an organized,
searchable panel, builds the command line live, runs it asynchronously, and
renders the output with syntax highlighting plus navigable section/symbol
indexes.

## Highlights

- **Every option, grouped & searchable** — disassembly, headers, symbols,
  relocations, section contents, DWARF, CTF/SFrame, demangling, source
  correlation, and display formatting. The panel is generated from a single
  declarative catalogue (`options.py`), so it always matches the flags.
- **Capability probing** — target formats, architectures, demangle styles and
  architecture-specific `-M` disassembler options are read from *your* installed
  `objdump` at startup, so it is correct across binutils versions and cross
  toolchains.
- **Aligned disassembly view** (View ▸ Aligned, `Ctrl+Shift+A`) — a parsed,
  column-aligned rendering of the disassembly: addresses, mnemonics and operands
  line up, raw byte columns are optional, functions are separated by blank lines,
  and operands are comma-spaced. It is a pure *display* transform on the last
  run's output (no re-run), only touches lines it recognizes as labels/
  instructions, and passes everything else (banners, `-S` source, symbol tables)
  through verbatim. Toggle back to raw objdump text any time.
- **Live command preview** — see and copy the exact `objdump …` command as you
  toggle options.
- **Asynchronous, cancellable runs** — large disassemblies never freeze the UI;
  Run is disabled while busy and Cancel kills the process.
- **Syntax-highlighted output** with an incremental find bar (plain /
  case-sensitive / regex, match count, wrap-around). ANSI color from
  `--disassembler-color` is stripped automatically.
- **Section & Symbol navigators** — model/view tables (fast on huge symbol
  tables; parsing runs off the UI thread) with substring filter and numeric
  hex sorting; double-click a symbol to jump to it, or right-click to re-run
  with `--disassemble=<sym>`.
- **In-disassembly navigation** — Ctrl+click a `<symbol>`/call target to follow
  it to its definition (or *Edit ▸ Follow Symbol*, `Ctrl+]`), and *Go to
  Address* (`Ctrl+G`) jumps to any instruction by address.
- **Option presets & session memory** — save/load named option sets (Presets
  menu); window/dock layout and last-used options persist across sessions.
- **Export** — raw output, aligned output, or syntax-highlighted HTML.
- **Cross-toolchain / AVR support** — GNU objdump backends on your `PATH`
  (`avr-objdump`, `arm-none-eabi-objdump`, `aarch64-linux-gnu-objdump`, …) are
  auto-discovered and listed under *File ▸ Backend Toolchain*; switch backend in
  one click (or use `OBJDUMP=` / `--objdump=`). The whole pipeline adapts to the
  selected target: options/architectures are re-probed, the disassembly
  highlighter switches register sets (x86 `%rax…`, AVR `r0–r31`/`X`/`Y`/`Z`,
  ARM/AArch64 `r0…`/`x0…`/`sp`/`lr`/`wzr`, RISC-V `a0…`/`ra`/`sp`/`fa0…`), and the
  aligned view normalizes each target's field layout — AVR/ARM/AArch64/RISC-V
  separate mnemonic⟶operands⟶comment with tabs and pack opcode bytes differently
  (x86/AVR as spaced pairs `48 89 e5`, ARM/AArch64 as contiguous words `4408`).
  Non-GNU variants (llvm-objdump, eu-objdump) are excluded since the GUI targets
  GNU objdump's option set. *(RISC-V register names were validated against real
  disassembly tokens; install a GNU `riscv*-objdump` and it is auto-discovered.)*
- Dark/light themes, recent files, save output, dockable/tabbed panels.

## Requirements

- Python ≥ 3.10
- PySide6 ≥ 6.5
- GNU binutils `objdump` on `PATH` (or pointed to explicitly)

## Run

```bash
./run.sh                       # from a checkout
./run.sh /bin/ls               # open a file immediately
OBJDUMP=avr-objdump ./run.sh firmware.elf      # AVR (or pick it in the menu)
OBJDUMP=arm-none-eabi-objdump ./run.sh fw.elf
python3 -m objdump_gui --objdump=/usr/bin/objdump a.out
```

Or install it:

```bash
pip install -e .
objdump-gui /bin/ls
```

## Layout

| Area | Contents |
|------|----------|
| Center | Syntax-highlighted output + find bar; command preview bar below |
| Right dock | **Options** (searchable) / **Disassembler Options (-M)** (tabbed) |
| Left docks | **Sections** and **Symbols** navigators (filterable) |
| Bottom dock | **Messages / stderr** log |

## Module map

| File | Responsibility |
|------|----------------|
| `introspect.py` | Probe the objdump binary for targets/arches/options |
| `options.py` | Declarative catalogue of every option + argv builders |
| `runner.py` | Async (QProcess) execution, cancellable |
| `parsers.py` | Tolerant parsing for the section/symbol tables; ANSI strip |
| `prettyprint.py` | Reformat disassembly into aligned, readable columns |
| `highlight.py` | Disassembly syntax highlighter (dark/light) |
| `widgets/options_panel.py` | Auto-generated options UI + command builder |
| `widgets/navigators.py` | Sections & Symbols tables |
| `widgets/output_view.py` | Output viewer + incremental find |
| `main_window.py` | Wiring: menus, toolbar, docks, run lifecycle |
| `app.py` | Bootstrap |
