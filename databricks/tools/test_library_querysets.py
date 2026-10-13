"""Exercise the prepared port's tree and flat library ordering with SQLite."""

import argparse
import json
import sys
from pathlib import Path


def run(source):
    """Use the real queryset and tree compiler without connecting to QA state."""
    sys.path.insert(0, str(source.resolve()))
    import django
    from django.conf import settings

    settings.configure(
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        },
        INSTALLED_APPS=["django.contrib.contenttypes", "django.contrib.auth"],
        USE_TZ=True,
    )
    django.setup()
    from django.db import connection, models
    from tree_queries.models import TreeNode

    from opencontractserver.shared.QuerySets import PermissionedTreeQuerySet

    class LibraryCard(TreeNode):
        title = models.CharField(max_length=100)
        objects = PermissionedTreeQuerySet.as_manager()

        class Meta:
            app_label = "port_library_order_check"

    with connection.schema_editor() as editor:
        editor.create_model(LibraryCard)
    parent = LibraryCard.objects.create(title="Zulu")
    LibraryCard.objects.create(title="Alpha", parent=parent)
    LibraryCard.objects.create(title="Mike")
    tree = LibraryCard.objects.with_tree_fields()
    flat = tree.without_tree_fields()
    checks = {
        "alphabetical_cards": list(
            flat.order_by("title", "pk").values_list("title", flat=True)
        )
        == ["Alpha", "Mike", "Zulu"],
        "oldest_cards": list(flat.order_by("pk").values_list("title", flat=True))
        == ["Zulu", "Alpha", "Mike"],
        "newest_cards": list(flat.order_by("-pk").values_list("title", flat=True))
        == ["Mike", "Alpha", "Zulu"],
        "tree_navigation_preserved": list(tree.values_list("title", flat=True))
        == ["Zulu", "Alpha", "Mike"],
    }
    return {"passed": all(checks.values()), "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.upstream)
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
