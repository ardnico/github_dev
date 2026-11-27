"""Resolve a rootfs path using explicitly selected local Yocto build evidence."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

from run import digest, source_file

PACKAGE_NAME = r"[a-zA-Z0-9_.+][a-zA-Z0-9_.+-]*"


def absolute(value, directory=False):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"Absolute path required: {value}")
    path = path.resolve(strict=True)
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"Wrong evidence file type: {value}")
    return path


def file_evidence(path):
    return {"path": str(path), "sha256": digest(path)}


def resolve(project, build, image, manifest, pkgdata, target, tool="oe-pkgdata-util",
            rootfs=None, patched_root=None, source_files=(), kernel_config=None, build_capture=None,
            build_metadata=None):
    project, build, pkgdata = (absolute(p, directory=True) for p in (project, build, pkgdata))
    image, manifest = map(absolute, (image, manifest))
    path = PurePosixPath(target)
    if (path.root != "/" or not path.name or ".." in path.parts or str(path) != target
            or any(char in target for char in "*?[]\n\r\t")):
        raise ValueError("Specify one exact absolute rootfs path; no globs")
    if not Path(tool).is_absolute() and tool != "oe-pkgdata-util":
        raise ValueError("Custom oe-pkgdata-util must use a trusted absolute executable path")
    calls = []

    def query(command, value):
        result = subprocess.run([tool, "-p", str(pkgdata), command, value],
                                cwd=build, capture_output=True, text=True, timeout=30)
        calls.append({"query": command, "argument": value, "returncode": result.returncode,
                      "stdout": result.stdout, "stderr": result.stderr})
        return result.stdout if result.returncode == 0 else ""

    installed = {}
    for row in manifest.read_text(encoding="utf-8").splitlines():
        fields = row.split()
        if fields:
            if len(fields) != 3:
                raise ValueError("Expected image manifest rows: package architecture version")
            installed.setdefault(fields[0], []).append(fields[1:])
    recipe_packages = set()
    for row in query("find-path", target).splitlines():
        name, sep, found = row.partition(":")
        if sep and found.strip() == target and re.fullmatch(PACKAGE_NAME, name.strip()):
            recipe_packages.add(name.strip())
    mappings = {}
    for name in sorted(recipe_packages):
        names = query("lookup-pkg", name).splitlines()
        mappings[name] = names[0].strip() if len(names) == 1 and re.fullmatch(PACKAGE_NAME, names[0].strip()) else None
    owners = [(name, runtime) for name, runtime in mappings.items() if runtime in installed]
    candidates = {runtime for _, runtime in owners}
    recipe, package = None, None
    recipe_package = None
    status = "package-unresolved"
    if len(owners) > 1 or any(len(set(map(tuple, installed[name]))) != 1 for name in candidates):
        status = "package-ambiguous"
    elif None in mappings.values():
        status = "package-name-unresolved"
    elif owners:
        recipe_package, package = owners[0]
        names = query("lookup-recipe", package).splitlines()
        # oe-pkgdata-util versions emit a recipe name or 'package: recipe'.
        if len(names) == 1:
            left, sep, right = names[0].partition(":")
            name = (right if sep and left == package else names[0]).strip()
            if re.fullmatch(PACKAGE_NAME, name):
                recipe = name
        status = "recipe-candidate" if recipe else "recipe-unresolved"
    if bool(patched_root) != bool(source_files):
        raise ValueError("Specify patched_root and one or more source files together")
    sources = {}
    if patched_root:
        patched_root = absolute(patched_root, directory=True)
        sources = {name: file_evidence(source_file(patched_root, name)) for name in source_files}
    rootfs_file = None
    if rootfs:
        rootfs = absolute(rootfs, directory=True)
        rootfs_file = file_evidence(source_file(rootfs, target[1:]))
    evidence = {
        "schema_version": 1, "status": status, "project_dir": str(project), "build_dir": str(build),
        "image": file_evidence(image), "image_manifest": file_evidence(manifest), "pkgdata_dir": str(pkgdata),
        "target": target, "rootfs_file": rootfs_file, "installed_owner_candidates": sorted(candidates),
        "package": package, "recipe_package": recipe_package, "package_name_mappings": mappings,
        "package_versions": installed.get(package, []), "recipe": recipe,
        "candidate_sources": sources, "kernel_config": file_evidence(absolute(kernel_config)) if kernel_config else None,
        "build_metadata": file_evidence(absolute(build_metadata)) if build_metadata else None,
        "queries": calls, "provenance": "unverified",
        "limitations": ["Image/manifest/pkgdata/rootfs/source build association is not established by paths or hashes alone.",
                        "A package path match is not proof the file survived image postprocessing.",
                        "Source files are caller-selected candidates, not inferred compiler inputs."],
    }
    if build_capture:
        capture = absolute(build_capture)
        # Hash the exact bytes read instead of a subsequent version of the file.
        contents = capture.read_bytes()
        previous = json.loads(contents)

        def identity(item):
            if item.get("schema_version") != 1 or item.get("status") != "recipe-candidate" or not item.get("candidate_sources"):
                raise ValueError("Build capture needs a resolved recipe and recorded source hashes")
            fixed = ("target", "package", "package_versions", "recipe")
            files = ("image", "image_manifest", "rootfs_file", "kernel_config", "build_metadata")
            return ([item[key] for key in fixed], [(item.get(key) or {}).get("sha256") for key in files],
                    {name: src["sha256"] for name, src in item["candidate_sources"].items()})

        expected = identity(previous)
        comparable = (evidence["status"] == "recipe-candidate" and bool(sources)
                      and previous.get("recipe_package") in (None, recipe_package))
        evidence["build_capture"] = {"path": str(capture), "sha256": sha256(contents).hexdigest()}
        evidence["provenance"] = "matches-build-capture" if comparable and identity(evidence) == expected else "build-capture-mismatch"
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("project", "build", "image", "manifest", "pkgdata", "target"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--tool", default="oe-pkgdata-util")
    parser.add_argument("--rootfs", help="Optional prepared rootfs; this tool does not mount an image")
    parser.add_argument("--patched-root")
    parser.add_argument("--source-file", dest="source_files", action="append", default=[])
    parser.add_argument("--kernel-config")
    parser.add_argument("--build-metadata", help="Optional release metadata file to hash (recipe, revisions, patch order, configuration)")
    parser.add_argument("--build-capture", help="Compare with a trusted record saved at build/release time")
    args = parser.parse_args()
    try:
        print(json.dumps(resolve(**vars(args)), ensure_ascii=False, indent=2))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
