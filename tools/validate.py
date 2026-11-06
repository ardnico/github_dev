"""Static integrity checks; this is not a live Copilot/Codex acceptance test."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"Missing header: {path}"
    return text.split("---\n", 2)[1]


def validate(root=ROOT):
    catalog = json.loads((root / "agent-kit/catalog.json").read_text(encoding="utf-8"))
    roles = catalog["roles"]
    ids = [role["id"] for role in roles]
    assert len(ids) == len(set(ids)), "Duplicate role ID"
    assert sum(role["parent"] for role in roles) == 3
    assert len(roles) == 5
    for role in roles:
        role_id = role["id"]
        assert re.fullmatch(r"[a-z0-9-]+", role_id)
        path = root / f".github/agents/{role_id}.agent.md"
        # Generated YAML deliberately uses JSON scalar/array syntax.
        header = dict((key, json.loads(value.strip())) for key, value in
                      (line.split(":", 1) for line in frontmatter(path).splitlines() if line))
        assert header["name"] == role_id
        assert header["target"] == "github-copilot"
        assert header["user-invocable"] == role["parent"]
        assert header["disable-model-invocation"] == role["parent"]
        assert "model" not in header, "Default must inherit host model"
        assert "agents" not in header, "Local-only field in Copilot adapter"
        assert ("agent" in header["tools"]) == role["parent"]
        if not role["parent"]:
            assert not {"edit", "execute", "agent"}.intersection(header["tools"])
            config = tomllib.loads((root / f".codex/agents/{role_id}.toml").read_text(encoding="utf-8"))
            assert config["name"] == role_id and config["developer_instructions"]
            assert config["features"]["shell_tool"] is False
            assert not {"sandbox_mode", "approval_policy", "mcp_servers", "model_provider"}.intersection(config)
    for path in (root / ".agents/skills").glob("*/SKILL.md"):
        header = frontmatter(path)
        fields = dict(line.split(":", 1) for line in header.splitlines() if line)
        assert set(fields) == {"name", "description"}
        assert fields["name"].strip() == path.parent.name
        assert re.fullmatch(r"[a-z0-9-]{1,64}", path.parent.name)
        assert 0 < len(fields["description"].strip()) <= 1024
        assert (root / ".github/skills" / path.parent.name / "SKILL.md").read_bytes() == path.read_bytes()
    policy = json.loads((root / "agent-kit/model-policy.json").read_text(encoding="utf-8"))
    assert policy["automatic_routing_implemented"] is False
    assert policy["mode"] == "host-selected"
    return len(roles)


if __name__ == "__main__":
    try:
        count = validate()
        subprocess.run([sys.executable, str(ROOT / "tools/render.py"), "--check"], check=True)
        print(f"PASS: {count} roles, adapter syntax, skill mirrors, model policy")
    except (AssertionError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
