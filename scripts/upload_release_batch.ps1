param(
    [Parameter(Mandatory = $true)][string]$BatchRoot,
    [Parameter(Mandatory = $true)][string]$Tag,
    [Parameter(Mandatory = $true)][string]$BatchId,
    [string]$Repository = "sashkinbro/EmuCoreX-Textures",
    [int]$ExpectedCount = 10
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repositoryParts = $Repository.Split("/")
if ($repositoryParts.Count -ne 2) {
    throw "Repository must use owner/name format."
}
$owner = $repositoryParts[0]
$repositoryName = $repositoryParts[1]
$batchDirectory = (Resolve-Path $BatchRoot).Path
$readyDirectory = Join-Path $batchDirectory "ready"
$manifestPath = Join-Path $batchDirectory "sources.json"
$logDirectory = Join-Path $batchDirectory "logs"
$progressPath = Join-Path $logDirectory "upload-progress.jsonl"
$resultPath = Join-Path $logDirectory "upload-results.json"
$userAgent = "EmuCoreX-catalog-maintenance"

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

function Write-ProgressRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Status,
        [long]$Size = 0,
        [string]$Digest = "",
        [string]$Detail = ""
    )
    [ordered]@{
        timestamp = [DateTime]::UtcNow.ToString("o")
        name = $Name
        status = $Status
        size = $Size
        digest = $Digest
        detail = $Detail
    } | ConvertTo-Json -Compress | Add-Content -LiteralPath $progressPath -Encoding UTF8
}

function Get-GitHubCredential {
    $credentialLines = "protocol=https`nhost=github.com`n`n" | git credential fill
    if ($LASTEXITCODE -ne 0) {
        throw "Git Credential Manager did not return a GitHub credential."
    }
    $fields = @{}
    foreach ($line in $credentialLines) {
        if ($line -match "^([^=]+)=(.*)$") {
            $fields[$matches[1]] = $matches[2]
        }
    }
    if (-not $fields["password"]) {
        throw "Git Credential Manager returned no GitHub token."
    }
    return $fields["password"]
}

function Get-ApiHeaders {
    param([Parameter(Mandatory = $true)][string]$Token)
    return @{
        Accept = "application/vnd.github+json"
        Authorization = "Bearer $Token"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = $userAgent
    }
}

function Get-Release {
    param([Parameter(Mandatory = $true)][string]$Token)
    $uri = "https://api.github.com/repos/$owner/$repositoryName/releases/tags/$Tag"
    return Invoke-RestMethod -Headers (Get-ApiHeaders -Token $Token) -Uri $uri
}

function Get-ReleaseAssets {
    param(
        [Parameter(Mandatory = $true)][string]$Token,
        [Parameter(Mandatory = $true)][long]$ReleaseId
    )
    for ($page = 1; ; $page++) {
        $uri = "https://api.github.com/repos/$owner/$repositoryName/releases/$ReleaseId/assets?per_page=100&page=$page"
        # Windows PowerShell can wrap a JSON array as one nested array when
        # Invoke-RestMethod is called directly inside @(...). Flatten it
        # explicitly so pagination continues once a release exceeds 100 assets.
        $response = Invoke-RestMethod -Headers (Get-ApiHeaders -Token $Token) -Uri $uri
        $responseItems = @($response | ForEach-Object { $_ })
        foreach ($asset in $responseItems) {
            Write-Output $asset
        }
        if ($responseItems.Count -lt 100) {
            break
        }
    }
}

