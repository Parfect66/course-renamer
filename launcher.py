"""
Course Renamer Launcher - checks github.com/Parfect66/course-renamer for the
latest release, downloads CourseRenamer.exe if a newer version isn't already
sitting next to this launcher, then runs it.

Requires the `customtkinter` package: pip install customtkinter
"""

import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# Same customtkinter Windows dark-titlebar bug as course_renamer.py - see
# that file's comment for details.
ctk.CTk._deactivate_windows_window_header_manipulation = True

REPO = "Parfect66/course-renamer"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "CourseRenamer.exe"
USER_AGENT = "CourseRenamerLauncher"
REQUEST_TIMEOUT = 15


def app_dir() -> Path:
    """The folder this launcher itself lives in - works both as a frozen exe and as a script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def local_version_path() -> Path:
    return app_dir() / "version.txt"


def local_exe_path() -> Path:
    return app_dir() / ASSET_NAME


def read_local_version() -> str:
    p = local_version_path()
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def fetch_latest_release() -> dict:
    req = urllib.request.Request(
        API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_asset_url(release: dict) -> str:
    for asset in release.get("assets", []):
        if asset.get("name") == ASSET_NAME:
            return asset["browser_download_url"]
    raise RuntimeError(f"No {ASSET_NAME} asset found on the latest release.")


def download_to(url: str, dest: Path, progress_cb=None) -> None:
    """Downloads to a temp file first, then atomically replaces `dest` -
    an interrupted download never leaves a corrupt exe in place."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".download")
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT * 4) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total:
                    progress_cb(downloaded / total)
    tmp.replace(dest)


class LauncherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Course Renamer Launcher")
        self.geometry("420x180")
        self.resizable(False, False)

        ctk.CTkLabel(
            self, text="Course Renamer", font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(26, 6))
        self.status_label = ctk.CTkLabel(self, text="Checking for updates...", font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=(0, 14))
        self.progress = ctk.CTkProgressBar(self, width=340)
        self.progress.set(0)
        self.progress.pack(pady=(0, 16))

        self.after(200, self._start_check)

    def _set_status(self, text: str):
        self.after(0, lambda: self.status_label.configure(text=text))

    def _set_progress(self, fraction: float):
        self.after(0, lambda: self.progress.set(fraction))

    def _start_check(self):
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            self._set_status("Checking for updates...")
            release = fetch_latest_release()
            latest_version = release.get("tag_name", "")
            local_version = read_local_version()
            needs_download = (latest_version != local_version) or not local_exe_path().exists()

            if needs_download:
                self._set_status(f"Downloading {latest_version}...")
                url = find_asset_url(release)
                download_to(url, local_exe_path(), self._set_progress)
                local_version_path().write_text(latest_version, encoding="utf-8")
                self._set_status("Update installed.")
            else:
                self._set_status("Already up to date.")
                self._set_progress(1)

        except (urllib.error.URLError, OSError, RuntimeError, TimeoutError) as exc:
            if local_exe_path().exists():
                self._set_status("Offline - launching the installed version...")
            else:
                self._set_status(f"Update check failed: {exc}")
                self.after(3000, self.destroy)
                return

        self.after(400, self._launch)

    def _launch(self):
        exe = local_exe_path()
        if not exe.exists():
            self.status_label.configure(text="No installed version found and the update failed.")
            self.after(3000, self.destroy)
            return
        subprocess.Popen([str(exe)], cwd=str(app_dir()))
        self.destroy()


if __name__ == "__main__":
    LauncherApp().mainloop()
