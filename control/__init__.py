"""Control plane — the platform/SaaS layer (orthogonal to the agent runtime).

Holds what turns Syntony from a demo into a product others can use: users + organizations
(multi-tenant), authentication (email/password + org-scoped API keys), durable persistence
of projects/agent configs/runs/the append-only audit `events` mirror, encrypted provider
credentials, and usage metering (the basis for usage-based billing).

Separate from `engine/` (the domain-independent agent runtime) on purpose: this is the
control plane, not the data plane. Persistence is PostgreSQL via SQLModel.
"""
