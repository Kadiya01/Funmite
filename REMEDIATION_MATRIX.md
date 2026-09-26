# Funmite POS — Finding-to-Change Matrix

Maintained across the remediation phases. Each row proves a finding was addressed by a change and a test.

| Finding | Phase | Files changed | Test proving fix | Status |
| ------- | ----- | ------------- | ---------------- | ------ |
| #1 Reproducibility (no declared deps) | 1 | `pyproject.toml`, `requirements.txt`, `requirements-build.txt` | Fresh-venv `pip install -e .[dev]` + full suite in that venv (collected/passed/skipped recorded below) | **Done** (Phase 1 gate green) |
| #2 Migration safety (005 table rebuild) | 3 | `app/data/migrations/runner.py`, `app/data/migrations/versions/005_...py`, `app/data/db.py`, `tests/test_migration_safety.py` | new migration-safety tests (4), `test_migrations` (8), full suite (842/8) | **Done** (Phase 3 gate green) |
| #3 SQLite durability (no WAL) | 2 | `app/data/db.py`, `app/sync/cloud_db.py` | `test_schema/test_migrations/test_constraints/test_repositories` (35), `test_sync_integration` (21), full suite (838/8), WAL artifact probe | **Done** (Phase 2 gate green) |
| #4 CLI (`python -m app.data.db` no-op) | 4 | `app/data/db.py`, `tests/test_cli_entry.py` | new CLI tests (4): no-op pointed at `python -m app.main`, `--help`, unknown→exit 2, headless `init` → DB at v5 | **Done** (Phase 4 gate green) |
| #5 Display math (float chart sums) | 4 | `app/ui/reports/reports_page.py`, `app/ui/reports/my_sales_page.py`, `tests/test_report_display_math.py` | new display-math tests (4): Decimal-exact daily aggregation, first-seen ordering, `0.1+0.2==0.3`, empty→0 | **Done** (Phase 4 gate green) |
| #6 Accessibility/UI contrast + focus | 5 | `app/ui/theme.py`, `app/main.py`, `tests/test_ui_accessibility.py` | new a11y tests (31): WCAG-AA normal-text contrast for 27 palette pairs, focus-ring 3:1 on card/bg, focus selectors present, no suppressed focus outlines | **Done** (Phase 5 gate green) |
| #7 Backup hygiene (same-disk backup) | 6 | `app/ui/settings/settings_page.py`, `docs/DEPLOYMENT_GUIDE.md`, `DEPLOYMENT_CHECKLIST.md`, `tests/test_ops_hygiene.py` | new ops tests: `_same_volume` helper (2) + Settings backup-location hint branches | **Done** (Phase 6 gate green) |
| #8 Documentation/ops drift | 6 | `docs/DEPLOYMENT_GUIDE.md`, `DEPLOYMENT_CHECKLIST.md`, `PROJECT_STATUS.md`, `app/ui/expenses/expense_form.py`, `tests/test_ops_hygiene.py` | new ops tests (5): stale-count absence, matrix pointer, backup guidance, unused import removed | **Done** (Phase 6 gate green) |

## Gate record (Phase 7 — final regression, all findings)

- Final acceptance gate per plan: full suite run in the project `.venv`, `QT_QPA_PLATFORM=offscreen`, `-o addopts=` (no overrides, no deselection).
- Result: **888 passed, 8 skipped, 15 warnings in 343.07s — 0 failures, 0 errors.** Collected = 896. Skipped = 8 (env-gated by design: `test_shop_two_pc_workflow`, `test_cloud_postgres`, `test_hosted_gate` demand a PostgreSQL server that is not provisioned in the dev environment).
- Count lineage: 838 (P1) → 838 (P2) → 842 (P3) → 850 (P4) → 881 (P5) → 888 (P6) → **888 (P7)**; new tests were only ever *added*, never changed or removed.
- Full diff inspected (`git status --short`: 15 modified + 7 untracked = 22 entries): every file maps to a remediation finding from this matrix and the phased gates above; no unrelated changes present. LoC summary: 305 insertions, 39 deletions across 15 tracked files.
- Known immutable fact: `Reporting report · 657 passing tests` and CHANGELOG/phase-report figures describe their respective historical eras and are intentionally left untouched.
- Outstanding post-remediation items are operational, not code: delete `data/funmite.db.bak-pre005` once the app is verified (WAL backup is redundant), point `FUNMITE_BACKUP_DIR` at an external/network drive on deployment, copy `dist\FunmitePOS` to the shop/second PC, and rebuild the EXE only on request.

