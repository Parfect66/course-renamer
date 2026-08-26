# Course Renamer

A small desktop tool for renaming OPCD/GSPro course files after Arborist and
Greenkeeper have already generated them under a placeholder name.

## The problem

After running Arborist and Greenkeeper in Unity, a course folder ends up with
several files whose names are tied to whatever course name was set at the
time (e.g. `setbergsvollur_gsp`). If you then rename the course (by renaming
its `.gspcrse` file, or editing it in another tool), the folder name, `.GKD`
file, and a handful of other files are left out of sync and have to be
renamed by hand.

## What it does

Point the app at a course folder. It:

1. Finds the single `.gspcrse` file in the folder - its filename (without
   the extension) is treated as the correct/target course name.
2. Finds the single `.GKD` file - its filename is treated as the current
   (old) name.
3. Renames the `.GKD` file to the target name.
4. Renames these files (if present) to start with the target name, keeping
   their original suffix:
   - `*.gspcrse.csv`
   - `*_benchmark.jpg`
   - `*_scorecard_imperial.jpg`
   - `*_scorecard_metric.jpg`
5. Updates the `"SceneFolderName"` field inside the `.GKD` file to match the
   new name, so it stays internally consistent.
6. Renames the course folder itself to the target name.

It always shows a preview of exactly what it's about to do (via **Scan**)
before you confirm with **Rename**. Nothing is changed until you click
**Rename**.

Files that don't carry the course name in their filename - `arboristdata.dat`,
`arboristspawnpositions.json`, `arboristversion.dat`,
`arborist_postprocess.dat`, `coursedetails.txt`, and any `.GKD_BAK` /
`.GKDalt` backups - are left untouched.

## Usage

**As an app (recommended):** build a standalone `CourseRenamer.exe` that
needs no Python install to run:

```
python -m pip install pyinstaller
python -m PyInstaller --onefile --windowed --name "CourseRenamer" course_renamer.py
```

The `.exe` is written to `dist\CourseRenamer.exe`. Double-click it, or make
a shortcut to it (e.g. on the Desktop) - no console window, just the GUI.

**As a script:** requires only Python 3 (standard library, no extra
packages):

```
python course_renamer.py
```

Either way:

1. Click **Browse...** and select the course folder.
2. Click **Scan** to see the planned renames.
3. Review the log. If everything looks right, click **Rename** and confirm.

If the folder doesn't have exactly one `.gspcrse` file or exactly one `.GKD`
file, scanning will report an error and the **Rename** button stays
disabled - fix the ambiguity by hand first.
