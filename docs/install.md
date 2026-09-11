# Install Stamp CLI

[Back to the overview](../README.md)

## Homebrew

```bash
brew install paperfoot/tap/stamp-cli
stamp --version
```

Homebrew manages the Python runtime and application dependencies. Upgrade with:

```bash
brew update
brew upgrade paperfoot/tap/stamp-cli
```

## uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv tool install --python 3.14 https://github.com/paperfoot/stamp-cli/releases/download/v0.3.2/stamp_cli-0.3.2-py3-none-any.whl
stamp --version
```

uv manages Python and keeps the application in its own environment. If `stamp` is not found after installation, run `uv tool update-shell`, then open a new terminal.

To upgrade an older GitHub installation, run the command above with `--force --reinstall`. Published wheels and source archives are listed under [Releases](https://github.com/paperfoot/stamp-cli/releases).

## Fonts

macOS supplies the standard Latin and CJK fonts used by most styles. On Debian or Ubuntu, install the common substitutes:

```bash
sudo apt-get install fontconfig fonts-arphic-ukai fonts-arphic-uming fonts-dejavu-core fonts-liberation fonts-noto-cjk
```

Check available fonts and rendering support:

```bash
stamp fonts
stamp doctor
```

Some decorative symbols need the optional Noto symbol fonts. Fetch them explicitly when needed:

```bash
stamp fonts --fetch
```

These downloads contain fonts only and do not upload your input. Styles also accept explicit font paths through `--font`, `--zh-font`, or `--script-font` where relevant.

## Platform support

The test matrix covers macOS and Linux on Python 3.12 and 3.14. Other systems are not part of the verified matrix. Rendering depends on the fonts available on the machine; PNG carries the finished appearance, while SVG text requires matching fonts.

Choose either Homebrew or uv for everyday use. If you have both installed, `command -v stamp` tells you which copy your shell runs.
