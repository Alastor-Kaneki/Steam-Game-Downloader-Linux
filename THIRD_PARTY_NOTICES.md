# Third-party notices

## SteamRE/DepotDownloader

- Project: SteamRE/DepotDownloader
- Pinned release: DepotDownloader 3.4.0
- License: GNU General Public License v2.0
- Changes: machine-readable QR/account markers, owned-license app enumeration, and JSON library output.

DepotDownloader includes or references SteamKit2, protobuf-net, QRCoder, and Microsoft.Windows.CsWin32 under their respective licenses. The AppImage build obtains these dependencies from the pinned upstream project and NuGet during CI.

## qrcode

The Python `qrcode` package is used only to render the challenge URL supplied by SteamKit2 into the GUI canvas. Its license is BSD-3-Clause.
