# Drag-and-drop front end for universal-spp\spp_downgrader\uspp_tool.py.
# Drop a .spp or .uspp, pick a target Painter version, click Convert.
# Output is written next to the input as <name>_v<target>.spp. The source file is never modified.
param([string]$InputFile)

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$Root   = $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Tool   = Join-Path $Root 'universal-spp\spp_downgrader\uspp_tool.py'
$Chain  = @('12.1', '12', '11', '10', '9', '8.1')   # fallback when a .uspp has no supported_versions

$state = @{ Input = $null; Uspp = $null; TempUspp = $null; Source = $null; Proc = $null; OnDone = $null; Out = $null; Err = $null }

# ------------------------------------------------------------------ UI
$form = New-Object System.Windows.Forms.Form
$form.Text = 'SPP Downgrader'
$form.Size = New-Object System.Drawing.Size(560, 430)
$form.MinimumSize = $form.Size
$form.StartPosition = 'CenterScreen'
$form.AllowDrop = $true
$form.Font = New-Object System.Drawing.Font('Segoe UI', 9)

$drop = New-Object System.Windows.Forms.Label
$drop.Text = "Drop a .spp or .uspp file here`r`n(or click to browse)"
$drop.TextAlign = 'MiddleCenter'
$drop.BorderStyle = 'FixedSingle'
$drop.Font = New-Object System.Drawing.Font('Segoe UI', 11)
$drop.SetBounds(12, 12, 520, 90)
$drop.Anchor = 'Top,Left,Right'
$drop.Cursor = 'Hand'
$drop.AllowDrop = $true

$srcLabel = New-Object System.Windows.Forms.Label
$srcLabel.Text = 'Source version: -'
$srcLabel.SetBounds(12, 114, 250, 22)

$tgtLabel = New-Object System.Windows.Forms.Label
$tgtLabel.Text = 'Target version:'
$tgtLabel.SetBounds(12, 146, 95, 22)

$combo = New-Object System.Windows.Forms.ComboBox
$combo.DropDownStyle = 'DropDownList'
$combo.SetBounds(110, 143, 90, 24)
$combo.Enabled = $false

$convert = New-Object System.Windows.Forms.Button
$convert.Text = 'Convert'
$convert.SetBounds(212, 141, 100, 28)
$convert.Enabled = $false

$openFolder = New-Object System.Windows.Forms.Button
$openFolder.Text = 'Open output folder'
$openFolder.SetBounds(322, 141, 130, 28)
$openFolder.Enabled = $false

$log = New-Object System.Windows.Forms.TextBox
$log.Multiline = $true
$log.ReadOnly = $true
$log.ScrollBars = 'Vertical'
$log.Font = New-Object System.Drawing.Font('Consolas', 9)
$log.SetBounds(12, 180, 520, 200)
$log.Anchor = 'Top,Bottom,Left,Right'

$form.Controls.AddRange(@($drop, $srcLabel, $tgtLabel, $combo, $convert, $openFolder, $log))

function Write-Log([string]$text) {
    $log.AppendText(($text -replace "`r?`n", "`r`n") + "`r`n")
}

function Set-Busy([bool]$busy) {
    $drop.Enabled = -not $busy
    $combo.Enabled = (-not $busy) -and $combo.Items.Count -gt 0
    $convert.Enabled = (-not $busy) -and $combo.Items.Count -gt 0
    $form.UseWaitCursor = $busy
}

# ------------------------------------------------------------------ async runner
# Runs uspp_tool.py without freezing the window; a timer polls for exit and calls $OnDone(exitCode, stdout, stderr).
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 250
$timer.Add_Tick({
    if ($state.Proc -and $state.Proc.HasExited) {
        $timer.Stop()
        $code = $state.Proc.ExitCode
        $out = (Get-Content -Raw -LiteralPath $state.Out -ErrorAction SilentlyContinue)
        $err = (Get-Content -Raw -LiteralPath $state.Err -ErrorAction SilentlyContinue)
        Remove-Item -LiteralPath $state.Out, $state.Err -ErrorAction SilentlyContinue
        $state.Proc = $null
        & $state.OnDone $code "$out" "$err"
    }
})

