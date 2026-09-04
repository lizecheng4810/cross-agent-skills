#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
临时脚本管家 —— 跨 Agent / 跨 Harness 临时脚本治理主工具（跨平台，Python 3.8+）

命令：
  配置 [--path <目录>] [--name <署名>]      查看/设置本机临时脚本根目录/默认署名并初始化结构
  查 <关键词> [--lang py] [--project X]    检索索引找可复用脚本
  登记 <文件> --purpose P [--reuse one-off|reusable] [--project X]
                                           把脚本收编入库（复制或移动）并登记元数据
  审计 <工作区>                            启发式扫描疑似临时脚本，输出候选清单+报告
  迁移 <文件> --to reusable|sessions|quarantine [--project X]
                                           移动脚本入库并更新索引（quarantine 记录原路径可回迁）
  使用 <文件或id> [--note N]               标记某脚本被复用过（use_count+1，更新 last_used）
  回迁 <文件或id>                          把 quarantine 中的脚本移回工作区原路径
  清理 [--project X] [--before YYYY-MM-DD] [--quarantined] [--yes]
                                           处置 one-off / 过期 / 已确认的 quarantine 脚本
  报告                                     库内现状摘要

没有 Python 时，Agent 可按 SKILL.md 协议手工读写目录和 manifests/index.json。
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".agent-tsg", "config.json")
INDEX_REL = os.path.join("manifests", "index.json")
DIRS = ["reusable", "sessions", "quarantine", "manifests", "reports"]
SCRIPT_EXTS = {".py", ".ps1", ".sh", ".js", ".mjs", ".cjs", ".ts", ".bat", ".cmd", ".rb", ".pl"}
# 名称启发式：疑似临时脚本
TEMP_NAME_PAT = re.compile(
    r"(tmp|temp|test_|test-|demo|scratch|debug|draft|尝试|临时|测试|新建|副本|_old|bak|copy|untitled|fix-?try)",
    re.IGNORECASE,
)
# 疑似正式文件（降低误报，仅作初筛提示，最终由 Agent 深度判断）
FORMAL_NAME_PAT = re.compile(
    r"(setup|install|build|deploy|migrate|main|app|server|client|manage|__init__|conftest|run)",
    re.IGNORECASE,
)
# 记忆层文件夹名：跨 Agent 的就地记忆（层数 1~99 不限），审计一律跳过
MEM_LAYER_PAT = re.compile(r"^记忆第[一二三四五六七八九十]{1,3}层$")
AUDIT_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}


def now_iso():
    return dt.datetime.now().isoformat(timespec="seconds")


def today():
    return dt.date.today().isoformat()


def load_json(path):
    """utf-8-sig 兼容 PowerShell 5 写出的 BOM 文件；损坏时报错而非裸 traceback。"""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        sys.exit(f"[错误] {path} 无法解析（{e}）。\n"
                 f"       文件可能被并发写坏或手工改错：请先备份，与相关 Agent 核对后再手工修复。")


