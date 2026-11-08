# Documentation claim auditor

Version 0.1.0. An offline, deterministic, standard-library-only checker for
claims about assigning one category label to a whole clip. Requires Python
3.9 or newer. No LLM, network access, telemetry, or filesystem writes.

## Install and run

```sh
python3 -m pip install .
audio-classification-claim-audit --version
python3 -m audio_classification_claim_audit --help
audio-classification-claim-audit audit . --json
audio-classification-claim-audit audit --ignore tests/ . --fail-on medium
```

The repository defaults to the current directory. Repeat the single-value
ignore option to skip relative path prefixes. Verbose mode reports scope and
per-file decisions on standard error. JSON output is an array of findings,
each containing rule, severity, verdict, and message. Exit status is 0 when
no finding reaches the threshold, 2 when one does, and 1 for usage or IO errors.
The default threshold is high; medium also fails test-only findings.

## Scope and rules

The checker reads the root README and Markdown files recursively under docs.
Triple-backtick fenced blocks are excluded; inline backticks retain their
contents as prose. Test fixtures under a tests directory can produce medium
findings when shipped documentation contains no positive claim. Each family
produces at most one finding. A denial without source evidence passes.

```text
documented-audio-classification-claim-false (HIGH; test-only: MEDIUM)
documented-no-audio-classification-claim-false (HIGH)
```

Source inspection covers Python modules recursively, excluding Git metadata,
bytecode caches, and virtual environments. Each evidence route must be
complete within one module. Imports and aliases are resolved; local function
and class definitions shadow route names throughout that module. A pipeline
or dedicated model must be constructed and called. Generic method calls or
imported function calls can also provide evidence. Mere imports, references,
comments, strings, and external command invocations do not provide evidence.

## Differentiation

These neighboring tools cover different capabilities, respectively:

```text
sound-event-detection-claim-audit
speech-emotion-recognition-claim-audit
genre-classification-claim-audit
speech-recognition-claim-audit
```

The first finds events with timestamps inside a recording, whereas this tool
checks assigning one label to a whole clip. The second labels a speaker's
feeling, whereas the checked feature concerns arbitrary audio. The third
names a music track's style, whereas the checked feature concerns arbitrary
audio. The fourth turns speech into words, whereas this tool checks assigning
a label to a clip. Event detection calls deliberately do not count: finding
events with timestamps does not assign one label to a whole clip. Emotion,
genre, instrument, keyword, transcription, loading, and fingerprinting calls
alone also do not count.

## Limitations

This is static pattern matching, not semantic judgement or runtime validation.
Only exact phrases match, case-insensitively; restatements do not. Hyphens are
not normalized. Denial spans are removed first. Longest-first matching blanks
matched spans, so each occurrence matches once under its longest phrase.

The following phrases can also describe sorting sound files by hand, a school
exercise, and a person who sorts recordings, respectively. Those ordinary
uses still match; the checker cannot infer the intended meaning.

```text
classify audio files by date
sound classification worksheet
our audio classifier reviews every clip
```

An unrelated object's method with the following shared name counts via the
generic route. This can produce false evidence. Dynamic dispatch, wrappers,
inter-module construction/call pairs, and unsupported naming patterns can
produce missed evidence. Invalid Python is skipped with a verbose diagnostic.

```python
unrelated.classify_audio(data)
```

## Development

```sh
python3 -m unittest discover
python3 -m build
```

The source distribution includes the discoverable test suite. Licensed under MIT.
