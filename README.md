# Rupevia MF Data Snapshot

Snapshot-first mutual-fund data layer for Rupevia.

The Android/web app does **not** download the full mutual-fund universe or per-fund history during normal use. GitHub Actions builds `data/mf-snapshot.json` once daily. Rupevia immediately uses its last cached good snapshot and checks the compact remote snapshot silently in the background; on a true first install, the existing fully populated preview remains usable until the first snapshot arrives.

## Published universe

Eight Rupevia segments are published with 30 Direct Growth funds each: Large Cap, Mid Cap, Small Cap, Flexi Cap, ELSS, Index, Hybrid, and Debt.

Returns use historical NAV points: 1M/3M/6M are point-to-point; 1Y/3Y/5Y/10Y are annualised. The default ranking signal is 3Y annualised return, with deterministic tie-breakers/fallback metadata recorded per fund. Each clean refresh compares the current rank with the previous clean snapshot and preserves `rankDirection` (`↑`, `↓`, `—`), `rankChange`, and `previousRank`.

## Sources and quality guards

- Latest scheme/category/NAV universe: MFAPI `/mf/latest`, used as an AMFI-mirror feed because hosted GitHub runners do not reliably receive parseable `NAVAll.txt` from the AMFI portal.
- Historical NAV series: MFAPI's AMFI mirror, used by the scheduled updater only.
- App runtime source: only the precomputed GitHub snapshot JSON; no per-fund history fan-out.

The updater accepts open-ended Direct Growth schemes, rejects stale NAV rows outside the configured freshness window, and excludes segregated/side-pocket portfolios. A broken or partial upstream response cannot overwrite the last good snapshot because the workflow validates schema, category counts, and the 240-fund total before commit.

The snapshot records source dates and calculation metadata. Legacy UI-only research fields such as expense/AUM/consistency remain explicitly marked `previewResearch`; they are not represented as live AMFI/MFAPI facts and do not drive the return ranking.

## Update schedule

`.github/workflows/update-mf-snapshot.yml` runs daily at 21:00 IST and can also be run manually. Rank movement is reset only when the ranking-quality baseline version changes; otherwise daily `↑/↓/—` movement is carried forward from the preceding clean snapshot.
