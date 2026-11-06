"""
Command-line interface for workspace-teleport.
"""

import sys
import json
import argparse
import shutil
from pathlib import Path
from workspace_teleport.core import (
    scan_directory,
    relocate_project,
)


def main():
    parser = argparse.ArgumentParser(
        prog="workspace-teleport",
        description="workspace-teleport: AI Agent-Native Workspace & Project Relocation Engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # scan
    scan_parser = subparsers.add_parser(
        "scan", help="Scan a directory and identify Codex/Git anchors"
    )
    scan_parser.add_argument(
        "path", nargs="?", default="~/Desktop", help="Directory to scan (default: ~/Desktop)"
    )
    scan_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # move
    move_parser = subparsers.add_parser(
        "move", help="Relocate a project safely with self-healing"
    )
    move_parser.add_argument("src", help="Source project folder")
    move_parser.add_argument("dest", help="Destination folder (e.g. ~/Projects or ~/Archive)")
    move_parser.add_argument(
        "--mode",
        choices=["both", "shadow", "heal"],
        default="both",
        help="Relocation mode (default: both)",
    )
    move_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a trial run without modifying anything",
    )
    move_parser.add_argument("--json", action="store_true", help="Output result as JSON")

    # batch-free
    batch_parser = subparsers.add_parser(
        "batch-free", help="Move all unanchored (free) items to a clean archive"
    )
    batch_parser.add_argument(
        "src", default="~/Desktop", nargs="?", help="Source directory (default: ~/Desktop)"
    )
    batch_parser.add_argument(
        "dest", help="Archive destination directory (e.g. ~/Desktop/Archive)"
    )
    batch_parser.add_argument(
        "--dry-run", action="store_true", help="Perform trial run"
    )
    batch_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "scan":
        res = scan_directory(args.path)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(f"\n📂 Directory: {res['scanned_directory']}")
            print(
                f"📊 Total items: {res['total_items']} | 🔒 Locked by Codex/Git: {res['locked_count']} | ✨ Free to organize: {res['free_count']}\n"
            )
            print(f"{'STATUS':<8} {'TYPE':<6} {'NAME'}")
            print("-" * 50)
            for it in res["items"]:
                st = "🔒 LOCK" if it["locked_by_codex"] else "✨ FREE"
                t = "DIR" if it["is_dir"] else "FILE"
                print(f"{st:<8} {t:<6} {it['name']}")

    elif args.command == "move":
        res = relocate_project(args.src, args.dest, mode=args.mode, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            if res.get("status") == "success":
                print(f"\n✅ Relocation Complete: {res['source']} -> {res['destination']}")
                for act in res.get("actions", []):
                    print(f"   • {act}")
                if "codex_healing" in res:
                    ch = res["codex_healing"]
                    print(
                        f"   • Codex state updated: {ch.get('state_json_updated')} | SQLite threads updated: {ch.get('sqlite_threads_updated')}"
                    )
                if "git_healing" in res:
                    gh = res["git_healing"]
                    print(f"   • Git worktrees repaired: {gh.get('worktree_repaired')}")
            else:
                print(f"\n❌ Error: {res.get('message')}")
                sys.exit(1)

    elif args.command == "batch-free":
        scan = scan_directory(args.src)
        free_items = [it for it in scan.get("items", []) if not it["locked_by_codex"]]
        dest_p = Path(args.dest).expanduser().resolve()
        dest_p.mkdir(parents=True, exist_ok=True)

        print(f"\n📦 Batch Organizing {len(free_items)} free items from {args.src} -> {dest_p}")
        moved = []
        for it in free_items:
            s = Path(it["path"])
            t = dest_p / s.name
            if args.dry_run:
                print(f"   [Dry-Run] Would move: {s.name}")
                moved.append(s.name)
            else:
                try:
                    shutil.move(str(s), str(t))
                    print(f"   ✔ Moved: {s.name}")
                    moved.append(s.name)
                except Exception as e:
                    print(f"   ✖ Failed {s.name}: {e}")

        print(f"\nDone! Successfully processed {len(moved)} items.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
