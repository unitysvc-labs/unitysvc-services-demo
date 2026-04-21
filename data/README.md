# Example Services

This folder holds minimal working examples of UnitySVC services under
`unitysvc-demo/`, one per delivery pattern. HTTP examples relay to
`https://echo.staging.svcmarket.com`; S3 uses `s3.staging.svcpass.com`;
SMTP uses `mail.staging.svcmarket.com`. Use them as copy-paste starting
points for your own services.

## Service overview

| Service            | Gateway | Enrollment | Secrets                            | Demonstrates                                      |
| ------------------ | ------- | ---------- | ---------------------------------- | ------------------------------------------------- |
| `relay`            | HTTP    | no         | none                               | minimal managed service                           |
| `llm`              | HTTP    | no         | none                               | LLM service with token pricing + request template |
| `byok`             | HTTP    | no         | customer `api_key`                 | BYOK pattern                                      |
| `byoe`             | HTTP    | no         | customer `base_url` + `api_key`    | BYOE pattern                                      |
| `params`           | HTTP    | yes        | none                               | user parameter as routing key                     |
| `byoe-params`      | HTTP    | yes        | customer, names via params         | parameterized secret names                        |
| `enrollment_vars`  | HTTP    | yes        | none                               | `enrollment_vars` for per-enrollment URL          |
| `recurrent`        | HTTP    | yes        | none                               | `prompt_recurrence` scheduling                    |
| `routing_vars`     | HTTP    | no         | none                               | post-activation seller knobs via `routing_vars`   |
| `s3`               | S3      | no         | seller `access_key` / `secret_key` | S3-specific upstream fields                       |
| `s3-byoe`          | S3      | no         | customer (all 5 S3 fields)         | BYOE for S3                                       |
| `s3-byoe-params`   | S3      | yes        | customer, names via params         | parameterized S3                                  |
| `smtp`             | SMTP    | no         | none                               | SMTP gateway + username routing                   |
| `smtp-byoe`        | SMTP    | no         | customer (host/port/user/pass)     | BYOE for SMTP                                     |
| `smtp-byoe-params` | SMTP    | yes        | customer, names via params         | parameterized SMTP                                |

## Service descriptions

### `relay` — Managed HTTP relay

The minimal service definition: seller-supplied static upstream, no auth. The
gateway maps `${API_GATEWAY_BASE_URL}/demo/echo-relay` to the upstream echo URL.

- **offering.json** required fields: `schema`, `name`, `service_type`,
  `upstream_access_config` (with `access_method` and `base_url`), `time_created`.
- **listing.json** required fields: `schema`, `user_access_interfaces` (with
  `access_method` and gateway `base_url`), `time_created`.

### `llm` — LLM service

An LLM-flavored relay: same mechanics as `relay`, but showcases the fields
that make a service an LLM on the marketplace.

- **offering.json** sets `service_type: "llm"`, `capabilities: ["llm"]`,
  a `details` block with `context_window`, `max_input_tokens`,
  `max_output_tokens`, `mode: "chat"`, and a token-based `payout_price`
  (`type: "one_million_tokens"`) with split `input` / `output` rates.
  Upstream is `https://mock.staging.svcmarket.com/openai/v1` (OpenAI-compatible).
- **listing.json** uses token-based `list_price` (input/output split), gateway
  path `${API_GATEWAY_BASE_URL}/demo/llm`, and a `request_template` document
  (`docs/llm/request-template.json`) that pre-fills the marketplace playground
  with a standard chat completion payload.

### `byok` — Bring Your Own Key

BYOK is the pattern used when the upstream requires an API key that the customer
must provide. The key is referenced in `upstream_access_config` as
`${ customer_secrets.NAME }` and resolved at request time from the customer's
own secret store.

- **offering.json**: adds `api_key = "${ customer_secrets.ECHO_API_KEY }"` in
  `upstream_access_config`, plus the `byok` tag.
