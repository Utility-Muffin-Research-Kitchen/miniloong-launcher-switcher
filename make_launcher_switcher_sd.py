#!/usr/bin/env python3
"""Generate a standalone Miniloong Pocket 1 launcher-switcher SD payload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_VER_INNER = 2147483647
DEFAULT_OTA_FILE = "launcher_probe.bin"
DEFAULT_PROBE_CONTENT = b"miniloong launcher switcher probe\n"
INSTALLER_NAME = "umrk-launcher-install.sh"
MLP1_SDCARD_PATH = "/mnt/sdcard"

ROOT_DIR = Path(__file__).resolve().parent
WRAPPER_PATH = ROOT_DIR / "device" / "loong_pangu.wrapper"
UNINSTALLER_PATH = ROOT_DIR / "device" / "umrk-launcher-switcher-uninstall.sh"

MASK64 = (1 << 64) - 1


def _rotl64(value: int, count: int) -> int:
    value &= MASK64
    return ((value << count) & MASK64) | (value >> (64 - count))


def _fmix64(value: int) -> int:
    value ^= value >> 33
    value = (value * 0xFF51AFD7ED558CCD) & MASK64
    value ^= value >> 33
    value = (value * 0xC4CEB9FE1A85EC53) & MASK64
    value ^= value >> 33
    return value & MASK64


def murmurhash3_x64_128_digest(data: bytes, seed: int = 42) -> bytes:
    """Return MurmurHash3_x64_128 as loong_daemon formats it."""
    c1 = 0x87C37B91114253D5
    c2 = 0x4CF5AD432745937F
    h1 = seed & MASK64
    h2 = seed & MASK64

    block_count = len(data) // 16
    for index in range(block_count):
        block = data[index * 16 : (index + 1) * 16]
        k1 = int.from_bytes(block[:8], "little")
        k2 = int.from_bytes(block[8:], "little")

        k1 = (k1 * c1) & MASK64
        k1 = _rotl64(k1, 31)
        k1 = (k1 * c2) & MASK64
        h1 ^= k1

        h1 = _rotl64(h1, 27)
        h1 = (h1 + h2) & MASK64
        h1 = (h1 * 5 + 0x52DCE729) & MASK64

        k2 = (k2 * c2) & MASK64
        k2 = _rotl64(k2, 33)
        k2 = (k2 * c1) & MASK64
        h2 ^= k2

        h2 = _rotl64(h2, 31)
        h2 = (h2 + h1) & MASK64
        h2 = (h2 * 5 + 0x38495AB5) & MASK64

    tail = data[block_count * 16 :]
    k1 = 0
    k2 = 0

    for offset, value in enumerate(tail[:8]):
        k1 ^= value << (offset * 8)
    for offset, value in enumerate(tail[8:]):
        k2 ^= value << (offset * 8)

    if k2:
        k2 = (k2 * c2) & MASK64
        k2 = _rotl64(k2, 33)
        k2 = (k2 * c1) & MASK64
        h2 ^= k2

    if k1:
        k1 = (k1 * c1) & MASK64
        k1 = _rotl64(k1, 31)
        k1 = (k1 * c2) & MASK64
        h1 ^= k1

    length = len(data)
    h1 ^= length
    h2 ^= length

    h1 = (h1 + h2) & MASK64
    h2 = (h2 + h1) & MASK64

    h1 = _fmix64(h1)
    h2 = _fmix64(h2)

    h1 = (h1 + h2) & MASK64
    h2 = (h2 + h1) & MASK64

    return h1.to_bytes(8, "little") + h2.to_bytes(8, "little")


def loong_upgrade_hash(ver_inner: int, ota_file: str, ota_size: int) -> tuple[str, str]:
    hash_input = f"{ver_inner}{MLP1_SDCARD_PATH}/{ota_file}{ota_size}"
    digest = murmurhash3_x64_128_digest(hash_input.encode("utf-8"), seed=42)
    return digest.hex().upper(), hash_input


def shell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def read_required(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"missing required file: {path}")
    return path.read_text(encoding="utf-8")


def build_installer_script() -> str:
    wrapper = read_required(WRAPPER_PATH).rstrip()
    uninstaller = read_required(UNINSTALLER_PATH).rstrip()
    return f"""#!/bin/sh
