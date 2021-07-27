import os

from publisher import jobrunner_stats

# Fixtures:
#
# a `study_repo` is an empty git repo which the extracted file will be pushed to
#
# temp_jobrunner is a temporary directory mimicing the job-runner


def test_successful_push_message(capsys, study_repo, temp_jobrunner):
    extracted = jobrunner_stats.main(
        current_dir=os.getcwd(),
        job_runner_dir=temp_jobrunner.name,
        days_to_extract=7,
        repo_url=study_repo.name,
        branch="main",
        token="",
    )

    assert extracted

    captured = capsys.readouterr()
    assert captured.out.startswith("Pushed new extraction file"), captured.out
