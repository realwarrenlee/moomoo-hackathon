import pytest

from app.broker.account_lock import (
    AccountLock,
    AccountLockError,
    BrokerAccount,
    fingerprint_account_id,
    mask_account_id,
)

FAKE_ACCOUNT_ID = "0000000000000101"


def make_account(
    account_id: str = FAKE_ACCOUNT_ID,
    *,
    market_id: int = 100,
    source: str = "simulated",
    account_type: str = "MARGIN",
) -> BrokerAccount:
    return BrokerAccount.from_provider(
        account_id=account_id,
        market_id=market_id,
        source=source,
        account_type=account_type,
    )


def make_lock(**overrides) -> AccountLock:
    values = {
        "expected_masked_id": "****0101",
        "expected_fingerprint": fingerprint_account_id(FAKE_ACCOUNT_ID),
        "expected_market_id": 100,
    }
    values.update(overrides)
    return AccountLock(**values)


def test_exact_simulated_account_resolves():
    account = make_account()

    resolved = make_lock().resolve([account])

    assert resolved is account
    assert resolved.account_id == FAKE_ACCOUNT_ID
    assert resolved.masked_id == "****0101"


def test_live_account_with_matching_identity_is_rejected():
    live = make_account(source="live")

    with pytest.raises(AccountLockError, match="live account"):
        make_lock().resolve([live])


def test_other_paper_account_is_rejected():
    other = make_account("0000000000009999")

    with pytest.raises(AccountLockError, match="not found"):
        make_lock().resolve([other])


def test_market_id_alone_cannot_select_an_account():
    other = make_account("0000000000009999", market_id=100)

    with pytest.raises(AccountLockError, match="not found"):
        make_lock().resolve([other])


def test_duplicate_identity_is_rejected():
    first = make_account()
    second = make_account()

    with pytest.raises(AccountLockError, match="multiple"):
        make_lock().resolve([first, second])


def test_fingerprint_mismatch_is_rejected():
    lock = make_lock(expected_fingerprint=fingerprint_account_id("0000000000000202"))

    with pytest.raises(AccountLockError, match="not found"):
        lock.resolve([make_account()])


def test_market_mismatch_is_rejected():
    lock = make_lock(expected_market_id=1)

    with pytest.raises(AccountLockError, match="market"):
        lock.resolve([make_account(market_id=100)])


def test_full_account_id_is_not_in_error_text():
    other = make_account("0000000000009999")

    with pytest.raises(AccountLockError) as excinfo:
        make_lock().resolve([other])

    assert "0000000000009999" not in str(excinfo.value)


def test_masked_id_is_non_secret():
    assert mask_account_id(FAKE_ACCOUNT_ID) == "****0101"
    assert mask_account_id("abc") == "****"


def test_lock_requires_both_identity_parts():
    with pytest.raises(AccountLockError):
        AccountLock(expected_masked_id="", expected_fingerprint="0" * 64)
    with pytest.raises(AccountLockError):
        AccountLock(expected_masked_id="****0101", expected_fingerprint="")


def test_from_env_fails_closed_when_identity_is_missing():
    with pytest.raises(AccountLockError, match="required"):
        AccountLock.from_env({})


def test_from_env_builds_strict_lock():
    lock = AccountLock.from_env(
        {
            "COMPETITION_ACCOUNT_MASKED_ID": "****0101",
            "COMPETITION_ACCOUNT_FINGERPRINT": fingerprint_account_id(FAKE_ACCOUNT_ID),
            "COMPETITION_ACCOUNT_MARKET_ID": "100",
        }
    )

    assert lock.resolve([make_account()]).masked_id == "****0101"