function Invoke-Tool([string[]]$toolArgs, [scriptblock]$onDone) {
    $state.Out = [IO.Path]::GetTempFileName()
    $state.Err = [IO.Path]::GetTempFileName()
    $state.OnDone = $onDone
    $quoted = @($Tool) + $toolArgs | ForEach-Object { '"' + $_ + '"' }
    $state.Proc = Start-Process -FilePath $Python -ArgumentList $quoted -NoNewWindow -PassThru `
        -RedirectStandardOutput $state.Out -RedirectStandardError $state.Err
    [void]$state.Proc.Handle   # cache the handle, otherwise ExitCode reads back empty
    $timer.Start()
}

# ------------------------------------------------------------------ steps
function Clear-TempUspp {
    if ($state.TempUspp -and (Test-Path -LiteralPath $state.TempUspp)) {
        Remove-Item -LiteralPath $state.TempUspp -ErrorAction SilentlyContinue
    }
    $state.TempUspp = $null
}

function Load-File([string]$path) {
    $ext = [IO.Path]::GetExtension($path).ToLower()
    if ($ext -notin '.spp', '.uspp') {
        Write-Log "Not a .spp or .uspp: $path"
        return
    }
    Clear-TempUspp
    $state.Input = $path
    $state.Source = $null
    $combo.Items.Clear()
    $srcLabel.Text = 'Source version: -'
    $openFolder.Enabled = $false
    $drop.Text = [IO.Path]::GetFileName($path)
    $log.Clear()
    Write-Log "Loaded $path"
    Set-Busy $true

    if ($ext -eq '.uspp') {
        $state.Uspp = $path
        Read-Info
    } else {
        # A .spp is packed to a temporary .uspp first so the version can be read and the build reused.
        $state.TempUspp = Join-Path $env:TEMP ("sppdowngrader_" + [guid]::NewGuid().ToString('N') + '.uspp')
        $state.Uspp = $state.TempUspp
        Write-Log 'Reading project (packing to temporary .uspp)...'
        Invoke-Tool @('pack', $path, '-o', $state.TempUspp) {
            param($code, $out, $err)
            if ($code -ne 0) { Write-Log "Pack failed (exit $code):`n$err"; Set-Busy $false; return }
            Read-Info
        }
    }
}

function Read-Info {
    Invoke-Tool @('info', '--uspp', $state.Uspp) {
        param($code, $out, $err)
        if ($code -ne 0) { Write-Log "Could not read file (exit $code):`n$err"; Set-Busy $false; return }
        $info = $out | ConvertFrom-Json
        $state.Source = $info.created_version
        if (-not $state.Source) { Write-Log 'File has no source version; cannot convert.'; Set-Busy $false; return }
        $srcLabel.Text = "Source version: $($state.Source)"
        $versions = if ($info.supported_versions) { @($info.supported_versions) } else { $Chain }
        foreach ($v in $versions) { [void]$combo.Items.Add($v) }
        # Default to the next version below the source.
        $combo.SelectedIndex = [Math]::Min(1, $combo.Items.Count - 1)
        Write-Log "Source is Painter $($state.Source). Pick a target and click Convert."
        Set-Busy $false
    }
}

