# Project Memory

Use this optional file for stable context that should be available in every run, such as:

- domain constraints
- citation conventions
- preferred output structure
- known assumptions

When you want a local memory file, copy this template:

```bash
cp projects/pama/memory.example.md <PROJECT_MEMORY_FILE>
```

`memory.md` is ignored by Git because the application can update it with run-specific state.
