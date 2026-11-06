"""
Core business logic for workspace-teleport.
Handles path detection, ghost symlinks, Codex state healing, and Git worktree repair.
"""

import os
import sys
import json
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

CODEX_DIR = Path.home() / ".codex"
CODEX_STATE_FILE = CODEX_DIR / ".codex-global-state.json"
CODEX_DB_FILE = CODEX_DIR / "state_5.sqlite"
CODEX_WORKTREES_DIR = CODEX_DIR / "worktrees"


def get_codex_anchors():
    """
    扫描并返回当前被 Codex / Git Worktree 活跃引用的绝对路径集合。
    """
    anchors = set()

    # 1. 扫描 Codex 全局状态文件 (.codex-global-state.json)
    if CODEX_STATE_FILE.exists():
        try:
            with open(CODEX_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            for r in state.get("electron-saved-workspace-roots", []):
                if isinstance(r, str):
                    anchors.add(os.path.realpath(r))

            for r in state.get("active-workspace-roots", []):
                if isinstance(r, str):
                    anchors.add(os.path.realpath(r))

            for proj in state.get("local-projects", {}).values():
                for p in proj.get("rootPaths", []):
                    anchors.add(os.path.realpath(p))

            for p in state.get("thread-workspace-root-hints", {}).values():
                if isinstance(p, str):
                    anchors.add(os.path.realpath(p))
        except Exception:
            pass

    # 2. 扫描 Codex SQLite 数据库 (state_5.sqlite threads.cwd)
    if CODEX_DB_FILE.exists():
        try:
            conn = sqlite3.connect(CODEX_DB_FILE)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT cwd FROM threads WHERE cwd IS NOT NULL;")
            for (cwd,) in cur.fetchall():
                if cwd and os.path.exists(cwd):
                    anchors.add(os.path.realpath(cwd))
            conn.close()
        except Exception:
            pass

    # 3. 扫描 ~/.codex/worktrees 下的关联主仓库
    if CODEX_WORKTREES_DIR.exists():
        for wt in CODEX_WORKTREES_DIR.iterdir():
            git_file = wt / ".git"
            if git_file.exists() and git_file.is_file():
                try:
                    with open(git_file, "r") as gf:
                        content = gf.read()
                        if "gitdir:" in content:
                            raw_path = content.split("gitdir:", 1)[1].strip()
                            if "/.git/worktrees/" in raw_path:
                                main_repo = raw_path.split("/.git/worktrees/")[0]
                                anchors.add(os.path.realpath(main_repo))
                except Exception:
                    pass

    return anchors


def scan_directory(target_dir):
    """
    扫描目标目录，精准分类出“受保护锁定的项目”与“完全自由可归档的项目”。
    """
    target_path = Path(target_dir).expanduser().resolve()
    if not target_path.exists() or not target_path.is_dir():
        return {"error": f"Directory not found: {target_dir}"}

    anchors = get_codex_anchors()

    items = []
    for item in sorted(target_path.iterdir()):
        if item.name.startswith("."):
            continue

        real_p = os.path.realpath(str(item))
        is_locked = (real_p in anchors) or (str(item.resolve()) in anchors)
        is_git = (item / ".git").exists() if item.is_dir() else False
        is_symlink = item.is_symlink()

        items.append({
            "name": item.name,
            "path": str(item),
            "is_dir": item.is_dir(),
            "is_symlink": is_symlink,
            "is_git": is_git,
            "locked_by_codex": is_locked,
        })

    locked_count = sum(1 for i in items if i["locked_by_codex"])
    free_count = len(items) - locked_count

    return {
        "scanned_directory": str(target_path),
        "total_items": len(items),
        "locked_count": locked_count,
        "free_count": free_count,
        "items": items,
    }


def heal_codex_state(old_path, new_path):
    """
    自动热修补 Codex 的 JSON 状态与 SQLite 数据库中的路径记录。
    """
    old_p_str = str(Path(old_path).expanduser().resolve())
    new_p_str = str(Path(new_path).expanduser().resolve())
    healed = {"state_json_updated": False, "sqlite_threads_updated": 0}

    # 1. 更新 .codex-global-state.json
    if CODEX_STATE_FILE.exists():
        try:
            with open(CODEX_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            modified = False

            # 替换 saved roots
            if "electron-saved-workspace-roots" in state:
                new_roots = []
                for r in state["electron-saved-workspace-roots"]:
                    if r == old_p_str:
                        new_roots.append(new_p_str)
                        modified = True
                    else:
                        new_roots.append(r)
                state["electron-saved-workspace-roots"] = new_roots

            # 替换 active roots
            if "active-workspace-roots" in state:
                new_roots = []
                for r in state["active-workspace-roots"]:
                    if r == old_p_str:
                        new_roots.append(new_p_str)
                        modified = True
                    else:
                        new_roots.append(r)
                state["active-workspace-roots"] = new_roots

            # 替换 local-projects 中的 rootPaths
            if "local-projects" in state:
                for proj in state["local-projects"].values():
                    if "rootPaths" in proj:
                        updated_paths = []
                        for p in proj["rootPaths"]:
                            if p == old_p_str:
                                updated_paths.append(new_p_str)
                                modified = True
                            else:
                                updated_paths.append(p)
                        proj["rootPaths"] = updated_paths

            # 替换 hints
            if "thread-workspace-root-hints" in state:
                for tid, p in state["thread-workspace-root-hints"].items():
                    if p == old_p_str:
                        state["thread-workspace-root-hints"][tid] = new_p_str
                        modified = True

            if modified:
                backup_file = CODEX_STATE_FILE.with_suffix(f".json.bak.{int(time.time())}")
                shutil.copy2(CODEX_STATE_FILE, backup_file)

                with open(CODEX_STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2, ensure_ascii=False)
                healed["state_json_updated"] = True
        except Exception as e:
            healed["state_json_error"] = str(e)

    # 2. 更新 state_5.sqlite 中的 threads 表
    if CODEX_DB_FILE.exists():
        try:
            conn = sqlite3.connect(CODEX_DB_FILE)
            cur = conn.cursor()
            cur.execute("UPDATE threads SET cwd = ? WHERE cwd = ?;", (new_p_str, old_p_str))
            affected = cur.rowcount
            conn.commit()
            conn.close()
            healed["sqlite_threads_updated"] = affected
        except Exception as e:
            healed["sqlite_error"] = str(e)

    return healed


def heal_git_worktrees(new_path):
    """
    在新路径和 Codex worktree 目录自动执行 git worktree repair。
    """
    results = {"worktree_repaired": False}
    new_p = Path(new_path).expanduser().resolve()

    if (new_p / ".git").exists():
        try:
            cmd = ["git", "-C", str(new_p), "worktree", "repair"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            results["worktree_repaired"] = (res.returncode == 0)
        except Exception as e:
            results["worktree_error"] = str(e)

    if CODEX_WORKTREES_DIR.exists():
        for wt in CODEX_WORKTREES_DIR.iterdir():
            if (wt / ".git").exists():
                try:
                    subprocess.run(["git", "-C", str(wt), "worktree", "repair"], capture_output=True, timeout=5)
                except Exception:
                    pass

    return results


def relocate_project(src, dest_dir, mode="both", dry_run=False):
    """
    安全搬移项目核心流水线：
    1. 物理搬移目录
    2. 原位创建隐形软链接 (chflags hidden)，保持 100% 穿透
    3. 自动修补 Codex 数据库与全局配置
    4. 自动修复关联的 Git Worktrees
    """
    src_path = Path(src).expanduser().resolve()
    dest_base = Path(dest_dir).expanduser().resolve()

    if not src_path.exists():
        return {"status": "error", "message": f"Source path does not exist: {src}"}

    dest_base.mkdir(parents=True, exist_ok=True)
    target_path = dest_base / src_path.name

    if target_path.exists():
        return {"status": "error", "message": f"Destination already exists: {target_path}"}

    report = {
        "status": "success",
        "source": str(src_path),
        "destination": str(target_path),
        "mode": mode,
        "dry_run": dry_run,
        "actions": []
    }

    if dry_run:
        report["message"] = f"Dry-run: Would move {src_path} -> {target_path} (mode={mode})"
        return report

    # 1. 物理移动
    try:
        shutil.move(str(src_path), str(target_path))
        report["actions"].append(f"Moved directory to {target_path}")
    except Exception as e:
        return {"status": "error", "message": f"Failed to move directory: {e}"}

    # 2. 建立幽灵影子软链接
    if mode in ["shadow", "both"]:
        try:
            os.symlink(str(target_path), str(src_path))
            report["actions"].append(f"Created symlink at {src_path} -> {target_path}")

            if sys.platform == "darwin":
                subprocess.run(["chflags", "hidden", str(src_path)], check=True)
                report["actions"].append("Hidden symlink from macOS Finder (chflags hidden)")
        except Exception as e:
            report["shadow_error"] = f"Failed to create hidden symlink: {e}"

    # 3. 自愈 Codex 状态与 Git Worktree
    if mode in ["heal", "both"]:
        codex_res = heal_codex_state(src_path, target_path)
        report["codex_healing"] = codex_res

        git_res = heal_git_worktrees(target_path)
        report["git_healing"] = git_res

    return report
