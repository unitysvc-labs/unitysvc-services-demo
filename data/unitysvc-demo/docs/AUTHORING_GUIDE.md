# Authoring Code Examples for Services

A practical checklist for writing `*.j2` code examples that (a) pass
`usvc_seller data run-tests` against the real upstream, and (b) render
into accurate customer-facing documentation when the listing is published.

This guide distills the design in
`unitysvc-bridge-uptime/docs/fix-local-testing-params.md` into
actionable rules. Read this first; reach for the design doc only if
the invariant below doesn't answer your question.

## The one invariant

> A code example must work correctly in **both** rendering modes:
>
> - `local_testing=True` — rendered by `usvc_seller data run-tests`
>   against the seller's upstream. Tests the service's raw upstream
>   contract.
>
> - `local_testing=False` — rendered for customers reading the
>   listing. Tests the gateway-routed contract.
>
> The two modes differ in *where inputs come from* (environment vars
> injected by the test harness vs. gateway-provided routing). If your
> template writes the same literals in both modes, something is wrong.

If you only remember one thing from this guide: **never hardcode a
request parameter, URL, or credential that the gateway is supposed to
inject at runtime.** Wrap it in `{% if local_testing %}` so the test
harness provides it in test mode and the customer-facing rendering
shows what the customer will actually write.

## File layout

All examples live under `data/<provider>/docs/`, never inlined in JSON.

```
data/unitysvc-demo/
├── docs/
│   ├── <service-or-family>/
│   │   ├── code-example.py.j2      # primary example customers see
│   │   ├── connectivity.sh.j2      # minimal smoke test
│   │   └── description.md          # optional: extra prose
│   └── <another-family>/
│       └── ...
└── services/<service>/
    ├── offering.json
    └── listing.json                # references docs via file_path
```

Filename conventions:

- `*.j2` — Jinja2-rendered template. Extension before `.j2` picks the
  code language (`.py.j2`, `.sh.j2`, `.ts.j2`, `.json.j2`).
- `connectivity.sh.j2` — convention for the minimal "does the pipe
  open" smoke test. Most services should have one.
- `code-example.*.j2` — convention for the primary example customers
  copy-paste.
- `description.md` — non-executable prose, shown on the listing page.

Put templates in a subdirectory named after the service family (not
the individual service); they're often shared across `byok`, `byoe`,
and base variants of the same service (see
`services/byoe/listing.json` and `services/byoe-params/listing.json`
both referencing `../../docs/connectivity.sh.j2`).

## Wiring a template into a listing

In the service's `listing.json`, add an entry to `documents`:

```json
{
  "documents": {
    "Connectivity test": {
      "category": "connectivity_test",
      "description": "Verify endpoint is reachable",
      "file_path": "../../docs/connectivity.sh.j2",
      "is_active": true,
      "is_public": false,
      "meta": { "output_contains": "connectivity ok" },
      "mime_type": "bash"
    },
    "Python example": {
      "category": "code_examples",
      "description": "Minimal boto3 client",
      "file_path": "../../docs/s3/code-example.py.j2",
      "is_active": true,
      "is_public": true,
      "meta": { "output_contains": "connectivity ok" },
      "mime_type": "python"
    }
  }
}
```

Key fields:

- `category` — `connectivity_test` for smoke tests, `code_examples`
  for customer-facing examples, `description` for prose.
- `is_public` — `false` keeps the example in the seller's dashboard
  only; `true` shows it on the public listing page.