set -u

PLATFORM="${{PLATFORM:-mlp1}}"
SDCARD_PATH="${{SDCARD_PATH:-{MLP1_SDCARD_PATH}}}"
USERDATA_PATH="${{USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}}"
LOGS_PATH="${{LOGS_PATH:-$USERDATA_PATH/logs}}"
INTERNAL_DATA="${{UMRK_INTERNAL_DATA_PATH:-$USERDATA_PATH}}"
LOG="$LOGS_PATH/umrk-launcher-install.log"
TARGET=/loong/loong_pangu
BACKUP=/loong/loong_pangu.stock.umrk
WRAPPER_TMP=/tmp/loong_pangu.umrk-wrapper.$$
UNINSTALL=/usr/bin/umrk-launcher-switcher-uninstall.sh

log_msg() {{
    mkdir -p "$LOGS_PATH" "$INTERNAL_DATA" 2>/dev/null || true
    printf '[%s] %s\\n' "$(date '+%F %T' 2>/dev/null || echo unknown)" "$*" >>"$LOG" 2>/dev/null || true
}}

fail() {{
    log_msg "$*"
    echo "$*" >&2
    exit 1
}}

log_msg "launcher switcher installer starting"
mv "$SDCARD_PATH/loong_upgrade" "$SDCARD_PATH/loong_upgrade.used" 2>/dev/null || true

if [ ! -f "$BACKUP" ]; then
    if [ ! -e "$TARGET" ]; then
        fail "target missing: $TARGET"
    fi

    first_two="$(dd if="$TARGET" bs=2 count=1 2>/dev/null || true)"
    if [ "$first_two" = "#!" ]; then
        fail "target looks like a script and no stock backup exists; refusing to overwrite"
    fi

    cp -p "$TARGET" "$BACKUP" || fail "failed to create stock backup"
    chmod 755 "$BACKUP" 2>/dev/null || true
    log_msg "created backup: $BACKUP"
else
    log_msg "backup already exists: $BACKUP"
fi

if [ ! -s "$BACKUP" ]; then
    fail "stock backup is empty or invalid"
fi

cat > "$WRAPPER_TMP" <<'UMRK_LAUNCHER_WRAPPER_EOF'
{wrapper}
UMRK_LAUNCHER_WRAPPER_EOF

chmod 755 "$WRAPPER_TMP" || fail "failed to chmod wrapper"
mv "$WRAPPER_TMP" "$TARGET" || fail "failed to install wrapper"
chmod 755 "$TARGET" 2>/dev/null || true

cat > "$UNINSTALL" <<'UMRK_LAUNCHER_UNINSTALL_EOF'
{uninstaller}
UMRK_LAUNCHER_UNINSTALL_EOF

chmod 755 "$UNINSTALL" 2>/dev/null || true
touch "$INTERNAL_DATA/umrk_launcher_switcher_installed" 2>/dev/null || true
sync

