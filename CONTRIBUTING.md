# Contributing

1. Read [BUILD.md](BUILD.md) and [the application licence](LICENSE).
2. Reproduce the problem with synthetic text. Include version, direction, engine selection, expected meaning and actual output.
3. Make a focused change. Keep source text, cancellation, data recovery and language identity intact.
4. Run `--self-test`. For a provider/voice change, add a targeted test and record the actual live check separately.
5. Open a pull request explaining the behavior change, validation and remaining limits.

Do not commit conversations, credentials, recordings, model weights, native executables, generated test reports or release ZIPs. Preserve third-party licences and provenance. Contributions to original Gray Feather code are submitted under the project's PolyForm Noncommercial 1.0.0 terms; identify any third-party material explicitly.

Avoid broad language-ranking claims from a few examples. An error report should distinguish source ambiguity, translation error, incomplete output and provider failure.
