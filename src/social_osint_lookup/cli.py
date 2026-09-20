"""CLI entrypoint for social-osint-lookup."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from social_osint_lookup import __version__
from social_osint_lookup.formatters import to_json, to_pretty
from social_osint_lookup.platforms import PLATFORMS


def _lookup(platform: str, target: str) -> dict:
    mod = PLATFORMS[platform]
    return mod.lookup(target)


def _emit(data: dict | list, *, fmt: str, output: str | None) -> None:
    if fmt == "json":
        text = to_json(data)
    else:
        if isinstance(data, list):
            text = "\n".join(to_pretty(item) for item in data)
        else:
            text = to_pretty(data)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"Wrote {output}", err=True)
    else:
        click.echo(text, nl=False)


@click.group()
@click.version_option(__version__, prog_name="social-osint-lookup")
def main() -> None:
    """Public-profile OSINT lookup for TikTok, Instagram, and Facebook.

    Educational / research use only. Public pages only — no login bypass,
    no private data, no credential stuffing.
    """


@main.command("lookup")
@click.argument("target")
@click.option(
    "-p",
    "--platform",
    type=click.Choice(["tiktok", "instagram", "facebook", "all"], case_sensitive=False),
    default="all",
    show_default=True,
    help="Platform to query (or all three).",
)
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(["pretty", "json"], case_sensitive=False),
    default="pretty",
    show_default=True,
)
@click.option("-o", "--output", type=click.Path(dir_okay=False), default=None)
def cmd_lookup(target: str, platform: str, fmt: str, output: str | None) -> None:
    """Look up public profile info for TARGET (username or profile URL)."""
    platform = platform.lower()
    try:
        if platform == "all":
            results = []
            for name in ("tiktok", "instagram", "facebook"):
                try:
                    results.append(_lookup(name, target))
                except ValueError as exc:
                    results.append(
                        {
                            "platform": name,
                            "query": target,
                            "found": False,
                            "error": str(exc),
                        }
                    )
            _emit(results, fmt=fmt, output=output)
        else:
            result = _lookup(platform, target)
            _emit(result, fmt=fmt, output=output)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(f"lookup failed: {exc}") from exc


@main.command("tiktok")
@click.argument("target")
@click.option("-f", "--format", "fmt", type=click.Choice(["pretty", "json"]), default="pretty")
@click.option("-o", "--output", type=click.Path(dir_okay=False), default=None)
def cmd_tiktok(target: str, fmt: str, output: str | None) -> None:
    """Look up a public TikTok profile."""
    try:
        _emit(_lookup("tiktok", target), fmt=fmt, output=output)
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(str(exc)) from exc


@main.command("instagram")
@click.argument("target")
@click.option("-f", "--format", "fmt", type=click.Choice(["pretty", "json"]), default="pretty")
@click.option("-o", "--output", type=click.Path(dir_okay=False), default=None)
def cmd_instagram(target: str, fmt: str, output: str | None) -> None:
    """Look up a public Instagram profile."""
    try:
        _emit(_lookup("instagram", target), fmt=fmt, output=output)
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(str(exc)) from exc


@main.command("facebook")
@click.argument("target")
@click.option("-f", "--format", "fmt", type=click.Choice(["pretty", "json"]), default="pretty")
@click.option("-o", "--output", type=click.Path(dir_okay=False), default=None)
def cmd_facebook(target: str, fmt: str, output: str | None) -> None:
    """Look up a public Facebook profile or page."""
    try:
        _emit(_lookup("facebook", target), fmt=fmt, output=output)
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(str(exc)) from exc


@main.command("platforms")
def cmd_platforms() -> None:
    """List supported platforms and what each covers."""
    click.echo(
        """Supported platforms (public pages only):

  tiktok     username/URL → display name, bio, follower/following/likes,
             video count, verified/private, user id, profile URL
             (via __UNIVERSAL_DATA_FOR_REHYDRATION__ / SIGI_STATE / meta)

  instagram  username/URL → display name, bio, follower/following/posts,
             verified/private when public, profile URL
             (via _sharedData / og:description meta)

  facebook   username/slug/URL → public name, about snippet, entity type
             (page vs profile when detectable), profile URL
             (via Open Graph / ld+json meta)
"""
    )


if __name__ == "__main__":
    main(sys.argv[1:])
