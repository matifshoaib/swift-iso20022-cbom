#!/usr/bin/env python3
"""
validate_cbom.py — Structural validation + risk summary for the generated CBOM.

This is intentionally dependency-light: it checks the CycloneDX 1.6 CBOM shape
by hand (required top-level fields, per-assetType required sub-objects, and
dangling bom-ref references in the dependency graph), then prints a
migration-priority rollup an analyst can paste into a status report.

For full JSON-Schema validation against the official CycloneDX 1.6 schema, use
the cyclonedx CLI:  `cyclonedx validate --input-file cbom/payment-estate-cbom.json`

Usage:
    python scripts/validate_cbom.py cbom/payment-estate-cbom.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROP_NS = "payments-pqc"
REQUIRED_TOP = ["bomFormat", "specVersion", "components"]
ASSET_SUBOBJECT = {
    "algorithm": "algorithmProperties",
    "protocol": "protocolProperties",
    "certificate": "certificateProperties",
    "related-crypto-material": "relatedCryptoMaterialProperties",
}


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")


def prop(comp: dict, name: str) -> str | None:
    for p in comp.get("properties", []):
        if p["name"] == f"{PROP_NS}:{name}":
            return p["value"]
    return None


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "cbom/payment-estate-cbom.json")
    cbom = json.loads(path.read_text())
    errors = 0

    # 1. top-level shape
    for k in REQUIRED_TOP:
        if k not in cbom:
            fail(f"missing top-level '{k}'"); errors += 1
    if cbom.get("bomFormat") != "CycloneDX":
        fail("bomFormat must be 'CycloneDX'"); errors += 1
    if cbom.get("specVersion") != "1.6":
        fail(f"specVersion is {cbom.get('specVersion')}, expected 1.6"); errors += 1

    # 2. per-component shape + collect bom-refs
    refs: set[str] = set()
    for c in cbom.get("components", []):
        if c.get("type") != "cryptographic-asset":
            fail(f"{c.get('name')}: type must be 'cryptographic-asset'"); errors += 1
        refs.add(c.get("bom-ref", ""))
        cp = c.get("cryptoProperties", {})
        at = cp.get("assetType")
        if at not in ASSET_SUBOBJECT:
            fail(f"{c.get('name')}: bad assetType '{at}'"); errors += 1
            continue
        if ASSET_SUBOBJECT[at] not in cp:
            fail(f"{c.get('name')}: assetType '{at}' missing {ASSET_SUBOBJECT[at]}")
            errors += 1

    # 3. dependency graph: dependsOn edges to crypto assets must resolve
    for d in cbom.get("dependencies", []):
        for edge in d.get("dependsOn", []):
            if edge.startswith("crypto/") and edge not in refs:
                fail(f"dangling dependency: {d['ref']} -> {edge}"); errors += 1

    # 4. risk rollup
    prio = Counter()
    vuln = 0
    for c in cbom.get("components", []):
        p = prop(c, "migration-priority") or "UNCLASSIFIED"
        prio[p] += 1
        if prop(c, "quantum-vulnerable") == "True":
            vuln += 1

    total = len(cbom.get("components", []))
    print(f"\nCBOM: {path.name}")
    print(f"Spec: CycloneDX {cbom.get('specVersion')}")
    print(f"Assets: {total}   Quantum-vulnerable: {vuln} "
          f"({(vuln/total*100 if total else 0):.0f}%)\n")
    print("Migration-priority rollup")
    print("-" * 34)
    order = ["P1-CRITICAL", "P2-HIGH", "P3-MEDIUM", "P4-MONITOR", "TARGET"]
    for k in order:
        if prio.get(k):
            print(f"  {k:<14} {prio[k]}")
    for k, v in prio.items():
        if k not in order:
            print(f"  {k:<14} {v}")

    print()
    if errors:
        print(f"VALIDATION FAILED — {errors} error(s)")
        return 1
    print("VALIDATION PASSED — structure conforms to CycloneDX 1.6 CBOM shape")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
