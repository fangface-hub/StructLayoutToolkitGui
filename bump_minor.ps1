$tomlFile = "pyproject.toml"
$content = Get-Content $tomlFile -Raw
$versionMatch = [regex]::Match($content, 'version\s*=\s*"(\d+)\.(\d+)\.(\d+)"')

if ($versionMatch.Success) {
    $major = [int]$versionMatch.Groups[1].Value
    $minor = [int]$versionMatch.Groups[2].Value
    $patch = [int]$versionMatch.Groups[3].Value

    $newMinor = $minor + 1
    $newVersion = "$major.$newMinor.0"
    
    $newContent = $content -replace 'version\s*=\s*"\d+\.\d+\.\d+"', "version = `"$newVersion`""
    Set-Content $tomlFile $newContent -NoNewline
    Write-Host "Bumped version to $newVersion"
} else {
    Write-Error "Could not find version in $tomlFile"
}
