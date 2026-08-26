"""
Course Renamer - renames OPCD/GSPro course files to match the course's
.gspcrse file after Arborist/Greenkeeper have already generated them under
a different (placeholder) name.

Usage: run this file with Python (double-click, or `python course_renamer.py`).
No third-party dependencies - uses only the standard library (tkinter).
"""

import re
import shutil
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

SUFFIX_PATTERNS = [
    ".gspcrse.csv",
    "_benchmark.jpg",
    "_scorecard_imperial.jpg",
    "_scorecard_metric.jpg",
]

SCENE_FOLDER_NAME_RE = re.compile(r'"SceneFolderName"\s*:\s*"([^"]*)"')


@dataclass
class RenamePlan:
    folder: Path = None
    old_name: str = None
    new_name: str = None
    file_renames: list = field(default_factory=list)  # list of (Path old, Path new)
    folder_rename: tuple = None  # (Path old, Path new) or None
    scene_folder_name_update: tuple = None  # (old_value, new_value) or None
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    needs_selection: bool = False
    gspcrse_candidates: list = field(default_factory=list)  # list of Path, when ambiguous

    @property
    def is_valid(self):
        return not self.errors


def _find_by_suffix(folder: Path, suffix: str, exclude: set):
    """Case-insensitive search for files ending in `suffix`, skipping paths in `exclude`."""
    suffix_lower = suffix.lower()
    matches = []
    for p in folder.iterdir():
        if not p.is_file() or p in exclude:
            continue
        if p.name.lower().endswith(suffix_lower):
            matches.append(p)
    return matches


def scan_folder(folder: Path, chosen_gspcrse: Path = None) -> RenamePlan:
    plan = RenamePlan(folder=folder)

    if not folder.is_dir():
        plan.errors.append(f"Not a folder: {folder}")
        return plan

    # 1. Find the .gspcrse file - its name is the target course name.
    # There can legitimately be two (e.g. the original export plus a
    # renamed copy) - if so, the caller must tell us which one is correct.
    gspcrse_matches = [
        p for p in folder.iterdir()
        if p.is_file() and p.name.lower().endswith(".gspcrse")
    ]
    if not gspcrse_matches:
        plan.errors.append("No .gspcrse file found in this folder.")
        return plan

    if len(gspcrse_matches) > 1:
        if chosen_gspcrse is None:
            plan.needs_selection = True
            plan.gspcrse_candidates = sorted(gspcrse_matches, key=lambda p: p.name.lower())
            return plan
        if chosen_gspcrse not in gspcrse_matches:
            plan.errors.append(f"Selected file is no longer in the folder: {chosen_gspcrse.name}")
            return plan
        gspcrse_path = chosen_gspcrse
    else:
        gspcrse_path = gspcrse_matches[0]

    new_name = gspcrse_path.stem  # strips ".gspcrse"
    plan.new_name = new_name

    other_gspcrse = [p for p in gspcrse_matches if p != gspcrse_path]
    if other_gspcrse:
        names = ", ".join(p.name for p in other_gspcrse)
        plan.warnings.append(f"Other .gspcrse file(s) present and left untouched: {names}")

    # 2. Find the single .GKD file - its name is the current (old) course name.
    gkd_matches = [
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() == ".gkd"
    ]
    if not gkd_matches:
        plan.errors.append("No .GKD file found in this folder.")
        return plan
    if len(gkd_matches) > 1:
        names = ", ".join(p.name for p in gkd_matches)
        plan.errors.append(f"Multiple .GKD files found (expected exactly one): {names}")
        return plan

    gkd_path = gkd_matches[0]
    old_name = gkd_path.stem
    plan.old_name = old_name

    accounted_for = {gspcrse_path, gkd_path}

    # 3. Plan the .GKD rename (skip if already correctly named).
    if gkd_path.name != f"{new_name}{gkd_path.suffix}":
        target = folder / f"{new_name}{gkd_path.suffix}"
        plan.file_renames.append((gkd_path, target))
    else:
        plan.warnings.append(".GKD file is already named correctly - no change needed.")

    # 4. Plan renames for the suffix-based files.
    for suffix in SUFFIX_PATTERNS:
        matches = _find_by_suffix(folder, suffix, accounted_for)
        if not matches:
            plan.warnings.append(f"No file matching *{suffix} found - skipped.")
            continue
        if len(matches) > 1:
            names = ", ".join(p.name for p in matches)
            plan.warnings.append(
                f"Multiple files matching *{suffix} found - skipped, rename manually: {names}"
            )
            continue

        src = matches[0]
        accounted_for.add(src)
        matched_tail = src.name[-len(suffix):]  # preserve on-disk case of the suffix
        target = folder / f"{new_name}{matched_tail}"
        if src.name == target.name:
            plan.warnings.append(f"{src.name} is already named correctly - no change needed.")
        else:
            plan.file_renames.append((src, target))

    # 5. Check for collisions among planned targets and with existing files.
    planned_targets = {t for _, t in plan.file_renames}
    if len(planned_targets) != len(plan.file_renames):
        plan.errors.append("Internal conflict: two planned renames would produce the same filename.")

    for src, target in plan.file_renames:
        if target.exists() and target not in {s for s, _ in plan.file_renames}:
            plan.errors.append(
                f"Target file already exists and would be overwritten: {target.name}"
            )

    # 6. Plan the folder rename.
    if folder.name != new_name:
        new_folder = folder.parent / new_name
        if new_folder.exists():
            plan.errors.append(f"A folder named '{new_name}' already exists next to this one.")
        else:
            plan.folder_rename = (folder, new_folder)
    else:
        plan.warnings.append("Folder is already named correctly - no change needed.")

    # 7. Plan the SceneFolderName update inside the (post-rename) .GKD file.
    try:
        gkd_text = gkd_path.read_text(encoding="utf-8")
    except OSError as exc:
        plan.errors.append(f"Could not read {gkd_path.name}: {exc}")
        return plan

    m = SCENE_FOLDER_NAME_RE.search(gkd_text)
    if m is None:
        plan.warnings.append('"SceneFolderName" field not found in .GKD file - nothing to update.')
    else:
        current_value = m.group(1)
        if current_value != new_name:
            plan.scene_folder_name_update = (current_value, new_name)
        else:
            plan.warnings.append('"SceneFolderName" already matches the new name.')

    return plan


