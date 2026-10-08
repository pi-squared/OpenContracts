"""Pure annotation visibility and lazy compatibility imports for native services.

AnnotationService imports this predicate while its package initializes. Resolve
persistence services lazily to keep that native initialization cycle well formed.
"""


def active_domain_annotation_filter():
    """Keep ordinary annotations and domain annotations whose labels are active.

    PostgreSQL's missing JSON keys need an explicit branch so unmanaged
    reviewer annotations remain visible alongside active domain evidence.
    """
    from django.db.models import Q

    return Q(data__domainEvidence__active__isnull=True) | ~Q(
        data__domainEvidence__active=False
    )


_SERVICE_EXPORTS = {
    "fingerprint",
    "bind_label_policy",
    "ensure_selected_policy",
    "apply_finding_labels",
    "replay_labels",
}


def __getattr__(name):
    if name not in _SERVICE_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module

    return getattr(
        import_module("opencontractserver.annotations.services.domain_evidence"), name
    )
