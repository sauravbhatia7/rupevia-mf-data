# Rupevia MF Data Snapshot

Snapshot-first mutual-fund data layer for Rupevia.

The Android/web app does **not** download AMFI's full NAV universe or per-fund history during normal use. GitHub Actions builds `data/mf-snapshot.json` once daily, and Rupevia reads that small precomputed file in the background while immediately showing its last cached/embedded snapshot.

## Published universe

Eight Rupevia segments are published with 30 Direct Growth funds each: Large Cap, Mid Cap, Small Cap, Flexi Cap, ELSS, Index, Hybrid, and Debt.

Returns use historical NAV points: 1M/3M/6M are point-to-point; 1Y/3Y/5Y/10Y are annualised. The default rank is 3Y annualised return. Each refresh compares the current rank with the previous snapshot and preserves `rankDirection` (`↑`, `↓`, `—`), `rankChange`, and `previousRank`.

## Sources

- Latest active schemes, category and NAV: AMFI `NAVAll.txt`.
- Historical NAV series: MFAPI's AMFI mirror, used by the scheduled updater only.

The snapshot records source dates and calculation metadata. Some legacy UI-only research fields (expense/AUM/consistency) are explicitly marked `previewResearch`; they are not represented as live AMFI/MFAPI facts.

## Update schedule

`.github/workflows/update-mf-snapshot.yml` runs daily at 21:00 IST and can also be run manually. The workflow validates that all eight segments have 30 funds before it commits a new snapshot, so a broken/partial upstream response cannot replace the last good file.
