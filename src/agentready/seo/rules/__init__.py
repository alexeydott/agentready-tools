"""Built-in atomic SEO rules and rule metadata."""

from .builtin import SEO_ATOMIC_RULES
from .models import AtomicFinding, RuleKind, SeoRuleSpec

__all__ = ["SEO_ATOMIC_RULES", "AtomicFinding", "RuleKind", "SeoRuleSpec"]
