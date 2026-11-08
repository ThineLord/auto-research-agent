# Release dependency constraints

`constraints.txt` pins the runtime and development dependency graph for this release, with Python/platform markers for supported variants. `make install`, `make install-dev`, isolated wheel checks and CI use it. It is a pip constraints file, not a declaration that all listed packages must be installed. Browser tooling is optional.

```bash
python -m pip install -c scripts/dependencies/constraints.txt -e '.[dev,browser]'
```

The baseline retains the locally tested dependency versions. Python 3.10 and 3.13 are checked in CI; Chromium and WebKit use Python 3.13. Other Python versions/platforms are not release-tested. The file fixes package versions, not artifact hashes or a complete OS image.

Maintainers can resolve a candidate with `uv 0.13.7`:

```bash
uv pip compile pyproject.toml --extra dev --extra browser --universal --python-version 3.10 --constraint scripts/dependencies/constraints.txt --no-annotate --no-header -o /tmp/ara-constraints-candidate.txt
```

Review the diff, run the full Python/browser and wheel checks, then update the constraints in a reviewed versioned PR. Removing a constraint for an intentional dependency upgrade is a separate reviewable change. Runtime records contain actual installed versions; a constraints fingerprint alone does not prove the environment matches it.
