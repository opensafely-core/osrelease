# OpenSAFELY output publication

**WORK IN PROGRESS**

All outputs from OpenSAFELY pipelines are subject to tiered levels of scrutiny,
to provide assurance that identifiable data is not leaked accidentally, or
maliciously.

The final tier is review of so-called "Level 4" outputs, where the OpenSAFELY
framework stores outputs marked as `moderately_sensitive` in the `project.yaml` file.

The script here is a work in progress to help the review process.

The current model is that people check out a study repo, edit outputs, copy edited outputs to the study repo, commit and push.

The proposed model is as follows:

* The outputs for a single workspace are stored in a per-workspace folder
* This folder should be maintained as a local git repo (which we'll call the *redaction repo*). The redaction repos will never leave the server: it only exists for reviewers to track redaction activity over time. The git history may, therefore, contain identifying information.
* Whenever new outputs are generated in the workspace folder, a reviewer will use their usual git tools (typically Github Desktop) to examine the outputs. Outputs intended for public release should be redacted (as necessary) and then committed to the redaction repo.
* The `osrelease` script should then be run in a command terminal, from the root folder of the workspace folder. It:
  * finds the URL of the github repo to where the redacted outputs should be published (the *study repo*)
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


## Usage summary

* Log into L4 server
* Open a console at the root of the workspace you want to publish (e.g. `/d/Level4Files/workspaces/my-amazing-research`)
  * If doing this on the L3 server (_you shouldn't be..._) then be sure to do this in the `/e/FILESFORL4/workspaces` folder to mitigate the risk of publishing high-privacy outputs
* If this is the first time any releases have been made, type `git init` to start a new git repo there
   * On Windows, run `git config --global core.safecrlf false` to suppress warnings about CRLF conversion
* Run `git status` to see any changes
* Run `git add` to add any new files, or changes from any existing files, to the local repo
* Edit files to redact, as necessary
* Commit any edits you make
* Run `osrelease`
* Follow the instructions. It will only publish files you have committed locally, and won't send any intermediate history; just their state as they currently are in the local repo


## Installing on TPP level 4 server

* Create or update a checkout 

    git clone https://github.com/opensafely/output-publisher /d/output-publisher

* Create venv at `/d/osrelease`

    /c/Program\ Files\Python39.exe -m pyenv /d/osrelease

* Install into venv
 
    /d/osrelease/Scripts/pip install -e /d/output-publisher

* Configure
  
    Add the github private repo token to /d/osrelease/osrelease_config.py: 'PRIVATE_REPO_ACCESS_TOKEN="<token>"'

* Work with TPP to ensure /d/osrelease/Scripts on system PATH


## Updating

* Update checkout

    cd /d/output-publisher && git pull
