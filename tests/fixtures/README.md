# Official v4 message fixtures

Source revision is pinned in `protocol-source.json` (Bridge C# DTOs in
`src/LiveSplit.Bridge.Json/Models.cs`). These are message examples, not JSON schemas.
Normal client tests use them offline to exercise the real RPC / Events decoding paths.

- `validation-cases.json` contains the official malformed messages from
  `tools/schema/samples/validation-cases.json` at the pinned source revision.
- `csharp-serialized-cases.json` is the output of the official net481
  `tools/schema/ContractSamples/LiveSplit.Bridge.ContractSamples.csproj` exporter.
  `tools/run_integration.py` exports fresh samples and verifies they match this fixture.

After intentionally updating the Bridge revision, run model generation and integration
checks. If C# output changed, replace `csharp-serialized-cases.json` with
`.tmp/contract-samples/csharp-serialized-cases.json`; copy updated malformed messages
from the official checkout if necessary. Generated Python models must never be edited.
