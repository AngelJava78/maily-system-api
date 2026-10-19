<#
.SYNOPSIS
    Inicia o detiene un Azure Database for PostgreSQL flexible server.

.DESCRIPTION
    Pensado para correr como runbook de Azure Automation con identidada
    administrada asignada por el sistema.

    Solo depende de Az.Accounts, que Azure Automation ya trae instalado por
    defecto: habla con ARM por REST en vez de usar Az.PostgreSql, asi no hay
    que importar modulos adicionales en la cuenta de Automation.

    Es idempotente: si el servidor ya esta en el estado deseado, no hace nada.

.PARAMETER Action
    'start' para encender, 'stop' para apagar.

.EXAMPLE
    .\Set-PgFlexServerState.ps1 -Action stop -SubscriptionId <guid> `
        -ResourceGroupName rg-maily-dev-mex -ServerName pgsql-maily-dev-mex
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('start', 'stop')]
    [string] $Action,

    [Parameter(Mandatory = $true)]
    [string] $SubscriptionId,

    [Parameter(Mandatory = $true)]
    [string] $ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string] $ServerName
)

$ErrorActionPreference = 'Stop'

# API GA de Microsoft.DBforPostgreSQL. Si Azure la retira, sube la version aqui.
$apiVersion = '2024-08-01'

Disable-AzContextAutosave -Scope Process | Out-Null
Connect-AzAccount -Identity | Out-Null
Set-AzContext -Subscription $SubscriptionId | Out-Null

$serverPath = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName" +
              "/providers/Microsoft.DBforPostgreSQL/flexibleServers/$ServerName"

$response = Invoke-AzRestMethod -Method GET -Path "${serverPath}?api-version=$apiVersion"
if ($response.StatusCode -ne 200) {
    throw "No se pudo leer $ServerName (HTTP $($response.StatusCode)): $($response.Content)"
}

$state = ($response.Content | ConvertFrom-Json).properties.state
Write-Output "[$ServerName] estado actual: $state"

# 'Ready' es el estado de un servidor encendido y disponible.
$desired = if ($Action -eq 'stop') { 'Stopped' } else { 'Ready' }

if ($state -eq $desired) {
    Write-Output "[$ServerName] ya esta en '$desired'; no hay nada que hacer."
    return
}

Write-Output "[$ServerName] ejecutando '$Action'..."
$response = Invoke-AzRestMethod -Method POST -Path "${serverPath}/${Action}?api-version=$apiVersion"

# ARM responde 202 Accepted: la operacion termina de forma asincrona.
if ($response.StatusCode -notin 200, 202) {
    throw "La operacion '$Action' fallo (HTTP $($response.StatusCode)): $($response.Content)"
}

Write-Output "[$ServerName] '$Action' aceptada (HTTP $($response.StatusCode))."
