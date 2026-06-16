from deep_harness import crypto
from deep_harness.server.agents import AgentManager
from deep_harness.server.db import AppDB


def test_encrypt_decrypt_roundtrip(settings):
    token = crypto.encrypt_secret("as-supersecret")
    assert token.startswith("enc:")
    assert "as-supersecret" not in token
    assert crypto.decrypt_secret(token) == "as-supersecret"


def test_empty_secret_stays_empty(settings):
    assert crypto.encrypt_secret("") == ""
    assert crypto.decrypt_secret("") == ""


def test_legacy_plaintext_is_returned_as_is(settings):
    # secrets written before encryption existed have no 'enc:' prefix
    assert crypto.decrypt_secret("as-legacy-plaintext") == "as-legacy-plaintext"


def test_env_key_is_used_when_set(monkeypatch, settings):
    monkeypatch.setenv(crypto.ENV_KEY, "a-unit-test-key")
    token = crypto.encrypt_secret("secret")
    assert crypto.decrypt_secret(token) == "secret"


def test_modal_secret_encrypted_at_rest(settings, tmp_path):
    """The Modal token secret must never sit in the DB as plaintext, and must
    decrypt back to the original for the compute config."""
    db = AppDB(tmp_path / "app.db")
    user_id = db.create_user("alice", "hash", "salt")
    db.upsert_user_settings(
        user_id,
        compute_backend="modal",
        gpu_type="A100",
        modal_token_id="ak-test",
        modal_token_secret="as-supersecret",
        gate_plan=True,
        gate_training_jobs=True,
        gate_shell=True,
    )
    row = db.get_user_settings(user_id)
    assert row["modal_token_secret"] != "as-supersecret"
    assert row["modal_token_secret"].startswith("enc:")

    mgr = AgentManager(checkpointer=None, db=db, model=None)
    assert mgr.compute_config(user_id).modal_token_secret == "as-supersecret"
