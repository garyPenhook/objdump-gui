"""Tests for the declarative option catalogue and its argv builders."""

from objdump_gui.options import build_groups


def _specs(caps):
    return {s.key: s for _grp, specs in build_groups(caps) for s in specs}


def test_flag_builders(x86_caps):
    s = _specs(x86_caps)
    assert s["d"].build(True) == ["-d"]
    assert s["d"].build(False) == []
    assert s["x"].build(True) == ["-x"]


def test_short_option_value_uses_space_not_equals(x86_caps):
    # -m / -b are short options: objdump rejects "-m=i386"; must be "-m i386".
    s = _specs(x86_caps)
    assert s["m"].build("i386") == ["-m", "i386"]
    assert s["b"].build("elf64-x86-64") == ["-b", "elf64-x86-64"]
    assert s["m"].build("") == []


def test_long_option_value_uses_equals(x86_caps):
    s = _specs(x86_caps)
    assert s["insn_width"].build("7") == ["--insn-width=7"]
    assert s["start_address"].build("0x401000") == ["--start-address=0x401000"]
    assert s["insn_width"].build("") == []


def test_choice_builders(x86_caps):
    s = _specs(x86_caps)
    assert s["endian"].build("big") == ["-EB"]
    assert s["endian"].build("little") == ["-EL"]
    assert s["endian"].build("") == []
    assert s["demangle"].build("rust") == ["--demangle=rust"]
    assert s["demangle"].build("default") == ["-C"]
    assert s["visualize"].build("color") == ["--visualize-jumps=color"]
    assert s["visualize"].build("on") == ["--visualize-jumps"]


def test_dwarf_builder(x86_caps):
    s = _specs(x86_caps)
    assert s["dwarf"].build(["info", "abbrev"]) == ["--dwarf=info,abbrev"]
    assert s["dwarf"].build(["all"]) == ["-W"]
    assert s["dwarf"].build([]) == []


def test_section_repeat_builder(x86_caps):
    s = _specs(x86_caps)
    assert s["j"].build(".text, .data") == ["-j", ".text", "-j", ".data"]
    assert s["j"].build("") == []


def test_msyntax_and_M(x86_caps):
    s = _specs(x86_caps)
    assert s["msyntax"].build("intel") == ["-M", "intel"]
    assert s["M"].build("intel,addr64") == ["-M", "intel,addr64"]


def test_architecture_choices_reflect_caps(x86_caps):
    s = _specs(x86_caps)
    arch_values = [data for _disp, data in s["m"].choices]
    assert "i386:x86-64" in arch_values
    assert "" in arch_values  # the "(auto)" no-op entry
