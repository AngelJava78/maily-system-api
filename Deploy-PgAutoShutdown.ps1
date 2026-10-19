#Requires -Version 7
<#
.SYNOPSIS
    Crea la automatizacion de apagado/encendido nocturno para un Azure
    Database for PostgreSQL flexible server.

.DESCRIPTION
    Despliega, de forma idempotente:
      1. Una cuenta de Azure Automation con identidad administrada.
      2. Un rol Contributor acotado UNICAMENTE al servidor de PostgreSQL.
      3. El runbook Set-PgFlexServerState.ps1, publicado.
      4. Dos horarios semanales (lunes a viernes) y sus job schedules.

    Requiere Azure CLI con sesion iniciada (az login) y la extension
    'automation' (el script la instala si falta).

.EXAMPLE
    .\Deploy-PgAutoShutdown.ps1

.EXAMPLE
    # Horario mas corto y cuenta de Automation en otra region
    .\Deploy-PgAutoShutdown.ps1 -StartTimeOfDay 09:00 -StopTimeOfDay 18:00 -AutomationLocation southcentralus
#>
[CmdletBinding()]
param(
    # Si se omite, usa la suscripcion activa de 'az account show'.
    [string] $SubscriptionId,

    [string] $ResourceGroup     = 'rg-maily-dev-mex',
    [string] $ServerName        = 'pgsql-maily-dev-mex',
    [string] $AutomationAccount = 'aa-maily-dev-mex',

    # Azure Automation no esta en todas las regiones. Si Mexico Central no lo
    # soporta, pasa southcentralus o centralus: la cuenta de Automation no
    # tiene que vivir en la misma region que el servidor.
    [string] $AutomationLocation = 'mexicocentral',

    # Mexico ya no aplica horario de verano, asi que esto es UTC-6 todo el ano.
    [string] $TimeZone       = 'America/Mexico_City',
    [string] $StartTimeOfDay = '08:00',
    [string] $StopTimeOfDay  = '20:00',

    [ValidateSet('PowerShell72', 'PowerShell74')]
    [string] $RunbookType = 'PowerShell72',

    [string] $RunbookPath = (Join-Path $PSScriptRoot 'Set-PgFlexServerState.ps1')
)

$ErrorActionPreference = 'Stop'
$automationApi = '2023-11-01'
$runbookName   = 'Set-PgFlexServerState'

function Invoke-Arm {
    param(
        [ValidateSet('GET', 'PUT', 'POST', 'PATCH')] [string] $Method,
        [string] $Path,
        [hashtable] $Body
    )

    $cliArgs  = @('rest', '--method', $Method, '--url', "https://management.azure.com$Path")
    $bodyFile = $null

    if ($Body) {
        $bodyFile = New-TemporaryFile
        $Body | ConvertTo-Json -Depth 10 | Set-Content -Path $bodyFile -Encoding utf8
        $cliArgs += @('--body', "@$bodyFile")
    }

    try {
        $raw = & az @cliArgs 2>&1
        if ($LASTEXITCODE -ne 0) { throw "az rest $Method $Path fallo:`n$raw" }
        if ($raw) { return ($raw | ConvertFrom-Json) }
    }
    finally {
        if ($bodyFile) { Remove-Item $bodyFile -ErrorAction SilentlyContinue }
    }
}

function Get-NextWeekdayOccurrence {
    <# Automation exige que startTime este en el futuro y, sin offset, lo
       interpreta como UTC. Por eso se devuelve con el offset de $TimeZone. #>
    param([string] $TimeOfDay)

    $tz  = [System.TimeZoneInfo]::FindSystemTimeZoneById($TimeZone)
    $now = [System.TimeZoneInfo]::ConvertTime([System.DateTimeOffset]::UtcNow, $tz)

    $h, $m = $TimeOfDay.Split(':')
    $candidate = $now.Date.AddHours([int]$h).AddMinutes([int]$m)

    while ($candidate -lt $now.DateTime.AddMinutes(15) -or
           $candidate.DayOfWeek -in @('Saturday', 'Sunday')) {
        $candidate = $candidate.AddDays(1)
    }

    $offset = $tz.GetUtcOffset($candidate)
    ([System.DateTimeOffset]::new($candidate, $offset)).ToString('yyyy-MM-ddTHH:mm:ssK')
}

# --- 0. Contexto ---------------------------------------------------------

if (-not $SubscriptionId) {
    $SubscriptionId = (az account show --query id -o tsv)
    if (-not $SubscriptionId) { throw "No hay sesion de Azure CLI. Corre 'az login' primero." }
}
Write-Host "Suscripcion : $SubscriptionId"
Write-Host "Servidor    : $ServerName ($ResourceGroup)"

if (-not (Test-Path $RunbookPath)) {
    throw "No encuentro el runbook en '$RunbookPath'."
}

$serverId = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup" +
            "/providers/Microsoft.DBforPostgreSQL/flexibleServers/$ServerName"

$accountPath = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup" +
               "/providers/Microsoft.Automation/automationAccounts/$AutomationAccount"

