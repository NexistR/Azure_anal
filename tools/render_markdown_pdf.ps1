[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$OutputPdf
)

$ErrorActionPreference = "Stop"

function Convert-InlineMarkdown {
    param([string]$Text)

    $encoded = [Net.WebUtility]::HtmlEncode($Text)
    $encoded = [regex]::Replace($encoded, '\*\*(.+?)\*\*', '<strong>$1</strong>')
    $encoded = [regex]::Replace($encoded, '`([^`]+)`', '<code>$1</code>')
    return $encoded
}

function Split-MarkdownTableRow {
    param([string]$Text)

    return @(($Text.Trim().Trim('|') -split '\|') | ForEach-Object { $_.Trim() })
}

$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$outputPath = [IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPdf))
$projectRoot = Split-Path -Parent $PSScriptRoot
$renderDirectory = Join-Path $projectRoot ".tools\render"
$htmlPath = Join-Path $renderDirectory (([IO.Path]::GetFileNameWithoutExtension($outputPath)) + ".html")
$profilePath = Join-Path $renderDirectory "chrome-profile"
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"

if (-not (Test-Path -LiteralPath $chromePath)) {
    throw "Google Chrome was not found at $chromePath"
}

New-Item -ItemType Directory -Path $renderDirectory, $profilePath -Force | Out-Null
$lines = @(Get-Content -LiteralPath $sourcePath -Encoding UTF8)
$body = [Text.StringBuilder]::new()
$index = 0

