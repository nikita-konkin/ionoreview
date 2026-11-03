param(
    [string]$Python = "python",
    [string]$OutputRoot = (Join-Path $env:LOCALAPPDATA "IonoReview\build")
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$output = [System.IO.Path]::GetFullPath($OutputRoot)
if ($output.TrimEnd('\') -eq [System.IO.Path]::GetPathRoot($output).TrimEnd('\') -or $output.TrimEnd('\') -eq $repo.TrimEnd('\')) {
    throw "OutputRoot must be a dedicated build folder, not a drive or project root"
}
if ($output.StartsWith((Join-Path $repo 'datasets'), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must be outside the annotation datasets"
}
New-Item -ItemType Directory -Force -Path $output | Out-Null
$distribution = Join-Path $output "dist"
$work = Join-Path $output "work"
& $Python -m PyInstaller --noconfirm --clean --distpath $distribution --workpath $work (Join-Path $repo "packaging\ionoreview.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
$app = Join-Path $distribution "IonoReview"
Copy-Item -LiteralPath (Join-Path $repo "docs\WINDOWS_BUILD.md") -Destination (Join-Path $app "README-Windows.md")
$report = Join-Path $output "frozen-self-test.json"
$executable = Join-Path $app "IonoReview.exe"
$process = Start-Process -FilePath $executable -ArgumentList @("--self-test", ('"' + $report + '"')) -PassThru -WindowStyle Hidden
if (-not $process.WaitForExit(120000)) {
    $process.Kill()
    throw "Frozen self-test did not exit within 120 seconds"
}
if ($process.ExitCode -ne 0) { throw "Frozen self-test failed with exit code $($process.ExitCode). See $report" }
$result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if (-not $result.ok -or -not $result.frozen) { throw "Frozen self-test report is invalid" }
# Ensure accidental imports cannot silently turn the reviewer into a CUDA/LLM distribution.
$forbidden = Get-ChildItem -LiteralPath $app -Directory -Recurse | Where-Object { $_.Name -in @('torch','transformers','bitsandbytes','training_data') }
foreach ($name in @('datasets','references')) {
    if (Test-Path -LiteralPath (Join-Path $app $name)) { throw "Unexpected user data folder in distribution: $name" }
}
if ($forbidden) { throw "Unexpected heavyweight package/data in distribution: $($forbidden.FullName -join ', ')" }
$archive = Join-Path $output "IonoReview-windows-x64.zip"
Compress-Archive -Path $app -DestinationPath $archive -Force
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  IonoReview-windows-x64.zip" | Set-Content -LiteralPath ($archive + '.sha256') -Encoding ascii
Write-Output "Build: $executable"
Write-Output "Archive: $archive"
Write-Output "Self-test: $report"
