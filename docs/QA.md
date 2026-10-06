# FaintMark QA

Use an image you can safely share. Use your own private test destinations or
consenting recipients. Keep the same FaintMark registry throughout the test.

## Prepare

1. Start FaintMark and create five copies labelled Recipient 1 through Recipient 5.
2. CLI/MCP: use the created output folder. Web: unzip the download.
   Check every marked PNG locally: all five must match their
   assigned label and exact ten-character copy ID.
3. Check the unmarked original: it must not match a registered copy.
4. Record each ID below. Send the matching file for each row; do not accidentally
   send the original or another recipient's copy.
5. Save downloaded files into separate row folders so files never overwrite one
   another. Keep recipient labels, screenshots and downloads out of Git.

| Label | Expected copy ID |
| --- | --- |
| Recipient 1 | |
| Recipient 2 | |
| Recipient 3 | |
| Recipient 4 | |
| Recipient 5 | |

## Platform matrix

Check the final downloaded file, including after forwarding/reposting. Record
app version, operating system, date, upload quality, download method, final pixel
dimensions, result and actual ID. A preview or screenshot is a different route
from downloading an attachment; record which one you used.

| Case | Platform / route | Copy | Expected | Actual result / ID | Status |
| --- | --- | --- | --- | --- | --- |
| L1–L5 | Local marked PNGs | All five | Exact assigned IDs | | Not run |
| L6 | Local unmarked original | Original | No registered match | | Not run |
| D1 | Discord: upload image, download attachment | Recipient 1 | Exact ID | | Not run |
| D2 | Discord: save displayed preview | Recipient 1 | Exact ID if recoverable | | Not run |
| D3 | Discord: download D1, reupload, download again | Recipient 2 | Exact ID | | Not run |
| W1 | WhatsApp: Standard photo, download | Recipient 3 | Exact ID | | Not run |
| W2 | WhatsApp: HD photo, download | Recipient 3 | Exact ID | | Not run |
| W3 | WhatsApp: forward W1, download again | Recipient 4 | Exact ID | | Not run |
| W4 | WhatsApp: send as document/file, download | Recipient 4 | Exact ID | | Not run |
| I1 | Instagram: DM photo, recover received file | Recipient 5 | Exact ID | | Not run |
| I2 | Instagram: feed post, recover displayed image | Recipient 5 | Exact ID if recoverable | | Not run |
| I3 | Instagram: forward/repost recovered I1, recover again | Recipient 2 | Exact ID | | Not run |
| X1 | WhatsApp Standard download → Discord upload/download | Recipient 1 | Exact ID | | Not run |
| X2 | Discord download → Instagram DM → recover file | Recipient 4 | Exact ID | | Not run |
| C1 | Restart FaintMark, check a previously matched download | Any | Same assigned ID | | Not run |
| C2 | Check a marked image using a fresh empty `--home` | Any | Unknown; no recipient name | | Not run |
| C3 | Back up; restore into a new empty home; check again | Any | Same assigned ID | | Not run |

## Pass/fail

- **Pass:** exact registered ID and correct assigned recipient.
- **Recovery failure:** Unknown or Inconclusive where a match was expected. Keep
  that file; it is useful evidence for improving the engine/settings.
- **Critical failure:** a different registered recipient or ID is reported.
  Stop relying on that build and preserve the original, marked and recovered
  files privately for investigation.
- **Control pass:** the unmarked original produces no registered match.

Run the platform rows once with a detailed photograph and again with a
text-heavy or smooth image. Respect existing preflight warnings. Do not call a
platform supported after one passing image. Screenshots, deliberate cropping,
rotation and watermark removal are optional later stress tests, outside the
initial target.

## Record a failure

```text
Case:
Date:
Platform / app version / OS:
Expected recipient / ID:
Actual status / ID:
Input and recovered dimensions:
Send settings / download method:
Forwarding or reposting steps:
FaintMark version:
Preflight warnings:
```

For contribution, replace private labels with anonymous IDs and share images
only if you have permission. The repository stays private until the platform
matrix and release review give us confidence to change its visibility.
