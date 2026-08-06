#!/usr/bin/env python3
"""Export a Codex rollout JSONL as an authoritative raw copy and readable Markdown."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def text_parts(content: Any) -> Iterable[str]:
    if isinstance(content, str):
        yield content
        return
    if not isinstance(content, list):
        return
    for item in content:
        if not isinstance(item, dict):
            continue
        for key in ("text", "input_text", "output_text"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                yield value
                break
        else:
            item_type = item.get("type", "attachment")
            if item_type in {"input_image", "image", "local_image"}:
                yield f"[Image attachment: {item_type}]"


def message_from_record(record: dict[str, Any]) -> tuple[str, str] | None:
    if record.get("type") != "response_item":
        return None
    payload = record.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None
    role = str(payload.get("role", "unknown"))
    if role not in {"user", "assistant"}:
        return None
    text = "\n\n".join(text_parts(payload.get("content"))).strip()
    if not text:
        return None
    return role, text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Codex rollout JSONL file")
    parser.add_argument("output", type=Path, help="Export directory")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw_target = output / "codex-conversation-complete.jsonl"
    markdown_target = output / "codex-conversation-readable.md"

    message_count = 0
    with source.open("r", encoding="utf-8") as src, markdown_target.open(
        "w", encoding="utf-8", newline="\n"
    ) as md:
        md.write("# DuskRain Food Map - Codex Conversation Export\n\n")
        md.write(f"- Exported: {datetime.now(timezone.utc).isoformat()}\n")
        md.write(f"- Source: `{source.name}`\n")
        md.write("- The JSONL file is the complete authoritative record, including tool calls and attachments.\n\n")
        for line in src:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = message_from_record(record)
            if not message:
                continue
            role, text = message
            message_count += 1
            timestamp = record.get("timestamp", "")
            heading = "User" if role == "user" else "Assistant"
            md.write(f"## {heading} - {timestamp}\n\n{text}\n\n")

    shutil.copy2(source, raw_target)
    manifest = {
        "source": str(source),
        "raw_export": raw_target.name,
        "readable_export": markdown_target.name,
        "messages": message_count,
        "raw_bytes": raw_target.stat().st_size,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / "conversation-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
