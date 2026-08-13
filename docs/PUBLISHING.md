# Publishing DeepTrap

DeepTrap is published to PyPI as `deeptrap`. The installed command is also
`deeptrap`. Existing ActBench result schema names and direct source scripts are
retained for compatibility, but the wheel does not export an `actbench` command
that would conflict with the unrelated package already using that PyPI name.

## One-time PyPI setup

1. Create the `deeptrap` project on PyPI with an initial upload, or let the first
   trusted-publisher release create it.
2. In the PyPI project settings, add a GitHub trusted publisher for:
   - owner: `ZJUICSR`
   - repository: `ActBench`
   - workflow: `publish.yml`
   - environment: `pypi`
3. Create a protected `pypi` environment in the GitHub repository. Requiring a
   reviewer is recommended.

No long-lived PyPI API token is required by the release workflow.

## Release process

1. Update `version` in `pyproject.toml` and `__version__` in
   `deeptrap/__init__.py` to the same value.
2. Run the local release checks:

   ```bash
   uv run --extra dev pytest -q
   uv build
   uvx --from twine twine check dist/*
   ```

3. Commit the version change and create a GitHub release whose tag is exactly
   `v<version>`, for example `v0.1.0`.

Publishing the GitHub release triggers `.github/workflows/publish.yml`. The
workflow checks that the tag matches the package version, runs the test suite,
builds both distributions, installs the wheel in an isolated environment, runs
`deeptrap test --self-test`, and then publishes through PyPI trusted publishing.

## TestPyPI dry run

For a manual pre-release check, upload the already validated artifacts to
TestPyPI rather than rebuilding them:

```bash
uvx twine upload --repository testpypi dist/*
```

Never commit repository tokens or local provider configuration.
