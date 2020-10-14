# OpenSAFELY output publication

**WORK IN PROGRESS**

All outputs from OpenSAFELY pipelines are subject to tiered levels of scrutiny,
to provide assurance that identifiable data is not leaked accidentally, or
maliciously.

The final tier is review of so-called "Level 4" outputs, where the OpenSAFELY
framework stores outputs marked as `medium_privacy` in the `project.yaml` file.

The script here is a work in progress to help the review process.

The current model is that people check out a study repo, edit outputs, copy edited outputs to the study repo, commit and push.

The proposed model is as follows:

* The outputs for a single workspace are stored in a per-workspace folder
* This folder should be maintained as a local git repo (which we'll call the *redaction repo*). The redaction repos will never leave the server: it only exists for reviewers to track redaction activity over time. The git history may, therefore, contain identifying information.
* Whenever new outputs are generated in the workspace folder, a reviewer will use their usual git tools (typically Github Desktop) to examine the outputs. Outputs intended for public release should be redacted (as necessary) and then committed to the redaction repo.
* The `report.py` script should then be run in a command terminal, from the root folder of the workspace folder. It:
  * prompts the review for the URL of a github repo to where the redacted outputs should be published (the *study repo*)
  * checks out the *study repo* and creates a branch `release-candidates` (if it doesn't already exist)
  * copies every file that has been committed to the *redaction repo* into a subfolder `released_outputs`
  * creates or updates an index file at `released_outputs/README.md` with links to all the release files
  * adds all new changes as a single commit, using the most recent commit message in the *redaction repo* as the text. It also appends a trailer indicating from where the commit was originated
  * force-pushes `release-candidates` to the study repo
  * outputs a URL to the "create Pull Request" page in github for the `release-candidates` branch of the study repo

The benefit of maintaining a separate *redaction repo* is that when new outputs
are generated and written to that repo, the usual git tools can be used to diff
outputs, making it easier to reapply redactions or decide where new redactions
should be applied.



