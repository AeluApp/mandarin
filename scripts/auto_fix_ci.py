#!/usr/bin/env python3
"""Autonomous CI fix agent — diagnoses failures and creates fix PRs.

Called by the auto-fix GitHub Actions workflow when CI fails on main.
Uses LiteLLM + Together.ai with tool use to read failure logs, analyze
the codebase, generate fixes, and create a pull request.

Requires:
    TOGETHER_API_KEY — set as a GitHub secret
    GITHUB_TOKEN — provided by GitHub Actions
    WORKFLOW_RUN_ID — the failing workflow run ID

Usage:
    python scripts/auto_fix_ci.py
"""

from __future__ import annotations

import json
import os
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
    jobs_json = run(f"gh run view {run_id} --json jobs")
    jobs = json.loads(jobs_json).get("jobs", [])

    failed_jobs = [j for j in jobs if j.get("conclusion") == "failure"]
    if not failed_jobs:
        return "No failed jobs found."

    logs = run(f"gh run view {run_id} --log-failed", check=False)
    if not logs:
        logs = "Could not retrieve failure logs."

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


# Tool definitions in OpenAI/LiteLLM format
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to repo root"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file in the repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to repo root"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files matching a glob pattern",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern (e.g., 'tests/test_*.py')"}
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a regex pattern in Python files",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Search pattern"},
                    "path": {"type": "string", "description": "Directory to search", "default": "."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command (read-only: lint, test, grep, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"}
                },
                "required": ["command"],
            },
        },
    },
]


def _dispatch_tool(name: str, inp: dict) -> tuple[str, str | None]:
    """Execute a tool call. Returns (result, modified_file_or_None)."""
    if name == "read_file":
        return read_file(inp["path"]), None
    elif name == "write_file":
        return write_file(inp["path"], inp["content"]), inp["path"]
    elif name == "list_files":
        return list_files(inp["pattern"]), None
    elif name == "search_code":
        return search_code(inp["pattern"], inp.get("path", ".")), None
    elif name == "run_command":
        cmd = inp["command"]
        if any(danger in cmd for danger in ["rm -rf", "git push", "git reset", "DROP TABLE"]):
            return "BLOCKED: destructive command not allowed", None
        return run(cmd, check=False), None
    else:
        return f"Unknown tool: {name}", None


def call_llm(system_prompt: str, user_message: str) -> dict:
    """Call LLM via LiteLLM and return the response with tool use support."""
    try:
        import litellm
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "litellm"], check=True)
        import litellm

    model = os.environ.get("LITELLM_MODEL", "together_ai/deepseek-ai/DeepSeek-V3.1")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    files_modified = []

    for _turn in range(20):
        response = litellm.completion(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=8192,
            temperature=0.2,
        )

        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            return {"text": msg.content or "", "files_modified": files_modified}

        # Append assistant message with tool calls
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ],
        })

        # Execute tool calls and append results
        for tc in tool_calls:
            name = tc.function.name
            try:
                inp = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                inp = {}

            result, modified_file = _dispatch_tool(name, inp)
            if modified_file:
                files_modified.append(modified_file)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result[:8000],
            })

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

    commit_msg = f"Auto-fix CI failure from run {run_id}"
    run(f'git commit -m "{commit_msg}"')
    run(f"git push -u origin {branch}")

    repo = os.environ.get('GITHUB_REPOSITORY', 'AeluApp/mandarin')
    n_files = len(files_modified)
    file_list = ", ".join(files_modified)
    short_diagnosis = diagnosis[:2000]

    pr_body = textwrap.dedent(f"""\
    ## What happened

    A test or check failed in the app. The auto-fix bot looked at the error,
    figured out what went wrong, and made a fix.

    **What broke:** [See the failing run](https://github.com/{repo}/actions/runs/{run_id})

    ## What the bot changed

    **{n_files} file(s) modified:** {file_list}

    ## Bot's explanation

    {short_diagnosis}

    ## What happens next

    This PR will **merge itself automatically** if all tests pass.
    You'll get an email confirming what changed. If any test fails,
    it stays open for a human to look at.

    ---
    🤖 *Created automatically by the CI Auto-Fix Agent*
    """)

    body_file = Path("/tmp/pr_body.md")
    body_file.write_text(pr_body)

    pr_url = run(f'gh pr create --title "Auto-fix: CI failure from run {run_id}" --body-file /tmp/pr_body.md')

    if pr_url:
        run("gh pr merge --auto --squash", check=False)

    return pr_url


def main():
    run_id = os.environ.get("WORKFLOW_RUN_ID", "")
    if not run_id:
        print("ERROR: WORKFLOW_RUN_ID not set", file=sys.stderr)
        return 1

    api_key = os.environ.get("TOGETHER_API_KEY")
    if not api_key:
        print("TOGETHER_API_KEY secret not set — skipping auto-fix agent")
        print("Set it via: gh secret set TOGETHER_API_KEY --repo AeluApp/mandarin")
        return 0

    print(f"Diagnosing CI failure for run {run_id}...")

    failure_logs = get_failure_logs(run_id)
    print(f"Extracted {len(failure_logs)} chars of failure logs")

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

    try:
        result = call_llm(system_prompt, user_message)
    except Exception as e:
        err = str(e)
        if any(kw in err.lower() for kw in ["credit", "rate_limit", "quota", "billing", "payment"]):
            print(f"Skipping auto-fix: API issue — {err[:200]}")
            return 0
        raise

    diagnosis = result["text"]
    files_modified = result["files_modified"]

    print(f"\n{'='*60}")
    print("DIAGNOSIS:")
    print(diagnosis)
    print(f"\nFiles modified: {files_modified}")
    print(f"{'='*60}")

    if files_modified:
        pr_url = create_fix_pr(files_modified, diagnosis, run_id)
        if pr_url:
            print(f"\nFix PR created: {pr_url}")
        return 0
    else:
        print("\nNo automated fix possible. Creating issue instead.")
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
