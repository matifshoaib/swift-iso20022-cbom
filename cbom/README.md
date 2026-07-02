# The CBOM artifact

[`payment-estate-cbom.json`](./payment-estate-cbom.json) is a **CycloneDX 1.6
Cryptography Bill of Materials** for the reference wire-payment estate. It is a
**build artifact** — generated from [`../data/crypto-inventory.yaml`](../data/crypto-inventory.yaml),
never hand-edited.

## How it's structured

Each cryptographic asset is a component of `type: "cryptographic-asset"` with a
`cryptoProperties.assetType` of `algorithm`, `protocol`, `certificate`, or
`related-crypto-material`. The payments/PQC reasoning (lifecycle stage, threat,
target algorithm, migration priority) is carried in namespaced
`properties` under the `payments-pqc:` prefix, so it survives ingestion by any
standard CycloneDX tool without breaking the schema.

A `dependencies` graph links each **payment lifecycle stage**
(`lifecycle/…`) to the crypto assets it relies on, and links certificates and
keys to their underlying algorithms — so you can trace, for any stage, exactly
which quantum-vulnerable assets sit beneath it.

## Regenerate & validate

```bash
pip install -r requirements.txt
python scripts/generate_cbom.py --inventory data/crypto-inventory.yaml --out cbom/payment-estate-cbom.json
python scripts/validate_cbom.py cbom/payment-estate-cbom.json
```

## Validate against the official schema

The JSON validates against the upstream CycloneDX 1.6 JSON Schema. With the
CycloneDX CLI:

```bash
cyclonedx validate --input-file cbom/payment-estate-cbom.json
```

## Query it

The CBOM is designed to be queried. Examples with `jq`:

```bash
# List every quantum-vulnerable asset and its target algorithm
jq -r '.components[]
  | select(.properties[]? | select(.name=="payments-pqc:quantum-vulnerable" and .value=="True"))
  | .name' cbom/payment-estate-cbom.json

# Everything at P1-CRITICAL (harvest-now-decrypt-later)
jq -r '.components[]
  | select(.properties[]? | select(.name=="payments-pqc:migration-priority" and .value=="P1-CRITICAL"))
  | .name' cbom/payment-estate-cbom.json
```