function Remove-FailedAsset {
    param(
        [Parameter(Mandatory = $true)][string]$Token,
        [Parameter(Mandatory = $true)][long]$ReleaseId,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $asset = Get-ReleaseAssets -Token $Token -ReleaseId $ReleaseId |
        Where-Object { $_.name -eq $Name } |
        Select-Object -First 1
    if ($null -ne $asset -and $asset.state -ne "uploaded") {
        $uri = "https://api.github.com/repos/$owner/$repositoryName/releases/assets/$($asset.id)"
        Invoke-RestMethod -Method Delete -Headers (Get-ApiHeaders -Token $Token) -Uri $uri
    }
}

function Upload-Asset {
    param(
        [Parameter(Mandatory = $true)][string]$Token,
        [Parameter(Mandatory = $true)][long]$ReleaseId,
        [Parameter(Mandatory = $true)][System.IO.FileInfo]$File
    )
    $encodedName = [Uri]::EscapeDataString($File.Name)
    $uploadUrl = "https://uploads.github.com/repos/$owner/$repositoryName/releases/$ReleaseId/assets?name=$encodedName"
    $responsePath = Join-Path $logDirectory "$($File.Name).response.json"
    $filePathForCurl = $File.FullName.Replace("\", "/")
    $responsePathForCurl = $responsePath.Replace("\", "/")
    $config = @(
        "url = `"$uploadUrl`""
        "request = `"POST`""
        "header = `"Accept: application/vnd.github+json`""
        "header = `"Authorization: Bearer $Token`""
        "header = `"Content-Type: application/zip`""
        "header = `"User-Agent: $userAgent`""
        "header = `"X-GitHub-Api-Version: 2022-11-28`""
        "upload-file = `"$filePathForCurl`""
        "output = `"$responsePathForCurl`""
        "write-out = `"%{http_code}`""
        "silent"
        "show-error"
    )
    $httpCode = ($config | & curl.exe --config -).Trim()
    $curlExitCode = $LASTEXITCODE
    if ($curlExitCode -ne 0 -or $httpCode -ne "201") {
        $detail = "GitHub returned HTTP $httpCode."
        if (Test-Path -LiteralPath $responsePath) {
            try {
                $detail = [string](Get-Content -LiteralPath $responsePath -Raw |
                    ConvertFrom-Json).message
            } catch {
                # Keep the HTTP detail without exposing response bodies or credentials.
            }
        }
        throw "Upload failed for $($File.Name): curl=$curlExitCode HTTP=$httpCode $detail"
    }
    return Get-Content -LiteralPath $responsePath -Raw | ConvertFrom-Json
}

$token = Get-GitHubCredential
try {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $manifestCount = @($manifest).Count
    if ($manifestCount -ne $ExpectedCount) {
        throw "Expected $ExpectedCount manifest entries, found $manifestCount."
    }
    $expectedNames = @($manifest | ForEach-Object { [string]$_.assetName })
    if (($expectedNames | Sort-Object -Unique).Count -ne $ExpectedCount) {
        throw "Manifest asset names are missing or duplicated."
    }
    $files = @($expectedNames | ForEach-Object {
        $path = Join-Path $readyDirectory $_
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Ready asset is missing: $_"
        }
        Get-Item -LiteralPath $path
    } | Sort-Object Length, Name)

    $release = Get-Release -Token $token
    $results = @()
    foreach ($file in $files) {
        $localSize = [Convert]::ToInt64($file.Length)
        $localDigest = "sha256:$((Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant())"
        $existing = @(Get-ReleaseAssets -Token $token -ReleaseId $release.id |
            Where-Object { $_.name -eq $file.Name }) | Select-Object -First 1
        if ($null -ne $existing) {
            if (
                $existing.state -eq "uploaded" -and
                [Convert]::ToInt64($existing.size) -eq $localSize -and
                [string]$existing.digest -eq $localDigest
            ) {
                Write-ProgressRecord -Name $file.Name -Status "verified-existing" `
                    -Size $localSize -Digest $localDigest
                $results += $existing
                continue
            }
            throw "Release already contains a conflicting asset named $($file.Name)."
        }

        Write-ProgressRecord -Name $file.Name -Status "uploading" `
            -Size $localSize -Digest $localDigest
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                $null = Upload-Asset -Token $token -ReleaseId $release.id -File $file
                break
            } catch {
                Remove-FailedAsset -Token $token -ReleaseId $release.id -Name $file.Name
                if ($attempt -eq 3) {
                    throw
                }
                Start-Sleep -Seconds (5 * $attempt)
            }
        }

        $verified = @(Get-ReleaseAssets -Token $token -ReleaseId $release.id |
            Where-Object { $_.name -eq $file.Name }) | Select-Object -First 1
        if (
            $null -eq $verified -or
            $verified.state -ne "uploaded" -or
            [Convert]::ToInt64($verified.size) -ne $localSize -or
            [string]$verified.digest -ne $localDigest
        ) {
            throw "Post-upload verification failed for $($file.Name)."
        }
        Write-ProgressRecord -Name $file.Name -Status "verified-uploaded" `
            -Size $localSize -Digest $localDigest
        $results += $verified
    }

    $results | Select-Object id, name, size, digest, state, browser_download_url |
        ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-ProgressRecord -Name $BatchId -Status "complete" `
        -Size (($files | Measure-Object Length -Sum).Sum) `
        -Detail "$($files.Count) assets verified"
} catch {
    Write-ProgressRecord -Name $BatchId -Status "failed" -Detail $_.Exception.Message
    throw
} finally {
    $token = $null
}