def backup_folder(folder: Path, base_name: str, log) -> Path:
    """Zips the whole course folder into a sibling archive before any
    renaming happens, so the operation can be undone by hand if needed."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_stem = folder.parent / f"{base_name}_backup_{timestamp}"
    log(f"Backing up {folder.name} ...")
    archive_path = Path(shutil.make_archive(str(backup_stem), "zip", root_dir=str(folder.parent), base_dir=folder.name))
    log(f"Backup saved: {archive_path}")
    return archive_path


def execute_plan(plan: RenamePlan, log) -> bool:
    """Executes a validated RenamePlan. Returns True on full success."""
    if not plan.is_valid:
        log("Refusing to execute: plan has errors.")
        return False

    gkd_final_path = None

    try:
        # File renames first (folder path is still the original one here).
        for src, target in plan.file_renames:
            shutil.move(str(src), str(target))
            log(f"Renamed: {src.name}  ->  {target.name}")
            if src.suffix.lower() == ".gkd":
                gkd_final_path = target

        # Patch SceneFolderName inside the .GKD file, addressed at its
        # (possibly just-renamed) current path, before the folder itself moves.
        if plan.scene_folder_name_update:
            old_value, new_value = plan.scene_folder_name_update
            gkd_path = gkd_final_path or (plan.folder / f"{plan.old_name}.GKD")
            text = gkd_path.read_text(encoding="utf-8")
            patched = text.replace(f'"SceneFolderName":"{old_value}"', f'"SceneFolderName":"{new_value}"')
            if patched == text:
                # Field may have different spacing; fall back to regex substitution once.
                patched = SCENE_FOLDER_NAME_RE.sub(f'"SceneFolderName":"{new_value}"', text, count=1)
            gkd_path.write_text(patched, encoding="utf-8")
            log(f'Updated "SceneFolderName": "{old_value}" -> "{new_value}"')

        # Folder rename last.
        if plan.folder_rename:
            src, target = plan.folder_rename
            shutil.move(str(src), str(target))
            log(f"Renamed folder: {src.name}  ->  {target.name}")

        log("Done.")
        return True
    except OSError as exc:
        log(f"ERROR during rename: {exc}")
        return False


class GspcrseChoiceDialog(tk.Toplevel):
    """Modal dialog letting the user pick which .gspcrse file is correct
    when more than one is present (e.g. the original export plus a
    renamed copy)."""

    def __init__(self, parent, candidates: list):
        super().__init__(parent)
        self.title("Select the correct course file")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.candidates = candidates
        self.result: Path = None

        ttk.Label(
            self,
            text="Multiple .gspcrse files were found. Select the one with\n"
                 "the correct course name - it will be used as the target\n"
                 "name for all the other files.",
            justify="left",
        ).pack(padx=12, pady=(12, 8), anchor="w")

        self.listbox = tk.Listbox(self, width=70, height=min(8, len(candidates)), exportselection=False)
        for p in candidates:
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            self.listbox.insert("end", f"{p.name}    (modified: {mtime})")
        self.listbox.selection_set(0)
        self.listbox.pack(padx=12, pady=(0, 8), fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", lambda e: self._on_ok())

        buttons = ttk.Frame(self)
        buttons.pack(padx=12, pady=(0, 12), fill="x")
        ttk.Button(buttons, text="Cancel", command=self._on_cancel).pack(side="right")
        ttk.Button(buttons, text="OK", command=self._on_ok).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Return>", lambda e: self._on_ok())

        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        self.geometry(f"+{parent_x + 40}+{parent_y + 40}")

    def _on_ok(self):
        selection = self.listbox.curselection()
        if selection:
            self.result = self.candidates[selection[0]]
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Course Renamer")
        self.geometry("720x560")
        self.minsize(600, 480)

        self.folder_var = tk.StringVar()
        self.plan: RenamePlan | None = None

        self._build_widgets()

    def _build_widgets(self):
        pad = {"padx": 8, "pady": 6}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="Course folder:").pack(side="left")
        entry = ttk.Entry(top, textvariable=self.folder_var)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        ttk.Button(top, text="Browse...", command=self.on_browse).pack(side="left")

        actions = ttk.Frame(self)
        actions.pack(fill="x", **pad)
        ttk.Button(actions, text="Scan", command=self.on_scan).pack(side="left")
        self.rename_button = ttk.Button(actions, text="Rename", command=self.on_rename, state="disabled")
        self.rename_button.pack(side="left", padx=(8, 0))

        ttk.Label(self, text="Plan / log:").pack(anchor="w", padx=8)
        self.log_text = tk.Text(self, wrap="word", height=24)
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log_text.configure(state="disabled")

    def log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.configure(state="disabled")
        self.log_text.see("end")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def on_browse(self):
        chosen = filedialog.askdirectory(title="Select the course folder")
        if chosen:
            self.folder_var.set(chosen)

    def on_scan(self):
        self.clear_log()
        self.rename_button.configure(state="disabled")
        self.plan = None

        folder_str = self.folder_var.get().strip()
        if not folder_str:
            self.log("Pick a folder first.")
            return

        folder = Path(folder_str)
        plan = scan_folder(folder)

        if plan.needs_selection:
            dialog = GspcrseChoiceDialog(self, plan.gspcrse_candidates)
            self.wait_window(dialog)
            if dialog.result is None:
                self.log("Cancelled - no course file selected.")
                return
            plan = scan_folder(folder, chosen_gspcrse=dialog.result)

        self.plan = plan

        self.log(f"Folder: {folder}")
        self.log(f"Detected current name (.GKD):  {plan.old_name}")
        self.log(f"Target name (.gspcrse):        {plan.new_name}")
        self.log("")

        if plan.file_renames:
            self.log("Files to rename:")
            for src, target in plan.file_renames:
                self.log(f"  {src.name}  ->  {target.name}")
        else:
            self.log("No files need renaming.")

        if plan.folder_rename:
            src, target = plan.folder_rename
            self.log(f"\nFolder to rename:\n  {src.name}  ->  {target.name}")

        if plan.scene_folder_name_update:
            old_value, new_value = plan.scene_folder_name_update
            self.log(f'\n.GKD "SceneFolderName" will be updated:\n  "{old_value}"  ->  "{new_value}"')

        if plan.warnings:
            self.log("\nWarnings (not blocking):")
            for w in plan.warnings:
                self.log(f"  - {w}")

        if plan.errors:
            self.log("\nErrors (must fix before renaming):")
            for e in plan.errors:
                self.log(f"  - {e}")

        if plan.is_valid and (plan.file_renames or plan.folder_rename or plan.scene_folder_name_update):
            self.rename_button.configure(state="normal")
        elif plan.is_valid:
            self.log("\nNothing to do - everything is already named correctly.")

    def on_rename(self):
        if self.plan is None or not self.plan.is_valid:
            return

        summary_lines = [f"{s.name} -> {t.name}" for s, t in self.plan.file_renames]
        if self.plan.folder_rename:
            s, t = self.plan.folder_rename
            summary_lines.append(f"[folder] {s.name} -> {t.name}")
        if self.plan.scene_folder_name_update:
            summary_lines.append("Update SceneFolderName inside .GKD")
        summary = "\n".join(summary_lines) if summary_lines else "(nothing to change)"

        if not messagebox.askyesno("Confirm rename", f"Apply these changes?\n\n{summary}"):
            return

        self.rename_button.configure(state="disabled")

        self.log("\n--- Backing up folder ---")
        try:
            backup_path = backup_folder(self.plan.folder, self.plan.old_name, self.log)
        except OSError as exc:
            self.log(f"ERROR creating backup: {exc}")
            messagebox.showerror(
                "Course Renamer",
                f"Could not create a backup - aborting without making any changes.\n\n{exc}",
            )
            self.plan = None
            return

        self.log("\n--- Applying changes ---")
        success = execute_plan(self.plan, self.log)

        if success:
            messagebox.showinfo("Course Renamer", "Rename complete.")
            if messagebox.askyesno(
                "Delete backup?",
                f"Rename succeeded. Delete the backup now?\n\n{backup_path}",
            ):
                try:
                    backup_path.unlink()
                    self.log(f"Deleted backup: {backup_path}")
                except OSError as exc:
                    self.log(f"Could not delete backup: {exc}")
            else:
                self.log(f"Backup kept at: {backup_path}")
        else:
            messagebox.showerror(
                "Course Renamer",
                f"Something went wrong - see the log for details.\n\n"
                f"Your original files are backed up at:\n{backup_path}",
            )
        self.plan = None


if __name__ == "__main__":
    App().mainloop()
