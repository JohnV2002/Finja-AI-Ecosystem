<#
======================================================================
                     Finja's Brain & Knowledge Core
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Author: JohnV2002 (J. Apps / Sodakiller1)
  Version: 1.0.0 (Brain Module)

----------------------------------------------------------------------

  Copyright (c) 2025 J. Apps
  Licensed under the MIT License.

  (MIT License Text is omitted for brevity in comments, but applies)

======================================================================
#>

param(
  [string]$QueuePath = "missingsongs/artist_not_sure.jsonl",
  [string]$KbPath    = "SongsDB/songs_kb.json",
  [string]$ReviewedPath = "missingsongs/artist_not_sure.reviewed.jsonl",
  [switch]$Backup = $true,
  [ValidateSet("json","text")]
  [string]$NotesMode = "json",
  [switch]$AllowTitleOnly,
  [int]$MaxAmbiguous = 3
)

function Write-Info($msg){ Write-Host "[i] $msg" -ForegroundColor Cyan }
function Write-Warn($msg){ Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err($msg){ Write-Host "[x] $msg" -ForegroundColor Red }

if(-not (Test-Path $QueuePath)){ Write-Info "Queue leer oder nicht vorhanden: $QueuePath"; exit 0 }
if(-not (Test-Path $KbPath)){ Write-Err "KB nicht gefunden: $KbPath"; exit 1 }

# --- Utils: Normalize wie im Writer (vereinfacht) ---
function Normalize([string]$s){
  if([string]::IsNullOrWhiteSpace($s)){ return "" }
  $s = $s.ToLower().Trim()
  $s = [regex]::Replace($s,"[\(\[].*?[\)\]]","")         # Klammern raus
  $s = $s -replace "&", "and"
  $s = [regex]::Replace($s,"\bfeat\.?\b|\bfeaturing\b","")
  $s = [regex]::Replace($s,"[^\w\s]"," ")
  $s = [regex]::Replace($s,"\s{2,}"," ")
  return $s.Trim()
}

# --- KB laden (List oder {songs:[...]}) ---
$kbRaw = Get-Content -Raw -Encoding UTF8 $KbPath | ConvertFrom-Json
$kbSongs = @()
$kbIsWrapped = $false
if($kbRaw -is [System.Collections.IEnumerable] -and $kbRaw -isnot [Hashtable]){
  $kbSongs = @($kbRaw)
}else{
  if($kbRaw.songs){
    $kbSongs = @($kbRaw.songs)
    $kbIsWrapped = $true
  }else{
    Write-Err "Unbekanntes KB-Format."
    exit 1
  }
}

# Index nach normalisiertem Titel
$mapByTitle = @{}
for($i=0;$i -lt $kbSongs.Count;$i++){
  $e = $kbSongs[$i]
  $t = Normalize($e.title)
  if(-not $t){ continue }
  if(-not $mapByTitle.ContainsKey($t)){ $mapByTitle[$t] = New-Object System.Collections.ArrayList }
  [void]$mapByTitle[$t].Add($i)
}

# Backup
if($Backup){
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  Copy-Item $KbPath "$KbPath.$stamp.bak" -Force
  Write-Info "Backup angelegt: $KbPath.$stamp.bak"
}

# Queue lesen
$lines = Get-Content $QueuePath -Encoding UTF8
if(-not $lines -or $lines.Count -eq 0){ Write-Info "Keine offenen Items in $QueuePath"; exit 0 }

# Reviewed-File sicherstellen
$revDir = Split-Path $ReviewedPath -Parent
if($revDir -and -not (Test-Path $revDir)){ New-Item -ItemType Directory -Force -Path $revDir | Out-Null }

# Helfer: Notes mergen
function Merge-NotesJson([Hashtable]$entry,[string]$confirmArtist,[string]$denyArtist,[bool]$allowTitleOnly,[int]$maxAmb){
  $notesRaw = $entry.notes
  $obj = @{}
  $parsed = $false
  if($notesRaw -and ($notesRaw.Trim().StartsWith("{") -and $notesRaw.Trim().EndsWith("}"))){
    try { $obj = $notesRaw | ConvertFrom-Json -AsHashtable; $parsed = $true } catch {}
  }
  if(-not $parsed){ $obj = @{} }

  if($confirmArtist){
    if(-not $obj.artist_aliases){ $obj.artist_aliases = @() }
    $aliasLower = $confirmArtist.ToLower()
    if(-not ($obj.artist_aliases -contains $aliasLower)){
      $obj.artist_aliases += $aliasLower
    }
  }
  if($denyArtist){
    # im JSON-Modus führen wir eine "deny_artists" Liste (wird in v1.4.0 als Freitext gelesen, im JSON kannst du sie später auch nutzen)
    if(-not $obj.deny_artists){ $obj.deny_artists = @() }
    $dLower = $denyArtist.ToLower()
    if(-not ($obj.deny_artists -contains $dLower)){
      $obj.deny_artists += $dLower
    }
  }
  if($allowTitleOnly){ $obj.allow_title_only = $true }
  if($maxAmb -gt 0){ $obj.max_ambiguous_candidates = $maxAmb }

  return ($obj | ConvertTo-Json -Depth 6 -Compress)
}

function Merge-NotesText([Hashtable]$entry,[string]$confirmArtist,[string]$denyArtist,[bool]$allowTitleOnly,[int]$maxAmb){
  $parts = @()
  $old = $entry.notes
  if($old){ $parts += $old.Trim() }

  if($confirmArtist){ $parts += "Bestätigt: $confirmArtist" }
  if($denyArtist){ $parts += "Nicht bestätigt: $denyArtist" }
  if($allowTitleOnly){ $parts += "allow_title_only: true" }
  if($maxAmb -gt 0){ $parts += "max_ambiguous_candidates: $maxAmb" }

  return ($parts -join " | ")
}

# Interaktive Schleife
$keep = New-Object System.Collections.Generic.List[string]
for($li=0; $li -lt $lines.Count; $li++){
  $line = $lines[$li].Trim()
  if(-not $line){ continue }
  try{
    $obj = $line | ConvertFrom-Json -AsHashtable
  }catch{
    Write-Warn "Zeile $($li+1) ist kein JSON – überspringe."
    $keep.Add($line)
    continue
  }

  $obsT = $obj.observed.title
  $obsA = $obj.observed.artist
  $kbT  = $obj.kb_entry.title
  $kbA  = $obj.kb_entry.artist

  Write-Host ""
  Write-Host "==============================================" -ForegroundColor DarkGray
  Write-Host ("Observed :  {0}  —  {1}" -f $obsT, $obsA) -ForegroundColor White
  Write-Host ("KB Entry :  {0}  —  {1}" -f $kbT , $kbA ) -ForegroundColor Gray
  if($obj.reason){ Write-Host ("Reason   :  {0}" -f $obj.reason) -ForegroundColor DarkGray }

  # Kandidaten im KB finden (per normalisiertem Titel)
  $tNorm = Normalize($kbT)
  $candsIdx = @()
  if($mapByTitle.ContainsKey($tNorm)){ $candsIdx = @($mapByTitle[$tNorm]) }
  if($candsIdx.Count -eq 0){
    Write-Warn "Kein KB-Kandidat per Titel gefunden. [S]kip"
    $ans = "S"
  }else{
    # Auswahl anzeigen (falls mehrere)
    for($ci=0; $ci -lt $candsIdx.Count; $ci++){
      $e = $kbSongs[$candsIdx[$ci]]
      Write-Host ("  [{0}] {1} — {2}" -f $ci, $e.title, $e.artist) -ForegroundColor DarkGray
    }
    Write-Host ""
    Write-Host "[C]onfirm observed artist  |  [D]eny observed artist  |  [T]oggle allow_title_only  |  [S]kip  |  [O]pen KB" -ForegroundColor Cyan
    $ans = Read-Host "Aktion"
  }

  switch -Regex ($ans.ToUpper()){
    "^C$" {
      $sel = 0
      if($candsIdx.Count -gt 1){
        $sel = [int](Read-Host "Index wählen (0..$($candsIdx.Count-1))")
      }
      $idx = $candsIdx[$sel]
      $entry = $kbSongs[$idx]
      if($NotesMode -eq "json"){
        $entry.notes = Merge-NotesJson $entry $obsA $null $AllowTitleOnly.IsPresent $MaxAmbiguous
      }else{
        $entry.notes = Merge-NotesText $entry $obsA $null $AllowTitleOnly.IsPresent $MaxAmbiguous
      }
      # reviewed schreiben, Zeile aus Queue entfernen
      Add-Content -Encoding UTF8 -Path $ReviewedPath -Value $line
      Write-Info "Artist bestätigt → notes aktualisiert."
    }
    "^D$" {
      $sel = 0
      if($candsIdx.Count -gt 1){
        $sel = [int](Read-Host "Index wählen (0..$($candsIdx.Count-1))")
      }
      $idx = $candsIdx[$sel]
      $entry = $kbSongs[$idx]
      if($NotesMode -eq "json"){
        $entry.notes = Merge-NotesJson $entry $null $obsA $false 0
      }else{
        $entry.notes = Merge-NotesText $entry $null $obsA $false 0
      }
      Add-Content -Encoding UTF8 -Path $ReviewedPath -Value $line
      Write-Info "Artist verneint → notes aktualisiert."
    }
    "^T$" {
      $sel = 0
      if($candsIdx.Count -gt 1){
        $sel = [int](Read-Host "Index wählen (0..$($candsIdx.Count-1))")
      }
      $idx = $candsIdx[$sel]
      $entry = $kbSongs[$idx]
      if($NotesMode -eq "json"){
        $entry.notes = Merge-NotesJson $entry $null $null $true $MaxAmbiguous
      }else{
        $entry.notes = Merge-NotesText $entry $null $null $true $MaxAmbiguous
      }
      Add-Content -Encoding UTF8 -Path $ReviewedPath -Value $line
      Write-Info "allow_title_only gesetzt."
    }
    "^O$" {
      Write-Info "Öffne KB im Editor…"
      & notepad $KbPath
      # Zeile in der Queue belassen
      $keep.Add($line)
    }
    Default {
      Write-Info "Übersprungen."
      $keep.Add($line)
    }
  }
}

# KB zurückschreiben
if($kbIsWrapped){
  $kbRaw.songs = $kbSongs
  ($kbRaw | ConvertTo-Json -Depth 20) | Out-File -Encoding UTF8 $KbPath
}else{
  ($kbSongs | ConvertTo-Json -Depth 20) | Out-File -Encoding UTF8 $KbPath
}
Write-Info "KB gespeichert: $KbPath"

# Queue neu schreiben (nur unbehandelte Einträge)
$keepText = ($keep -join "`n")
Set-Content -Encoding UTF8 -Path $QueuePath -Value $keepText
Write-Info "Queue aktualisiert: $QueuePath"
Write-Info "Reviewed-Log: $ReviewedPath"