- **listing.json**: distinct gateway path (`${API_GATEWAY_BASE_URL}/demo/echo-byok`)
  so this service does not collide with `relay`.

### `byoe` — Bring Your Own Endpoint

BYOE extends BYOK: both the upstream `base_url` and `api_key` are customer-supplied
via `customer_secrets`. Each customer routes to their own backend.

- **offering.json**: `base_url = "${ customer_secrets.ECHO_BYOE_BASE_URL }"` and
  `api_key = "${ customer_secrets.ECHO_BYOE_API_KEY }"`, plus the `byoe` tag.
- **listing.json**: gateway path `${API_GATEWAY_BASE_URL}/demo/echo-byoe`.

### `params` — User parameters and routing keys

Some services need per-enrollment configuration. `params` declares a single
string parameter, `model`, that each customer supplies at enrollment time. The
same value is used as the `routing_key` so a request carrying
`{"model": "<value>", ...}` is matched to this service listing.

- **listing.json** adds:
  - `user_parameters_schema` — JSON Schema declaring `model` (required string).
  - `service_options.ops_testing_parameters.model` — default value used by
    automated tests (`usvc data run-tests` / gateway tests). `ops_testing_parameters`
    is mandatory whenever a required parameter has no schema `default`.
  - `user_access_interfaces."HTTP Gateway".routing_key = {"model": "{{ params.model }}"}`
    — Jinja-templated routing key rendered at enrollment time with the
    customer's chosen model.
- **offering.json** mirrors the routing key inside
  `upstream_access_config."Echo Service".routing_key` so the gateway can
  match the upstream for the same model value.

The customer request body **must** include `"model": "<their-value>"` so the
gateway can extract the routing key and dispatch to the correct service.

### `byoe-params` — BYOE with parameterized secret names

Like `byoe`, but the customer secret **names** are themselves enrollment
parameters. This lets one offering serve many independent backends per
customer — each enrollment points at a different pair of secrets.

- **offering.json** uses the Jinja-inside-secret form:
  `base_url = "${ customer_secrets.{{ params.base_url_secret }} }"` and
  `api_key = "${ customer_secrets.{{ params.api_key_secret }} }"`. The
  `{{ params.X }}` is rendered at enrollment time to a concrete secret name,
  which is then resolved from the customer's secret store at request time.
- **listing.json** declares `base_url_secret` (required) and
  `api_key_secret` (optional, default `""`) in `user_parameters_schema`.
  `ops_testing_parameters` pins them to `ECHO_BYOE_BASE_URL` /
  `ECHO_BYOE_API_KEY` for automated tests.

### `enrollment_vars` — Per-enrollment variables

Demonstrates `service_options.enrollment_vars`: values rendered once per
enrollment and reusable in any access interface template. Here a 6-char
code is generated at enrollment time and embedded in both the user-facing
gateway path and the upstream URL, so every enrollment gets a unique route.

- **listing.json** declares
  `service_options.enrollment_vars.code = "{{ enrollment_code(6) }}"` and uses
  `{{ enrollment_vars.code }}` inside
  `user_access_interfaces."HTTP Gateway".base_url`.
- **offering.json** references the same `{{ enrollment_vars.code }}` inside
  `upstream_access_config."Echo Service".base_url` so the gateway forwards to
  the matching upstream path.

Rendering runs in two phases: `enrollment_vars` first (so `{{ enrollment_code(6) }}`
materialises to something like `VTXBNM`), then the access interface URL
templates consume the rendered value.

### `recurrent` — Scheduled execution

Demonstrates recurrent services: the platform fires requests on a schedule the
customer picks at enrollment time.

- **listing.json** adds under `service_options`:
  - `prompt_recurrence: true` — the **master switch**. Frontend checks
    `serviceOptions?.prompt_recurrence === true` in `EnrollButton.tsx` to open
    the schedule wizard; backend derives `is_recurrent` in the `service_mview`
    from the same field.
  - `recurrence_min_interval_seconds` / `recurrence_max_interval_seconds` —
    bounds on the customer-chosen interval.
  - `recurrence_allow_cron` — whether cron expressions are allowed.

