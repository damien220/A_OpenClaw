"""Shell exec skill — run allowlisted commands and return their output."""

import shlex
import subprocess
from pathlib import Path

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_TIMEOUT = 30
_MAX_OUTPUT_CHARS = 8_000


class ShellExecSkill(BaseSkill):
    name = "shell_exec"
    description = (
        "Run a command and return its output. Only program names listed in "
        "the [shell] allowlist in config.toml may run. The command is never "
        "passed through a shell, so operators like pipes, redirects, `&&`, "
        "or backticks are treated as literal arguments, not interpreted."
    )
    parameters = {
        "command": "The command to run, e.g. 'git status' or 'ls -la notes/'.",
        "cwd": "Optional working directory, relative to the project root.",
    }

    def execute(self, params: dict, context: dict) -> str:
        command = params.get("command", "").strip()
        if not command:
            return "[shell_exec: no command provided]"

        shell_config = context.get("config", {}).get("shell", {})
        allowlist = set(shell_config.get("allowlist", []))
        timeout = shell_config.get("timeout_seconds", _DEFAULT_TIMEOUT)

        if not allowlist:
            return "[shell_exec: no commands are allowlisted — set [shell] allowlist in config.toml]"

        try:
            argv = shlex.split(command)
        except ValueError as e:
            return f"[shell_exec: could not parse command — {e}]"

        if not argv:
            return "[shell_exec: no command provided]"

        program = argv[0]
        if program not in allowlist:
            logger.warning("Blocked non-allowlisted command", extra={"program": program})
            return (
                f"[shell_exec: '{program}' is not in the allowlist. "
                f"Allowed: {', '.join(sorted(allowlist))}]"
            )

        cwd = self._resolve_cwd(params.get("cwd", "").strip())
        if cwd is None:
            return "[shell_exec: cwd is outside the project directory]"

        try:
            result = subprocess.run(
                argv,
                cwd=cwd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out", extra={"command": command, "timeout": timeout})
            return f"[shell_exec: command timed out after {timeout}s]"
        except OSError as e:
            return f"[shell_exec: failed to run command — {e}]"

        logger.info("Command executed", extra={"program": program, "returncode": result.returncode})

        output = (result.stdout or "") + (result.stderr or "")
        output = output.strip() or "(no output)"
        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + "\n...[truncated]"

        return f"### $ {command}\nExit code: {result.returncode}\n\n{output}"

    @staticmethod
    def _resolve_cwd(rel_path: str) -> Path | None:
        if not rel_path:
            return _PROJECT_ROOT
        try:
            target = (_PROJECT_ROOT / rel_path).resolve()
            target.relative_to(_PROJECT_ROOT.resolve())
        except (ValueError, RuntimeError):
            return None
        return target if target.is_dir() else None
