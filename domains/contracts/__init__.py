"""L3 domain pack — **contracts** (extension point).

A second domain pack lives here to keep the core honest about being domain-independent:
the engine and protocol must not need changes to support a new domain. A pack mirrors
``authbridge`` — ``schema`` + ``policy`` + ``roles`` — and is discovered the same way.
"""
