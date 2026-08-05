#!/usr/bin/env python3
"""Patch DepotDownloader 3.4.0 with GUI-safe QR and owned-library JSON modes."""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text("utf-8-sig")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one marker in {path}, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new), "utf-8")


def patch(root: Path) -> None:
    program = root / "DepotDownloader" / "Program.cs"
    session = root / "DepotDownloader" / "Steam3Session.cs"
    downloader = root / "DepotDownloader" / "ContentDownloader.cs"

    replace_once(
        program,
        "using System.Text.RegularExpressions;\n",
        "using System.Text.RegularExpressions;\nusing System.Text.Json;\n",
    )
    replace_once(
        program,
        "            #endregion\n\n            var appId = GetParameter(args, \"-app\", ContentDownloader.INVALID_APP_ID);",
        """            #endregion

            if (HasParameter(args, "--sld-version"))
            {
                Console.WriteLine("@@SLD_BACKEND@@1");
                return 0;
            }

            var listOwned = HasParameter(args, "-list-owned-json");
            if (listOwned)
            {
                PrintUnconsumedArgs(args);

                if (!InitializeSteam(username, password))
                {
                    Console.WriteLine("Error: InitializeSteam failed");
                    return 1;
                }

                try
                {
                    var apps = await ContentDownloader.GetOwnedAppsAsync().ConfigureAwait(false);
                    Console.WriteLine("@@OWNED_APPS@@" + JsonSerializer.Serialize(apps));
                }
                catch (Exception ex)
                {
                    Console.WriteLine("Failed to list owned apps: {0}", ex.Message);
                    return 1;
                }
                finally
                {
                    ContentDownloader.ShutdownSteam3();
                }

                return 0;
            }

            var appId = GetParameter(args, "-app", ContentDownloader.INVALID_APP_ID);""",
    )

    replace_once(
        session,
        "                        logonDetails.AccessToken = result.RefreshToken;\n",
        "                        logonDetails.AccessToken = result.RefreshToken;\n                        Console.WriteLine($\"@@STEAM_ACCOUNT@@{result.AccountName}\");\n",
    )
    replace_once(
        session,
        "        private static void DisplayQrCode(string challengeUrl)\n        {\n            // Encode the link as a QR code\n",
        "        private static void DisplayQrCode(string challengeUrl)\n        {\n            Console.WriteLine($\"@@STEAM_QR@@{challengeUrl}\");\n            if (Environment.GetEnvironmentVariable(\"STEAM_LIBRARY_DOWNLOADER_GUI\") == \"1\")\n                return;\n\n            // Encode the link as a QR code\n",
    )
    marker = "        public async Task RequestPackageInfo(IEnumerable<uint> packageIds)\n"
    batch_method = """        public async Task RequestAppInfo(IEnumerable<uint> appIds)
        {
            var requested = appIds.Distinct().Where(appId => !AppInfo.ContainsKey(appId)).ToList();
            if (requested.Count == 0 || bAborted)
                return;

            var appTokens = await steamApps.PICSGetAccessTokens(requested, []);
            foreach (var token in appTokens.AppTokens)
            {
                AppTokens[token.Key] = token.Value;
            }

            foreach (var batch in requested.Chunk(200))
            {
                var requests = new List<SteamApps.PICSRequest>();
                foreach (var appId in batch)
                {
                    var request = new SteamApps.PICSRequest(appId);
                    if (AppTokens.TryGetValue(appId, out var token))
                        request.AccessToken = token;
                    requests.Add(request);
                }

                var appInfoMultiple = await steamApps.PICSGetProductInfo(requests, []);
                foreach (var appInfo in appInfoMultiple.Results)
                {
                    foreach (var appValue in appInfo.Apps)
                    {
                        AppInfo[appValue.Key] = appValue.Value;
                    }

                    foreach (var unknown in appInfo.UnknownApps)
                    {
                        AppInfo[unknown] = null;
                    }
                }
            }
        }

"""
    replace_once(session, marker, batch_method + marker)

    record_marker = "    static class ContentDownloader\n    {\n"
    replace_once(
        downloader,
        record_marker,
        record_marker + "        internal sealed record OwnedAppInfo(uint AppId, string Name, string Type);\n\n",
    )
    method_marker = "        static uint GetSteam3AppBuildNumber(uint appId, string branch)\n"
    owned_method = """        internal static async Task<List<OwnedAppInfo>> GetOwnedAppsAsync()
        {
            if (steam3 == null || steam3.steamUser.SteamID == null || steam3.steamUser.SteamID.AccountType == EAccountType.AnonUser)
                throw new ContentDownloaderException("A signed-in Steam account is required.");

            for (var attempt = 0; attempt < 100 && steam3.Licenses == null; attempt++)
                await Task.Delay(100);

            if (steam3.Licenses == null)
                throw new ContentDownloaderException("Steam did not return the account license list.");

            var packageIds = steam3.Licenses.Select(license => license.PackageID).Distinct().ToList();
            await steam3.RequestPackageInfo(packageIds);

            var appIds = new HashSet<uint>();
            foreach (var packageId in packageIds)
            {
                if (!steam3.PackageInfo.TryGetValue(packageId, out var package) || package == null)
                    continue;

                foreach (var child in package.KeyValues["appids"].Children)
                {
                    var appId = child.AsUnsignedInteger();
                    if (appId > 0)
                        appIds.Add(appId);
                }
            }

            await steam3.RequestAppInfo(appIds);

            var result = new List<OwnedAppInfo>();
            foreach (var appId in appIds)
            {
                var common = GetSteam3AppSection(appId, EAppInfoSection.Common);
                if (common == null || common == KeyValue.Invalid)
                    continue;

                var name = common["name"].Value;
                var type = common["type"].Value;
                if (string.IsNullOrWhiteSpace(name))
                    continue;

                result.Add(new OwnedAppInfo(appId, name, type ?? string.Empty));
            }

            return result
                .OrderBy(app => app.Name, StringComparer.OrdinalIgnoreCase)
                .ThenBy(app => app.AppId)
                .ToList();
        }

"""
    replace_once(downloader, method_marker, owned_method + method_marker)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Path to a DepotDownloader 3.4.0 checkout")
    args = parser.parse_args()
    patch(args.source.resolve())
