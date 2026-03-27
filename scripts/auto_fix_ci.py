#!/usr/bin/env python3
"""Autonomous CI fix agent — diagnoses failures and creates fix PRs.

Called by the auto-fix GitHub Actions workflow when CI fails on main.
Uses the Anthropic API with tool use to read failure logs, analyze
the codebase, generate fixes, and create a pull request.

Requires:
    ANTHROPIC_API_KEY — set as a GitHub secret
    GITHUB_TOKEN — provided by GitHub Actions
    WORKFLOW_RUN_ID — the failing workflow run ID

Usage:
    python scripts/auto_fix_ci.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path


def run(cmd: str, check: bool = True) -> str:
    """Run a shell command and return stdout."""
    result = subprocess.run(  # noqa: S602
        cmd, shell=True, capture_output=True, text=True, timeout=120
    )
    if check and result.returncode != 0:
        print(f"Command failed: {cmd}\nstderr: {result.stderr}", file=sys.stderr)
    return result.stdout.strip()


def get_failure_logs(run_id: str) -> str:
    """Extract failure logs from a GitHub Actions workflow run."""
    # Get failed jobs
    jobs_json = run(f"gh run view {run_id} --json jobs")
    jobs = json.loads(jobs_json).get("jobs", [])

    failed_jobs = [j for j in jobs if j.get("conclusion") == "failure"]
    if not failed_jobs:
        return "No failed jobs found."

    # Get the failed log output
    logs = run(f"gh run view {run_id} --log-failed", check=False)
    if not logs:
        logs = "Could not retrieve failure logs."

    # Summarize which jobs failed and their step names
    summary_parts = []
    for job in failed_jobs:
        name = job.get("name", "unknown")
        failed_steps = [
            s["name"]
            for s in job.get("steps", [])
            if s.get("conclusion") == "failure"
        ]
        summary_parts.append(f"Job '{name}' failed at: {', '.join(failed_steps) or 'unknown step'}")

    summary = "\n".join(summary_parts)

    # Truncate logs to avoid token limits (keep last 3000 chars per job)
    if len(logs) > 12000:
        logs = "...(truncated)...\n" + logs[-12000:]

    return f"## Failed Jobs\n{summary}\n\n## Failure Logs\n{logs}"


def read_file(path: str) -> str:
    """Read a file from the repo."""
    try:
        return Path(path).read_text()
    except (FileNotFoundError, IsADirectoryError):
        return f"File not found: {path}"


def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content)
    return f"Written {len(content)} bytes to {path}"


def list_files(pattern: str) -> str:
    """List files matching a glob pattern."""
    from glob import glob
    matches = glob(pattern, recursive=True)
    return "\n".join(sorted(matches)[:50])


def search_code(pattern: str, path: str = ".") -> str:
    """Search for a pattern in the codebase."""
    result = run(f"grep -rn '{pattern}' {path} --include='*.py' | head -30", check=False)
    return result or "No matches found."


def call_claude(system_prompt: str, user_message: str) -> dict:
    """Call Claude API and return the response with tool use support."""
    try:
        import anthropic
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "anthropic"], check=True)
        import anthropic

    client = anthropic.Anthropic()

    tools = [
        {
            "name": "read_file",
            "description": "Read a file from the repository",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to repo root"}
                },
                "required": ["path"],
            },
        },
        {
            "name": "write_file",
            "description": "Write content to a file in the repository",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to repo root"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
        },
        {
            "name": "list_files",
            "description": "List files matching a glob pattern",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g., 'tests/test_*.py')"}
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "search_code",
            "description": "Search for a regex pattern in Python files",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern"},
                    "path": {"type": "string", "description": "Directory to search", "default": "."},
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "run_command",
            "description": "Run a shell command (read-only: lint, test, grep, etc.)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"}
                },
                "required": ["command"],
            },
        },
    ]

    messages = [{"role": "user", "content": user_message}]
    files_modified = []

    # Agentic loop — let Claude use tools until it's done
    for _turn in range(20):  # max 20 tool-use turns
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        # Collect text and tool use blocks
        text_parts = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        if not tool_uses:
            # No more tool calls — Claude is done
            return {"text": "\n".join(text_parts), "files_modified": files_modified}

        # Process tool calls
        tool_results = []
        for tool_use in tool_uses:
            name = tool_use.name
            inp = tool_use.input

            if name == "read_file":
                result = read_file(inp["path"])
            elif name == "write_file":
                result = write_file(inp["path"], inp["content"])
                files_modified.append(inp["path"])
            elif name == "list_files":
                result = list_files(inp["pattern"])
            elif name == "search_code":
                result = search_code(inp["pattern"], inp.get("path", "."))
            elif name == "run_command":
                cmd = inp["command"]
                # Safety: block destructive commands
                if any(danger in cmd for danger in ["rm -rf", "git push", "git reset", "DROP TABLE"]):
                    result = "BLOCKED: destructive command not allowed"
                else:
                    result = run(cmd, check=False)
            else:
                result = f"Unknown tool: {name}"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result[:8000],  # truncate large outputs
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return {"text": "Agent reached max turns", "files_modified": files_modified}


def create_fix_pr(files_modified: list[str], diagnosis: str, run_id: str) -> str:
    """Create a branch, commit changes, and open a fix PR."""
    if not files_modified:
        print("No files modified — nothing to PR.")
        return ""

    branch = f"auto-fix/ci-{run_id}"
    run(f"git checkout -b {branch}")

    for f in files_modified:
        run(f"git add {f}")

    # Commit
    commit_msg = f"Auto-fix CI failure from run {run_id}"
    run(f'git commit -m "{commit_msg}"')
    run(f"git push -u origin {branch}")

    # Create PR
    pr_body = textwrap.dedent(f"""\
    ## Automated CI Fix

    This PR was automatically generated by the CI auto-fix agent.

    **Triggering run:** https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'AeluApp/mandarin')}/actions/runs/{run_id}

    **Diagnosis:**
    {diagnosis[:2000]}

    **Files modified:** {', '.join(files_modified)}

    ---
    *This PR was created automatically. Please review before merging.*

    🤖 Generated by CI Auto-Fix Agent
    """)

    # Write body to temp file to avoid shell escaping issues
    body_file = Path("/tmp/pr_body.md")
    body_file.write_text(pr_body)

    pr_url = run(f'gh pr create --title "Auto-fix: CI failure from run {run_id}" --body-file /tmp/pr_body.md')
    return pr_url


def main():
    run_id = os.environ.get("WORKFLOW_RUN_ID", "")
    if not run_id:
        print("ERROR: WORKFLOW_RUN_ID not set", file=sys.stderr)
        return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    print(f"Diagnosing CI failure for run {run_id}...")

    # Step 1: Get failure logs
    failure_logs = get_failure_logs(run_id)
    print(f"Extracted {len(failure_logs)} chars of failure logs")

    # Step 2: Call Claude to diagnose and fix
    system_prompt = textwrap.dedent("""\
    You are an autonomous CI fix agent for the Aelu project (a Mandarin learning platform).

    Your job: diagnose CI failures and fix them by editing the codebase.

    Rules:
    - NEVER lower test coverage thresholds or floors. Always write tests instead.
    - NEVER lower --cov-fail-under or fail_under values.
    - Only modify files that are directly related to the failure.
    - Keep fixes minimal and focused.
    - Run lint checks (ruff) on any Python files you modify.
    - If you can't fix the issue with confidence, explain why and don't modify files.
    - Do not modify .github/workflows/ files unless the failure is clearly a CI config issue.

    Process:
    1. Read the failure logs carefully
    2. Identify the root cause
    3. Read the relevant source files
    4. Make the minimal fix
    5. Verify with lint/tests if possible
    """)

    user_message = f"""\