# --- 1. Cuenta de Automation con identidad administrada ------------------

Write-Host "`n[1/4] Cuenta de Automation '$AutomationAccount'..."
$account = Invoke-Arm -Method PUT -Path "${accountPath}?api-version=$automationApi" -Body @{
    location   = $AutomationLocation
    identity   = @{ type = 'SystemAssigned' }
    properties = @{ sku = @{ name = 'Basic' } }
}

$principalId = $account.identity.principalId
if (-not $principalId) { throw "La cuenta de Automation no devolvio un principalId." }
Write-Host "      identidad administrada: $principalId"

# --- 2. Permiso, acotado solo a este servidor ----------------------------

Write-Host "`n[2/4] Asignando Contributor sobre el servidor..."
$existing = az role assignment list --assignee $principalId --scope $serverId --role Contributor --query "[].id" -o tsv

if ($existing) {
    Write-Host "      ya existe, se deja como esta."
}
else {
    # La identidad recien creada tarda unos segundos en replicarse en Entra ID.
    $assigned = $false
    foreach ($attempt in 1..6) {
        az role assignment create --assignee-object-id $principalId --assignee-principal-type ServicePrincipal --role Contributor --scope $serverId -o none 2>$null
        if ($LASTEXITCODE -eq 0) { $assigned = $true; break }
        Write-Host "      reintentando ($attempt/6)..."
        Start-Sleep -Seconds 10
    }
    if (-not $assigned) { throw "No se pudo asignar el rol sobre $serverId." }
    Write-Host "      listo."
}

# --- 3. Runbook ----------------------------------------------------------

Write-Host "`n[3/4] Publicando el runbook '$runbookName' ($RunbookType)..."
az extension add --name automation --only-show-errors 2>$null | Out-Null

Invoke-Arm -Method PUT -Path "$accountPath/runbooks/${runbookName}?api-version=$automationApi" -Body @{
    location   = $AutomationLocation
    properties = @{
        runbookType = $RunbookType
        logProgress = $false
        logVerbose  = $false
        draft       = @{}
    }
} | Out-Null

az automation runbook replace-content --resource-group $ResourceGroup --automation-account-name $AutomationAccount --name $runbookName --content "@$RunbookPath" -o none
if ($LASTEXITCODE -ne 0) { throw "No se pudo subir el contenido del runbook." }

az automation runbook publish --resource-group $ResourceGroup --automation-account-name $AutomationAccount --name $runbookName -o none
if ($LASTEXITCODE -ne 0) { throw "No se pudo publicar el runbook." }
Write-Host "      publicado."

# --- 4. Horarios ---------------------------------------------------------

Write-Host "`n[4/4] Creando horarios (L-V, $TimeZone)..."

$schedules = @(
    @{ Name = 'pg-start-weekdays'; Action = 'start'; Time = $StartTimeOfDay
       Desc = "Enciende $ServerName de lunes a viernes" }
    @{ Name = 'pg-stop-weekdays';  Action = 'stop';  Time = $StopTimeOfDay
       Desc = "Apaga $ServerName de lunes a viernes" }
)

foreach ($s in $schedules) {
    $startTime = Get-NextWeekdayOccurrence -TimeOfDay $s.Time

    Invoke-Arm -Method PUT -Path "$accountPath/schedules/$($s.Name)?api-version=$automationApi" -Body @{
        name       = $s.Name
        properties = @{
            description      = $s.Desc
            startTime        = $startTime
            frequency        = 'Week'
            interval         = 1
            timeZone         = $TimeZone
            advancedSchedule = @{
                weekDays = @('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')
            }
        }
    } | Out-Null

    # El nombre de un jobSchedule tiene que ser un GUID. Lo derivamos del
    # nombre del horario para que volver a correr el script no duplique nada.
    $jobScheduleId = [guid]::new(
        [System.Security.Cryptography.MD5]::HashData(
            [System.Text.Encoding]::UTF8.GetBytes($s.Name))).ToString()

    # Automation pasa las llaves de 'parameters' en minusculas; PowerShell
    # enlaza parametros sin distinguir mayusculas, asi que esto funciona.
    Invoke-Arm -Method PUT -Path "$accountPath/jobSchedules/${jobScheduleId}?api-version=$automationApi" -Body @{
        properties = @{
            schedule   = @{ name = $s.Name }
            runbook    = @{ name = $runbookName }
            parameters = @{
                action            = $s.Action
                subscriptionid    = $SubscriptionId
                resourcegroupname = $ResourceGroup
                servername        = $ServerName
            }
        }
    } | Out-Null

    Write-Host "      $($s.Name): $($s.Time) $TimeZone, primera corrida $startTime"
}

Write-Host "`nListo. Para probar sin esperar al horario, corre:"
Write-Host "  az automation runbook start -g $ResourceGroup --automation-account-name $AutomationAccount -n $runbookName --parameters action=stop subscriptionid=$SubscriptionId resourcegroupname=$ResourceGroup servername=$ServerName"
