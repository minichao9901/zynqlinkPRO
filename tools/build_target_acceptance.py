"""Build and inspect the three-board acceptance images without opening hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path("firmware/target")
SHARED = Path("firmware/target-support/acceptance")
COMMON = ("dbg-a", "dbg-b", "dbg-ram", "uart")
MATRIX = {
    "hpm6800evk": (*COMMON, "performance-axi", "performance-ahb"),
    "f103ze": (*COMMON, "performance", "swo", "spi", "etm", "etm-ram", "etm-loop", "etm-fault"),
    "h743": (*COMMON, "performance-axi", "performance-dtcm", "swo", "swo-source", "spi", "etm"),
}
MARKERS = {"dbg-a": 0x44424741, "dbg-b": 0x44424742, "dbg-ram": 0x44424752}
REQUIRED = {
    "dbg": {"main", "g_boot_id", "g_data_probe", "g_bss_probe", "_SEGGER_RTT", "g_ticks", "g_seq_slot"},
    "performance": {"main", "g_mode", "g_scope", "_SEGGER_RTT", "g_perf_sram_bytes", "g_fixture_ready"},
    "uart": {"main", "g_uart_baud_request", "g_uart_mode", "g_uart_rx_errors", "g_uart_tx"},
    "swo": {"main", "g_itm_request", "g_itm_sent", "g_itm_port"},
    "swo-source": {"main", "g_source_request", "g_source_mode", "g_source_sent"},
    "spi": {"main"},
    "etm": {"main", "g_trace"},
    "etm-ram": {"main", "g_trace"},
    "etm-loop": {"trace_entry", "loop_count"},
    "etm-fault": {"fault_entry", "fault_handler"},
}


def check_output(command, **kwargs):
    return subprocess.check_output([str(item) for item in command], cwd=ROOT, text=True, **kwargs).strip()


def run(command, log, **kwargs):
    with log.open("ab") as output:
        quoted = subprocess.list2cmdline([str(item) for item in command])
        output.write(("\n> " + quoted + "\n").encode())
        result = subprocess.run(
            [str(item) for item in command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, **kwargs
        )
    if result.returncode:
        raise RuntimeError(f"build failed ({result.returncode}): {log}")
    return [str(item) for item in command]


def binary_tool(compiler, utility):
    compiler = Path(compiler)
    return compiler.with_name(compiler.name.replace("gcc", utility))


def elf_layout(path):
    data = path.read_bytes()
    if data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError(f"expected a little-endian ELF32 image: {path}")
    entry, phoff = struct.unpack_from("<II", data, 24)
    phsize, phnum = struct.unpack_from("<HH", data, 42)
    segments = []
    for index in range(phnum):
        kind, offset, vaddr, paddr, filesz, memsz, flags, _ = struct.unpack_from(
            "<8I", data, phoff + phsize * index
        )
        if kind == 1 and memsz:
            if filesz > memsz or offset + filesz > len(data):
                raise ValueError(f"invalid PT_LOAD segment: {path}")
            segments.append((offset, vaddr, paddr, filesz, memsz, flags))
    if not any((entry & ~1) >= v and (entry & ~1) < v + n and f & 1 for _, v, _, n, _, f in segments):
        raise ValueError(f"ELF entry is outside executable file content: {path}")
    return struct.unpack_from("<H", data, 18)[0], entry, segments


def arm_profile(board, name):
    startup = SHARED / "arm_startup.c"
    platform = SHARED / "arm_platform.c"
    h7 = board == "h743"
    cpu = 60 if name == "swo" and h7 else 480 if h7 else 48 if name == "swo" else (
        128 if name in ("performance", "spi") else 72
    )
    hclk = 240 if cpu == 480 else cpu
    ram = name in ("dbg-ram", "swo-source") or (not h7 and name in ("performance", "spi"))
    if h7:
        image = (0x24000000, 0x10000) if ram else (0x08000000, 0x200000)
        data = (0x20008000, 0x8000) if name == "performance-dtcm" else (0x24010000, 0x30000)
    else:
        image = (0x20000000, 0x8000) if ram else (0x08000000, 0x80000)
        data = (0x20008000, 0x8000) if ram else (0x20000000, 0x10000)
    group = "dbg" if name.startswith("dbg-") else "performance" if name.startswith("performance") else name
    sources = [startup, platform]
    if group == "dbg":
        sources.extend(SHARED / (part + ".c") for part in (
            "arm_debug", "engine", "model", "dbg_frames", "debug_observables", "rtt"
        ))
    elif group == "performance":
        sources.extend((SHARED / "performance.c", SHARED / "rtt.c"))
    elif group == "spi":
        sources.append(TARGET / board / "spi/spi_fixture.c")
    else:
        sources.append(SHARED / (group.replace("-", "_") + ".c"))
    return cpu, hclk, image, data, group, sources


def compile_arm(board, name, out, compiler, log):
    cpu, hclk, image, data, group, sources = arm_profile(board, name)
    h7 = board == "h743"
    flags = ["-mcpu=cortex-m7" if h7 else "-mcpu=cortex-m3", "-mthumb"]
    if h7:
        flags += ["-mfpu=fpv5-d16", "-mfloat-abi=hard", "-DTARGET_H743"]
    sdk = TARGET / board / "etm/cdc/sdk/Drivers/CMSIS"
    flags += [
        "-Og" if group == "dbg" else "-O2", "-g3", "-gdwarf-4", "-ffreestanding",
        "-ffunction-sections", "-fdata-sections", "-fno-common", "-Wall", "-Wextra",
        f"-ffile-prefix-map={ROOT}=.", f"-DFIXTURE_CPU_MHZ={cpu}", f"-DFIXTURE_HCLK_MHZ={hclk}",
        f'-DFIXTURE_BUILD_ID="{board}-{name}"', f"-DFIXTURE_BUILD_MARKER={MARKERS.get(name, 0):#x}",
        "-I" + str(SHARED), "-I" + str(sdk / "Include"),
        "-I" + str(sdk / f"Device/ST/STM32{'H7' if h7 else 'F1'}xx/Include"),
    ]
    if group == "dbg":
        flags += ["-fasynchronous-unwind-tables", "-fno-optimize-sibling-calls"]
    flags += [
        "-nostartfiles", "-specs=nano.specs", "-specs=nosys.specs",
        "-Wl,--gc-sections,--build-id=none", f"-Wl,-Map={out / 'fw.map'}",
        f"-Wl,--defsym=image_base={image[0]:#x},--defsym=image_size={image[1]:#x}",
        f"-Wl,--defsym=data_base={data[0]:#x},--defsym=data_size={data[1]:#x}",
        "-T", SHARED / "arm.ld",
    ]
    command = run([compiler, *flags, *sources, "-o", out / "fw.elf"], log)
    return cpu, hclk, "Ram" if image[0] != 0x08000000 else "Flash", command


def compile_hpm(name, out, sdk_env, log):
    toolchain = sdk_env / "toolchains/rv32imac_zicsr_zifencei_multilib_b_ext-win"
    compiler = toolchain / "bin/riscv32-unknown-elf-gcc.exe"
    host_tools = [sdk_env / "tools" / piece for piece in ("python3", "cmake/bin", "ninja")]
    env = {
        **os.environ,
        "HPM_SDK_BASE": str(sdk_env / "hpm_sdk"),
        "GNURISCV_TOOLCHAIN_PATH": str(toolchain),
        "HPM_SDK_TOOLCHAIN_VARIANT": "gcc",
        "PATH": os.pathsep.join([*map(str, host_tools), os.environ["PATH"]]),
    }
    build = out / "sdk-build"
    build_type = "ram" if name == "dbg-ram" else "flash_xip"
    configure = run([
        "cmake", "-G", "Ninja", "-DBOARD=hpm6800evk", "-DCMAKE_BUILD_TYPE=debug",
        f"-DHPM_BUILD_TYPE={build_type}", f"-DFIXTURE_IMAGE={name}",
        f"-DFIXTURE_BUILD_MARKER={MARKERS.get(name, 0):#x}",
        "-S", TARGET / "hpm6800evk/acceptance", "-B", build,
    ], log, env=env)
    build_cmd = run(["cmake", "--build", build, "--parallel", "3"], log, env=env)
    shutil.copyfile(build / "output/demo.elf", out / "fw.elf")
    return compiler, "Ram" if build_type == "ram" else "Flash", [configure, build_cmd]


def compile_legacy(board, name, out, compiler, log):
    if name in ("etm-loop", "etm-fault"):
        path = TARGET / board / "etm"
        args = ["-mcpu=cortex-m3", "-mthumb", "-g3", "-nostdlib", "-Wl,--build-id=none"]
        if name == "etm-loop":
            args += ["-T", path / "f103_etm_clock_loop.ld", path / "f103_etm_clock_loop.S"]
        else:
            args += ["-Wl,-Ttext=0x20002100,-e,fault_entry", "tools/fixtures/f103_fault_return.S"]
        command = run([compiler, *args, "-o", out / "fw.elf"], log)
        return None, None, "Ram fixture", command
    script = TARGET / board / "etm/cdc/build.ps1"
    if board == "f103ze":
        cpu = 72 if name == "etm-ram" else 48
        args = ["-Chip", "ze", "-CpuMHz", str(cpu)]
        if name == "etm-ram":
            args += ["-Ram", "-TraceWorkload"]
        hclk = cpu
    else:
        cpu, hclk = (480, 240) if name == "spi" else (60, 60)
        args = ["-CoreMHz", str(cpu), "-TraceR", "24" if name == "spi" else "12"]
        if name == "spi":
            args += ["-SpiFixture", "-BannerEveryMs", "0"]
    command = run([
        "pwsh", "-NoProfile", "-File", script, *args, "-Gcc", compiler, "-OutputDir", out, "-NoPublish",
    ], log)
    return cpu, hclk, "Ram" if name == "etm-ram" else "Flash", command


def build_image(board, name, out, arm_gcc, sdk_env, metadata):
    out.mkdir(parents=True)
    log = out / "build.log"
    if board == "hpm6800evk":
        compiler, load_kind, command = compile_hpm(name, out, sdk_env, log)
        cpu, hclk = 600, None
    else:
        compiler = arm_gcc
        if name.startswith("etm") or (board, name) == ("h743", "spi"):
            cpu, hclk, load_kind, command = compile_legacy(board, name, out, compiler, log)
        else:
            cpu, hclk, load_kind, command = compile_arm(board, name, out, compiler, log)
    elf = out / "fw.elf"
    machine, entry, segments = elf_layout(elf)
    if machine != (243 if board == "hpm6800evk" else 40):
        raise ValueError(f"wrong architecture: {elf}")
    group = "dbg" if name.startswith("dbg-") else "performance" if name.startswith("performance") else name
    symbol_text = check_output([binary_tool(compiler, "nm"), "-n", "--defined-only", elf])
    symbols = {fields[-1]: int(fields[0], 16) for line in symbol_text.splitlines()
               if len(fields := line.split()) == 3 and fields[1] in "tTrRdDbBaAwWvV"}
    required = REQUIRED[group] | ({"g_spi_arm", "g_spi_rx_bytes"} if (board, name) == ("f103ze", "spi") else set())
    if missing := required - symbols.keys():
        raise ValueError(f"missing symbols in {elf}: {sorted(missing)}")
    for ext, output_type in (("bin", "binary"), ("hex", "ihex")):
        path = out / f"fw.{ext}"
        if not path.exists():
            run([binary_tool(compiler, "objcopy"), "-O", output_type, elf, path], log)
    image = elf.read_bytes()
    if group == "dbg" and board != "hpm6800evk":
        flash = 0x08000000 if load_kind == "Flash" else (0x20000000 if board == "f103ze" else 0x24000000)
        boot_segment = next(s for s in segments if s[2] == flash and s[3] >= 8)
        sp, pc = struct.unpack_from("<II", image, boot_segment[0])
        if pc != entry or sp % 8 or sp != symbols["_estack"]:
            raise ValueError(f"bad Cortex-M initial vector: {elf}")
    return {
        **metadata, "board": board, "image": name, "cpu_mhz": cpu, "hclk_mhz": hclk,
        "load_kind": load_kind, "entry": f"{entry:#010x}",
        "load_segments": [
            {"vaddr": f"{vaddr:#010x}", "paddr": f"{paddr:#010x}", "filesz": n, "memsz": mem}
            for _, vaddr, paddr, n, mem, _ in segments
        ],
        "symbols": {key: f"{symbols[key]:#010x}" for key in sorted(symbols)
                    if key in required or key.startswith("g_") or key == "_SEGGER_RTT"},
        "compiler": check_output([compiler, "--version"]).splitlines()[0],
        "build_command": command,
        "files": {f"fw.{ext}": hashlib.sha256((out / f"fw.{ext}").read_bytes()).hexdigest()
                  for ext in ("elf", "bin", "hex")},
        "validation": "built and ELF layout inspected; hardware pending",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", choices=("all", *MATRIX), default="all")
    parser.add_argument("--image", action="append", help="limit build to these image names")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--sdk-env", type=Path, default=Path(os.getenv("HPM_SDK_ENV_DIR", "E:/sdk_env_v1.11.0")))
    parser.add_argument("--gcc", type=Path, help="ARM GCC executable")
    parser.add_argument("--list", action="store_true", help="preview images without building")
    args = parser.parse_args()
    boards = list(MATRIX) if args.board == "all" else [args.board]
    images = [(board, image) for board in boards for image in MATRIX[board] if not args.image or image in args.image]
    if set(args.image or ()) - {image for _, image in images}:
        parser.error("an image name does not apply to the selected boards")
    if args.list:
        for board, name in images:
            print(f"{board}/{name}")
        return
    if not args.out:
        parser.error("--out is required when building")
    arm_gcc = args.gcc or shutil.which("arm-none-eabi-gcc")
    if not arm_gcc and any(board != "hpm6800evk" for board, _ in images):
        parser.error("ARM GCC is missing; pass --gcc")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    metadata = {
        "source_revision": check_output(["git", "rev-parse", "HEAD"]),
        "source_dirty": bool(check_output(["git", "status", "--porcelain", "--untracked-files=no"])),
    }
    manifests = []
    for board, name in images:
        print(f"Building {board}/{name}", flush=True)
        dest = out / board / name
        manifest = build_image(board, name, dest, arm_gcc, args.sdk_env.resolve(), metadata)
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        manifests.append(f"{board}/{name}/manifest.json")
    (out / "manifest.json").write_text(json.dumps({**metadata, "images": manifests}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
