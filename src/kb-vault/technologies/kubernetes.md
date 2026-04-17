---
doc_type: technology
domain: platform
tags: [platform, kubernetes, runtime]
---
# Kubernetes

## Capability Summary
Our default compute plane for server-side workloads. EKS/GKE/AKS in cloud engagements, k3s at the edge (e.g., [[ironworks-mes]]), self-managed only when mandated by customer policy (e.g., the OpenStack install at [[telora-5g-bss]]).

## Where we have delivered
- [[acme-core-banking]] — EKS hosted 28 [[microservices]].
- [[medix-emr-2024]] — EKS with IRSA for HIPAA boundary isolation.
- [[ironworks-mes]] — k3s edge clusters per plant federated to EKS in cloud.
- [[telora-5g-bss]] — self-managed on OpenStack for telco regulatory reasons.

## Patterns we standardize on
- GitOps via Argo CD; no cluster changes without a reviewed PR.
- Namespaces as the unit of multi-tenant isolation; NetworkPolicies mandatory.
- Platform team owns the base image + golden Helm chart; product teams ship charts that inherit.
