#!/usr/bin/env python3
"""Extract useful artifacts from compiled .pyc files.

Run this script with the same CPython minor version used to compile the .pyc files.
"""

from __future__ import annotations

import argparse
import json
import marshal
import struct
import types
from io import StringIO
from pathlib import Path
import dis
import importlib.util

HEADER_SIZE = 16


def parse_header(raw: bytes) -> dict:
    magic = raw[:4].hex()
    flags = struct.unpack('<I', raw[4:8])[0]
    timestamp = struct.unpack('<I', raw[8:12])[0]
    source_size = struct.unpack('<I', raw[12:16])[0]
    return {
        'magic_hex': magic,
        'flags': flags,
        'timestamp_or_hash_low': timestamp,
        'source_size_or_hash_high': source_size,
    }


def walk_code_objects(code: types.CodeType):
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from walk_code_objects(const)


def code_summary(code: types.CodeType) -> dict:
    return {
        'name': code.co_name,
        'qualname': getattr(code, 'co_qualname', code.co_name),
        'filename': code.co_filename,
        'firstlineno': code.co_firstlineno,
        'argcount': code.co_argcount,
        'posonlyargcount': code.co_posonlyargcount,
        'kwonlyargcount': code.co_kwonlyargcount,
        'varnames': list(code.co_varnames),
        'names': list(code.co_names),
        'freevars': list(code.co_freevars),
        'cellvars': list(code.co_cellvars),
    }


def disassemble(code: types.CodeType) -> str:
    buf = StringIO()
    dis.dis(code, file=buf, depth=None, show_caches=False)
    return buf.getvalue()


def process_file(path: Path, output_dir: Path) -> None:
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE:
        raise ValueError(f'Invalid .pyc: {path}')

    header = parse_header(raw[:HEADER_SIZE])
    code = marshal.loads(raw[HEADER_SIZE:])

    base = output_dir / path.stem
    base.mkdir(parents=True, exist_ok=True)

    metadata = {
        'runtime_magic_hex': importlib.util.MAGIC_NUMBER.hex(),
        'pyc_header': header,
        'top_level': code_summary(code),
        'nested_code_objects': [code_summary(obj) for obj in walk_code_objects(code)],
    }

    (base / 'metadata.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    (base / 'disassembly.txt').write_text(disassemble(code), encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()

    pyc_files = sorted(args.input_dir.glob('*.pyc'))
    if not pyc_files:
        raise SystemExit(f'No .pyc files found in: {args.input_dir}')

    for path in pyc_files:
        process_file(path, args.output_dir)
        print(f'OK: {path.name}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