def load_config():
    return load_json(CONFIG_PATH) or {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    _atomic_write_json(CONFIG_PATH, cfg)
    print(f"[配置] 已写入 {CONFIG_PATH}")


def _atomic_write_json(path, data):
    """原子写入：先写临时文件再 os.replace，避免并发写把 JSON 截断成半截
    （借鉴 cross-agent-memory 的指纹并发保护思想）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def root_of(cfg):
    root = cfg.get("temp_script_root")
    if not root:
        sys.exit("[错误] 本机尚未配置临时脚本根目录。请运行：临时脚本管家.py 配置 --path <目录>\n"
                 "       按协议必须先询问用户，不得擅自选路径。")
    if not os.path.isdir(root):
        sys.exit(f"[错误] 已配置的根目录不可达：{root}\n"
                 f"       按协议不得静默回退到工作区，请向用户确认后重新指定。")
    return root


def index_path(root):
    return os.path.join(root, INDEX_REL)


def load_index(root):
    """加载索引，并快照当前内容的 sha256，供保存前做并发改动检测。"""
    data = load_json(index_path(root)) or {"scripts": []}
    try:
        with open(index_path(root), "rb") as f:
            data["_disk_snapshot"] = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        data["_disk_snapshot"] = None
    return data


def save_index(root, idx):
    # 并发检测（借鉴 cross-agent-memory 指纹校验）：保存前重读磁盘，
    # 若索引已被其他 Agent 改过而本次载入的是旧副本 → 拒写，让 Agent 重读合并。
    snap = idx.pop("_disk_snapshot", None)
    p = index_path(root)
    if snap is not None and os.path.isfile(p):
        try:
            with open(p, "rb") as f:
                cur = hashlib.sha256(f.read()).hexdigest()
            if cur != snap:
                sys.exit("[并发警告] manifests/index.json 在本次载入后已被其他 Agent/Harness 修改！\n"
                         "       按协议不得覆盖：请重新读取索引、合并你的条目后再保存。")
        except OSError:
            pass
    idx["_updated_at"] = now_iso()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    _atomic_write_json(p, idx)


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def new_id():
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + format(random.getrandbits(12), "03x")


def ensure_tree(root):
    for d in DIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)


def unique_dest(dest):
    """目标路径已存在时追加序号，绝不静默覆盖库内已有脚本。"""
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    n = 2
    while os.path.exists(f"{base}__{n}{ext}"):
        n += 1
    return f"{base}__{n}{ext}"


def project_dir(root, zone, project):
    base = os.path.join(root, zone)
    if zone == "sessions" and project:
        base = os.path.join(base, project)
    os.makedirs(base, exist_ok=True)
    return base


def find_entry(idx, ref, root=None):
    """按 id、库内相对路径或文件名匹配条目。"""
    ref_norm = ref.replace("\\", "/").lower()
    base = os.path.basename(ref_norm)
    for s in idx["scripts"]:
        f = s.get("file", "").lower()
        if s.get("id") == ref or f == ref_norm or os.path.basename(f) == base:
            return s
    if root and os.path.isfile(ref):
        for s in idx["scripts"]:
            if os.path.abspath(os.path.join(root, s["file"])) == os.path.abspath(ref):
                return s
    return None


# ---------------- 命令实现 ----------------

def agent_name(explicit=None):
    """署名：显式 --by 优先，否则取本机配置的 agent_name（两技能共享），再否则 agent。"""
    if explicit:
        return explicit
    return load_config().get("agent_name") or "agent"


def cmd_config(args):
    cfg = load_config()
    if args.name:
        cfg["agent_name"] = args.name
        save_config(cfg)
        print(f"[配置] 默认署名（agent_name）：{args.name}（记忆管家/临时脚本管家共用）")
        if not args.path:
            return
    if args.path:
        root = os.path.abspath(args.path)
        os.makedirs(root, exist_ok=True)
        cfg["temp_script_root"] = root
        cfg["configured_at"] = now_iso()
        save_config(cfg)
        ensure_tree(root)
        print(f"[配置] 临时脚本根目录：{root}，目录结构已初始化：{', '.join(DIRS)}")
    elif cfg.get("temp_script_root"):
        root = cfg["temp_script_root"]
        print(f"当前根目录：{root}（配置于 {cfg.get('configured_at', '?')}）")
        print(f"可达：{os.path.isdir(root)}")
    else:
        print("未配置。请询问用户后运行：临时脚本管家.py 配置 --path <用户指定的目录>")


def cmd_find(args):
    root = root_of(load_config())
    idx = load_index(root)
    kw = args.keywords.lower()
    hits = []
    for s in idx["scripts"]:
        if s.get("status") == "deleted":
            continue
        blob = " ".join([s.get("file", ""), s.get("purpose", ""), s.get("language", ""),
                         s.get("project", "")]).lower()
        if kw and kw not in blob:
            continue
        if args.lang and s.get("language") != args.lang:
            continue
        if args.project and s.get("project") not in (args.project, "global"):
            continue
        hits.append(s)
    if not hits:
        print("[查] 库中没有匹配脚本，可新建（记得建在库内并登记）。")
        return
    print(f"[查] 命中 {len(hits)} 个：")
    for s in hits:
        print(f"  - {s['file']}  (id={s['id']})\n"
              f"      用途: {s.get('purpose', '')} | 复用性: {s.get('reusability')}"
              f" | 使用: {s.get('use_count', 0)}次/最后{s.get('last_used') or '?'}"
              f" | 来源: {s.get('created_by', '')}")


def _register(root, src, zone, purpose, reuse, project, created_by, move=False, origin_path=None):
    """收编一个脚本入库并登记。返回 entry。目标已有同路径条目时更新而非重复登记。"""
    if not os.path.isfile(src):
        sys.exit(f"[错误] 文件不存在：{src}")
    dest_dir = project_dir(root, zone, project)
    dest = os.path.join(dest_dir, os.path.basename(src))
    same_place = os.path.abspath(src) == os.path.abspath(dest)
    if not same_place:
        dest = unique_dest(dest)
    if move and not same_place:
        shutil.move(src, dest)
    elif not same_place:
        shutil.copy2(src, dest)

    idx = load_index(root)
    dest_rel = os.path.relpath(dest, root).replace("\\", "/")
    old = next((s for s in idx["scripts"] if s.get("file", "").lower() == dest_rel.lower()), None)
    if old and old.get("status") not in ("deleted", "moved"):
        changed = False
        if purpose and purpose != old.get("purpose"):
            old["purpose"] = purpose
            changed = True
        if reuse and reuse != old.get("reusability"):
            old["reusability"] = reuse
            changed = True
        old["content_hash"] = "sha256:" + file_hash(dest)
        save_index(root, idx)
        print(f"[登记] 已存在条目，已更新：{dest_rel}  (id={old['id']})")
        return old
    if old:
        idx["scripts"].remove(old)

    entry = {
        "id": new_id(),
        "file": dest_rel,
        "purpose": purpose or "",
        "language": os.path.splitext(src)[1].lstrip(".").lower() or "unknown",
        "reusability": reuse,
        "status": "quarantined" if zone == "quarantine" else "active",
        "project": project or "global",
        "created_by": created_by or "agent",
        "created_at": now_iso(),
        "source_workspace": project or "",
        "origin_path": origin_path or "",
        "use_count": 0,
        "last_used": "",
        "content_hash": "sha256:" + file_hash(dest),
    }
    idx["scripts"].append(entry)
    save_index(root, idx)
    print(f"[登记] {entry['file']}  (id={entry['id']}, reuse={reuse}, zone={zone})")
    return entry


def cmd_register(args):
    root = root_of(load_config())
    zone = "reusable" if args.reuse == "reusable" else "sessions"
    args.by = agent_name(args.by)
    _register(root, args.file, zone, args.purpose, args.reuse, args.project, args.by, move=args.move)


def cmd_move(args):
    """单次流程内完成：读索引 → 移动文件 → 更新/追加条目 → 写回。避免 stale 索引覆盖。"""
    root = root_of(load_config())
    if not os.path.isfile(args.file):
        sys.exit(f"[错误] 文件不存在：{args.file}")
    args.by = agent_name(args.by)
    src_abs = os.path.abspath(args.file)
    idx = load_index(root)
    old = next((s for s in idx["scripts"]
                if os.path.abspath(os.path.join(root, s["file"])) == src_abs), None)
    # 回迁依据是「迁移前文件的真实所在路径」；老条目缺 origin_path 时一律用当前实际路径
    origin = old.get("origin_path") if (old and old.get("origin_path")) else src_abs

    dest_dir = project_dir(root, args.to, args.project)
    dest = os.path.join(dest_dir, os.path.basename(args.file))
    if src_abs != os.path.abspath(dest):
        dest = unique_dest(dest)
        shutil.move(src_abs, dest)
    dest_rel = os.path.relpath(dest, root).replace("\\", "/")

    if old:
        old["file"] = dest_rel
        old["status"] = "quarantined" if args.to == "quarantine" else "active"
        if args.to == "quarantine" and not old.get("origin_path"):
            old["origin_path"] = origin
        if args.purpose:
            old["purpose"] = args.purpose
        old["content_hash"] = "sha256:" + file_hash(dest)
        entry = old
    else:
        entry = {
            "id": new_id(),
            "file": dest_rel,
            "purpose": args.purpose or "",
            "language": os.path.splitext(args.file)[1].lstrip(".").lower() or "unknown",
            "reusability": "reusable" if args.to == "reusable" else "unknown",
            "status": "quarantined" if args.to == "quarantine" else "active",
            "project": args.project or "global",
            "created_by": args.by or "agent",
            "created_at": now_iso(),
            "source_workspace": args.project or "",
            "origin_path": origin if args.to == "quarantine" else "",
            "use_count": 0,
            "last_used": "",
            "content_hash": "sha256:" + file_hash(dest),
        }
        idx["scripts"].append(entry)
    save_index(root, idx)
    print(f"[迁移] {entry['file']}  (id={entry['id']}, zone={args.to}, status={entry['status']})")
    if args.to == "quarantine":
        print(f"       原路径已记录：{origin}（可用 回迁 命令移回）")


def cmd_use(args):
    root = root_of(load_config())
    idx = load_index(root)
    entry = find_entry(idx, args.ref, root)
    if not entry:
        sys.exit(f"[错误] 索引中找不到：{args.ref}")
    entry["use_count"] = entry.get("use_count", 0) + 1
    entry["last_used"] = today()
    if args.note:
        entry["notes"] = entry.get("notes", []) + [f"{today()}: {args.note}"]
    save_index(root, idx)
    print(f"[使用] {entry['file']} 已标记复用（第 {entry['use_count']} 次）")


def cmd_restore(args):
    root = root_of(load_config())
    idx = load_index(root)
    entry = find_entry(idx, args.ref, root)
    if not entry:
        sys.exit(f"[错误] 索引中找不到：{args.ref}")
    if entry.get("status") != "quarantined":
        sys.exit(f"[错误] 该条目不在 quarantine 中：{entry['file']}（status={entry.get('status')}）")
    origin = entry.get("origin_path")
    if not origin or not os.path.isdir(os.path.dirname(origin)):
        sys.exit(f"[错误] 原路径不可用：{origin}。请手工指定恢复位置。")
    if os.path.exists(origin):
        sys.exit(f"[错误] 原路径已有同名文件（可能是用户后来新建/恢复的）：{origin}\n"
                 f"       绝不覆盖。请先让用户确认，再手工处理。")
    src = os.path.join(root, entry["file"])
    if not os.path.isfile(src):
        sys.exit(f"[错误] 库内文件不存在（可能已被清理或手工移动）：{src}")
    shutil.move(src, origin)
    entry["status"] = "active"
    # 库内目标存相对路径（清理等命令正常治理）；库外（如工作区）存绝对路径，清理守卫会跳过
    try:
        rel = os.path.relpath(origin, root).replace("\\", "/")
    except ValueError:
        rel = ".."
    entry["file"] = origin if rel.startswith("..") else rel
    save_index(root, idx)
    print(f"[回迁] 已移回 {origin}")


def git_untracked(ws, path):
    """返回是否未被跟踪。非 git 仓库时按未跟踪处理（仅作为候选提示，最终由 Agent 判断）。"""
    if not os.path.isdir(os.path.join(ws, ".git")):
        return True
    try:
        r = subprocess.run(["git", "-C", ws, "ls-files", "--", path],
                           capture_output=True, text=True, timeout=10)
        return r.returncode != 0 or not r.stdout.strip()
    except Exception:
        return True


def cmd_audit(args):
    ws = os.path.abspath(args.workspace)
    if not os.path.isdir(ws):
        sys.exit(f"[错误] 工作区不存在：{ws}")
    root = root_of(load_config())
    idx = load_index(root)
    known = {os.path.basename(s["file"]).lower() for s in idx["scripts"]}
    candidates = []
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [d for d in dirnames
                       if d not in AUDIT_SKIP_DIRS and not MEM_LAYER_PAT.match(d)]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in SCRIPT_EXTS or fn.lower() in known:
                continue
            is_temp = bool(TEMP_NAME_PAT.search(fn)) and not FORMAL_NAME_PAT.match(fn)
            path = os.path.join(dirpath, fn)
            untracked = git_untracked(ws, path)
            depth = len(os.path.relpath(path, ws).split(os.sep))
            score = (2 if is_temp else 0) + (2 if untracked else 0) + (1 if depth <= 2 else 0)
            if score >= 3:
                candidates.append((score, os.path.relpath(path, ws)))
    candidates.sort(reverse=True)
    lines = [f"# 遗留物审计报告 — {os.path.basename(ws)} — {today()}", "",
             f"- 扫描根：{ws}",
             f"- 候选数：{len(candidates)}", "",
             "> 启发式初筛结果。Agent 必须逐个深度判断后按 SKILL.md 分级处置：",
             "> B(有复用价值→迁移 reusable/)、C(一次性→清理，先记录)、D(来源不明→迁移 quarantine/ 等用户确认)。",
             "> 红线：git 已跟踪文件、源代码、构建/CI 配置、文档、数据、拿不准的文件——绝不自动删除。", "",
             "> 处置完成后按联动协议写入 cross-agent-memory（读后改不覆盖）：",
             "> 审计结论+日期→记忆 1_项目架构/5_代办；待用户拍板项→6_需要我配合；逐项决策→决策.md。", ""]
    for score, rel in candidates:
        lines.append(f"- [ ] (score={score}) {rel}")
    out = os.path.join(root, "reports", f"审计-{os.path.basename(ws)}-{today()}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[审计] 候选 {len(candidates)} 个，报告已写入：{out}")
    for score, rel in candidates[:30]:
        print(f"  (score={score}) {rel}")
    if len(candidates) > 30:
        print(f"  ... 其余 {len(candidates) - 30} 个见报告文件")


def cmd_clean(args):
    root = root_of(load_config())
    idx = load_index(root)
    before = dt.date.fromisoformat(args.before) if args.before else None
    targets = []
    for s in idx["scripts"]:
        if args.quarantined:
            if s.get("status") == "quarantined":
                targets.append(s)
            continue
        if s.get("status") != "active" or s.get("reusability") != "one-off":
            continue
        # 红线防护：回迁后的条目 file 可能是库外绝对路径，绝不允许清理命令删到库外文件
        f = s.get("file", "")
        abspath = os.path.abspath(os.path.join(root, f))
        if not abspath.startswith(os.path.abspath(root) + os.sep):
            continue
        if args.project and s.get("project") != args.project:
            continue
        if before:
            lu = (s.get("last_used") or s.get("created_at", ""))[:10]
            if not lu or dt.date.fromisoformat(lu) >= before:
                continue
        targets.append(s)
    if not targets:
        print("[清理] 没有符合条件的待清理脚本。")
        return
    label = "quarantine（用户已确认）" if args.quarantined else "one-off"
    print(f"[清理] 待清理清单（{label}）：")
    for s in targets:
        print(f"  - {s['file']}  用途: {s.get('purpose', '')}  原路径: {s.get('origin_path', '')}")
    if not args.yes:
        print("确认无误后加 --yes 重新执行；不确定的条目请保留并列入记忆 6_需要我配合.txt。")
        return
    for s in targets:
        p = os.path.join(root, s["file"])
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError as e:
                print(f"  [失败] {p}: {e}")
                continue
        s["status"] = "deleted"
        print(f"  [已删] {s['file']}")
    save_index(root, idx)


def cmd_report(args):
    root = root_of(load_config())
    idx = load_index(root)
    zones = {"reusable": 0, "sessions": 0, "quarantine": 0}
    for s in idx["scripts"]:
        st = s.get("status")
        if st == "quarantined":
            zones["quarantine"] += 1
        elif s.get("reusability") == "reusable" and st == "active":
            zones["reusable"] += 1
        elif st == "active":
            zones["sessions"] += 1
    print(f"[报告] 根目录：{root}")
    print(f"  reusable: {zones['reusable']}  sessions(active): {zones['sessions']}  quarantine: {zones['quarantine']}")
    top = sorted([s for s in idx["scripts"] if s.get("use_count")], key=lambda s: -s["use_count"])[:5]
    if top:
        print("  最常复用：")
        for s in top:
            print(f"    - {s['file']} ({s['use_count']}次)")
    quar = [s for s in idx["scripts"] if s.get("status") == "quarantined"]
    if quar:
        print("  待用户确认（quarantine）：")
        for s in quar:
            print(f"    - {s['file']}  原路径: {s.get('origin_path', '?')}")


def main():
    ap = argparse.ArgumentParser(description="临时脚本管家")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("配置"); p.add_argument("--path"); p.add_argument("--name",
        help="默认署名 agent_name（记忆管家/临时脚本管家共用）"); p.set_defaults(fn=cmd_config)
    p = sub.add_parser("查"); p.add_argument("keywords"); p.add_argument("--lang"); p.add_argument("--project"); p.set_defaults(fn=cmd_find)
    p = sub.add_parser("登记"); p.add_argument("file"); p.add_argument("--purpose", required=True)
    p.add_argument("--reuse", choices=["one-off", "reusable"], default="one-off")
    p.add_argument("--project"); p.add_argument("--by"); p.add_argument("--move", action="store_true"); p.set_defaults(fn=cmd_register)
    p = sub.add_parser("迁移"); p.add_argument("file"); p.add_argument("--to", required=True,
        choices=["reusable", "sessions", "quarantine"]); p.add_argument("--purpose"); p.add_argument("--project"); p.add_argument("--by"); p.set_defaults(fn=cmd_move)
    p = sub.add_parser("使用"); p.add_argument("ref"); p.add_argument("--note"); p.set_defaults(fn=cmd_use)
    p = sub.add_parser("回迁"); p.add_argument("ref"); p.set_defaults(fn=cmd_restore)
    p = sub.add_parser("审计"); p.add_argument("workspace"); p.set_defaults(fn=cmd_audit)
    p = sub.add_parser("清理"); p.add_argument("--project"); p.add_argument("--before")
    p.add_argument("--quarantined", action="store_true"); p.add_argument("--yes", action="store_true"); p.set_defaults(fn=cmd_clean)
    p = sub.add_parser("报告"); p.set_defaults(fn=cmd_report)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
