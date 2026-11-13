# Hackathon / Grant Judge (GenLayer Intelligent Contract)

An organizer funds a prize pool in **native GEN** and publishes a fixed rubric. Teams submit a GitHub repo and a demo link. After the submission deadline, validators read the repo **as it was at the deadline**, check hard facts in code, and score each rubric criterion with an LLM. Prizes are split by rank or proportionally to score and claimed on-chain.

Files: `contract/hackathon_judge.py`, `tests/test_hackathon_judge.py`, `DECISIONS.md`.

## Frontend

A Vite + React app for Vercel lives in `frontend/` (see `frontend/README.md`).

## Lifecycle

1. **Create:** `create_event(...)` with GEN attached (the pool). Rubric (2-8 criteria, weights sum to 100), payout mode, min score, entry deposit, event window and limits are fixed forever.
2. **Fund:** anyone can `fund_event` until the submission deadline (sponsors).
3. **Submit:** `submit_project(event_id, team, pitch, repo_url, demo_url)` with the exact entry deposit. The README must contain the team wallet (`Wallet: 0x...`).
4. **Precheck (free):** `precheck_submission` dry-runs the hard gates (max 5 times) so teams can fix problems before the deadline.
5. **Judge:** after the deadline anyone calls `judge_project(event_id, project_id)`.
6. **Appeal:** one paid appeal per project (fee = entry deposit, goes to the pool); the two scores are averaged.
7. **Finalize:** `finalize_event` ranks projects and computes prizes.
8. **Claim:** `claim(event_id, project_id)` pays prize + deposit refund to the team wallet (anyone can trigger it).

## Scoring

- Each criterion is rated on a **0-5 scale** with written anchors. The final score is computed **in code**: sum(level x weight) x 2, range **0-1000** (shown as 0-10).
- The judge **reads the actual repository**: manifests, up to 8 source files (entry points first, then largest), up to 3 test files, plus the README, all fetched by commit SHA at the deadline. File selection is deterministic, so every validator reads the same material.
- Each evaluation runs **3 independent LLM passes**; the per-criterion lower median is used, and the injection flag needs a majority.
- **Exact consensus, no tolerance:** validators accept a result only if the gate outcome, snapshot SHA, evidence digest (SHA-256 of the SHA, source excerpts and README), injection flag and **every criterion level** are identical. A score difference can never change qualification, ranking or prizes. If validators disagree the call simply fails and can be retried at no cost.
- Ties are broken by earlier submission time.
- Payout modes: **ranked** (basis-point shares for the top N, normalized if fewer teams qualify) or **proportional** (pool split by score). Rounding dust goes to rank 1.

## Hard gates (checked in code, not by the LLM)

Repo exists and is public, not a fork, not archived, at least `min_commits` commits inside the event window, README at the deadline snapshot contains the team wallet, demo URL reachable. A failed gate at judging time disqualifies the project and its deposit joins the prize pool.

## Safety features

Immutable rules, deadline snapshot, wallet-in-README ownership proof, one repo wins once globally, https-only demo URLs (no IPs, ports or credentials), prompt-injection disqualification, organizer cannot enter, pull payouts with state updated first, strict accounting (`get_accounting`), pause switch, owner can only withdraw stranded funds.

## Functions

| Group | Functions |
|---|---|
| Organizer / sponsors | `create_event`, `fund_event`, `cancel_event` (only with no submissions), `refund_contribution` |
| Teams | `submit_project`, `withdraw_submission`, `precheck_submission`, `appeal`, `claim` |
| Anyone | `judge_project`, `finalize_event`, `claim` |
| Owner | `set_params`, `set_paused`, `transfer_ownership`, `withdraw_treasury` |
| Views | `get_event`, `get_events`, `get_project`, `get_project_of`, `get_leaderboard`, `get_contribution`, `is_repo_locked`, `get_config`, `get_accounting` |

## Lint and test

```
pip install genvm-linter genlayer-test pytest
genvm-lint check contract/hackathon_judge.py
gltest tests/ -v
```

Verified locally: the pure logic (time conversion, rubric and payout validation, prize math that always sums to the pool, hard gates, URL rules) was unit-tested with a stubbed SDK, and the file passes a structural lint-style check. It has **not** been deployed or run against real GitHub or an LLM.

## Check on your network

- `gl.message.datetime`, `emit_transfer` via the EVM interface proxy, `gl.vm.run_nondet_unsafe` / `gl.vm.Return`, and `gl.nondet.web.render` behaviour on your Studio version.
- Unauthenticated GitHub API rate limits (60 requests/hour per IP) can cause `FETCH_ERROR` when many projects are judged; those retries are free.
- Only `README.md` at the repo root is read.
- Not audited. Use small amounts until reviewed.
