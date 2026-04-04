# md/

Working documents for the Crate project. Three subdirectories, each with a distinct purpose.

---

## plans/

Named `plan-<topic>.md`. Implementation plans handed to Claude Code to execute and build.

Each file is a self-contained brief: what to build, in what order, with enough detail
that Claude can complete the task without further clarification.

## prompts/

Named `prompt-<output-filename>.md` (e.g. `prompt-research-essentia.md`). Prompts handed to Claude to produce research documents or plans.

Use these when you need Claude to write a new `research/` or `plans/` file.
The prompt is the input; the resulting `.md` is the output.

## research/

Named `research-<topic>.md`. Research outputs documenting what each data source or tool actually returns.

These are the source of truth for field names, data types, units, and caveats.
The database schema and import pipeline are derived from these documents —
do not assume a field exists until it is confirmed here.

---

## Other files

- `new-machine-setup.md` — steps to get a new dev machine running the project