log_msg "installed launcher switcher wrapper"
echo "installed launcher switcher wrapper"
"""


def install_command() -> str:
    return (
        f"SDCARD_PATH={MLP1_SDCARD_PATH}; "
        "PLATFORM=${PLATFORM:-mlp1}; "
        "USERDATA_PATH=${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}; "
        "LOGS_PATH=${LOGS_PATH:-$USERDATA_PATH/logs}; "
        "mkdir -p $LOGS_PATH 2>/dev/null || true; "
        "INSTALL_LOG=$LOGS_PATH/umrk-launcher-install-command.log; "
        "printf 'launcher switcher otaCommand started\\n' >$INSTALL_LOG 2>/dev/null || true; "
        f"sh $SDCARD_PATH/{INSTALLER_NAME} >>$INSTALL_LOG 2>&1; "
        "printf 'launcher switcher installer returned\\n' >>$INSTALL_LOG 2>/dev/null || true; "
        "sync; "
        "while true; do sleep 3600; done"
    )


def probe_command() -> str:
    return (
        f"SDCARD_PATH={MLP1_SDCARD_PATH}; "
        "PLATFORM=${PLATFORM:-mlp1}; "
        "USERDATA_PATH=${USERDATA_PATH:-$SDCARD_PATH/.userdata/$PLATFORM}; "
        "LOGS_PATH=${LOGS_PATH:-$USERDATA_PATH/logs}; "
        "INTERNAL_DATA=${UMRK_INTERNAL_DATA_PATH:-$USERDATA_PATH}; "
        "mkdir -p $LOGS_PATH $INTERNAL_DATA 2>/dev/null || true; "
        "LOG=$LOGS_PATH/umrk-launcher-probe.log; "
        "printf 'launcher switcher probe started\\n' >$LOG 2>/dev/null || true; "
        "touch $INTERNAL_DATA/umrk_launcher_probe_started 2>/dev/null || true; "
        "mv $SDCARD_PATH/loong_upgrade $SDCARD_PATH/loong_upgrade.used 2>/dev/null || true; "
        "sync; "
        "while true; do sleep 3600; done"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate standalone SD-root files for the MLP1 launcher switcher."
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="launcher_switcher_sd",
        help="Directory to write SD-root payload files into.",
    )
    parser.add_argument(
        "--mode",
        choices=("install", "probe"),
        default="install",
        help="Payload command mode. Defaults to install.",
    )
    parser.add_argument(
        "--ver-inner",
        type=int,
        default=DEFAULT_VER_INNER,
        help=f"Firmware internal version to declare. Defaults to {DEFAULT_VER_INNER}.",
    )
    parser.add_argument(
        "--ota-file",
        default=DEFAULT_OTA_FILE,
        help=f"Dummy nonzero OTA filename. Defaults to {DEFAULT_OTA_FILE}.",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="Custom otaCommand to embed. Overrides --mode.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated files.",
    )
    return parser.parse_args()


def validate_ota_file_name(name: str) -> None:
    if not name or name in {".", "..", "loong_upgrade", "loong_upgrade.used"}:
        raise SystemExit(f"unsafe --ota-file value: {name!r}")
    if "/" in name or "\\" in name:
        raise SystemExit("--ota-file must be a simple filename, not a path")


def write_text_if_allowed(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists; rerun with --force to overwrite")
    path.write_text(content, encoding="utf-8")


def write_bytes_if_allowed(path: Path, content: bytes, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"{path} already exists; rerun with --force to overwrite")
    path.write_bytes(content)


def write_payload(args: argparse.Namespace) -> None:
    validate_ota_file_name(args.ota_file)
    if args.ver_inner < 1:
        raise SystemExit("--ver-inner must be positive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ota_path = output_dir / args.ota_file
    trigger_path = output_dir / "loong_upgrade"
    installer_path = output_dir / INSTALLER_NAME

    write_bytes_if_allowed(ota_path, DEFAULT_PROBE_CONTENT, args.force)
    ota_hash, hash_input = loong_upgrade_hash(args.ver_inner, args.ota_file, ota_path.stat().st_size)

    if args.command is not None:
        command = args.command
    elif args.mode == "probe":
        command = probe_command()
    else:
        command = install_command()

    payload = {
        "verInner": args.ver_inner,
        "otaFile": args.ota_file,
        "otaHash": ota_hash,
        "otaCommand": command,
    }
    write_text_if_allowed(
        trigger_path,
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        args.force,
    )

    if args.command is None and args.mode == "install":
        write_text_if_allowed(installer_path, build_installer_script(), args.force)
    elif installer_path.exists() and args.force:
        installer_path.unlink()

    print(f"Wrote SD payload directory: {output_dir}")
    print(f"  {trigger_path}")
    print(f"  {ota_path}")
    if installer_path.exists():
        print(f"  {installer_path}")
    print(f"otaHash: {ota_hash}")
    print(f"hash input: {hash_input}")
    print(f"mode: {args.mode if args.command is None else 'custom'}")
    print("Copy the generated files to the root of a FAT32 or ext4 SD card.")
    print("Do not use exFAT; stock loong_daemon ignores exFAT SD media.")


def main() -> None:
    write_payload(parse_args())


if __name__ == "__main__":
    main()
