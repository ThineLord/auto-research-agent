# Optional Project Memory

Use this optional file for stable context that should be available in every run, such as:

- Domain constraints
- Citation conventions
- Preferred output structure
- Known assumptions

To use it locally, copy this file to `memory.md`:

```bash
cp projects/example/memory.example.md projects/example/memory.md
```

`memory.md` is ignored by Git because the application can update it with run-specific state.
