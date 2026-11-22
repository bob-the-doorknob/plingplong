# Selection and scheduling

The source of truth is SQLGlot revision eb11aec4be8cb2122afe713a4816662c3f0fb2fa and the starter test catalog. The offline collector runs the locked pytest environment in the organizer Python 3.13 image with SKIP_INTEGRATION=0. Numeric test numbers are resolved from the incoming manifest. Any difference in the sorted test identities triggers full-suite scheduling.

## Evidence

The collector observes Python code-object entries (qualified names) and file opens under sqlglot and tests/fixtures. It groups setup/teardown and child interpreters by test file. Import initialization enters a shared context, including code called by lazy imports. Shared observations require a full selection for the affected scope or file. Process launches with uncertain attribution retain their parent tests. Function entry covers either side of a branch inside an entered function. Collection uses the original source only.

Forward and reverse runs contribute observations. The packer checks all catalog identities, the exact pinned tar and actual test outcomes. Every numbered test must pass in organizer order. Tests failing in reverse order are included on every narrowed patch. Static import extraction from impact.py adds test-module importers and tests using those test helpers. Missing or dynamic edges never remove observations. Global incompleteness in the standalone static selector has no pruning authority.

## Production

hybrid.py validates same-path Git text hunks against the original stored bytes decoded as UTF-8. semantic.py splits every function and lambda body into its own scope, keyed by the qualified name CPython gives its code object (`f.<locals>.g`, `C.<lambda>`). Inner bodies are split first, so an outer body keeps only its own statements plus placeholders. Decorators, defaults, annotations and bases stay in the enclosing body. A skeleton retains class and module statements, signatures, docstrings and generator status. Lambdas sharing a qualified name share evidence, which covers all of them. Comprehensions, generator expressions and module or class level compound statements are not split. A nested scope present on one side only is reached through its changed parent, so the parent's evidence covers it. Body changes select the union of observed entries, file readers, static test importers and uncertain tests. Existing SQL fixture edits select file readers plus uncertain tests. An edited fixture line that contains a block-comment delimiter falls back. Otherwise the delimiter sequence is unchanged, block and line comments are removed from both versions, and an edit that leaves the rest equal is a comment-only edit that falls back. A sqlglot Python file whose ast.dump is unchanged, such as a comment or layout edit, compiles to the same code apart from line numbers. It selects only the tests that read it as text (hits[path], recorded from open audit events through read_text, inspect or linecache) plus untraced tests. Imports open only the precompiled .pyc in shared context, so they never appear in hits[path]. Such a file does not force a full fallback of a multi-file patch. A patch made only of such files may select nothing. A shared reader, a failed reconstruction or coding[:=] on line 1 or 2 of either version selects the entire suite. Unobserved scopes, ambiguous definitions, structural edits, textual changes, unknown paths, invalid code and unsupported patch forms select the entire suite. Multi-file changes union candidates, with a full fallback dominating the union.

selector.py emits one compact JSON line per patch and writes diagnostics to stderr. LPT sorts descending rounded milliseconds, tries one through eight workers and selects the least costly schedule. The full-suite assignment is cached. No incoming code executes. The submission contains neither public failure labels nor a patch lookup table.

Finite traces can miss reflective code inspection, cached initialization, native operations, indirect file reads, directory enumeration or cross-process behavior. The two independent full-suite mutations exercise function and fixture selection. They do not establish hidden-case recall.

## Class attributes and import-time state

Phase 8 records defining and receiving classes, import consumers, runtime writes,
and a cache-writer flag. The selector closes over downstream holders and
subclasses. Phase 9 keeps each import edge's source attribute. In the pinned
SQLGlot source, Expr.__init_subclass__ derives key from the class name and
required_args separately from arg_types. EXPR_CLASSES registers the same class
under that key. An isolated boolean toggle in the literal arg_types mapping of
a plain, direct, observed leaf Expression class can therefore ignore the module
read of its unchanged key. The selector still follows import consumers of
arg_types, required_args and other attributes. Changed dictionary keys, dynamic
computation, mixed edits, subclasses and unresolved dependencies retain the
ordinary fallback rules.

The cache snapshot detects reassignment and container size changes. It can miss
same-size replacements and nested mutations. The rule above makes no claim
about the equivalence of mutable containers. General import instrumentation
would need source-attributed readers for the changed state, including lazy
imports and cached aliases. The existing offline traces also retain uncertainty
around source read caches and child processes.

## Phase 10 precision and process attribution

The optional line map is tied to the pinned evidence digest and organizer IDs.
It uses the original span for supported literal, operator, and Boolean
regrouping edits. Unmapped or shared spans keep function coverage. Spawned pool
tasks carry the submitting test ID, and setup and teardown stay file-wide.
The comparison map records agreement for native identity and equality operators
in both suite orders. Unknown values, shared reads, and other semantic edits
keep the ordinary candidates. The tokenizer radix and week-offset rules are
limited to the audited value readers present at the pinned revision.

A direct Python subprocess footprint can narrow its historical blanket
selection. The collector requires successful exit, matching launch and startup
metadata, complete records in both orders, and audited file reads covering
every independently observed child execution path. The selector keeps the guard
if any changed file intersects the footprint. Other evidence can still select
the same test. Tests that failed in reverse order retain their safety selection.