There is no separate `recurrence_enabled` flag; `prompt_recurrence` alone
controls both the enrollment UI and backend scheduling.

### `routing_vars` — Post-activation seller knobs

Demonstrates `routing_vars` (unitysvc/unitysvc#555): operational variables
the seller can edit **after** a service is live, without another approval
cycle. Because the admin approves the _template_ at publish time, changing
values it references is safe.

- **listing.json** declares the initial values under
  `service_options.routing_vars` (`backend_host: "https://echo.staging.svcmarket.com"`).
- **offering.json** references them as `{{ routing_vars.backend_host }}` in
  `upstream_access_config."Echo Service".base_url`. Rendered at request time
  only (not at enrollment).
- After activation the seller can retarget without re-upload:

  ```
  usvc services update routing_vars --set-routing-var backend_host=https://echo.other.example.com
  ```

Contrast with `enrollment_vars` (per-enrollment, customer-initiated) and
`customer_secrets` (customer-owned, looked up at request time).
The same pattern works for S3 (`{{ routing_vars.bucket }}`) or SMTP
(`{{ routing_vars.host }}`).

### `s3` — S3 content service

Demonstrates a content-delivery service routed through the **S3 gateway** rather
than the HTTP API gateway. No user enrollment or customer secrets; the seller
supplies upstream S3 credentials via seller secrets.

- **offering.json** `upstream_access_config` uses S3-specific fields in addition
  to `access_method`: `storage_type: "s3"`, `s3_endpoint`, `bucket`, `region`,
  and `access_key` / `secret_key` referencing `${ secrets.SVCMARKET_S3_ACCESS_KEY_ID }`
  / `${ secrets.SVCMARKET_S3_SECRET_ACCESS_KEY }` from the seller's secret store.
- **listing.json** `user_access_interfaces."S3 Gateway".base_url` uses
  `${S3_GATEWAY_BASE_URL}/s3` (not `${API_GATEWAY_BASE_URL}`), since S3 traffic
  goes through the dedicated S3 gateway.
- `service_type` is `content`, capabilities are `s3_browse` and `s3_download`.

Seller must create `SVCMARKET_S3_ACCESS_KEY_ID` and `SVCMARKET_S3_SECRET_ACCESS_KEY` in the
seller secret store before the service can relay to the upstream bucket.

### `s3-byoe` — BYOE for S3

S3 equivalent of the HTTP `byoe` service. The customer brings their own
bucket — all of `s3_endpoint`, `bucket`, `region`, `access_key`, `secret_key`
are resolved from `customer_secrets`.

- **offering.json** `upstream_access_config` fields all reference
  `${ customer_secrets.S3_* }`.
- **listing.json** gateway path is `${S3_GATEWAY_BASE_URL}/s3-byoe`.

### `s3-byoe-params` — BYOE S3 with parameterized secret names

S3 equivalent of `byoe-params`. Enrollment parameters declare which of the
customer's secrets hold each piece of upstream config, using the Jinja-
rendered dot form
`${ customer_secrets.{{ params.NAME }} }` — the inner `{{ params.NAME }}`
resolves to the secret's name, which the secret resolver then looks up.

- **offering.json** uses this pattern for all five upstream fields
  (matches the same pattern as `smtp-byoe-params`).
- **listing.json** declares a `user_parameters_schema` with the five
  parameter names (all required) and pins them to `SVCPASS_S3_*` in
  `service_options.ops_testing_parameters` for automated tests.

### `smtp` — SMTP relay

Demonstrates an email service routed through the **SMTP gateway** (not the
HTTP or S3 gateway). Seller-managed upstream; no customer enrollment or
secrets required.

- **offering.json** `upstream_access_config` uses `access_method: "smtp"` plus
  SMTP-specific fields: `host: "mail.staging.svcmarket.com"`, `port: 587`,
  `tls: true`.
- **listing.json** `user_access_interfaces."SMTP Gateway"` uses
  `access_method: "smtp"`, `base_url: "${SMTP_GATEWAY_BASE_URL}"`, and a
  `routing_key` on `username` so the SMTP gateway can dispatch mail
  submissions (authenticated with a UnitySVC API key) to this service.
- `service_type` is `email`, capability is `smtp_relay`.

### `smtp-byoe` — BYOE for SMTP

SMTP equivalent of `byoe`: the customer brings their own SMTP server. All
four upstream fields (`host`, `port`, `username`, `password`) are resolved
from fixed `customer_secrets` names.

- **offering.json** `upstream_access_config."Customer SMTP"` references
  `${ customer_secrets.SMTP_HOST }`, `SMTP_PORT`, `SMTP_USERNAME`,
  `SMTP_PASSWORD`, with `tls: true`.
- **listing.json** routes through the SMTP gateway with
  `routing_key.username = "smtp-byoe"`.

### `smtp-byoe-params` — BYOE SMTP with parameterized secret names

Multi-enrollment SMTP relay, equivalent to `byoe-params` and `s3-byoe-params`.
The customer supplies the **names** of their secrets as enrollment
parameters, so one offering can serve multiple SMTP configurations per
customer (personal Gmail, work SendGrid, transactional SES, etc.).

- **offering.json** uses the Jinja-inside-secret form:
  `"host": "${ customer_secrets.{{ params.SMTP_HOST_SECRET }} }"` (and the
  three other fields).
- **listing.json** declares `user_parameters_schema` with the four
  `*_SECRET` params (all required) and pins them to `SMTP_HOST` /
  `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` in
  `service_options.ops_testing_parameters` for automated tests.

## Environment variables for local testing

`usvc_seller data run-tests` resolves every `${ secrets.NAME }` and
`${ customer_secrets.NAME }` reference in an offering's
`upstream_access_config` by reading `NAME` from the current process
environment. A service is skipped (with a clear "missing environment
variables: …" message) if any referenced variable is unset.

Export the variables below before running the tests. Services not
listed here require no environment configuration.

| Service            | Required env vars                                            | Optional                       |
| ------------------ | ------------------------------------------------------------ | ------------------------------ |
| `byok`             | —                                                            | `ECHO_API_KEY` (→ empty)       |
| `byoe`             | `ECHO_BYOE_BASE_URL`, `ECHO_BYOE_API_KEY`                    |                                |
| `byoe-params`      | `ECHO_BYOE_BASE_URL`, `ECHO_BYOE_API_KEY`                    |                                |
| `s3`               | `S3_ACCESS_KEY`, `S3_SECRET_KEY`                             |                                |
| `s3-byoe`          | `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | `S3_REGION` (→ `us-east-1`)    |
| `s3-byoe-params`   | `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | `S3_REGION` (→ `us-east-1`)    |
| `smtp-byoe`        | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`   |                                |
| `smtp-byoe-params` | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`   |                                |

Notes:

- The `s3` family all use the same `S3_*` env vars whether referenced
  as seller `${ secrets.* }` (in `s3`) or customer `${ customer_secrets.* }`
  (in the BYOE variants) — at local-test time both resolve from the
  process environment.
- `s3-byoe-params` and `smtp-byoe-params` declare the secret names via
  `service_options.ops_testing_parameters` in their listing. Changing
  those mappings changes which env vars the tests read.
- `S3_REGION` is optional for both S3 BYOE services — the `?? us-east-1`
  default in their offerings is used when the env var is unset.
- `byok`'s `ECHO_API_KEY` is optional (`?? ` default empty): the echo
  upstream accepts any key, so local tests work without it set.