while ($index -lt $lines.Count) {
    $line = $lines[$index]
    $trimmed = $line.Trim()

    if ($trimmed.Length -eq 0) {
        $index++
        continue
    }

    if ($trimmed.StartsWith('```')) {
        $language = $trimmed.Substring(3).Trim()
        $index++
        $codeLines = [Collections.Generic.List[string]]::new()
        while ($index -lt $lines.Count -and -not $lines[$index].Trim().StartsWith('```')) {
            $codeLines.Add($lines[$index])
            $index++
        }
        if ($index -lt $lines.Count) { $index++ }
        $languageClass = if ($language) { " class=`"language-$([Net.WebUtility]::HtmlEncode($language))`"" } else { "" }
        $code = [Net.WebUtility]::HtmlEncode(($codeLines -join [Environment]::NewLine))
        [void]$body.AppendLine("<pre><code$languageClass>$code</code></pre>")
        continue
    }

    if ($trimmed -match '^(#{1,4})\s+(.+)$') {
        $level = $matches[1].Length
        $heading = Convert-InlineMarkdown $matches[2]
        [void]$body.AppendLine("<h$level>$heading</h$level>")
        $index++
        continue
    }

    if ($trimmed.StartsWith('>')) {
        $quoteLines = [Collections.Generic.List[string]]::new()
        while ($index -lt $lines.Count -and $lines[$index].Trim().StartsWith('>')) {
            $quoteLines.Add((Convert-InlineMarkdown ($lines[$index].Trim().Substring(1).Trim())))
            $index++
        }
        [void]$body.AppendLine("<blockquote><p>$($quoteLines -join '<br>')</p></blockquote>")
        continue
    }

    $hasTableSeparator = $false
    if ($trimmed.StartsWith('|') -and $index + 1 -lt $lines.Count) {
        $nextLine = $lines[$index + 1].Trim()
        $hasTableSeparator = $nextLine.StartsWith('|') -and
            $nextLine.Contains('---') -and
            (($nextLine -replace '[\|:\-\s]', '').Length -eq 0)
    }

    if ($hasTableSeparator) {
        $headers = Split-MarkdownTableRow $line
        [void]$body.AppendLine('<table><thead><tr>')
        foreach ($header in $headers) {
            [void]$body.AppendLine("<th>$(Convert-InlineMarkdown $header)</th>")
        }
        [void]$body.AppendLine('</tr></thead><tbody>')
        $index += 2
        while ($index -lt $lines.Count -and $lines[$index].Trim().StartsWith('|')) {
            $cells = Split-MarkdownTableRow $lines[$index]
            [void]$body.AppendLine('<tr>')
            foreach ($cell in $cells) {
                [void]$body.AppendLine("<td>$(Convert-InlineMarkdown $cell)</td>")
            }
            [void]$body.AppendLine('</tr>')
            $index++
        }
        [void]$body.AppendLine('</tbody></table>')
        continue
    }

    if ($trimmed -match '^[-*]\s+(.+)$') {
        [void]$body.AppendLine('<ul>')
        while ($index -lt $lines.Count -and $lines[$index].Trim() -match '^[-*]\s+(.+)$') {
            [void]$body.AppendLine("<li>$(Convert-InlineMarkdown $matches[1])</li>")
            $index++
        }
        [void]$body.AppendLine('</ul>')
        continue
    }

    if ($trimmed -match '^\d+\.\s+(.+)$') {
        [void]$body.AppendLine('<ol>')
        while ($index -lt $lines.Count -and $lines[$index].Trim() -match '^\d+\.\s+(.+)$') {
            [void]$body.AppendLine("<li>$(Convert-InlineMarkdown $matches[1])</li>")
            $index++
        }
        [void]$body.AppendLine('</ol>')
        continue
    }

    [void]$body.AppendLine("<p>$(Convert-InlineMarkdown $trimmed)</p>")
    $index++
}

$style = @'
@page { size: A4; margin: 16mm 22mm 18mm 22mm; }
* { box-sizing: border-box; }
html { background: white; }
body {
  margin: 0;
  color: #000;
  font-family: SimSun, "宋体", "Noto Serif CJK SC", serif;
  font-size: 10.4pt;
  line-height: 1.5;
  letter-spacing: 0;
}
h1, h2, h3, h4, th {
  font-family: SimHei, "黑体", "Noto Sans CJK SC", sans-serif;
  color: #000;
}
h1 {
  margin: 12mm 0 8mm;
  padding-bottom: 7mm;
  border-bottom: 2px solid #000;
  font-size: 24pt;
  line-height: 1.3;
  font-weight: 700;
  break-after: avoid;
}
h2 {
  margin: 8mm 0 5mm;
  padding: 0 0 3mm;
  border-bottom: 1px solid #000;
  font-size: 17pt;
  line-height: 1.35;
  break-after: avoid;
}
h3 {
  margin: 6mm 0 3mm;
  font-size: 13pt;
  line-height: 1.4;
  break-after: avoid;
}
h4 {
  margin: 5mm 0 2mm;
  font-size: 11.2pt;
  line-height: 1.4;
  break-after: avoid;
}
p { margin: 0 0 3.4mm; orphans: 3; widows: 3; }
strong { color: #000; font-weight: 700; }
blockquote {
  margin: 0 0 7mm;
  padding: 4mm 5mm;
  border-left: 4px solid #000;
  background: #fff;
  color: #000;
}
blockquote p { margin: 0; }
ul, ol { margin: 1mm 0 4mm 6mm; padding-left: 5mm; }
li { margin: 0 0 1.5mm; break-inside: avoid; }
table {
  width: 100%;
  margin: 3mm 0 6mm;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 8.7pt;
  line-height: 1.5;
}
thead { display: table-header-group; }
tr { break-inside: avoid; }
th, td {
  padding: 2.2mm 2.4mm;
  border: 1px solid #000;
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th { background: #fff; color: #000; font-weight: 700; }
tbody tr:nth-child(even) { background: #fff; }
pre {
  margin: 3mm 0 6mm;
  padding: 4mm;
  border: 1px solid #000;
  background: #fff;
  border-radius: 4px;
  white-space: pre-wrap;
  break-inside: avoid;
}
code {
  font-family: Consolas, "Cascadia Mono", monospace;
  font-size: 0.92em;
  overflow-wrap: anywhere;
}
p code, li code, td code {
  padding: 0.2mm 1mm;
  border: 1px solid #000;
  background: #fff;
  border-radius: 3px;
}
'@

$title = [Net.WebUtility]::HtmlEncode([IO.Path]::GetFileNameWithoutExtension($sourcePath))
$html = @"
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>$style</style>
</head>
<body>
$body
</body>
</html>
"@

[IO.File]::WriteAllText($htmlPath, $html, [Text.UTF8Encoding]::new($false))
$htmlUri = [Uri]::new($htmlPath).AbsoluteUri

$chromeArguments = @(
    "--headless",
    "--disable-gpu",
    "--no-pdf-header-footer",
    "--run-all-compositor-stages-before-draw",
    "--user-data-dir=`"$profilePath`"",
    "--print-to-pdf=`"$outputPath`"",
    "`"$htmlUri`""
)
$chromeProcess = Start-Process `
    -FilePath $chromePath `
    -ArgumentList $chromeArguments `
    -WindowStyle Hidden `
    -Wait `
    -PassThru

if ($chromeProcess.ExitCode -ne 0) {
    throw "Chrome PDF export failed with exit code $($chromeProcess.ExitCode)"
}
if (-not (Test-Path -LiteralPath $outputPath) -or (Get-Item -LiteralPath $outputPath).Length -eq 0) {
    throw "Chrome did not create a non-empty PDF"
}

Get-Item -LiteralPath $outputPath | Select-Object FullName, Length, LastWriteTime
