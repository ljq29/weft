param(
    [Parameter(Mandatory = $true)]
    [string]$SelectionFile,
    [Parameter(Mandatory = $true)]
    [string]$InsecureHostFile,
    [int]$ProbeTimeoutSeconds = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$OfficialIndex = "https://pypi.org/simple"
$TsinghuaIndex = "https://pypi.tuna.tsinghua.edu.cn/simple"

function Get-PipConfigIndex {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }
    $inGlobal = $false
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or $trimmed.StartsWith(";")) {
            continue
        }
        if ($trimmed -match '^\[(.+)\]$') {
            $inGlobal = $Matches[1].Trim().ToLowerInvariant() -eq "global"
            continue
        }
        if ($inGlobal -and $trimmed -match '^(?i:index-url)\s*=\s*(.+)$') {
            return $Matches[1].Trim()
        }
    }
    return $null
}

function Get-ConfiguredIndex {
    $pipEnvironment = [Environment]::GetEnvironmentVariable("PIP_INDEX_URL")
    if (-not [string]::IsNullOrWhiteSpace($pipEnvironment)) {
        return $pipEnvironment.Trim()
    }
    $uvEnvironment = [Environment]::GetEnvironmentVariable("UV_INDEX_URL")
    if (-not [string]::IsNullOrWhiteSpace($uvEnvironment)) {
        return $uvEnvironment.Trim()
    }

    $paths = @([Environment]::GetEnvironmentVariable("PIP_CONFIG_FILE"))
    $appData = [Environment]::GetEnvironmentVariable("APPDATA")
    $programData = [Environment]::GetEnvironmentVariable("ProgramData")
    $userProfile = [Environment]::GetEnvironmentVariable("USERPROFILE")
    if ($appData) {
        $paths += Join-Path $appData "pip\pip.ini"
    }
    if ($programData) {
        $paths += Join-Path $programData "pip\pip.ini"
    }
    if ($userProfile) {
        $paths += Join-Path $userProfile "pip\pip.ini"
        $paths += Join-Path $userProfile ".pip\pip.conf"
    }
    foreach ($path in $paths) {
        $index = Get-PipConfigIndex -Path $path
        if (-not [string]::IsNullOrWhiteSpace($index)) {
            return $index
        }
    }
    return $null
}

function Get-DisplayIndex {
    param([string]$Url)

    $uri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri)) {
        return "地址无效"
    }
    if (-not $uri.UserInfo) {
        return $Url
    }
    $builder = New-Object System.UriBuilder($uri)
    $builder.UserName = ""
    $builder.Password = ""
    return $builder.Uri.AbsoluteUri
}

function Get-ExceptionDetail {
    param(
        [System.Exception]$Exception,
        [Uri]$Uri
    )

    $current = $Exception
    while ($null -ne $current.InnerException) {
        $current = $current.InnerException
    }
    $message = $current.Message
    if ($Uri.UserInfo) {
        $message = $message.Replace($Uri.UserInfo, "<redacted>")
    }
    return "$($current.GetType().Name): $message"
}

function Test-Index {
    param([string]$Url)

    $uri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri)) {
        $script:ProbeDetail = "地址无效或不是绝对 URL"
        return $false
    }
    if ($uri.Scheme -ne "http" -and $uri.Scheme -ne "https") {
        $script:ProbeDetail = "只支持 HTTP/HTTPS，实际为 $($uri.Scheme)"
        return $false
    }

    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object System.Net.Http.HttpClientHandler
    if ($uri.UserInfo) {
        $parts = $uri.UserInfo.Split(":", 2)
        $username = [Uri]::UnescapeDataString($parts[0])
        $password = ""
        if ($parts.Count -eq 2) {
            $password = [Uri]::UnescapeDataString($parts[1])
        }
        $handler.Credentials = New-Object System.Net.NetworkCredential($username, $password)
        $handler.PreAuthenticate = $true
    }
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds($ProbeTimeoutSeconds)
    $response = $null
    try {
        $response = $client.GetAsync(
            $uri,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        $script:ProbeDetail = "HTTP $([int]$response.StatusCode) $($response.ReasonPhrase)"
        return $response.IsSuccessStatusCode
    }
    catch {
        $script:ProbeDetail = Get-ExceptionDetail -Exception $_.Exception -Uri $uri
        return $false
    }
    finally {
        if ($null -ne $response) {
            $response.Dispose()
        }
        $client.Dispose()
        $handler.Dispose()
    }
}

