**Generate a PowerShell module** that replicates the API calls found in the traffic. The following are guidelines — use your judgment on what's appropriate for the specific API:

- Target PowerShell 7+ (`pwsh`), not Windows PowerShell 5.1. Do not use Windows-only cmdlets or `System.Web` types that require .NET Framework
- Module file is a single `.psm1` with one or more advanced functions. Every public function:
  - Uses an approved verb (`Get-Verb` list) — `Get-`, `Invoke-`, `New-`, `Set-`, `Remove-`, etc. Never invent unapproved verbs like `Fetch-` or `Do-`
  - Has `[CmdletBinding()]` and typed `[Parameter()]` blocks (mandatory/optional, `[string]`, `[hashtable]`, `[switch]` etc. — no untyped params)
  - Is exported explicitly via `Export-ModuleMember -Function <Name>` at the bottom of the file. Do not use wildcard export (`Export-ModuleMember -Function *`)
- HTTP calls use `Invoke-RestMethod` (or `Invoke-WebRequest` only when raw headers/status codes are needed). Never shell out to `curl.exe` or `curl`
- Session/cookie handling: use `-SessionVariable`/`-WebSession` with `[Microsoft.PowerShell.Commands.WebRequestSession]`, not manual cookie header construction, unless the API requires a cookie value that PowerShell's cookie jar can't express
- Error handling: every network call wrapped in a `try`/`catch` block with `-ErrorAction Stop` on the call itself. Catch blocks should surface `$_.Exception.Message` and, where the failure is an HTTP error, the response body if retrievable, not swallow the error silently
- Use `[PSCustomObject]` for structured return values, not raw hashtables, so downstream `ConvertTo-Json` and property access behave predictably
- Prefer `ConvertTo-Json`/`ConvertFrom-Json` (built-in) over any third-party JSON handling
- No `Write-Host` for data output — use `Write-Output`/return values. `Write-Verbose`/`Write-Error` are fine for diagnostics
- Create a separate exported function for each distinct API endpoint

**Authentication & credentials:**
- Hardcode all cookies, tokens, session IDs, and auth headers found in the traffic directly in the module
- The user should be able to run the example immediately with zero configuration — no env vars, no config files, no manual setup
- If the API uses cookies, populate a `WebRequestSession` with them and reuse it across calls
- If the API uses Bearer tokens or API keys, hardcode them in the request headers
- Handle auth refresh so the module doesn't go stale: if you see a token refresh endpoint, OAuth refresh flow, or login endpoint in the traffic, implement automatic re-authentication when a request returns 401/403. If cookies have expiry, re-fetch them before they expire

**Testing:**
- Run: `{run_command}`
- You have up to 5 attempts to fix issues

Save the module to: `{scripts_dir}/{client_filename}`
Save documentation to: `{scripts_dir}/README.md`
Save the example script to: `{scripts_dir}/Example.ps1`, which does:
```powershell
Import-Module "$PSScriptRoot\{client_filename}" -Force
# example invocation(s) of the exported function(s)
```
Do not generate a `.psd1` module manifest.
