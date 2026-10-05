param(
    [Parameter(Mandatory = $true)]
    [string] $ProgId,
    [Parameter(Mandatory = $true)]
    [string] $Extensions
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'SFTA.ps1')
$failed = @()
foreach ($extension in $Extensions.Split(',')) {
    if ($extension -notmatch '^\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v|mpeg|mpg|3gp)$') {
        throw "Unsupported video extension: $extension"
    }
    try {
        Set-FTA -ProgId $ProgId -Extension $extension
        if ((Get-FTA -Extension $extension) -ne $ProgId) {
            throw 'UserChoice verification failed'
        }
        Write-Output "OK $extension"
    }
    catch {
        $failed += $extension
        Write-Output "FAILED $extension : $($_.Exception.Message)"
    }
}
if ($failed.Count -gt 0) {
    exit 1
}