- `meta.output_contains` — the test harness asserts the substring is
  present in stdout. **Case-sensitive** (see issue #52).
- `meta.expect.status_code` — for HTTP-response tests, assert a
  specific status (e.g., `200`).

## The `local_testing` pattern

### When to use it

Every time a value comes from one of the following, assume you need
to branch:

1. **Routing / URL**. Test mode has direct access to the upstream;
   customers hit `SERVICE_BASE_URL` (the gateway URL).
2. **Authentication credentials**. Test mode uses seller-provided
   creds from `ops_testing_parameters`; customers use their
   `UNITYSVC_API_KEY` plus any gateway-injected secrets.
3. **Request-body parameters**. Test mode may need to write
   hardcoded params directly into the request body to reach upstream;
   customers get those params injected by the gateway's routing
   layer and should not write them themselves.

### Canonical shape

```jinja
{% if local_testing %}
# Bypass the gateway — talk to upstream directly using seller creds.
BASE_URL=${UPSTREAM_TEST_URL}
API_KEY=${UPSTREAM_TEST_KEY}
{% else %}
# Customer-facing: go through the UnitySVC gateway.
BASE_URL=${SERVICE_BASE_URL}
API_KEY=${UNITYSVC_API_KEY}
{% endif %}
```

The `{% else %}` branch is **what your customer sees**. If that
branch is wrong or incomplete, no test will catch it — the bug
surfaces only in production. Read the `else` branch as carefully as
the code inside it.

### Real examples in this repo

- `docs/connectivity.sh.j2` — HTTP connectivity test. No
  `{% if local_testing %}` branch needed: `$SERVICE_BASE_URL` and
  `$UNITYSVC_API_KEY` work in both modes.
- `docs/s3/connectivity.sh.j2` — S3 connectivity test. Branches on
  env var presence (`$S3_ENDPOINT`+`$BUCKET` vs. `$SERVICE_BASE_URL`)
  rather than `local_testing`, since local tests construct the URL
  from individual fields while online mode gets the fully-qualified
  gateway URL.
- `docs/smtp/connectivity.sh.j2` — SMTP connectivity test. Same
  env-var-presence branching (`$HOST`+`$PORT` vs. parsing
  `$SERVICE_BASE_URL`).
- `docs/s3/code-example.py.j2` — full Python code example. Uses
  `{% if local_testing %}` because the request shape genuinely
  differs: test uses `$ACCESS_KEY`/`$SECRET_KEY` with `$S3_ENDPOINT`,
  while the customer-facing branch uses `$UNITYSVC_API_KEY` as the S3
  access key and parses the bucket from `$SERVICE_BASE_URL`.

Steal liberally from these when writing new ones.

## Context available inside a template

There are two separate mechanisms, and which one to use depends on
whether you need the value at **render time** (Jinja) or at
**runtime** (the shell/python process the harness spawns).

### Render-time: Jinja context

Every `.j2` file is processed by Jinja2 with these variables in scope
(see `unitysvc-sellers/src/unitysvc_sellers/utils.py:render_template_file`):

| Variable | What it holds | Common access patterns |
|---|---|---|
| `local_testing` | Boolean. `True` under `run-tests`, `False` on upload and customer-facing render. | `{% if local_testing %}` |
| `listing` | Full listing dict. | `listing.service_options.ops_testing_parameters.api_key_secret` |
| `offering` | Full offering dict. | `offering.service_type`, `offering.upstream_access_config` |
| `provider` | Provider metadata. | `provider.name`, `provider.display_name` |
| `seller` | Seller metadata. | `seller.name`, `seller.contact_email` |
| `interface` | The first upstream access interface dict. | `interface.get("access_key")`, `interface.base_url` |

Use Jinja context for values that need to be **baked into the rendered
output** (e.g., literal URLs embedded in a customer-facing example,
or conditional text that shouldn't appear at all in one branch).

### Runtime: environment variables

At test time the harness (`execute_script_content` in
`unitysvc-sellers/src/unitysvc_sellers/utils.py`) invokes the rendered
script as a subprocess with an environment derived from the selected
upstream access interface. The derivation rules (see
`example.py:514-527`) are:

| `upstream_access_config` field | Env var set for the test |
|---|---|
| `base_url` | `$SERVICE_BASE_URL` |
| `api_key` | `$UNITYSVC_API_KEY` |
| `routing_key` (dict) | Flattened — each sub-key uppercased (`{"model": "foo"}` → `$MODEL=foo`) |
| everything else | Field name uppercased (`s3_endpoint` → `$S3_ENDPOINT`, `bucket` → `$BUCKET`, `host` → `$HOST`, `port` → `$PORT`, `access_key` → `$ACCESS_KEY`, …) |

In **online mode** (`services run-tests`) the harness sets the same
`$SERVICE_BASE_URL` and `$UNITYSVC_API_KEY` — but pointing at the
gateway URL and the customer's platform API key. So **env var names
are identical between local and online mode**; only the values
differ. Often this means you don't need `{% if local_testing %}` at
all — just read the env vars.

Standard Jinja2 machinery is also available: `{% if %}`, `{% for %}`,
`{{ x | default("fallback") }}`, `{{ x | tojson }}`. No custom
filters beyond `tojson`.

Favor `interface.get("field_name")` over `interface.field_name` for
optional fields — some interfaces don't define them and direct
attribute access raises.

### When to use Jinja vs env vars

- **Connectivity tests**: env vars are almost always enough — the
  same script works for both modes without any `{% if %}`. See
  `docs/connectivity.sh.j2`, `docs/s3/connectivity.sh.j2`, and
  `docs/smtp/connectivity.sh.j2` in this repo.
- **Code examples**: use `{% if local_testing %}` to branch on
  *request shape* — e.g., the test harness might send params directly
  in the body, while the customer-facing version relies on the
  gateway injecting them. Don't hardcode values the gateway should
  inject.
- **Literal URLs or path prefixes** that differ per-render
  (e.g., `description.md` showing the right base URL for the current
  seller's listing): Jinja context.

## The `meta` block: test assertions

The harness ships a couple of simple checks. Pick the narrowest one
that catches real failure:

```json
"meta": { "output_contains": "connectivity ok" }
```
Substring match against stdout. Case-sensitive (issue #52); pick a
literal phrase you print on success.

```json
"meta": { "expect": { "status_code": 200 } }
```
For HTTP-response tests; assert the response status code.

```json
"meta": { "output_contains": "models", "expect": { "status_code": 200 } }
```
Both can be combined.

**Anti-pattern:** asserting on the entire stdout, or on a dynamic
value (timestamp, UUID, throughput number). Write a success-marker
literal to stdout at the end of the example and assert on that —
that's what `echo "connectivity ok"` does in every `connectivity.sh.j2`
in this repo.

## Secret references in `upstream_access_config`

Seller and customer secrets appear in `offering.json`'s
`upstream_access_config` as `${ secrets.X }` (platform / seller-owned
secrets) or `${ customer_secrets.X }` (customer-owned, resolved by the
gateway at enrollment/request time).

### Only two forms are valid

The identifier `X` after `secrets.` / `customer_secrets.` must be one
of:

1. **A literal secret name** — letters, digits, and underscores only:
   ```json
   "api_key": "${ customer_secrets.ECHO_API_KEY }"
   ```
2. **A Jinja substitution** referencing `params.KEY`, where `KEY`
   exists in `service_options.ops_testing_parameters`:
   ```json
   "access_key": "${ customer_secrets.{{ params.s3_access_key_secret }} }"
   ```

Nothing else is supported. In particular:

- **Bracket lookup** is *not* supported — `${ customer_secrets[X] }`
  will pass through as a literal string and the test will fail with a
  confusing stderr.
- **Other Jinja namespaces** (`enrollment_vars.X`, `routing_vars.X`,
  arbitrary expressions) inside the secret reference are *not*
  supported yet — use `params` only.

### How it resolves at test time

Two stages, in order:

1. **Jinja render**: the seller harness substitutes `{{ params.KEY }}`
   using `service_options.ops_testing_parameters.KEY`. After this
   step the reference must look like `${ customer_secrets.NAME }`
   with a plain identifier.
2. **Environment lookup**: the resolver reads `os.environ.get(NAME)`.
   If the env var is set, the field is substituted with its value. If
   not, `usvc_seller data run-tests` aborts the test with
   `Error: secret NAME required by <field> is not defined as
   environment variable`.

### Author responsibilities

- Every name referenced via `{{ params.KEY }}` must also be declared
  in the listing's `user_parameters_schema.properties` (so customers
  know what to provide) and have a test value in
  `service_options.ops_testing_parameters.KEY` (so `data run-tests`
  can exercise it). `usvc_seller data validate` enforces the
  second part automatically via
  `validate_required_parameter_defaults()`.
- Export each required env var before running the tests. The harness
  will tell you which ones are missing if you forget — see the
  example output above.

### Example: the `s3-byoe-params` service

`offering.json`:
```json
"upstream_access_config": {
  "S3 Upstream": {
    "access_key": "${ customer_secrets.{{ params.s3_access_key_secret }} }",
    "bucket":     "${ customer_secrets.{{ params.s3_bucket_secret }} }",
    "region":     "${ customer_secrets.{{ params.s3_region_secret }} }",
    "s3_endpoint":"${ customer_secrets.{{ params.s3_endpoint_secret }} }",
    "secret_key": "${ customer_secrets.{{ params.s3_secret_key_secret }} }",
    "storage_type": "s3"
  }
}
```

`listing.json`:
```json
"service_options": {
  "ops_testing_parameters": {
    "s3_access_key_secret":  "SVCMARKET_S3_ACCESS_KEY_ID",
    "s3_bucket_secret":      "SVCPASS_S3_BUCKET",
    "s3_region_secret":      "SVCPASS_S3_REGION",
    "s3_endpoint_secret":    "SVCPASS_S3_ENDPOINT",
    "s3_secret_key_secret":  "SVCMARKET_S3_SECRET_ACCESS_KEY"
  }
}
```

Before `usvc_seller data run-tests`:
```bash
export SVCMARKET_S3_ACCESS_KEY_ID=…
export SVCPASS_S3_BUCKET=demo-bucket
export SVCPASS_S3_REGION=us-east-1
export SVCPASS_S3_ENDPOINT=https://s3.staging.svcpass.com
export SVCMARKET_S3_SECRET_ACCESS_KEY=…
```

## Authoring checklist

For each new example, before committing:

- [ ] Template file lives under `data/<provider>/docs/<family>/` with
      a `*.j2` extension.
- [ ] Referenced from the relevant `listing.json` `documents` entry
      with a relative `file_path`.
- [ ] Any URL, credential, or request parameter that the gateway
      injects at runtime is wrapped in `{% if local_testing %}`.
- [ ] The `{% else %}` branch (what customers see) is complete and
      correct in isolation — mentally read it without the
      `local_testing` scaffold and confirm it works.
- [ ] Every `${ secrets.X }` / `${ customer_secrets.X }` reference
      uses either a literal name or `{{ params.KEY }}` — nothing
      else (no bracket lookup, no `enrollment_vars`/`routing_vars`).
- [ ] Every `{{ params.KEY }}` used in a secret reference has a
      matching entry in `service_options.ops_testing_parameters`.
- [ ] `usvc_seller data validate` passes.
- [ ] A success marker (`connectivity ok` or similar) is echoed to
      stdout on the happy path, and `meta.output_contains` asserts on
      that exact literal.
- [ ] `usvc_seller data run-tests` passes locally with the required
      env vars exported.
- [ ] You also rendered the non-`local_testing` output (e.g., by
      running `usvc_seller data upload --dryrun` or equivalent) and
      eyeballed it — does it match what you would want a customer to
      copy-paste?

That last step is the one that catches issues #47 and #48. Automated
tests exercise the `local_testing=True` branch; the `False` branch is
only verified by human review.

## Common pitfalls

**Hardcoded request-body parameters leaking into customer view.**
Classic failure mode (issue #48). Test passes because the hardcoded
param makes it to upstream; customer documentation shows a param they
should *not* be writing. Fix: wrap the injection in
`{% if local_testing %}` and ensure the `else` branch relies on
gateway-injected values.

**Tests that pass even when upstream is wrong.** If your example
bypasses the gateway entirely (direct-to-upstream under `local_testing`)
AND also uses the same direct URL in the `else` branch, you're never
actually exercising the gateway path. The test is a false positive.
Fix: the `else` branch must use `SERVICE_BASE_URL` or the appropriate
gateway-routed URL.

**`output_contains` never matching due to case.** Issue #52. Match
the exact case you emit.

**Direct access to optional interface fields.** `interface.access_key`
raises when the field isn't set; `interface.get("access_key")` returns
`None`. Always use `.get()` for optional fields inside `{% if %}`
guards.

**Not committing the `.j2` extension.** A file named `code-example.py`
will be rendered as-is (no templating). Use `code-example.py.j2` so
the Jinja pipeline runs.

## References

- Design rationale: `unitysvc-bridge-uptime/docs/fix-local-testing-params.md`
- Seller-facing authoring docs: `unitysvc-sellers/docs/code-examples.md`
- Render implementation: `unitysvc-sellers/src/unitysvc_sellers/utils.py`
  (`render_template_file`)
- Template-system overview: `unitysvc/docs/dev-notes/features/jinja2-template-system.md`
- Related open issues (in `unitysvc/unitysvc-services`):
  - #47 — JS code example tests give false positives
  - #48 — Jinja2 secrets template not resolved in local tests
  - #57 — Failed tests showing success
