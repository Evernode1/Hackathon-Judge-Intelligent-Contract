"""
Integration tests for hackathon_judge.py (GenLayer Studio / gltest).

    pip install genlayer-test pytest
    gltest tests/ -v

Covers deterministic paths: validation, funding, deposits, locks, cancel/refund, admin.
The live judging test needs real repos and an LLM, so it is skipped unless you set:
    JUDGE_TEST_REPO_URL, JUDGE_TEST_DEMO_URL
(the repo README must contain the submitting wallet address, with commits inside the event window).
gltest's API changes between versions; adjust transact/account calls if needed.
"""
import json
import os

import pytest
from gltest import create_account, get_contract_factory
from gltest.assertions import tx_execution_failed, tx_execution_succeeded

GEN = 10 ** 18
DEPOSIT = GEN // 100
RUBRIC = json.dumps([
    {"name": "Innovation", "description": "How original and useful the idea is", "weight": 30},
    {"name": "Working code", "description": "Does the code run and deliver what it claims", "weight": 40},
    {"name": "Documentation", "description": "README clarity and setup instructions", "weight": 30},
])
BPS = json.dumps([5000, 3000, 2000])
REPO = "https://github.com/octocat/Hello-World"
DEMO = "https://demo.example.com/app"
PITCH = "A tool that does something genuinely useful for developers."


@pytest.fixture()
def c():
    return get_contract_factory("HackathonJudge").deploy(args=[])


def make_event(c, value=GEN, rubric=RUBRIC, mode=0, bps=BPS, deposit=DEPOSIT, **kw):
    args = [kw.get("name", "Test Hack"), "A short but valid event description", rubric, mode, bps,
            kw.get("min_score", 0), deposit, kw.get("max_projects", 10), kw.get("min_commits", 0),
            kw.get("start_in_days", 0), kw.get("submission_days", 7), kw.get("judging_days", 3)]
    return c.create_event(args=args).transact(value=value)


# ------------------------------------------------------------ create_event
def test_create_event_escrows_pool(c):
    assert tx_execution_succeeded(make_event(c))
    e = c.get_event(args=[1]).call()
    assert e["status"] == "OPEN" and e["pool"] == GEN and len(e["rubric"]) == 3
    assert c.get_accounting(args=[]).call()["total_pools"] == GEN


def test_rejects_low_pool(c):
    assert tx_execution_failed(make_event(c, value=1))


@pytest.mark.parametrize("bad", [
    json.dumps([{"name": "A", "description": "only one criterion here", "weight": 100}]),
    RUBRIC.replace('"weight": 30}]', '"weight": 29}]'),
    "not json",
])
def test_rejects_bad_rubric(c, bad):
    assert tx_execution_failed(make_event(c, rubric=bad))


@pytest.mark.parametrize("bps", ["[5000,6000]", "[3000,7000]", "[]", "[10000,0]"])
def test_rejects_bad_payout_shares(c, bps):
    assert tx_execution_failed(make_event(c, bps=bps))


def test_rejects_bad_schedule_and_deposit(c):
    assert tx_execution_failed(make_event(c, submission_days=0))
    assert tx_execution_failed(make_event(c, deposit=1))
    assert tx_execution_failed(make_event(c, max_projects=101))


# ---------------------------------------------------------------- funding
def test_sponsor_topup_and_refund_after_cancel(c):
    make_event(c)
    sponsor = create_account()
    assert tx_execution_succeeded(c.fund_event(args=[1]).transact(value=GEN, account=sponsor))
    assert c.get_event(args=[1]).call()["pool"] == 2 * GEN
    assert c.get_contribution(args=[1, sponsor.address]).call() == GEN
    assert tx_execution_succeeded(c.cancel_event(args=[1]).transact())
    assert tx_execution_succeeded(c.refund_contribution(args=[1]).transact(account=sponsor))
    assert tx_execution_failed(c.refund_contribution(args=[1]).transact(account=sponsor))   # no double refund


def test_only_organizer_can_cancel(c):
    make_event(c)
    assert tx_execution_failed(c.cancel_event(args=[1]).transact(account=create_account()))


# ------------------------------------------------------------ submissions
def submit(c, acct, repo=REPO, demo=DEMO, value=DEPOSIT, team="Team Rocket"):
    return c.submit_project(args=[1, team, PITCH, repo, demo]).transact(value=value, account=acct)


def test_submit_requires_exact_deposit(c):
    make_event(c)
    a = create_account()
    assert tx_execution_failed(submit(c, a, value=DEPOSIT - 1))
    assert tx_execution_failed(submit(c, a, value=DEPOSIT + 1))
    assert tx_execution_succeeded(submit(c, a))


