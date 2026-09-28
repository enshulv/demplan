"""Check that an sdist contains every file its metadata names as a License-File.

PyPI rejects an sdist whose PKG-INFO lists a License-File the archive lacks, and it does so
only at upload time. Run this on the built sdist before publishing:

    python tools/check_sdist.py dist/demplan-0.1.0.tar.gz
"""
import sys
import tarfile


def missing_license_files(path):
    with tarfile.open(path) as archive:
        names = set(archive.getnames())
        root = path.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".tar.gz")
        metadata = archive.extractfile(f"{root}/PKG-INFO").read().decode("utf-8")
    declared = [
        line.split(":", 1)[1].strip()
        for line in metadata.splitlines()
        if line.startswith("License-File:")
    ]
    return [name for name in declared if f"{root}/{name}" not in names]


def main(paths):
    failed = False
    for path in paths:
        missing = missing_license_files(path)
        for name in missing:
            print(f"{path}: License-File {name} is declared but not in the archive")
        failed = failed or bool(missing)
    if not paths:
        print("usage: check_sdist.py SDIST...")
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
