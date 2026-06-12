"""L3 — domain packs.

Each subpackage is a self-contained plugin supplying a domain's payload ``schema``,
``policy`` (decision rules + thresholds), and ``roles`` (the agent cast). The engine
(L2) and protocol (L1) stay domain-independent; a pack is what specializes Syntony to
prior-auth (``authbridge``), contracts (``contracts``), etc.
"""