Here are the CI failure details. Diagnose the root cause and fix it.

{failure_logs}

Start by reading the relevant files mentioned in the error, then make the fix.
"""

    result = call_claude(system_prompt, user_message)
    diagnosis = result["text"]
    files_modified = result["files_modified"]

    print(f"\n{'='*60}")
    print("DIAGNOSIS:")
    print(diagnosis)
    print(f"\nFiles modified: {files_modified}")
    print(f"{'='*60}")

    # Step 3: Create PR if files were modified
    if files_modified:
        pr_url = create_fix_pr(files_modified, diagnosis, run_id)
        if pr_url:
            print(f"\nFix PR created: {pr_url}")
        return 0
    else:
        print("\nNo automated fix possible. Creating issue instead.")
        # Create a GitHub issue with the diagnosis
        issue_title = f"CI failure needs manual fix (run {run_id})"
        issue_body = f"## CI Failure Diagnosis\n\n{diagnosis[:3000]}\n\n**Run:** https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'AeluApp/mandarin')}/actions/runs/{run_id}"
        body_file = Path("/tmp/issue_body.md")
        body_file.write_text(issue_body)
        issue_url = run('gh issue create --title "' + issue_title + '" --body-file /tmp/issue_body.md --label "ci-failure"', check=False)
        if issue_url:
            print(f"Issue created: {issue_url}")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
