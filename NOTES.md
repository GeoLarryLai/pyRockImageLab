# webapp branch progress notes (local only)
- Stage 1: processing.py split into GUI-free building blocks + replay functions; common/ui.py (matplotlib pop-ups) removed; old code staged at /workspace/prl_oldcodes (NOT in repo). Equivalence: 8/8 outputs + _picks.json byte-identical vs 2016e8c (baseline via /workspace/baseline.py).
- Stage 2: webapp (pyrockimagelab/webapp: routes.py, shell/ from pyPetrograph, static/ index+app.js+viewer.js+app.css). Start screen with 2 tools. tests/test_webapp.py 6 pass. Screenshots via /workspace/shots.py (server: python -m pyrockimagelab.webapp /workspace/demo --port 8777). App outputs byte-identical to baseline 8/8.

## Stage 3 — notebooks, README, docs, sizes
- Notebooks: ExampleCore drops QuadPicker/INTERACTIVE, keeps replay + figures, adds an app-launch cell; core_photo_processing rewritten (no `%matplotlib qt`, no pickers): config → app launch (+ optional prefill of photo groups) → process_lr_segments → process_hr_segments. Both run headless via nbclient (17.6 s, 21.7 s).
- README.md / README-pypi.md: v0.1.0, plain-language "The app" section with 4 screenshots in figures/app_*.png; Qt/PyQt5/gui/QuadPicker text removed. CITATION.cff version 0.1.0.
- FUNCTION_DOCUMENTATION.md regenerated from docstrings.
- Screenshots retaken after fit fix (0.92); no JS errors.
- Clean venv (py3.13) wheel install: 385 MB (old: 368 MB base, 569 MB with PyQt5 extra).
- Tests 6/6 pass. README_review.pdf (8 pages) is git-ignored.
