# social-osint-lookup

Polished **public-profile OSINT** CLI for **TikTok**, **Instagram**, and **X (Twitter)**.

Educational / research framing only. Fetches **public HTML pages** (and embedded
public JSON/meta) — never logs in, never bypasses privacy settings, never
pulls private DMs, follower dumps of real people, or credential-stuffed APIs.

```bash
social-osint-lookup lookup nasa -p all -f pretty
social-osint-lookup tiktok @nasa -f json
social-osint-lookup x nasa -f json
python -m social_osint_lookup instagram nasa
```

## Ethics & disclaimer

- **Public data only.** If a profile is private or behind a login wall, fields
  will be `null` / `found: false` — that is correct behavior.
- **No credential stuffing**, captcha bypass, session hijacking, or anti-bot evasion.
- **Rate limiting** is built in (~1.25s between requests). Be polite; respect
  robots.txt and each platform’s Terms of Service.
- **You** are responsible for lawful use. Do not use this tool to stalk,
  harass, dox, or build personal dossiers on private individuals.
- Honest nulls: missing fields stay `null`. Nothing is invented.
- **No Wayback / archive scraping** for username history. History is only
  returned when a public profile payload actually contains prior handles.

## Install

```bash
git clone https://github.com/LowIq11/social-osint-lookup.git
cd social-osint-lookup
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Or with requirements only:

```bash
pip install -r requirements.txt
pip install -e .
```

## CLI

| Command | Description |
|---------|-------------|
| `social-osint-lookup lookup TARGET -p all\|tiktok\|instagram\|x` | Unified lookup |
| `social-osint-lookup tiktok TARGET` | TikTok only |
| `social-osint-lookup instagram TARGET` | Instagram only |
| `social-osint-lookup x TARGET` | X (Twitter) only (`twitter` alias) |
| `social-osint-lookup platforms` | What each platform covers |
| `-f pretty\|json` | Output format |
| `-o PATH` | Write to file |

Also available as `sol` and `python -m social_osint_lookup`.

### Examples

```bash
# Pretty text across all three platforms
social-osint-lookup lookup nasa

# JSON for one platform
social-osint-lookup tiktok nasa -f json -o out/tiktok_nasa.json

# Instagram by URL
social-osint-lookup instagram 'https://www.instagram.com/nasa/'

# X / Twitter
social-osint-lookup x nasa -f json
```

See `examples/sample_output.json` for a sanitized shape (fictional demo values).

## Extended fields (every result)

Always present on every platform result (`null` when not publicly available):

| Field | Shape |
|-------|--------|
| `location` | string or `null` |
| `account_created_at` | ISO-8601 string or `null` |
| `username_history` | `[{username, changed_at, location_at_change}]` or `null` |
| `tiktok_creator_level` | string or `null` (TikTok only; always `null` elsewhere) |
| `field_availability` | per-field `"available"` / `"unavailable"` / `"n/a"` |

`username_history[].location_at_change` is the account location **at rename time**
**only** if a public unauthenticated payload exposes it. Otherwise `null`.
Most platforms do **not** expose this; do not treat null as “no location ever”.

### Field × platform support matrix

| Field | TikTok | Instagram | X (Twitter) |
|-------|--------|-----------|-------------|
| `location` | Often (`user.region` / related) | Rare (`city_name` / business address / ld+json) | Often (`location` / ld+json) |
| `account_created_at` | Often (`createTime` → ISO) | **Unavailable** from public profile page | Often (`created_at` / “Joined …”) |
| `username_history` | Rare (only if `uniqueIdHistory` etc. in page JSON) | **Unavailable** (no public profile field) | **Unavailable** (no public profile field) |
| `username_history[].changed_at` | Only if present in history item | n/a | n/a |
| `username_history[].location_at_change` | Only if present in history item (typically absent) | n/a | n/a |
| `tiktok_creator_level` | When `creatorLevel` / `supportLevel` / commerce badge keys exist | **n/a** | **n/a** |

## Platform coverage (honest)

### TikTok

| Field | Source |
|-------|--------|
| username, display name, bio | `__UNIVERSAL_DATA_FOR_REHYDRATION__` → `webapp.user-detail.userInfo` (fallback: `SIGI_STATE`, then og meta) |
| follower / following / likes / video counts | Same rehydration `stats` when present |
| user id, secUid, verified, private | Public user object when present |
| location | `user.region` / related when present |
| account_created_at | `user.createTime` (unix → ISO-8601 UTC) |
| username_history | `uniqueIdHistory` / similar **only if present** — structured entries |
| tiktok_creator_level | `creatorLevel` / `supportLevel` / commerce badge keys when present |
| profile URL | `https://www.tiktok.com/@{username}` |

Accepts `@user`, bare username, profile URL, or numeric share id (`/share/user/{id}`).

### Instagram

| Field | Source |
|-------|--------|
| display name, bio | `window._sharedData` / `__additionalDataLoaded` when present; else `og:title` / `og:description` |
| follower / following / post counts | GraphQL edges in shared data, or counts parsed from public og:description |
| verified / private | Public flags when exposed in shared data |
| location | Rare: `city_name` / `business_address_json` / ld+json |
| account_created_at | **Unavailable** from public profile page → `null` |
| username_history | **Unavailable** from public profile page → `null` |
| profile URL | `https://www.instagram.com/{username}/` |

Accepts `@user`, bare username, or profile URL.

### X (Twitter)

| Field | Source |
|-------|--------|
| display name, bio, verified | `__NEXT_DATA__` user/legacy object when present; else og meta |
| follower / following | Next data or public syndication follow-button JSON |
| location | `legacy.location` / ld+json `homeLocation` when public |
| account_created_at | `created_at` or visible “Joined Month Year” when public |
| username_history | **Unavailable** from public profile / syndication → `null` |
| profile URL | `https://x.com/{username}` |

Accepts `@user`, bare username, `x.com` / `twitter.com` profile URL. CLI alias: `twitter`.

## Project layout

```
src/social_osint_lookup/
  cli.py                 # Click CLI
  http_client.py         # requests + fake-useragent + rate limit + extended fields
  formatters.py          # JSON + pretty text
  platforms/
    tiktok.py            # lookup(username_or_url) -> dict
    instagram.py
    x.py                 # X / Twitter
tests/                   # mocked HTML unit tests
examples/                # sanitized sample JSON
```

Each platform module exposes:

```python
lookup(username_or_url: str) -> dict  # PUBLIC fields only
```

## Tests

```bash
pytest -q
```

Tests use **mocked HTML fixtures** — no live network, no real personal data dumps.

## Dependencies

- `requests` — HTTP
- `beautifulsoup4` — HTML / meta parsing
- `fake-useragent` — rotating desktop UA strings
- `click` — CLI

## License

MIT © LowIq11