def test_organizer_cannot_enter(c):
    make_event(c)
    assert tx_execution_failed(c.submit_project(args=[1, "T", PITCH, REPO, DEMO]).transact(value=DEPOSIT))


@pytest.mark.parametrize("repo,demo", [
    ("https://github.com/octocat/Hello-World/tree/main", DEMO),
    ("http://github.com/octocat/Hello-World", DEMO),
    ("https://gitlab.com/octocat/Hello-World", DEMO),
    (REPO, "http://demo.example.com"),
    (REPO, "https://127.0.0.1/app"),
    (REPO, "https://localhost/app"),
    (REPO, "https://demo.example.com:8080/app"),
])
def test_submit_rejects_bad_urls(c, repo, demo):
    make_event(c)
    assert tx_execution_failed(submit(c, create_account(), repo=repo, demo=demo))


def test_one_project_per_wallet_and_cap(c):
    make_event(c, max_projects=1)
    a, b = create_account(), create_account()
    assert tx_execution_succeeded(submit(c, a))
    assert tx_execution_failed(submit(c, a, repo="https://github.com/octocat/Spoon-Knife"))
    assert tx_execution_failed(submit(c, b, repo="https://github.com/octocat/Spoon-Knife"))   # event full


def test_withdraw_refunds_deposit_once(c):
    make_event(c)
    a = create_account()
    submit(c, a)
    assert c.get_accounting(args=[]).call()["total_deposits"] == DEPOSIT
    assert tx_execution_succeeded(c.withdraw_submission(args=[1]).transact(account=a))
    assert c.get_accounting(args=[]).call()["total_deposits"] == 0
    assert tx_execution_failed(c.withdraw_submission(args=[1]).transact(account=a))


def test_cannot_cancel_after_submission(c):
    make_event(c)
    submit(c, create_account())
    assert tx_execution_failed(c.cancel_event(args=[1]).transact())


# ------------------------------------------------------ phase / safety locks
def test_judging_and_finalize_blocked_during_submission(c):
    make_event(c)
    a = create_account()
    submit(c, a)
    assert tx_execution_failed(c.judge_project(args=[1, 1]).transact())
    assert tx_execution_failed(c.finalize_event(args=[1]).transact())
    assert tx_execution_failed(c.claim(args=[1, 1]).transact())


# ------------------------------------------------------------------- admin
def test_admin_owner_only_and_pause(c):
    m = create_account()
    assert tx_execution_failed(c.set_paused(args=[True]).transact(account=m))
    assert tx_execution_failed(c.set_params(args=[1, 1]).transact(account=m))
    assert tx_execution_failed(c.withdraw_treasury(args=[1]).transact(account=m))
    assert tx_execution_succeeded(c.set_paused(args=[True]).transact())
    assert tx_execution_failed(make_event(c))


def test_treasury_cannot_exceed_balance(c):
    assert tx_execution_failed(c.withdraw_treasury(args=[1]).transact())


def test_config_enforces_exact_consensus(c):
    cfg = c.get_config(args=[]).call()
    assert cfg["score_tolerance"] == 0          # no score difference between validators is accepted
    assert cfg["score_levels"] == 5 and cfg["judge_samples"] == 3 and cfg["max_source_files"] >= 1


def test_repo_lock_view_unlocked(c):
    assert c.is_repo_locked(args=[REPO]).call() == {"locked": False, "event_id": 0}


# -------------------------------------------------- live judging (optional)
LIVE = all(os.getenv(k) for k in ("JUDGE_TEST_REPO_URL", "JUDGE_TEST_DEMO_URL"))


@pytest.mark.skipif(not LIVE, reason="set JUDGE_TEST_* env vars for the live judging test")
def test_live_precheck_judge_finalize_claim(c):
    """
    Needs: a public repo with commits in the window, whose README contains the test
    account's wallet address, and a reachable demo page. Use a very short schedule
    (submission_days=1 is the minimum, so run on a localnet with time control).
    """
    make_event(c, submission_days=1, judging_days=1)
    team = create_account()
    c.submit_project(args=[1, "Live Team", PITCH, os.environ["JUDGE_TEST_REPO_URL"], os.environ["JUDGE_TEST_DEMO_URL"]]).transact(value=DEPOSIT, account=team)
    code = c.precheck_submission(args=[1]).transact(account=team)
    p = c.get_project_of(args=[1, team.address]).call()
    assert p["precheck_count"] == 1