$configuredIndex = Get-ConfiguredIndex
$configuredDisplay = if ([string]::IsNullOrWhiteSpace($configuredIndex)) {
    "未配置"
} else {
    Get-DisplayIndex -Url $configuredIndex
}
$selectedIndex = $null
$forceConfigured = [Environment]::GetEnvironmentVariable("WEFT_FORCE_CONFIGURED_INDEX") -eq "1"
if ($forceConfigured) {
    if ([string]::IsNullOrWhiteSpace($configuredIndex)) {
        throw "未找到已有 pip 源，无法强制使用；请先配置 pip 或改用 --index-url。"
    }
    $selectedIndex = $configuredIndex
    Write-Host "跳过可用性检测，强制使用已有 pip 源：$configuredDisplay"
} else {
    $configuredAvailable = $false
    $ProbeDetail = "未检测"
    if (-not [string]::IsNullOrWhiteSpace($configuredIndex)) {
        Write-Host "正在检测已有 pip 源：$configuredDisplay"
        $configuredAvailable = Test-Index -Url $configuredIndex
        if ($configuredAvailable) {
            Write-Host "已有 pip 源检测成功：$ProbeDetail"
        }
        else {
            Write-Host "已有 pip 源检测失败：$ProbeDetail"
        }
    }

    Write-Host ""
    Write-Host "首次安装需要下载 Python 依赖，请选择软件包源："
    Write-Host "  1. PyPI 官方源 ($OfficialIndex)"
    $configuredStatus = if ($configuredAvailable) { "可用" } else { "不可用" }
    Write-Host "  2. 已有 pip 源 ($configuredDisplay；$configuredStatus)"
    Write-Host "  3. 清华大学镜像源 ($TsinghuaIndex)"
    Write-Host "  4. 强制使用已有 pip 源（跳过检测；$configuredDisplay）"
    $defaultChoice = if ($configuredAvailable) { "2" } else { "1" }

    for ($attempt = 0; $attempt -lt 10 -and $null -eq $selectedIndex; $attempt++) {
        $choice = Read-Host "请输入 1、2、3 或 4（直接回车选择 $defaultChoice）"
        if ([string]::IsNullOrWhiteSpace($choice)) {
            $choice = $defaultChoice
        }
        switch ($choice.Trim()) {
            "1" { $selectedIndex = $OfficialIndex }
            "2" {
                if ($configuredAvailable) {
                    $selectedIndex = $configuredIndex
                }
                else {
                    Write-Host "已有 pip 源未配置或当前不可用；请选择其他源，或输入 4 强制使用。"
                }
            }
            "3" { $selectedIndex = $TsinghuaIndex }
            "4" {
                if (-not [string]::IsNullOrWhiteSpace($configuredIndex)) {
                    $selectedIndex = $configuredIndex
                }
                else {
                    Write-Host "未找到已有 pip 源，请选择其他源。"
                }
            }
            default { Write-Host "输入无效，请输入 1、2、3 或 4。" }
        }
    }
    if ($null -eq $selectedIndex) {
        throw "未收到有效的软件包源选择；非交互安装请使用 --index-url、--china 或 --force-configured-index。"
    }
}

$selectionDirectory = Split-Path -Parent $SelectionFile
if (-not (Test-Path -LiteralPath $selectionDirectory)) {
    [void](New-Item -ItemType Directory -Path $selectionDirectory -Force)
}
[System.IO.File]::WriteAllText(
    $SelectionFile,
    $selectedIndex + [Environment]::NewLine,
    (New-Object System.Text.UTF8Encoding($false))
)
if (Test-Path -LiteralPath $InsecureHostFile) {
    Remove-Item -LiteralPath $InsecureHostFile -Force
}
$selectedUri = New-Object System.Uri($selectedIndex)
if ($selectedUri.Scheme -eq "http") {
    [System.IO.File]::WriteAllText(
        $InsecureHostFile,
        $selectedUri.Authority + [Environment]::NewLine,
        (New-Object System.Text.UTF8Encoding($false))
    )
}
Write-Host "已选择软件包源：$(Get-DisplayIndex -Url $selectedIndex)"
