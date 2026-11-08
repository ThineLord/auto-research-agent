# Local pipeline performance

Date: 2026-10-15 (Asia/Hong_Kong)

This change removes repeated local work from artifact boundary lookup, log polling, workspace
loading, run analysis, and round evolution metrics. Model stages retain their existing dependency
order.

## Reproduce

```sh
make performance ARGS="--repeats 5"
make check
```

The benchmark creates temporary synthetic inputs and compares the current implementation with
the original algorithms, asserting identical output for each case. It reports median timings
without allocation tracing, then measures peak Python allocations separately. It reads no local
configuration or research artifacts and makes no provider calls.

## Measured local hot paths

Observed with Python 3.13.15 on macOS. These measurements describe these synthetic cases only;
they do not establish end-to-end research or model throughput.

| Case | Original median | Optimized median | Original peak Python allocation | Optimized peak |
| --- | ---: | ---: | ---: | ---: |
| 12,700,000-byte log, last 120 lines | 21.714 ms | 0.067 ms | 54,001,045 B | 112,133 B |
| Identical round outputs, 66,000 characters each | 64.366 ms | 1.587 ms | 2,535,956 B | 585,553 B |

Log reads grow with the requested suffix rather than total history. A regression fixture with
120 short current lines reads 8,192 bytes regardless of whether it has 1,000 or 100,000 historical
lines. Long lines or insufficient lines can still require the entire file. Identical metrics
return the same values directly; changed text continues through the existing difflib algorithms.

## Repeated work removed

| Operation per request | Original | Optimized |
| --- | ---: | ---: |
| Workspace checkpoint load in the server | 2 | 1 |
| Model discovery/profile artifact loads, each | 4 | 1 |
| Model candidate pool construction | 4 | 1 |
| Run-analysis metrics read and JSON decode, each | 2 | 1 |

These counts are enforced by regression tests. Analysis now uses the same metrics entries for
its summary and trend, avoiding disagreement if that file changes between two reads. Both
analysis and workspace loading read fresh artifacts on the next request; there is no persistent
artifact cache.

Boundary lookup now walks path ancestors through an index instead of scanning all registered
projects and runs. A regression checks four dictionary probes for the same run artifact among
2,000 registered projects. Randomized registration orders compare inheritance, descendant
rebasing, repeated registration, and lookup with the original rules; published snapshots remain
unchanged when later registrations occur.

## Behavior and safety

Positive log limits validate UTF-8 only in the inspected suffix. Malformed bytes in unread old
history no longer hide valid current lines; malformed bytes in the inspected suffix still return
an empty log view. Unicode line separators, CRLF, long lines, missing files, and the previous
nonpositive-limit slicing behavior are covered by tests.

Log access retains anchored descriptor traversal, no-follow opens, regular-file and single-link
checks, and file-identity validation. Analysis still checks pending/conflicting transactions
before artifact reads. Tests exercise unsafe paths, file replacement, malformed journals, output
equivalence, request freshness, and the reduction in reads. All fixtures are synthetic.

## Validation

The final `PYTEST_ADDOPTS="-o faulthandler_timeout=30" make check` passed: 613 tests and 1,669
subtests, plus Ruff formatting/lint, import smoke, and tracked/index safety scans. The timeout
option enables diagnostic stack dumps rather than skipping or terminating tests. One warning
comes from the existing fork-based lock test running in a multithreaded process.

The six newly added files also passed an explicit safety scan, since the tracked-file gate does
not include untracked additions. `git diff --check` passed. Earlier full-suite attempts were
manually interrupted while investigating path traversal cost; they are not recorded as successful
baselines. No real-provider or end-to-end model throughput benchmark was run.
