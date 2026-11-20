---
name: ask-jev
description: Ask Jev typed noul/choice/score questions about files, a command's output, or your own state through ask_jev_files.py; answers are numbers to branch on. Use before a judgment call.
---

# ask-jev

Ask Jev, a fast decision model, typed questions about one situation: files, a command's output, your own state, or any mix. It answers in about 300 ms for a fraction of a cent, and each answer is a number you can branch on, not prose. Use it whenever a judgment call would otherwise cost you a long think.

Do not paste content you already have; that costs output tokens. Pass `--paths` and the script reads the files into `files["path"]`. Pass `--command` and the script runs it in the repo and puts the result into `output` {command, exit_code, stdout, stderr}. Use `--state` for what only you can say: a customer report, your plan, a line of context. Plain text or a JSON object as a string; your field names are kept as is. You can combine all three, and you never receive the files or the output, only the answers.

## Commands

Run from the repo you are judging. `with_jev_key.sh` loads the Jev key in any repo.

```text
bash /home/alex/Projects/JevDev/with_jev_key.sh python3 /home/alex/Projects/JevDev/ask_jev_files.py <subcommand> ...
```

```text
ask_jev_files.py files [-r] -q QUESTIONS_JSON PATH_OR_GLOB...
ask_jev_files.py pick  -q QUESTION_TEXT PATH...
ask_jev_files.py ask   -q QUESTIONS_JSON [--state TEXT] [--paths P...] [--command CMD]
```

For a recursive-then-pick flow, run `files -r -q '<a noul>' .`, keep the paths whose `noul` is above your own bar, then run `pick -q '<question>' <those paths>` to choose one. `pick` does no expansion or recursion of its own.

One call judges one situation: up to 20 files and about 60k tokens in total. Over that the call is refused with a message naming the parts and a split that fits; make two calls with the same questions_json. For many files judged separately use `files`.

## Question types

questions_json: a JSON object keyed by question id. Three types:

```text
  noul   {"type":"noul","instructions":"Is `output` a real failure rather than a flaky one?","criteria":{"true":"...","false":"..."}}  -> { noul: 0..1 }
  choice {"type":"choice","instructions":"What kind of failure is `output`?","criteria":{"bug_in_code":"...","wrong_test":"...","environment":"...","other":"..."}}  -> { choice, confidence, probabilities }
  score  {"type":"score","instructions":"How risky is `diff`?","criteria":["Isolated, tested","Some callers","Security sensitive, no tests"]}  -> { score, confidence, legend }
```

Write questions against `files["path"]`, `output`, or your own field names.

## Recipes

Triage a failure: run the tests through `--command` and classify the failure before choosing a fix.

```bash
bash /home/alex/Projects/JevDev/with_jev_key.sh python3 /home/alex/Projects/JevDev/ask_jev_files.py ask --command 'python3 tests/test_sentinel.py' -q '{"kind":{"type":"choice","instructions":"What kind of failure is `output`?","criteria":{"bug_in_code":"The code under test misbehaves","wrong_test":"The test asserts the wrong expectation","environment":"A missing dependency, key, file, or service","none":"The run passed","other":"Something else"}},"flaky":{"type":"noul","instructions":"Is `output` a real failure rather than a flaky one?","criteria":{"true":"Deterministic assertion or error text","false":"Timeouts, network, or ordering that could pass on retry"}}}'
```

Judge a diff: put `git diff` through `--command` and score its risk before committing.

```bash
bash /home/alex/Projects/JevDev/with_jev_key.sh python3 /home/alex/Projects/JevDev/ask_jev_files.py ask --command 'git diff' -q '{"risk":{"type":"score","instructions":"How risky is `output`?","criteria":["Isolated, tested","Some callers","Security sensitive, no tests"]},"needs_review":{"type":"noul","instructions":"Should a human review this diff before it ships?","criteria":{"true":"Touches auth, money, deletion, or untested paths","false":"Local, covered by tests, easy to revert"}}}'
```

Classify a request: pass the customer's words as `--state` with the relevant paths and decide bug or expected.

```bash
bash /home/alex/Projects/JevDev/with_jev_key.sh python3 /home/alex/Projects/JevDev/ask_jev_files.py ask --state 'A customer wrote in: every time I click Export on the invoices page I get an error and no file downloads.' --paths scope_sentinel.py README.md -q '{"kind":{"type":"choice","instructions":"What kind of request is `text`?","criteria":{"bug":"Something that should work is broken","expected_behavior":"The product works as designed","config_change":"A setting or environment change fixes it","code_change":"A new or changed feature is needed","product_decision":"A policy or design call is needed first","other":"Something else"}},"clear_enough":{"type":"noul","instructions":"Is `text` clear enough to plan without asking a question first?","criteria":{"true":"A concrete symptom or change with the affected area named","false":"Missing the what, where, or why"}}}'
```

## Rules

Ask every question you might need in one call; they share the state. Always give a choice an `other` option. Describe situations, not degrees.

Not for: exact lookups, counting, math, or anything a grep answers. Not a substitute for reading code you need to edit.
