# Steam Library Downloader for Linux

A Linux desktop counterpart to the Android Steam downloader. It signs into the user's own Steam account through a **real, scannable Steam Mobile QR code**, lists apps present in the account's Steam licenses, and downloads selected app depots through a patched, pinned build of [SteamRE/DepotDownloader](https://github.com/SteamRE/DepotDownloader).

> This project is not affiliated with Valve or Steam. It is intended only for content the signed-in account is licensed to access.

## Features

- In-app QR sign-in rendered as a crisp black-and-white canvas.
- Steam Mobile scan/approval flow; no Steam password is collected by the GUI.
- Saved local refresh session through DepotDownloader's credential store.
- Searchable owned-app library with AppID and Steam app type.
- Downloads Linux, Windows, or macOS depots.
- Architecture, language, branch, destination, validation-ready backend options.
- Streaming backend log, parsed progress, cancellation, and open-folder action.
- AMOLED-first dark desktop interface.
- AppImage build that bundles Python, Tk, and a self-contained .NET 9 DepotDownloader backend.

## Authentication design

The AppImage builds DepotDownloader 3.4.0 from source and applies a small patch:

- `@@STEAM_QR@@<challenge-url>` lets the GUI render Steam's current challenge as a real QR image.
- `@@STEAM_ACCOUNT@@<account-name>` identifies the approved account locally.
- `-list-owned-json` enumerates account package licenses and resolves their app metadata through SteamKit2.
- `@@OWNED_APPS@@<json>` transfers the owned library to the GUI.

The same DepotDownloader credential store is reused for downloads, so the QR login that lists the library also authorizes the selected game's content. Session data is isolated under `~/.local/share/steam-library-downloader/backend-home` and is removed by **Sign out**.

## Build the AppImage

Requirements: Linux x86-64, Python 3, Git, .NET 9 SDK, `python3-tk`, and network access for NuGet/AppImage tooling.

```bash
./tools/build_appimage.sh
```

Output:

```text
dist/Steam-Library-Downloader-0.1.0-x86_64.AppImage
dist/SHA256SUMS.txt
```

GitHub Actions runs the same build and publishes artifacts. Tagging `v0.1.0` also creates a release.

## Package format

The supported release format is **AppImage**. A Flatpak build is intentionally not shipped yet because the sandbox needs a separately maintained set of offline NuGet/Python source declarations and broad destination-folder access.

## Development run

Build the patched backend first, then point the GUI at it:

```bash
export STEAM_DL_BACKEND=/absolute/path/to/DepotDownloader
python3 -m pip install -r requirements.txt
./tools/run_dev.sh
```

## Notes

- The initial packaged target is x86-64 Linux, matching typical CachyOS/Arch desktop systems.
- Steam may expose licenses that are tools, DLC helpers, runtimes, or test apps in addition to conventional games; the library view shows Steam's `type` field and supports filtering.
- Downloading an app does not install it into the official Steam client's library database. It downloads the account-authorized depot files into the chosen folder.
- Anti-cheat, DRM launchers, and redistributable installers may still affect whether a downloaded game can be run outside the official Steam client.

## Licensing

The application is GPL-2.0-only. The build includes a modified DepotDownloader 3.4.0 backend, also GPL-2.0. See `THIRD_PARTY_NOTICES.md`.
