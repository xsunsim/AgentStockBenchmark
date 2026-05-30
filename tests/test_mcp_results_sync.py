import subprocess

from agentstockbenchmark.mcp_server import server


def test_sync_results_repo_initializes_sparse_checkout_with_core_assets(
    monkeypatch, tmp_path
):
    results_repo = tmp_path / "AgentStockBenchmarkResults"
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["git", "--version"]:
            return subprocess.CompletedProcess(args, 0, stdout="git version 2.0\n")
        if args[-1] == "init":
            results_repo.mkdir(parents=True, exist_ok=True)
            (results_repo / ".git").mkdir()
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(server, "DEFAULT_RESULTS_REPO", results_repo)
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert server._sync_results_repo(
        include_parquets=True,
        specific_raw_date="20260528",
    )

    sparse_set = next(
        call for call in calls if call[3:6] == ["sparse-checkout", "set", "--no-cone"]
    )
    assert "/prompts/" in sparse_set
    assert "/strategies/" in sparse_set
    assert "/accounting/" in sparse_set
    assert "/data/parquet/" in sparse_set
    assert "/data/raw/daily/20260528.csv" in sparse_set
    assert any(
        call[3:7] == ["remote", "add", "origin", server.RESULTS_REPO_URL]
        for call in calls
    )
    assert any(call[3:6] == ["fetch", "--depth", "1"] for call in calls)
    assert any(call[3:7] == ["checkout", "-B", "main", "FETCH_HEAD"] for call in calls)


def test_sync_results_repo_does_not_sparsify_existing_full_clone(monkeypatch, tmp_path):
    results_repo = tmp_path / "AgentStockBenchmarkResults"
    (results_repo / ".git").mkdir(parents=True)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args == ["git", "--version"]:
            return subprocess.CompletedProcess(args, 0, stdout="git version 2.0\n")
        if args[3:6] == ["config", "--bool", "core.sparseCheckout"]:
            return subprocess.CompletedProcess(args, 1, stdout="")
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(server, "DEFAULT_RESULTS_REPO", results_repo)
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert server._sync_results_repo(include_parquets=True)

    assert not any(call[3:5] == ["sparse-checkout", "set"] for call in calls)
    assert any(call[3:6] == ["pull", "--ff-only", "origin"] for call in calls)
    assert not any(call[3:6] == ["pull", "--depth", "1"] for call in calls)


def test_ensure_results_repo_allows_existing_local_assets_when_sync_fails(
    monkeypatch, tmp_path
):
    results_repo = tmp_path / "AgentStockBenchmarkResults"
    (results_repo / "prompts" / "20260517").mkdir(parents=True)
    (results_repo / "strategies" / "20260517").mkdir(parents=True)

    monkeypatch.setattr(server, "DEFAULT_RESULTS_REPO", results_repo)
    monkeypatch.setattr(server, "_sync_results_repo", lambda **kwargs: False)

    assert server._ensure_results_repo(required_paths=("prompts", "strategies"))


def test_ensure_results_repo_reports_missing_assets_after_failed_sync(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(server, "DEFAULT_RESULTS_REPO", tmp_path / "missing")
    monkeypatch.setattr(server, "_sync_results_repo", lambda **kwargs: False)

    assert not server._ensure_results_repo(required_paths=("prompts", "strategies"))


def test_get_leaderboard_returns_synced_markdown_without_rebuild(monkeypatch, tmp_path):
    results_repo = tmp_path / "AgentStockBenchmarkResults"
    leaderboard_path = results_repo / "leaderboard" / "leaderboard.md"
    leaderboard_path.parent.mkdir(parents=True)
    leaderboard_path.write_text("# Leaderboard\n")

    monkeypatch.setattr(server, "DEFAULT_RESULTS_REPO", results_repo)
    monkeypatch.setattr(server, "_ensure_results_repo", lambda **kwargs: True)

    assert server.get_leaderboard() == {"leaderboard_markdown": "# Leaderboard\n"}
