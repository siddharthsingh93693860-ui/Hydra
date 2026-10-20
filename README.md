# HYDRA

## AI-Powered Web Workflow Automation and API Generation

**HYDRA turns authorised, repeatable website tasks into structured JSON
through a reusable API workflow.**

HYDRA is an open-innovation project for developers, startups, operations
teams, researchers, and small businesses that need data from websites
that do not provide a convenient public API.

Instead of repeatedly browsing a website and copying information
manually, a user describes the task in plain English. HYDRA is designed
to use TinyFish browser automation to interact with the authorised
website, normalise the collected result, and make the result available
as structured JSON.

> **Prototype status:** The project is still an MVP/feasibility
> prototype. TinyFish Browser/CDP has been tested, but the configured
> TinyFish Agent endpoint returned `FORBIDDEN`. The live Agent workflow
> must not be presented as working until access is resolved and a
> successful end-to-end run is verified. Some compiler/demo flows are
> controlled fixtures or mocks.

## The problem

Many useful websites do not expose a public API. Teams may have to:

-   Browse pages manually to collect data.
-   Build one-off scrapers for individual websites.
-   Repair scrapers when a website's layout changes.
-   Repeat the same collection process on a schedule.

HYDRA explores a more reusable approach: define a task once, validate
its output, and expose a repeatable workflow through an API.

## How HYDRA is designed to work

1.  **Enter a website URL** that you are authorised to access.
2.  **Describe the task** in plain English, such as "collect the first
    five books in the Travel category with price and rating."
3.  **Run the browser workflow** using TinyFish, where account access
    and website permissions allow it.
4.  **Structure the result** as JSON and validate the expected fields.
5.  **Publish or call a reusable endpoint** for the workflow, once that
    workflow is implemented and verified.

The diagram below represents the intended architecture, not a claim that
every stage is currently implemented end to end.

``` mermaid
flowchart LR
    A[Authorised URL + task] --> B[TinyFish Agent exploration]
    B --> C[Reference result]
    B --> D[LLM-assisted workflow compilation]
    D --> E[TinyFish Browser / CDP]
    E --> F[Validate fresh result]
    C --> F
    F --> G[Version verified workflow]
    G --> H[Reusable JSON API]
    H --> I[Validate each response]
    I -->|Failure| J[Repair or re-explore]
    J --> F
```

## Why TinyFish?

TinyFish is central to HYDRA's intended browser workflow. It is designed
to help HYDRA interact with live websites rather than relying only on
static sample data.

-   **TinyFish Agent:** intended for goal-driven website exploration and
    task execution.
-   **TinyFish Browser/CDP:** provides browser-session access for
    supported browser actions.
-   **Structured output:** HYDRA's backend is intended to normalise and
    validate the result before it is used by another application.

**Current limitation:** Browser/CDP feasibility has been tested, but the
configured Agent endpoint returned `FORBIDDEN`. Do not claim a
successful live Agent run until the credentials/account access are fixed
and the complete workflow is tested.

## Example use cases

-   **Product information:** collect product titles, prices,
    availability, and ratings from an authorised catalogue.
-   **Public notifications:** retrieve recent announcement titles and
    document links from a public notice page.
-   **Operations workflows:** collect read-only status information from
    a portal the user is authorised to access.
-   **Research and analysis:** reduce repetitive copying of public
    information into other tools.

Examples are intended use cases; do not assume each one has been
validated against a live external website.

## Tech stack

-   **Frontend:** React, TypeScript, Vite
-   **Backend:** Python, FastAPI
-   **Browser automation:** TinyFish Browser/CDP and
    Playwright-compatible browser connection
-   **LLM integration:** Groq/LLM-related code is present in the
    project; model configuration and end-to-end compilation should be
    verified before presenting it as fully operational
-   **Persistence:** SQLite
-   **Output:** REST endpoints and JSON

## Setup

Use Python 3.11 or later and a recent Node.js LTS version.

### 1. Configure environment variables

Copy `.env.example` to `.env` in the project root:

``` powershell
Copy-Item .env.example .env
```

Open `.env` and set the required values based on `.env.example`. For the
current TinyFish feasibility probe, the key settings are:

``` env
TINYFISH_API_KEY=replace_with_your_own_key
HYDRA_LIVE_TESTS=0
```

Use your own TinyFish API key. Do not commit `.env`, publish API keys,
or paste secrets into public issues or chat. Set `HYDRA_LIVE_TESTS=1`
only when you intentionally want to run live provider tests; these calls
may consume credits.

### 2. Install frontend dependencies

The frontend directory contains the React/Vite application. From the
project root:

``` powershell
cd frontend
npm install
npm run build
cd ..
```

### 3. Start the backend

Run this from the project root:

``` powershell
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

If the repository's dependency file or startup configuration differs,
follow the files actually present in the ZIP and update these commands
accordingly.

Open `http://127.0.0.1:8000` if the local server starts successfully.

## Tests and TinyFish feasibility probe

Run deterministic tests:

``` powershell
python -m pytest -m "not live" -q
```

Run the feasibility probe only after configuring your own key and
intentionally enabling live tests in `.env`:

``` powershell
python -m hydra.probe
```

The probe is intended to test the TinyFish Agent and Browser
integrations independently. It may fail if the account or endpoint does
not have access. A failed/blocked result is evidence of a limitation,
not a successful live demo.

Check the repository's `docs/TINYFISH_FEASIBILITY.md` and
`docs/SELF_REVIEW.md` for more detailed findings and limitations, if
those files are included in your copy.

## Safety and responsible use

-   Use only websites and accounts you are authorised to access.
-   Keep workflows read-only unless an explicit, safe approval mechanism
    is implemented.
-   Do not bypass CAPTCHA, access controls, authentication restrictions,
    or website policies.
-   Do not use the prototype to collect private or sensitive
    information.
-   Validate extracted fields before relying on them.
-   Keep API keys in local environment variables and never commit
    secrets.

Some production controls---such as full domain-policy enforcement, rate
limiting, authentication, worker isolation, retention controls, and
comprehensive audit/redaction---may still be incomplete in this
prototype. Do not describe them as implemented unless you verify them in
the current code.

## Current limitations and next steps

1.  Resolve the TinyFish Agent `FORBIDDEN` response and verify a
    successful live run.
2.  Demonstrate one authorised end-to-end workflow with real returned
    data.
3.  Validate the JSON schema and compare output against expected
    results.
4.  Confirm which workflow/API endpoints are fully functional in the
    current code.
5.  Add a short demo recording and screenshots that reflect the actual
    implementation.
6.  Document tested setup commands and known limitations before
    submission.

## Hackathon submission

HYDRA is being prepared for **Kritical Hacks '26**. The submission
should include:

-   A public GitHub repository with this README and working setup
    instructions.
-   A demo video showing the features that actually work, including
    TinyFish integration if live access is resolved.
-   A public project post with the repository link.
-   A presentation that distinguishes completed features from planned
    architecture.

**Be transparent in the demo:** do not label mock or controlled-fixture
output as a successful live TinyFish Agent result.
