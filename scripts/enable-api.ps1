# Enable the loopback API via iPhoneMirror's own UI. Does not copy/regenerate keys.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$scope = [System.Windows.Automation.TreeScope]::Descendants
function Find-Id($parent, [string]$id) {
    $condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
    $parent.FindFirst($scope, $condition)
}
$processes = @(Get-Process iPhoneMirror -ErrorAction SilentlyContinue)
if ($processes.Count -ne 1) { throw 'Start exactly one iPhoneMirror instance before enabling the API.' }
$condition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, [int]$processes[0].Id)
$windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)
$enabled = $null
foreach ($window in $windows) {
    $enabled = Find-Id $window 'ApiEnabled'
    if ($enabled) { break }
}
if (-not $enabled) {
    $version = $null
    foreach ($window in $windows) {
        $version = Find-Id $window 'VersionButton'
        if ($version) { break }
    }
    if (-not $version) { throw 'VersionButton unavailable. Use an iPhoneMirror build with Automation API; see docs/SETUP.md.' }
    $invoke = $version.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    1..5 | ForEach-Object { $invoke.Invoke() }
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 200
        $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $condition)
        foreach ($window in $windows) {
            $enabled = Find-Id $window 'ApiEnabled'
            if ($enabled) { break }
        }
        if ($enabled) { break }
    }
}
if (-not $enabled) { throw 'Automation API UI not found; check the installed app version.' }
$toggle = $enabled.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
if ($toggle.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On) { $toggle.Toggle() }
$buttons = $window.FindAll($scope, [System.Windows.Automation.Condition]::TrueCondition)
# Keep source ASCII so Windows PowerShell 5.1 also reads these names correctly.
$applyNames = @('Apply', (-join @([char]0x5E94, [char]0x7528)), (-join @([char]0x5957, [char]0x7528)), (-join @([char]0x61C9, [char]0x7528)))
$apply = @($buttons | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $_.Current.Name -in $applyNames })
if ($apply.Count -ne 1) { throw 'Cannot uniquely identify Apply; apply the enabled API checkbox in the developer window.' }
$apply[0].GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
Write-Host 'Automation API enabled through the application UI. No key was copied.'
