#!/usr/bin/env python3
"""
Simple test script for bump-version workflow using test_mode parameter
Workflow always runs on master branch, test_mode creates test branch automatically
"""

import os
import sys
import time
import subprocess
from typing import Optional, Tuple


class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    NC = '\033[0m'


def print_step(message: str, color: str = Colors.YELLOW):
    print(f"{color}{message}{Colors.NC}")


def print_success(message: str):
    print(f"{Colors.GREEN}✓ {message}{Colors.NC}")


def print_error(message: str):
    print(f"{Colors.RED}✗ {message}{Colors.NC}", file=sys.stderr)


def run_gh_command(args: list, capture_output: bool = True) -> Tuple[int, str, str]:
    try:
        result = subprocess.run(
            ['gh'] + args,
            capture_output=capture_output,
            text=True,
            check=False
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        print_error("GitHub CLI (gh) is not installed")
        sys.exit(1)


def check_gh_auth() -> bool:
    returncode, _, _ = run_gh_command(['auth', 'status'])
    return returncode == 0


def get_latest_tag(repo: str, release_branch: str) -> Optional[str]:
    returncode, stdout, _ = run_gh_command([
        'api', f'repos/{repo}/git/refs/tags',
        '--jq', f'.[] | select(.ref | startswith("refs/tags/v{release_branch}.")) | .ref'
    ])

    if returncode != 0 or not stdout.strip():
        return None

    tags = [line.replace('refs/tags/', '') for line in stdout.strip().split('\n')]
    if not tags:
        return None

    tags.sort(key=lambda x: [int(n) for n in x.lstrip('v').split('.')])
    return tags[-1]


def parse_version(version_tag: str) -> Tuple[int, int, int]:
    version = version_tag.lstrip('v')
    parts = version.split('.')
    return int(parts[0]), int(parts[1]), int(parts[2])


def tag_exists(repo: str, tag: str) -> bool:
    returncode, _, _ = run_gh_command([
        'api', f'repos/{repo}/git/refs/tags/{tag}'
    ])
    return returncode == 0


def delete_tag(repo: str, tag: str):
    run_gh_command([
        'api', f'repos/{repo}/git/refs/tags/{tag}',
        '-X', 'DELETE'
    ])


def delete_branch(repo: str, branch: str):
    run_gh_command([
        'api', f'repos/{repo}/git/refs/heads/{branch}',
        '-X', 'DELETE'
    ])


def trigger_workflow(repo: str, workflow_file: str, branch: str,
                     version: str, skip_nightly: bool, dry_run: bool, test_mode: bool):
    returncode, _, stderr = run_gh_command([
        'workflow', 'run', workflow_file,
        '--repo', repo,
        '--ref', branch,
        '-f', f'version={version}',
        '-f', f'skip_nightly_check={str(skip_nightly).lower()}',
        '-f', f'dry_run={str(dry_run).lower()}',
        '-f', f'test_mode={str(test_mode).lower()}'
    ])

    if returncode != 0:
        print_error(f"Failed to trigger workflow: {stderr}")
        sys.exit(1)


def get_latest_workflow_run(repo: str, workflow_file: str, branch: str) -> Optional[str]:
    returncode, stdout, _ = run_gh_command([
        'run', 'list',
        '--repo', repo,
        f'--workflow={workflow_file}',
        f'--branch={branch}',
        '--limit', '1',
        '--json', 'databaseId',
        '--jq', '.[0].databaseId'
    ])

    if returncode != 0 or not stdout.strip():
        return None

    return stdout.strip()


def wait_for_workflow(repo: str, run_id: str):
    returncode, _, _ = run_gh_command([
        'run', 'watch', run_id,
        '--repo', repo,
        '--exit-status'
    ], capture_output=False)

    if returncode != 0:
        print_error("Workflow failed")
        sys.exit(1)


def main():
    # Configuration
    REPO = os.getenv('REPO', 'bfeller18/RedisTimeSeries')
    RELEASE_BRANCH = os.getenv('RELEASE_BRANCH', '1.12')
    TEST_BRANCH = f"{RELEASE_BRANCH}-test"
    WORKFLOW_FILE = "bump-version.yml"
    WORKFLOW_TRIGGER_BRANCH = os.getenv('WORKFLOW_TRIGGER_BRANCH', 'master')
    SKIP_NIGHTLY_CHECK = os.getenv('SKIP_NIGHTLY_CHECK', 'true').lower() == 'true'
    DRY_RUN = os.getenv('DRY_RUN', 'false').lower() == 'true'


    print_step("=== Bump Version Workflow Test (Test Mode) ===", Colors.GREEN)
    print(f"Repository: {REPO}")
    print(f"Release Branch: {RELEASE_BRANCH}")
    print(f"Test Branch: {TEST_BRANCH} (created by workflow)")
    print(f"Workflow Trigger Branch: {WORKFLOW_TRIGGER_BRANCH}")
    print(f"Test Mode: {TEST_MODE}")
    print(f"Dry Run: {DRY_RUN}")
    print(f"Cleanup on Success: {CLEANUP_ON_SUCCESS}")
    print()

    # Check GitHub CLI authentication
    if not check_gh_auth():
        print_error("Not authenticated with GitHub CLI")
        print("Run: gh auth login")
        sys.exit(1)

    # Step 1: Get latest tag from release branch
    print_step(f"Step 1: Getting latest tag for branch {RELEASE_BRANCH}...")
    latest_tag = get_latest_tag(REPO, RELEASE_BRANCH)
    if not latest_tag:
        print_error(f"No tags found for branch {RELEASE_BRANCH}")
        sys.exit(1)
    print_success(f"Latest tag: {latest_tag}")

    # Step 2: Calculate next version
    print_step("Step 2: Calculating next version...")
    major, minor, patch = parse_version(latest_tag)
    next_version = f"{major}.{minor}.{patch + 1}"
    next_tag = f"v{next_version}"
    print_success(f"Next version: {next_version}")

    # Step 3: Delete existing tag if it exists
    print_step(f"Step 3: Checking if tag {next_tag} exists...")
    if tag_exists(REPO, next_tag):
        print(f"Tag {next_tag} already exists, deleting it...")
        delete_tag(REPO, next_tag)
        time.sleep(2)
        print_success(f"Deleted existing tag {next_tag}")
    else:
        print_success(f"Tag {next_tag} does not exist")

    # Step 4: Trigger workflow from master branch
    print_step(f"Step 4: Triggering bump-version workflow from {WORKFLOW_TRIGGER_BRANCH}...")
    print(f"  Version: {next_version}")
    print(f"  Test Mode: {TEST_MODE}")
    print(f"  Skip nightly check: {SKIP_NIGHTLY_CHECK}")
    print(f"  Dry run: {DRY_RUN}")
    if TEST_MODE:
        print(f"  → Workflow will create/use test branch: {TEST_BRANCH}")
    trigger_workflow(REPO, WORKFLOW_FILE, WORKFLOW_TRIGGER_BRANCH, next_version,
                    SKIP_NIGHTLY_CHECK, DRY_RUN, TEST_MODE)
    print_success("Workflow triggered")

    # Step 5: Wait for workflow to start
    print_step("Step 5: Waiting for workflow to start...")
    time.sleep(5)
    run_id = get_latest_workflow_run(REPO, WORKFLOW_FILE, WORKFLOW_TRIGGER_BRANCH)
    if not run_id:
        print_error("Could not find workflow run")
        sys.exit(1)
    print_success(f"Workflow run ID: {run_id}")
    print(f"View at: https://github.com/{REPO}/actions/runs/{run_id}")

    # Step 6: Wait for workflow to complete
    print_step("Step 6: Waiting for workflow to complete...")
    wait_for_workflow(REPO, run_id)
    print_success("Workflow completed successfully")

    # Step 7: Verify tag was created
    if not DRY_RUN:
        print_step(f"Step 7: Verifying tag {next_tag} was created...")
        time.sleep(3)
        if tag_exists(REPO, next_tag):
            print_success(f"Tag {next_tag} exists")
        else:
            print_error(f"Tag {next_tag} was not created")
            sys.exit(1)
    else:
        print_step("Step 7: Skipped (dry run mode)", Colors.YELLOW)

    # Step 8: Cleanup (optional)
    if CLEANUP_ON_SUCCESS and not DRY_RUN and TEST_MODE:
        print_step(f"Step 8: Cleaning up test branch and tag...")
        delete_tag(REPO, next_tag)
        delete_branch(REPO, TEST_BRANCH)
        print_success("Cleanup completed")
    else:
        print_step("Step 8: Cleanup skipped", Colors.YELLOW)
        if not DRY_RUN and TEST_MODE:
            print(f"To manually cleanup:")
            print(f"  gh api repos/{REPO}/git/refs/tags/{next_tag} -X DELETE")
            print(f"  gh api repos/{REPO}/git/refs/heads/{TEST_BRANCH} -X DELETE")

    # Summary
    print()
    print_step("=== Test Completed Successfully ===", Colors.GREEN)
    print("Summary:")
    print(f"  - Repository: {REPO}")
    print(f"  - Release Branch: {RELEASE_BRANCH}")
    if TEST_MODE:
        print(f"  - Test Branch: {TEST_BRANCH}")
    print(f"  - Previous Version: {latest_tag}")
    print(f"  - New Version: {next_tag}")
    print(f"  - Test Mode: {TEST_MODE}")
    print(f"  - Dry Run: {DRY_RUN}")
    if not DRY_RUN:
        print(f"  - Tag Created: ✓")
        if CLEANUP_ON_SUCCESS and TEST_MODE:
            print(f"  - Cleaned Up: ✓")
        elif TEST_MODE:
            print(f"  - Cleaned Up: ✗ (manual cleanup required)")


if __name__ == '__main__':
    main()

