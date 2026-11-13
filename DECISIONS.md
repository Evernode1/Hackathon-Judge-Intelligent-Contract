# Design Decisions: Hackathon / Grant Judge

Each entry: problem, decision, trade-off.

## 1. Fixed rules, set at creation
**Problem:** Disputes arise when rules change mid-event.  
**Decision:** Rubric, weights, payout mode and shares, min score, deposit, limits and all deadlines are immutable. The organizer cannot judge, edit, or enter.  
**Trade-off:** A mistake in the rubric means creating a new event. `cancel_event` works only while there are no submissions.

## 2. Judge the repo as of the submission deadline
**Problem:** A team could keep improving the repo while judging runs.  
**Decision:** Validators fetch the latest commit at or before the deadline and read the tree and README at that exact commit SHA. Commit counts only cover the event window.  
**Trade-off:** Work pushed after the deadline is ignored, even if it fixes a bug.

## 3. Hard gates in code, taste in the LLM
**Decision:** Fork, archived, commits in window, README present, wallet in README and demo reachable are checked deterministically. The LLM only scores the rubric criteria.  
**Why:** Facts should never depend on model mood, and gates are what stop fraud.

## 4. Wallet-in-README ownership proof
**Problem:** Anyone could submit someone else's repo and take the prize.  
**Decision:** The README at the deadline snapshot must contain the submitting wallet.  
**Trade-off:** One extra line for teams. The free `precheck_submission` lets them verify it early.

## 5. A repo wins once, globally, and squatting cannot block it
**Decision:** A repo is locked when it is judged, not when it is submitted. Two wallets may submit the same URL, but only a wallet written in the README passes the gate.  
**Trade-off:** A malicious second wallet can waste its own deposit, nothing more.

## 6. Scoring consensus: exact agreement on canonical levels
**Problem:** Accepting scores within a tolerance (for example +-1 per criterion) lets validators approve different results, which can flip a qualification threshold, swap two ranks, or change prize amounts.  
**Decision:** Scores are canonicalized and bound, not approximated:
- Criteria use a coarse 0-5 scale with written anchors. Coarser levels are more stable across LLM runs than 0-10 or fractions.
- Each evaluation takes 3 independent passes and uses the per-criterion lower median.
- A validator re-runs the whole evaluation from the same pinned evidence and accepts only if the gate outcome, snapshot SHA, evidence digest, injection flag and every level are exactly equal. There is no tolerance.
- The final score is computed by the contract from the agreed levels (sum of level x weight x 2), never taken from the LLM.
- Appeals average two such exact-agreed scores with integer math.

**Trade-off:** Safety over liveness. If validators cannot agree exactly, the transaction fails and nobody pays anything; anyone can retry. Heavy disagreement on one project can delay judging, so the judging window should be several days.

## 7. Prompt-injection protection
**Decision:** README, demo text and pitch are marked untrusted. The model reports `injection_detected`; if validators agree it is true, the project is disqualified.  
**Trade-off:** A clumsy README that quotes instructions could be flagged. The hard gates and integer scale limit how much one project can gain.

## 8. Entry deposit, and where forfeits go
**Decision:** Exact deposit per project. Disqualified deposits and appeal fees go to the prize pool, never to the organizer or owner.  
**Why:** The organizer gains nothing from disqualifying teams. If the event ends with no qualifying projects, those amounts become treasury funds, and sponsors get their own contributions back.

## 9. Free precheck, paid appeal
**Decision:** Teams can dry-run the gates up to 5 times before the deadline (no LLM, no cost). One appeal per project costs the entry deposit; the final score is the average of both rounds.  
**Trade-off:** An appeal can lower a score. That is intentional, so appeals are not free lottery tickets.

## 10. Two payout modes
**Decision:** Ranked basis-point shares (must sum to 10000 and not increase by rank) or proportional to score. If fewer teams qualify than ranks, shares are normalized so the whole pool is paid; rounding dust goes to rank 1.  
**Tie-break:** Earlier submission wins. It is deterministic and simple to verify.

## 11. Minimum score
**Decision:** Organizer sets `min_score` (0-1000). Below it, a project gets no prize but still gets its deposit back. If no one qualifies, the event is cancelled and contributors refund.

## 12. Time-boxed judging that cannot be stalled
**Decision:** Judging is permissionless between the submission and judging deadlines. After the judging deadline anyone can finalize; unjudged projects simply get no prize and their deposits are refundable.  
**Trade-off:** If nobody triggers judging in time, projects miss out. Keeping the window several days long makes this unlikely.

## 13. Sponsors and refunds
**Decision:** Anyone can top up the pool until the submission deadline. Contributions are tracked per wallet and refundable only if the event is cancelled or has no winners.

## 14. Money safety
Pull payouts, state updated before every transfer, accounting for pools, deposits and treasury, `get_accounting` exposes the real balance, owner can pause and withdraw only stranded funds. `claim` pays a fixed team wallet, so anyone may trigger it.

## 15. Demo URL restrictions
Validators fetch the demo URL, so it must be `https://` with a real domain name: no IP addresses, ports, credentials or localhost.

## 16. The judge reads source code, not just the README
**Problem:** Scoring "working code" from a README, a file list and a demo page rewards marketing.  
**Decision:** At the deadline commit the validators fetch real evidence by SHA: up to 2 manifests (package.json, pyproject.toml, Cargo.toml and similar), up to 8 source files (entry points such as main/index/app first, then largest) and up to 3 test files, each excerpted to 3,000 characters. Vendored, generated and minified files (node_modules, dist, build, lockfiles, `.min.`), files over 100 KB and unsafe paths are skipped. A repo with no readable source code is disqualified (`NO_SOURCE_FILES`). The prompt tells the judge to base code-quality ratings on the source, not on README claims.  
**Binding:** The evidence digest (SHA-256 over the commit SHA, the exact excerpts and the README) is part of consensus and is stored on the project with the commit SHA and the number of files read, so anyone can audit what was judged.  
**Trade-offs:** Excerpts, not full repositories, are judged, so very large projects are sampled. Dynamic demo-page text is deliberately excluded from the digest (it changes between fetches) but still informs the rating.

## Deliberately not included
- Human judges or multi-sig overrides (this contract is fully automatic by design).
- Team wallets with several payees (one wallet per project; teams can split off-chain).
- Plagiarism detection beyond the one-repo-one-win lock and fork gate.
- Private repos and non-GitHub hosts.
- Third-party audit. Required before real funds.
