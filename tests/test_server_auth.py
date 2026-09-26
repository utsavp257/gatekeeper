from harness.server import token_ok


def test_token_required_when_configured():
    assert token_ok(configured="s3cret", provided="s3cret")
    assert not token_ok(configured="s3cret", provided=None)
    assert not token_ok(configured="s3cret", provided="wrong")


def test_open_when_not_configured():
    assert token_ok(configured=None, provided=None)


def test_background_job_runs_and_reports_result():
    import time

    from harness.server import JOBS, start_job

    job = start_job("demo", lambda: {"promoted": True})
    for _ in range(50):
        if JOBS[job]["status"] != "running":
            break
        time.sleep(0.02)
    assert JOBS[job]["status"] == "done" and JOBS[job]["result"] == {"promoted": True}


def test_background_job_failure_is_captured():
    import time

    from harness.server import JOBS, start_job

    def boom():
        raise RuntimeError("no champion")

    job = start_job("demo2", boom)
    for _ in range(50):
        if JOBS[job]["status"] != "running":
            break
        time.sleep(0.02)
    assert JOBS[job]["status"] == "error" and "no champion" in JOBS[job]["error"]