## Gate record (Phase 6)

- Backup-location guidance (#7): `settings_page` gained a `backup_location_label` under the backup list — shows the active `backup_dir` and, when it resolves to the same volume as `data_dir`, warns to set `FUNMITE_BACKUP_DIR` to an external/network drive ("Same drive as your data…"); on a separate volume it confirms "Stored on a separate drive from the database." New `_same_volume` helper compares `Path(...).anchor` after `abspath` (drive letter or UNC share), OSError-safe. No code/architecture change — the external-destination path (`BackupService` + `FUNMITE_BACKUP_DIR`) already existed and is unchanged.
- Backup docs: `docs/DEPLOYMENT_GUIDE.md` Backup Location section now states that the built-in default is same-drive (single-failure risk) and recommends USB/network destinations; `DEPLOYMENT_CHECKLIST.md` gains a pre-deployment check to point `FUNMITE_BACKUP_DIR` at an external/network drive and points the regression verification at `REMEDIATION_MATRIX.md`.
- Doc/count drift (#8): stale hard-coded "838 tests passing" (deployment checklist) and "expect 657 passing tests" (PROJECT_STATUS validation step) replaced with a pointer to `REMEDIATION_MATRIX.md` (canonical per-phase totals). Historical phase reports/CHANGELOG entries left intact (they accurately describe their era). Removed the unused `format_money` import in `app/ui/expenses/expense_form.py`.
- New tests: `tests/test_ops_hygiene.py` (7) — `_same_volume` unit (C:/C: same, C:/D: different on NT), both hint branches via monkeypatched `_same_volume` (qtbot page build mirroring `test_settings_printer`), unused-import absence, checklist/status doc staleness + matrix pointer, deployment-guide backup guidance. **7 passed in 5.89s.**
- Relevant existing suites (settings/printer, expense form+service, backup service): **79 passed in 17.69s**.
- Diff inspected: `settings_page.py` diff is exactly the hint/helper/label additions (accidental mid-edit corruption of `_on_register_device` was repaired; its diff is empty → behavior unchanged).
- Full regression (`.venv`, offscreen): **888 passed, 8 skipped, 15 warnings in 230.02s** (baseline 881 + 7 new; no failures/errors). Warnings identical to prior phases.

## Gate record (Phase 5)

- Contrast remediation (WCAG 2.1 AA, normal text ≥ 4.5:1), token/component level, verified by computed ratios — NOT a blind re-theme:
  - `ACCENT` `#059669`(3.77:1 on white — failed) → `#047857` (5.49:1) — used by primary buttons (white text), selected tab text, POS cart/CONFIRM bars, exchange/inventory accent text. `SUCCESS` → same `#047857` (sync "Synced" on white 5.49; badge-active on `SUCCESS_LIGHT` 4.84).
  - `WARNING` `#F59E0B` (2.15:1 on white, 1.92 on `WARNING_LIGHT` — failed) → `#92400E` (7.09 on white, 6.33 on `WARNING_LIGHT`); fixes offline/POS badge + settings sync-status text.
  - `INFO` `#3B82F6` (3.68 white / 3.01 `INFO_LIGHT` — failed) → `#1D4ED8` (6.73 / 5.54); fixes badge-info + settings sync status.
  - `DESTRUCTIVE` `#DC2626` (4.85 white ok but 3.92 on `DESTRUCTIVE_LIGHT` — failed) → `#B91C1C` (6.51 white / 5.25 light); fixes all form error banners + badge-danger.
  - `badge-inactive` and unselected `QTabBar::tab` text `MUTED_FG` on `MUTED` (4.33 — failed) → `FG_SECONDARY` (9.4:1); ⚙ global `MUTED_FG` untouched (4.78:1 on white elsewhere — passes).
  - Focus indicator: `FOCUS_RING` `#93C5FD` (1.8:1 on white — failed 1.4.11 3:1) → `#2563EB` (5.19 on CARD / ~4.9 on BG); added explicit `:focus` rules for `#btnPrimary`/`#btnDanger`/`#btnSecondary`/`#btnSuccess` + `[cssClass=...]` variants (their ID-selector `border:none` previously out-specificity'd the generic `QPushButton:focus` ring) and `QTabBar::tab:focus` + `QTabBar::tab:selected:focus` (preserves accent underline); removed `outline: none` from `QTableWidget`/`QTableView` and `QComboBox QAbstractItemView` so the platform focus outline returns on keyboard tabbing.
- Sidebar nav (`app/main.py`): removed `outline: none` from `_SIDEBAR_QSS` (keyboard focus rect restored on dark bg); `self.nav.setAccessibleName("Main navigation")`; status-bar sync indicator pending color switched from hardcoded failing `#F59E0B` to token `C.WARNING`, and got a tooltip ("Sync state. See Settings > Cloud Sync & Device for details.").
- New tests: `tests/test_ui_accessibility.py` (31, incl. parametrization) — WCAG contrast helper (relative luminance), 27 normal-text pairs ≥ 4.5, focus ring ≥ 3.0 vs CARD/BG, all focus selectors present in generated QSS, no `outline: none` in theme QSS or sidebar QSS. **31 passed in 2.56s.**
- Relevant existing UI suites (app shell, login, dashboard, POS, products, inventory, customers, users, expense form, exchange, purchases, settings/printer, low stock, barcode, F5 receipt, report export): **195 passed in 61.29s** — no visual-state regressions.
- Full regression (`.venv`, offscreen): **881 passed, 8 skipped, 15 warnings in 233.55s** (baseline 850 + 31 new; no failures/errors). Warnings identical to prior phases.

## Gate record (Phase 4)

- CLI entry point: `app/data/db.py` gained a real `__main__` (module stays Qt-free, ~fast headless). No-arg / `-h` / `--help` / `help` prints: module is NOT the desktop entry point → `python -m app.main` (dev) / `dist\FunmitePOS\FunmitePOS.exe` (packaged). `init` → `load_settings()` + `initialize_database()` + prints resolved DB path and schema version (no UI). Unknown command → exit 2. Desktop launch behavior untouched (`app.main`, `README.md:216`, `scripts/run_dev.bat`, `funmite_pos.spec` entry all already consistent).
- Display math: `reports_page._populate_sales` daily chart aggregation now goes through module helper `_daily_sales_series(rows)` — Decimal accumulation, `float` only at the chart boundary (`charts.set_data` consumes floats); `my_sales_page._run_report` sum via helper `_sales_total(rows)` (Decimal) then `format_money` (already Decimal-safe). Reviewed-unchanged: `reports_page.py:541` product chart append already converts a single Decimal to float once at the chart boundary — no accumulation, already-correct pattern. No DB financial semantics or business rules altered.
- New tests: `tests/test_cli_entry.py` (4) — subprocess `python -m app.data.db` no-arg points to `python -m app.main`; `--help` exit 0; unknown command exit 2; `init` against temp dirs creates `funmite.db` at schema version 5. `tests/test_report_display_math.py` (4) — Decimal-exact grouping (100.10+0.90=101.00 → 101.0), first-seen ordering preserved, `0.1+0.2==0.3`, empty sum == 0. **8 passed in 10.52s.**
- Relevant existing suites: reports/export/dashboard/reporting-service + migrations + migration-safety + config + schema: **76 passed in 19.70s**.
- Full regression (`.venv`, offscreen): **850 passed, 8 skipped, 15 warnings in 232.94s** (baseline 842 + 8 new; no failures/errors). Warnings identical to prior phases (FastAPI/Starlette deprecations, SQLAlchemy LegacyAPIWarning, pre-existing SAWarning).

## Gate record (Phase 3)

- Pre-migration backup: `runner._backup_before_upgrade` uses `sqlite3.Connection.backup()` (WAL-safe, same `funmite_YYYYMMDD_HHMMSS_<hex>.db` naming and default destination as BackupService); wired from `db.initialize_database` with the real `backup_dir`; skipped only for in-memory/missing files. Backup failure aborts the upgrade.
- Schema-version fencing: new `NewerSchemaError`; `upgrade` AND `downgrade` refuse when `current_version > latest` known, with an actionable message; refusal precedes any backup/write.
- 005 hardening: `finally` still restores `PRAGMA foreign_keys=ON` on the AUTOCOMMIT connection; module + `_rebuild_table` docstrings now state the NON-ATOMIC contract and that the pre-upgrade backup is the recovery mechanism, and that re-runs are safe (idempotent, staging table dropped first).
- Empirical finding (probe + test): SQLAlchemy's sqlite3 dialect AUTO-COMMITS SQLite DDL even inside `engine.begin()` — the runner transaction only protects the `schema_version` record (never recorded on failure), so a partial 005 run leaves DDL present but is re-runnable; the new test asserts this documented state rather than a false "atomic rollback" assumption.
- Migration-specific tests: **4 passed** (5.29s) — pre-upgrade backup content/version/integrity; newer-schema rejection (upgrade + downgrade) with no backup/write; 005 mid-rebuild failure → exception propagates, `foreign_keys=ON` restored (`fk_after_restore == 1` spy read-back), `schema_version` stays 4, original data intact + documented `sales_mig5` leftover, recovery by re-run (idempotent → v5, staging gone) AND by backup restore (→ v4, integrity ok).
- Existing `tests/test_migrations.py`: **8 passed**.
- Full regression (`.venv`, offscreen): **842 passed, 8 skipped, 15 warnings in 225.24s** (baseline 838 + 4 new; no failures/errors).
- Diff scope: only `app/data/migrations/runner.py`, `app/data/migrations/versions/005_...py` (docs), `app/data/db.py` (wire backup_dir), `tests/test_migration_safety.py` (new). WAL settings untouched; no business-logic/UI/exchange/printer changes; no EXE rebuild; no version bump; nothing committed.

## Gate record (Phase 2)

- Targets: `app/data/db.py` `_set_sqlite_pragmas` → `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=10000`, `foreign_keys=ON`; `app/sync/cloud_db.py` `_set_sqlite_pragmas` → same durability set, attached only to SQLite URLs (`url.startswith("sqlite")`), PostgreSQL path untouched.
- Verified reasons no backup conflict: `BackupService` uses `sqlite3.Connection.backup()` (WAL-safe atomic online backup) and `VACUUM INTO` restore — no naive copies of the live DB (`backup_service.py:142-148`, `303-307`, `328-338`).
- Step 1 affected schema/database tests: **35 passed** (8.93s).
- Step 2 `tests/test_sync_integration.py`: **21 passed** (51.12s).
- Step 3 full regression (`.venv`, offscreen): **838 passed, 8 skipped, 15 warnings in 207.81s** — identical to Phase 1 baseline (838/8; warning count 16→15, no new warnings).
- Step 4 WAL artifact probe on a real file DB with an active uncommitted write: `journal_mode=wal`, `synchronous=1`, `busy_timeout=10000`, `foreign_keys=1`; files present: `probe.db`, `probe.db-wal`, `probe.db-shm`.
- Step 5 existing behavior intact: full regression (incl. backup/migration/schema/sync suites) green; live `data/funmite.db` **not mutated** during the gate — it will flip to WAL automatically on next app start via the connection pragma.
- Step 7 diff inspected: only `app/data/db.py` and `app/sync/cloud_db.py` changed; no Phase 3+ changes present.

## Gate record (Phase 1)

- Fresh venv: `pip install -e .[dev]` — **success**; 33 packages resolved cleanly + `funmite-pos 1.3.1` editable wheel built.
- Full suite in fresh venv: **838 passed, 8 skipped, 16 warnings in 336.21s** (env-gated skips unchanged).
- `requirements-build.txt` generated from the resolved fresh build venv (freeze header documents purpose; the `-e git+...` editable line dropped as it cannot be pip-installed by consumers and is irrelevant to the PyInstaller `.spec`, which bundles `app/` source directly).
- EXE rebuild: **intentionally skipped** — dependency resolution in the shop build venv is unchanged, so the binary would be byte-identical; rebuild deferred to the final release gate. Rebuild on request if preferred.
- Unrelated observation (pre-existing, out of scope): 16 warnings include SQLAlchemy 2.0 `Query.get()` LegacyAPIWarnings in `test_sync_integration.py`; SQLAlchemy resolved newer than shop venv (2.0.54 vs 2.0.52) with zero failures — backends compatible.

## Exclusions (fixed scope)

No PostgreSQL provisioning; no hosted gate; no exchange/refund business-rule changes; no printer architecture changes; no version bump; no commit until the full plan passes its final gate.