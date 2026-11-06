---
name: workspace-teleport
description: AI Agent-Native Workspace & Project Relocation Engine. Use when a user asks to clean up the desktop/downloads, move projects, archive codebases, or reorganize directories without breaking active sessions in Codex, Claude Code, Cursor, or Git Worktrees.
---

# Workspace Teleport (AI-Native Project Relocation)

This skill provides an automated, self-healing project relocation engine. It solves the **Path Anchoring Dilemma** where moving a project breaks IDE/Agent session state, Git worktrees, and terminal references.

## Core Capabilities

1. **Pre-flight Anchor Detection (`scan`)**:
   - Detects whether folders in `~/Desktop` or `~/Downloads` are actively registered in:
     - Codex (`~/.codex/.codex-global-state.json` and `state_5.sqlite`)
     - Git Worktrees (`~/.codex/worktrees/` and `.git/worktrees/`)
   - Distinguishes **Locked** projects from **Free** unanchored items.

2. **Self-Healing Relocation (`move`)**:
   - Moves directory to destination (e.g. `~/Projects/` or `~/Archive/`).
   - Creates a **Ghost Symlink** (`chflags hidden`) at original path so macOS Finder hides the icon, while terminal, scripts, and legacy tools resolve it transparently.
   - Hot-patches Codex `local-projects` and SQLite `threads.cwd`.
   - Runs `git worktree repair` to re-align all Git worktree pointers.

3. **Zero-Risk Batch Archival (`batch-free`)**:
   - Safely archives all free, unanchored items (spreadsheets, old screenshots, loose media, unreferenced folders) into an archive directory in one shot, leaving locked projects intact.

## CLI Usage (Run by Agent)

```bash
# 1. Scan directory status
workspace-teleport scan ~/Desktop
workspace-teleport scan ~/Downloads --json

# 2. Relocate a specific project (with full self-healing and ghost symlink)
workspace-teleport move ~/Desktop/my-project ~/Projects/

# 3. Dry-run first to inspect plan
workspace-teleport move ~/Desktop/my-project ~/Projects/ --dry-run

# 4. Batch archive only free items from Desktop to Archive
workspace-teleport batch-free ~/Desktop ~/Desktop/Archive
```

## Agent Guidelines

- When the user says "帮我整理桌面/下载", "把这个项目归档", "把这个项目挪走但别影响会话":
  1. Run `workspace-teleport scan` to identify which items are free and which are locked.
  2. For locked projects, use `workspace-teleport move` with the default `--mode=both` to guarantee that Codex/Claude/Git worktrees remain 100% operational.
  3. For free items, offer or execute `workspace-teleport batch-free` to instantly clear clutter.
