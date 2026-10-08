# Security

FaintMark processes images locally and never uploads them. The first successful
`mark` or `check` downloads Adobe's TrustMark Q models and verifies their
SHA-256 hashes.

The registry contains recipient labels and file information. Keep it private
and back it up. MCP tools return labels and results to your MCP client; that
client's data handling is outside FaintMark. Run the MCP server only with
clients you trust: paths it receives refer to the machine it runs on.

Only the latest published release receives security fixes.

Report vulnerabilities through
[GitHub private vulnerability reporting](https://github.com/matchalatteguy/FaintMark/security/advisories/new).
Include the FaintMark version, OS, reproduction steps and impact. Use synthetic
or sanitized examples; do not submit private photos or registries.

Watermark removal and unreliable attribution are documented limitations (see
the README). Report unexpected behaviour through an issue unless it exposes a
vulnerability.
