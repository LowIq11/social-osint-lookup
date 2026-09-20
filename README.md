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


## Notes on TikTok parsing

TikTok's public profile HTML embeds `__UNIVERSAL_DATA_FOR_REHYDRATION__`. This tool
parses that SSR JSON (not a thin stats-only endpoint). If compressed responses are
not decoded (e.g. Brotli without the `brotli` package), the page looks empty and
fields fall back to null — `brotli` is now a dependency so decoding works.

Fields such as bio, location, username/display-name history, and creator badge
are returned **only when present in the payload**. Public pages typically expose
`createTime`, `uniqueIdModifyTime`, and `nickNameModifyTime` but **not** region,
history arrays, or location-at-creation. Missing keys stay `null` with
`field_availability: unavailable` — we do not invent values. Optional session
cookie mode may surface richer keys when TikTok includes them for logged-in HTML.

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
| `location` | string or `null` (current region when public) |
| `location_at_creation` | string or `null` — **not** in public TikTok HTML; needs authenticated/internal |
| `account_created_at` | ISO-8601 string or `null` |
| `username_history` | `[{username, changed_at, location_at_change}]` or `null` — full prior handles **not** in public TikTok HTML |
| `display_name_history` | `[{display_name, changed_at, location_at_change}]` or `null` — full nickname history **not** in public TikTok HTML |
| `username_last_changed_at` | ISO-8601 or `null` — TikTok `uniqueIdModifyTime` (**last** change only, not a history) |
| `display_name_last_changed_at` | ISO-8601 or `null` — TikTok `nickNameModifyTime` (**last** change only) |
| `tiktok_creator_level` | string or `null` (TikTok only; always `null` elsewhere) |
| `auth_mode` | TikTok: `"public"` or `"session_cookie"` |
| `field_availability` | per-field `"available"` / `"unavailable"` / `"n/a"` |

`username_history[].location_at_change` / display-name equivalents are filled
**only** if the payload actually includes them. Public unauthenticated TikTok
pages for typical accounts expose **neither** history arrays nor location-at-
creation — those require authenticated/internal TikTok access.

### Field × platform support matrix

| Field | TikTok (public / unauthenticated) | Instagram | X (Twitter) |
|-------|-------------------------------------|-----------|-------------|
| `location` | Sometimes (`user.region` / related); often absent | Rare (`city_name` / business address / ld+json) | Often (`location` / ld+json) |
| `location_at_creation` | **Unavailable** publicly → `null` (requires auth/internal) | **Unavailable** | **Unavailable** |
| `account_created_at` | Often (`createTime` → ISO) | **Unavailable** from public profile page | Often (`created_at` / “Joined …”) |
| `username_history` | **Unavailable** publicly (no `uniqueIdHistory` array) → `null` | **Unavailable** | **Unavailable** |
| `username_last_changed_at` | Often (`uniqueIdModifyTime` → ISO) — last change only | **n/a** | **n/a** |
| `display_name_history` | **Unavailable** publicly → `null` (requires auth/internal) | **Unavailable** | **Unavailable** |
| `display_name_last_changed_at` | Often (`nickNameModifyTime` → ISO) — last change only | **n/a** | **n/a** |
| `username_history[].changed_at` / `location_at_change` | Only if a real history item is present (typically absent publicly) | n/a | n/a |
| `tiktok_creator_level` | When `creatorLevel` / `supportLevel` / commerce badge keys exist | **n/a** | **n/a** |

Optional TikTok **session cookie** mode may return richer keys when TikTok includes
them in the logged-in HTML/JSON. The scraper still only reports fields that are
actually present — it never invents history.

## Platform coverage (honest)

### TikTok

| Field | Source |
|-------|--------|
| username, display name, bio | `__UNIVERSAL_DATA_FOR_REHYDRATION__` → `webapp.user-detail.userInfo` (fallback: `SIGI_STATE`, then og meta) |
| follower / following / likes / video counts | Same rehydration `stats` when present |
| user id, secUid, verified, private | Public user object when present |
| location | `user.region` / related when present (often absent on public pages) |
| location_at_creation | **Not** in public user object → `null` (requires authenticated/internal) |
| account_created_at | `user.createTime` (unix → ISO-8601 UTC) |
| username_last_changed_at | `user.uniqueIdModifyTime` (last username change only — **not** prior handles) |
| display_name_last_changed_at | `user.nickNameModifyTime` (last nickname change only — **not** prior names) |
| username_history | `uniqueIdHistory` / similar **only if present** (absent on typical public pages) |
| display_name_history | `nickNameHistory` / similar **only if present** (absent on typical public pages) |
| tiktok_creator_level | `creatorLevel` / `supportLevel` / commerce badge keys when present |
| profile URL | `https://www.tiktok.com/@{username}` |
| auth_mode | `public` or `session_cookie` |

Accepts `@user`, bare username, profile URL, or numeric share id (`/share/user/{id}`).

#### Optional authenticated mode (your own browser cookie)

Some depth (full username/display-name change history with dates/locations,
location at account creation) is **not** available from unauthenticated public
HTML. If **you** are logged into TikTok in your browser, you can optionally pass
**your** session cookie so requests include a `Cookie` header:

1. Open https://www.tiktok.com while logged in.
2. DevTools → **Application** → **Cookies** → `https://www.tiktok.com`.
3. Copy the `sessionid` value (or `sid_guard`). Prefer setting it locally — **never
   paste the cookie into chat, tickets, or commits**.
4. On **your machine** only:

```bash
export TIKTOK_SESSION_COOKIE='sessionid=YOUR_VALUE_HERE'
social-osint-lookup tiktok @someone -f json
# or:
social-osint-lookup tiktok @someone --session-cookie 'sessionid=YOUR_VALUE_HERE'
# alias:
social-osint-lookup tiktok @someone --tiktok-session-cookie 'sessionid=YOUR_VALUE_HERE'
```

**Warnings**
- The cookie is equivalent to being logged in. Treat it as a password.
- This tool never stores, logs, prints, or commits the cookie. Errors are redacted.
- No captcha bypass, no credential phishing, no cookie harvesting from others.
- Even with a cookie, fields stay `null` unless TikTok actually returns them.

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
