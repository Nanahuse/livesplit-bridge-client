# Official v4 contract fixtures

Source revision is pinned in `protocol-source.json` (Bridge C# DTOs in
`src/LiveSplit.Bridge.Json/Models.cs`).

- `validation-cases.json` is copied verbatim from `tools/schema/samples/validation-cases.json`;
  `tools/update_protocol.py` synchronizes it together with the schemas.
- `csharp-serialized-cases.json` is the output of the official net481
  `tools/schema/ContractSamples/LiveSplit.Bridge.ContractSamples.csproj` exporter.
  `tools/run_integration.py` exports fresh samples and verifies they match this fixture.

After intentionally updating the Bridge revision, run the schema sync tool, run the
integration tool, and replace `csharp-serialized-cases.json` with
`.tmp/contract-samples/csharp-serialized-cases.json` if the DTO output changed.
