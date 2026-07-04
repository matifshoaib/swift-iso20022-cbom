# Migration Priorities — What Breaks, What Can Be Hybridised

A prioritised remediation view of the estate. Priorities follow a
Mosca-informed model and are carried in the CBOM as
`payments-pqc:migration-priority` properties, so the ranking is queryable
directly from the machine-readable artifact.

## The Mosca inequality (why "start now")

Let **X** = how long the data/decision must stay secure, **Y** = how long
migration takes, **Z** = time until a cryptographically relevant quantum
computer (CRQC). If **X + Y > Z**, you are already exposed.

For a bank archive: X ≈ 7–10 years (retention) + the residual value of the data
well beyond that; Y ≈ multi-year (inventory → hybrid pilots → estate rollout, as
Project Leap's redevelopment findings show); Z is uncertain but planning anchors
put meaningful CRQC risk inside the 2030–2035 window. For the archive DEK wrap,
**X + Y already exceeds plausible Z** — which is why it sits at `P1`.

## Priority tiers

### P1 · CRITICAL — Harvest-Now-Decrypt-Later
The attack is retroactive: data recorded today is decrypted after Q-day. Remediate first.

| Asset | Where | Why P1 | Target |
|---|---|---|---|
| Archive DEK wrap (`RSA-2048-OAEP`) | Stage 7 archive | Wrapped DEKs recorded today → decryptable post-Q-day → all archived payments/PII exposed | Re-wrap DEKs under **ML-KEM-768** |
| mTLS 1.3 key agreement (`ECDH-P256`) | Stages 2–3 | Recorded internal sessions decryptable post-Q-day | Hybrid **X25519 + ML-KEM-768** |
| RSA-2048-OAEP (key transport) | Archive / key-wrap | Confidentiality with long shelf-life | **ML-KEM-768** |
| ECDH-P256 (key agreement) | TLS everywhere | Confidentiality with long shelf-life | **ML-KEM-768** (hybrid) |

### P2 · HIGH — Authenticity at Q-day (regulatory-deadline driven)
Not retroactive, but must be quantum-safe before RSA/ECDSA are disallowed.

| Asset | Where | Why P2 | Target |
|---|---|---|---|
| SWIFT message-signing key (`RSA-2048`) | Stages 4–5 | Payment-authorisation forgery at Q-day | **ML-DSA-65** |
| RTGS liquidity-transfer signing key (`RSA-2048`) | Stage 6 | Settlement-instruction forgery — the Project Leap touchpoint | **ML-DSA-65** |
| SWIFT PKI end-entity cert (`RSA-2048`) | Stage 4 | Both subject key and signature are RSA | Hybrid → **ML-DSA-65** re-issue |
| RSA-2048-PKCS1-SHA256 (signature) | SWIFT / RTGS / PKI | Underlying signature primitive | **ML-DSA-65** |
| ECDSA-P256 (signature) | TLS certs | Signature/impersonation risk | **ML-DSA-65** |

### P3 · MEDIUM — Protocol & version hygiene
Real but lower-urgency; often remediated by upgrade rather than replacement.

| Asset | Where | Action |
|---|---|---|
| TLS 1.2 corporate channel | Stage 1 | Upgrade to TLS 1.3, then add hybrid ML-KEM |
| Corporate client cert (`ECDSA-P256`) | Stage 1 | Re-issue on ML-DSA-65 (shorter-lived cert, less urgent) |
| Corporate client auth key (`ECDSA-P256`) | Stage 1 | ML-DSA-65 key pair |

### P4 · MONITOR — Symmetric & hash (Grover only)
No replacement needed; remediate by parameter size, not algorithm swap.

| Asset | Rationale |
|---|---|
| AES-256-GCM (data-at-rest, HSM master, archive) | Grover halves effective strength → still 128-bit. Retain at 256. |
| SHA-256 | Grover mildly reduces collision resistance. Prefer SHA-384 for new high-assurance signing. |
| HMAC-SHA-256 (SWIFT LAU) | MAC security unaffected in practice. Retain. |

## Canadian domestic rails — Lynx & RTR

Two Payments Canada settlement endpoints, added with explicit evidence confidence.
Every asset carries `payments-pqc:confidence` (`DOCUMENTED` / `INFERRED`) and a
`confidence-note` in the CBOM — INFERRED assets are never presented as fact.

### Lynx (CAD RTGS) — mostly DOCUMENTED
Lynx runs over **SWIFTNet InterAct**, so it inherits the SWIFT PKI crypto already
in this estate. It is the low-risk modelling case — effectively a clone of the
cross-border SWIFT assets retagged for CAD domestic settlement.

| Asset | Priority | Target | Confidence |
|---|---|---|---|
| Lynx message-signing key (`RSA-2048`, SWIFTNet) | P2-HIGH | ML-DSA-65 | DOCUMENTED (SWIFT platform) |
| SWIFTNet PKI CA root (`RSA-4096`) | P2-HIGH | ML-DSA-87 | DOCUMENTED |
| Lynx IPsec transport (ECDH/RSA + AES-256) | P2-HIGH | ML-KEM-768 hybrid | DOCUMENTED (SWIFT) |
| Lynx HSM master key (`AES-256`, FIPS 140-2 L3) | P4-MONITOR | Retain; PQC-capable HSM | DOCUMENTED |
| Lynx web GUI TLS | P3-MEDIUM | ML-KEM hybrid + ML-DSA certs | INFERRED |

Lynx's PQC migration is effectively **coupled to SWIFT's SwiftNet 8.0 (2027)** PQC
rollout — Payments Canada largely inherits SWIFT's timeline.

### RTR (Real-Time Rail) — partly INFERRED
RTR is a modern JSON/REST + IPsec + OAuth/IDAM architecture (Vocalink lineage), not
SWIFTNet. The Participation Guide confirms signing, encryption, VPN and MFA, but
**names no algorithms** — so the signing algorithm, TLS version, and HSM mandate are
INFERRED and flagged as such.

| Asset | Priority | Target | Confidence |
|---|---|---|---|
| RTR API payload signature (JWS) | P2-HIGH | ML-DSA-65 / composite | INFERRED (algorithm) |
| RTR IPsec VPN transport | P2-HIGH | ML-KEM-768 hybrid | DOCUMENTED (tunnel) |
| RTR portal TLS + OAuth 2.0 (IDAM) | P3-MEDIUM | ML-KEM hybrid + ML-DSA | INFERRED (versions) |
| RTR SFTP/SSH reporting | P3-MEDIUM | PQC SSH (ML-KEM/ML-DSA) | DOCUMENTED (SSH pubkey) |
| RTR NPFS fraud-API auth | P3-MEDIUM | ML-KEM hybrid + ML-DSA | INFERRED |

Because RTR is greenfield and launching in 2026 — years before the 2031 deadline —
it is the natural candidate for **crypto-agility / hybrid-PQC design from
inception** rather than a later retrofit.

> **Regulatory scope, stated honestly.** Cyber Centre **ITSM.40.001** (2031 high-priority /
> 2035 full migration) is legally scoped to Government of Canada systems. Payments
> Canada and Interac are not federal departments, so it applies to Lynx and RTR by
> **best-practice analogy, Bank of Canada oversight expectations, and procurement
> pressure** — not direct mandate. Do not overstate its regulatory force.

## <a name="project-leap"></a>What BIS Project Leap Phase 2 actually found

Project Leap Phase 2 — a collaboration of the **BIS Innovation Hub Eurosystem
Centre, Banca d'Italia, Banque de France, Deutsche Bundesbank, Nexi-Colt and
SWIFT** — tested post-quantum signatures inside the euro RTGS system **T2 /
TARGET2**, replacing conventional RSA signatures on liquidity transfers. The
final report was published **11 December 2025** (BIS, *othp107*). Key findings
relevant to this estate:

- **Feasibility confirmed.** All test scenarios executed successfully; invalid
  signatures were correctly rejected. Migrating a live payment system to PQC is
  achievable.
- **Signature *size* was the headline problem, not just speed.** At the ISO 20022
  Business Application Header level, a **CRYSTALS-Dilithium (Round 3, NIST Level
  3) signature of 3,293 bytes replaced a 256-byte RSA-2048 signature — roughly a
  12.9× increase**. The larger headers **exceeded expected buffer sizes** in
  TARGET2's message-handling logic, forcing component redevelopment.
- **They tested Dilithium Round 3, *not* the final ML-DSA.** Due to time
  constraints the team could not test the standardised **ML-DSA (FIPS 204)**;
  they flagged this for future phases. (This repo therefore models the *target*
  as ML-DSA-65 while noting Leap validated its Round-3 predecessor.)
- **HSM performance is still an open question.** Leap Phase 2 substituted
  software key files for physical HSMs to gain testing flexibility — so
  production HSM latency for PQC signing was **not** measured. For this estate,
  where signing happens in a FIPS 140-2 HSM, that is a live unknown to flag in
  any migration plan.

> Verify exact figures against the primary source before quoting them publicly:
> BIS, *Project Leap phase 2: quantum-proofing payment systems* (othp107),
> 11 December 2025 — https://www.bis.org/publ/othp107.htm

**Implication for this CBOM.** The `pacs.009` liquidity-transfer signing key
(stage 6) is the direct analogue of what Leap stressed. The ~12.9× signature
inflation is why "just swap the algorithm" underestimates the work: message
schemas, buffer sizing, and throughput budgets across the SWIFT/ISO 20022 chain
all move when RSA becomes ML-DSA. Crypto-agility — the ability to regenerate this
inventory and swap targets without re-architecting — is the actual deliverable.

## Standards & deadline anchors (verify against primary sources)

- **NIST FIPS 203 / 204 / 205** finalised 13 Aug 2024 — ML-KEM, ML-DSA, SLH-DSA.
- **NIST IR 8547** (transition guidance) — RSA-2048 / ECC-P-256 class algorithms
  **deprecated after 2030, disallowed after 2035**.
- **Canada — Cyber Centre ITSM.40.001** — high-priority systems migrated by end
  **2031**, remainder by end **2035**; initial departmental plans in 2026.
- These are planning anchors, not certainties; confirm current text before use.
