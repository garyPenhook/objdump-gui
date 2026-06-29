"""Captured raw objdump output snippets used as golden fixtures.

x86/AVR/ARM/AArch64 snippets are verbatim from the respective GNU objdump
(tabs are real). The RISC-V snippet is synthesized in GNU's framing
(addr:<TAB>bytes<TAB>mnemonic<TAB>operands) using register tokens captured from
real disassembly, since no GNU riscv-objdump is available in this environment.
"""

X86_DISASM = "\n".join([
    "0000000000401115 <main>:",
    "  401115:\t55                   \tpush   %rbp",
    "  401116:\t48 89 e5             \tmov    %rsp,%rbp",
    "  40111e:\te8 e3 ff ff ff       \tcall   401106 <helper>",
    "  401124:\tc3                   \tret",
])

AVR_DISASM = "\n".join([
    "00000000 <add>:",
    "   0:\t86 0f       \tadd\tr24, r22",
    "   2:\t97 1f       \tadc\tr25, r23",
    "   4:\t8f ef       \tldi\tr24, 0xFF\t; 255",
])

ARM_THUMB_DISASM = "\n".join([
    "00000000 <add>:",
    "   0:\t4408      \tadd\tr0, r1",
    "   2:\t4770      \tbx\tlr",
])

AARCH64_DISASM = "\n".join([
    "0000000000000000 <add>:",
    "   0:\t0b010000 \tadd\tw0, w0, w1",
    "   4:\td65f03c0 \tret",
])

RISCV_DISASM = "\n".join([
    "0000000000000000 <add>:",
    "   0:\t9d2d\taddw\ta0, a0, a1",
    "   2:\t8082\tret",
])

# objdump -d --no-addresses (label and instructions lose the address).
NO_ADDRESSES_DISASM = "\n".join([
    "<main>:",
    "\t55                   \tpush   %rbp",
    "\t48 89 e5             \tmov    %rsp,%rbp",
    "\te8 e3 ff ff ff       \tcall   <helper>",
])

# objdump -d --prefix-addresses (no tabs; addr + <sym+off> + insn).
PREFIX_ADDRESSES_DISASM = "\n".join([
    "0000000000401115 <main> push   %rbp",
    "0000000000401116 <main+0x1> mov    %rsp,%rbp",
    "000000000040111e <main+0x9> call   0000000000401106 <helper>",
])

# objdump -h around a single-flag (.bss / no comma) section.
SECTIONS_TEXT = "\n".join([
    "Sections:",
    "Idx Name          Size      VMA               LMA               File off  Algn",
    " 20 .data         00000010  0000000000404000  0000000000404000  00003000  2**3",
    "                  CONTENTS, ALLOC, LOAD, DATA",
    " 21 .bss          00000008  0000000000404010  0000000000404010  00003010  2**0",
    "                  ALLOC",
])

# objdump -t snippet (AVR; tab between section and value, 7-char flag field).
SYMBOLS_TEXT = "\n".join([
    "SYMBOL TABLE:",
    "00000000 l    df *ABS*\t00000000 avr.c",
    "00000000 l    d  .text\t00000000 .text",
    "00000000 g     F .text\t0000000e add",
])

# A trimmed objdump --help block exercising the -M disassembler-option parser,
# including a wrapped description line that must NOT be ingested as an option.
HELP_DISASM_OPTIONS = "\n".join([
    "The following i386 specific disassembler options are supported for use",
    "  with the -M switch (multiple options should be separated by commas):",
    "  x86-64      Disassemble in 64bit mode",
    "  att         Display instruction in AT&T syntax",
    "  att-mnemonic  (AT&T syntax only)",
    "              Display instruction with AT&T mnemonic",
    "  intel       Display instruction in Intel syntax",
    "",
    "Options supported for -P/--private switch:",
    "  header      Display the file header",
])
