"""Copy the kit to an explicitly selected project; dry-run unless --apply."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ("agent-kit", ".agents/skills", ".github/agents", ".github/skills", ".codex/agents")
SINGLES = ("AGENTS.md", ".github/copilot-instructions.md")


def plan(target):
    target = target.resolve()
    if target == ROOT or target in (Path.home(), Path("/")):
        raise ValueError("Select a separate project directory, not the kit root/home/filesystem root")
    if not target.is_dir():
        raise ValueError("Target must be an existing project directory")
    source_files = [ROOT / p for p in SINGLES]
    for directory in DIRECTORIES:
        source_files += sorted(p for p in (ROOT / directory).rglob("*") if p.is_file())
    copies = []
    conflicts = []
    for source in source_files:
        relative = source.relative_to(ROOT)
        destination = target / relative
        # Do not follow a symlink into an unrelated directory, including dangling symlinks.
        chain = [destination] + list(destination.parents)
        if any(p.is_symlink() for p in chain if p != target.parent and p != target):
            raise ValueError(f"Symlink destination not supported: {relative}")
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != source.read_bytes():
                conflicts.append(str(relative))
        else:
            copies.append((source, destination))
    if conflicts:
        raise ValueError("Conflicts; nothing copied. Merge manually: " + ", ".join(conflicts))
    return copies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        copies = plan(args.target)
    except ValueError as error:
        parser.error(str(error))
    for source, destination in copies:
        print(f"{'COPY' if args.apply else 'PLAN'} {source.relative_to(ROOT)}")
        if args.apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive create; a concurrent edit is never overwritten.
            with destination.open("xb") as stream:
                stream.write(source.read_bytes())
    print(f"{len(copies)} files {'copied' if args.apply else 'planned; use --apply after review'}")


if __name__ == "__main__":
    main()
