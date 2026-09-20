# social-osint-lookup

Polished **public-profile OSINT** CLI for **TikTok**, **Instagram**, and **Facebook**.

Educational / research framing only. Fetches **public HTML pages** (and embedded
public JSON/meta) — never logs in, never bypasses privacy settings, never
pulls private DMs, follower dumps of real people, or credential-stuffed APIs.

```bash
social-osint-lookup lookup nasa -p all -f pretty
social-osint-lookup tiktok @nasa -f json
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
| `social-osint-lookup lookup TARGET -p all\|tiktok\|instagram\|facebook` | Unified lookup |
| `social-osint-lookup tiktok TARGET` | TikTok only |
| `social-osint-lookup instagram TARGET` | Instagram only |
| `social-osint-lookup facebook TARGET` | Facebook only |
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

# Facebook page slug
social-osint-lookup facebook nasa -f json
```

See `examples/sample_output.json` for a sanitized shape (fictional demo values).

## Platform coverage (honest)

### TikTok

| Field | Source |
|-------|--------|
| username, display name, bio | `__UNIVERSAL_DATA_FOR_REHYDRATION__` → `webapp.user-detail.userInfo` (fallback: `SIGI_STATE`, then og meta) |
| follower / following / likes / video counts | Same rehydration `stats` when present |
| user id, secUid, verified, private | Public user object when present |
| profile URL | `https://www.tiktok.com/@{username}` |

Accepts `@user`, bare username, profile URL, or numeric share id (`/share/user/{id}`).

### Instagram

| Field | Source |
|-------|--------|
| display name, bio | `window._sharedData` / `__additionalDataLoaded` when present; else `og:title` / `og:description` |
| follower / following / post counts | GraphQL edges in shared data, or counts parsed from public og:description (`N Followers, N Following, N Posts`) |
| verified / private | Public flags when exposed in shared data |
| profile URL | `https://www.instagram.com/{username}/` |

Accepts `@user`, bare username, or profile URL. Private accounts still yield limited public meta when Instagram exposes it; otherwise `found` may be false / fields null.

### Facebook

| Field | Source |
|-------|--------|
| public name | `og:title` / `<title>` |
| about snippet | `og:description` / meta description (public only) |
| entity type (`page` / `profile`) | `og:type`, ld+json `@type`, or embedded pageID/userID hints |
| profile URL | Canonical `og:url` or constructed URL |
| id | From `profile.php?id=` or embedded public IDs when present |

Accepts page slug, `profile.php?id=…`, or full facebook.com URL. Heavy login walls often leave only a name/title — reported honestly.

## Project layout

```
src/social_osint_lookup/
  cli.py                 # Click CLI
  http_client.py         # requests + fake-useragent + rate limit
  formatters.py          # JSON + pretty text
  platforms/
    tiktok.py            # lookup(username_or_url) -> dict
    instagram.py
    facebook.py
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
