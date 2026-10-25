# Official v4 message fixtures

Source revision is pinned in `protocol-source.json` (Bridge C# DTOs in
`src/LiveSplit.Bridge.Json/Models.cs`). These are message examples, not JSON schemas.
Normal client tests use them offline to exercise the real RPC / Events decoding paths.

- `csharp-serialized-cases.json` is the output of the official net481
  `tools/schema/ContractSamples/LiveSplit.Bridge.ContractSamples.csproj` exporter.
  `tools/run_integration.py` exports fresh samples and verifies they match this fixture.

After intentionally updating the Bridge revision, run model generation and integration
checks. If C# output changed, replace `csharp-serialized-cases.json` with
`.tmp/contract-samples/csharp-serialized-cases.json`. Generated Python models must never be edited.

Unit tests select representative messages to check public query data, flat Event access,
and Base64 conversion. They do not exhaust generated field constraints or compare JSON round trips.
