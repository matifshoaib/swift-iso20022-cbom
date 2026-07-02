#!/usr/bin/env python3
"""
generate_cbom.py — Build a CycloneDX 1.6 Cryptography Bill of Materials (CBOM)
from the human-editable inventory in data/crypto-inventory.yaml.

Design intent (crypto-agility): the YAML is the single source of truth. The
CBOM is a build artifact — regenerate it, never hand-edit it. This mirrors how
a bank should treat its cryptographic inventory: one authoritative register,
machine-generated evidence for auditors and regulators.

Output conforms to the CycloneDX 1.6 spec (which upstreamed IBM's CBOM model):
  - component.type = "cryptographic-asset"
  - cryptoProperties.assetType in {algorithm, protocol, certificate,
    related-crypto-material}
  - payments/PQC reasoning carried in component.properties (namespaced keys)
  - a dependencies graph linking each payment lifecycle stage to the crypto
    assets it relies on.

Usage:
    python scripts/generate_cbom.py \
        --inventory data/crypto-inventory.yaml \
        --out cbom/payment-estate-cbom.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import copy
import hashlib
import os
import uuid
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required:  pip install pyyaml")

SPEC_VERSION = "1.6"
PROP_NS = "payments-pqc"  # namespace for custom properties


def _props(asset: dict) -> list[dict]:
    """Map the payments/PQC reasoning fields to namespaced CycloneDX properties."""
    keys = [
        ("lifecycle_stage", "lifecycle-stage"),
        ("touchpoint", "touchpoint"),
        ("quantum_vulnerable", "quantum-vulnerable"),
        ("threat", "threat"),
        ("target", "target-algorithm"),
        ("hybrid_capable", "hybrid-capable"),
        ("migration_priority", "migration-priority"),
    ]
    out = []
    for src, name in keys:
        if src in asset and asset[src] is not None:
            out.append({"name": f"{PROP_NS}:{name}", "value": str(asset[src])})
    return out


def _algorithm_component(a: dict) -> dict:
    # NOTE: algorithmFamily is a CycloneDX 1.7 (Cryptography Registry) field,
    # not valid in 1.6 algorithmProperties — carried as a property instead.
    ap: dict = {"primitive": a["primitive"]}
    for field in (
        "parameterSetIdentifier", "curve", "mode",
        "padding", "classicalSecurityLevel", "nistQuantumSecurityLevel",
    ):
        if field in a and a[field] is not None:
            ap[field] = a[field]
    if a.get("cryptoFunctions"):
        ap["cryptoFunctions"] = a["cryptoFunctions"]
    ap["executionEnvironment"] = "software-plain-ram"

    comp = {
        "type": "cryptographic-asset",
        "bom-ref": f"crypto/algorithm/{a['ref']}",
        "name": a["name"],
        "cryptoProperties": {
            "assetType": "algorithm",
            "algorithmProperties": ap,
        },
    }
    if a.get("oid"):
        comp["cryptoProperties"]["oid"] = a["oid"]
    props = _props(a)
    if a.get("algorithmFamily"):
        props.insert(0, {"name": f"{PROP_NS}:algorithm-family", "value": a["algorithmFamily"]})
    if props:
        comp["properties"] = props
    return comp


def _protocol_component(p: dict) -> dict:
    suites = []
    for cs in p.get("cipher_suites", []):
        suites.append({
            "name": cs["name"],
            "algorithms": [f"crypto/algorithm/{r}" for r in cs.get("algorithms", [])],
        })
    comp = {
        "type": "cryptographic-asset",
        "bom-ref": f"crypto/protocol/{p['ref']}",
        "name": p["name"],
        "cryptoProperties": {
            "assetType": "protocol",
            "protocolProperties": {
                "type": p["type"],
                "version": p["version"],
                "cipherSuites": suites,
            },
        },
    }
    props = _props(p)
    if props:
        comp["properties"] = props
    return comp


def _certificate_component(c: dict) -> dict:
    cp = {
        "subjectName": c.get("subjectName"),
        "issuerName": c.get("issuerName"),
        "notValidBefore": c.get("notValidBefore"),
        "notValidAfter": c.get("notValidAfter"),
        "certificateFormat": c.get("certificateFormat", "X.509"),
    }
    if c.get("signatureAlgorithmRef"):
        cp["signatureAlgorithmRef"] = f"crypto/algorithm/{c['signatureAlgorithmRef']}"
    if c.get("subjectPublicKeyRef"):
        cp["subjectPublicKeyRef"] = f"crypto/key/{c['subjectPublicKeyRef']}"
    cp = {k: v for k, v in cp.items() if v is not None}

    comp = {
        "type": "cryptographic-asset",
        "bom-ref": f"crypto/certificate/{c['ref']}",
        "name": c["name"],
        "cryptoProperties": {
            "assetType": "certificate",
            "certificateProperties": cp,
        },
    }
    props = _props(c)
    if props:
        comp["properties"] = props
    return comp


def _key_component(k: dict) -> dict:
    rp = {
        "type": k["type"],
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"cbom/key/{k['ref']}")),
        "state": k.get("state", "active"),
    }
    if k.get("algorithmRef"):
        rp["algorithmRef"] = f"crypto/algorithm/{k['algorithmRef']}"
    if k.get("creationDate"):
        rp["creationDate"] = k["creationDate"]
    if k.get("size"):
        rp["size"] = k["size"]
    secured = {}
    if k.get("securedBy_mechanism"):
        secured["mechanism"] = k["securedBy_mechanism"]
    if k.get("securedBy_algorithmRef"):
        secured["algorithmRef"] = f"crypto/algorithm/{k['securedBy_algorithmRef']}"
    if secured:
        rp["securedBy"] = secured

    comp = {
        "type": "cryptographic-asset",
        "bom-ref": f"crypto/key/{k['ref']}",
        "name": k["name"],
        "cryptoProperties": {
            "assetType": "related-crypto-material",
            "relatedCryptoMaterialProperties": rp,
        },
    }
    if k.get("oid"):
        comp["cryptoProperties"]["oid"] = k["oid"]
    props = _props(k)
    if props:
        comp["properties"] = props
    return comp


def _dependencies(inv: dict) -> list[dict]:
    """Build the payment-lifecycle -> crypto-asset dependency graph."""
    ref_of = {
        "algorithms": "crypto/algorithm",
        "protocols": "crypto/protocol",
        "certificates": "crypto/certificate",
        "keys": "crypto/key",
    }
    # index every asset ref -> its bom-ref prefix
    index = {}
    for section, prefix in ref_of.items():
        for a in inv.get(section, []):
            index[a["ref"]] = f"{prefix}/{a['ref']}"

    deps = []
    for stage in inv.get("lifecycle", []):
        stage_ref = f"lifecycle/{stage['stage']}"
        depends = [index[r] for r in stage.get("depends_on", []) if r in index]
        deps.append({"ref": stage_ref, "dependsOn": depends})

    # certificates depend on their signing algorithm + subject key
    for c in inv.get("certificates", []):
        edges = []
        if c.get("signatureAlgorithmRef"):
            edges.append(f"crypto/algorithm/{c['signatureAlgorithmRef']}")
        if c.get("subjectPublicKeyRef"):
            edges.append(f"crypto/key/{c['subjectPublicKeyRef']}")
        if edges:
            deps.append({"ref": f"crypto/certificate/{c['ref']}", "dependsOn": edges})

    # keys depend on their algorithm + what secures them
    for k in inv.get("keys", []):
        edges = []
        if k.get("algorithmRef"):
            edges.append(f"crypto/algorithm/{k['algorithmRef']}")
        if k.get("securedBy_algorithmRef"):
            edges.append(f"crypto/algorithm/{k['securedBy_algorithmRef']}")
        if edges:
            deps.append({"ref": f"crypto/key/{k['ref']}", "dependsOn": edges})

    return deps


def build_cbom(inv: dict) -> dict:
    meta = inv.get("metadata", {})
    components = []
    components += [_algorithm_component(a) for a in inv.get("algorithms", [])]
    components += [_protocol_component(p) for p in inv.get("protocols", [])]
    components += [_certificate_component(c) for c in inv.get("certificates", [])]
    components += [_key_component(k) for k in inv.get("keys", [])]

    # Deterministic serial number: UUIDv5 derived from a content hash of the
    # inventory, so regenerating the same inventory yields the same CBOM
    # (reproducible build — this is what lets CI verify the JSON isn't stale).
    digest = hashlib.sha256(
        json.dumps(inv, sort_keys=True, default=str).encode()
    ).hexdigest()
    serial = uuid.uuid5(uuid.NAMESPACE_URL, digest)

    # Timestamp: reproducible-builds convention. Honour SOURCE_DATE_EPOCH when
    # set (e.g. in CI), otherwise use the current time for local runs.
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        ts = dt.datetime.fromtimestamp(int(epoch), dt.timezone.utc)
    else:
        ts = dt.datetime.now(dt.timezone.utc)
    now = ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": now,
            "component": {
                "type": "application",
                "bom-ref": "estate/wire-payment",
                "name": meta.get("estate_name", "Wire-Payment Estate"),
                "description": meta.get("description", ""),
            },
            "authors": [{"name": meta.get("author", "unknown")}],
        },
        "components": components,
        "dependencies": _dependencies(inv),
    }


def _semantic(cbom: dict) -> dict:
    """Copy with the volatile timestamp removed, for reproducibility checks."""
    c = copy.deepcopy(cbom)
    c.get("metadata", {}).pop("timestamp", None)
    return c


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a CycloneDX 1.6 CBOM.")
    ap.add_argument("--inventory", default="data/crypto-inventory.yaml")
    ap.add_argument("--out", default="cbom/payment-estate-cbom.json")
    ap.add_argument("--check", action="store_true",
                    help="Verify the committed CBOM matches the inventory "
                         "(ignoring timestamp) and exit non-zero on drift. "
                         "Does not write.")
    args = ap.parse_args()

    inv = yaml.safe_load(Path(args.inventory).read_text())
    cbom = build_cbom(inv)
    out = Path(args.out)

    if args.check:
        if not out.exists():
            sys.exit(f"CHECK FAILED: {out} does not exist — run the generator.")
        existing = json.loads(out.read_text())
        if _semantic(existing) != _semantic(cbom):
            sys.exit(
                f"CHECK FAILED: {out} is out of sync with {args.inventory}.\n"
                f"Run:  python scripts/generate_cbom.py  and commit the result."
            )
        print(f"CHECK PASSED: {out} is in sync with {args.inventory}")
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cbom, indent=2) + "\n")

    n = len(cbom["components"])
    vuln = sum(
        1 for c in cbom["components"]
        for p in c.get("properties", [])
        if p["name"] == f"{PROP_NS}:quantum-vulnerable" and p["value"] == "True"
    )
    print(f"Wrote {out}  |  {n} cryptographic assets  |  {vuln} quantum-vulnerable")


if __name__ == "__main__":
    main()