function Start-Convert {
    $target = [string]$combo.SelectedItem
    $state.Target = $target
    if (-not $target) { return }
    Set-Busy $true
    Write-Log "`nChecking v$($state.Source) -> v$target..."
    Invoke-Tool @('plan', '--uspp', $state.Uspp, '--target', $target) {
        param($code, $out, $err)
        if ($code -ne 0) { Write-Log "Plan failed (exit $code):`n$err"; Set-Busy $false; return }
        $plan = $out | ConvertFrom-Json
        if (-not $plan.supported) { Write-Log "No conversion path from v$($plan.source_version) to v$($state.Target)."; Set-Busy $false; return }
        if ($plan.lossy) {
            $lines = @($plan.lost_features | ForEach-Object { if ($_ -is [string]) { "- $_" } else { "- " + ($_ | ConvertTo-Json -Compress -Depth 4) } })
            if ($plan.missing_raster_fallbacks) { $lines += @($plan.missing_raster_fallbacks | ForEach-Object { "- $($_.dataset): $($_.reason)" } | Select-Object -Unique) }
            $shown = ($lines | Select-Object -First 25) -join "`n"
            if ($lines.Count -gt 25) { $shown += "`n...and $($lines.Count - 25) more" }
            Write-Log "This downgrade is lossy:`n$shown"
            $answer = [System.Windows.Forms.MessageBox]::Show(
                "Downgrading v$($plan.source_version) to v$($state.Target) will lose some data:`n`n$shown`n`nContinue? The original file is not changed.",
                'Lossy downgrade', 'YesNo', 'Warning')
            if ($answer -ne 'Yes') { Write-Log 'Cancelled.'; Set-Busy $false; return }
        }
        Start-Build $state.Target
    }
}

function Start-Build([string]$target) {
    $dir = [IO.Path]::GetDirectoryName($state.Input)
    $name = [IO.Path]::GetFileNameWithoutExtension($state.Input)
    $outPath = Join-Path $dir "${name}_v$target.spp"
    if (Test-Path -LiteralPath $outPath) {
        $answer = [System.Windows.Forms.MessageBox]::Show("$outPath already exists. Overwrite it?", 'File exists', 'YesNo', 'Question')
        if ($answer -ne 'Yes') { Write-Log 'Cancelled.'; Set-Busy $false; return }
    }
    Write-Log "Building $outPath ..."
    $state.LastOut = $outPath
    Invoke-Tool @('build', '--uspp', $state.Uspp, '--target', $target, '-o', $outPath) {
        param($code, $out, $err)
        if ($out) { Write-Log $out.Trim() }
        if ($code -eq 0) {
            Write-Log "Done. Close Painter fully before opening the new file."
            $openFolder.Enabled = $true
        } else {
            Write-Log "Build failed (exit $code):`n$err"
        }
        Set-Busy $false
    }
}

# ------------------------------------------------------------------ events
$onDragEnter = {
    param($s, $e)
    if ($e.Data.GetDataPresent([System.Windows.Forms.DataFormats]::FileDrop)) { $e.Effect = 'Copy' }
}
$onDragDrop = {
    param($s, $e)
    $files = $e.Data.GetData([System.Windows.Forms.DataFormats]::FileDrop)
    if ($files -and -not $state.Proc) { Load-File $files[0] }
}
foreach ($c in @($form, $drop)) { $c.Add_DragEnter($onDragEnter); $c.Add_DragDrop($onDragDrop) }

$drop.Add_Click({
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Filter = 'Painter projects (*.spp;*.uspp)|*.spp;*.uspp'
    if ($dlg.ShowDialog() -eq 'OK') { Load-File $dlg.FileName }
})
$convert.Add_Click({ Start-Convert })
$openFolder.Add_Click({ if ($state.LastOut) { Start-Process explorer.exe "/select,`"$($state.LastOut)`"" } })
$form.Add_FormClosing({
    if ($state.Proc -and -not $state.Proc.HasExited) { $state.Proc.Kill() }
    Clear-TempUspp
})
$form.Add_Shown({ if ($InputFile) { Load-File $InputFile } })

if (-not (Test-Path -LiteralPath $Python)) {
    [System.Windows.Forms.MessageBox]::Show("Python not found at $Python. Run setup.ps1 first.", 'SPP Downgrader', 'OK', 'Error') | Out-Null
    exit 1
}
[void]$form.ShowDialog()
