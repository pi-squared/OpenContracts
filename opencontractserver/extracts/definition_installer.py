"""Install trusted versioned Fieldsets and LabelSets only, preserving native edits."""


class DefinitionDriftError(ValueError):
    """Native user edits prevent certifying the original package definitions."""


def install_definitions(package_hash, username, *, verify_only=False):
    from opencontractserver.extracts.workflows import package, resolve_response_model

    manifest, _ = package(package_hash)
    for column in manifest["columns"]:
        resolve_response_model("workflow:" + package_hash + ":" + column["key"])

    from django.contrib.auth import get_user_model
    from django.db import transaction
    from django.db.models import Field

    from opencontractserver.annotations.models import AnnotationLabel, LabelSet
    from opencontractserver.extracts.models import (
        Column,
        Fieldset,
        InstalledWorkflowPackage,
    )
    from opencontractserver.types.enums import PermissionTypes
    from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

    user = get_user_model().objects.get(username=username)
    name = manifest["identity"] + " " + manifest["version"] + " · " + package_hash[:12]
    controls = {}
    for field_name in (
        "task_name",
        "extract_is_list",
        "must_contain_text",
        "match_text",
        "limit_to_label",
        "is_manual_entry",
    ):
        field = Column._meta.get_field(field_name)
        if not isinstance(field, Field):
            raise ValueError("Workflow controls must name concrete column fields")
        controls[field_name] = field.get_default()
    description = (
        "Workflow package SHA-256: " + package_hash + "\nOwner: " + manifest["owner"]
    )
    with transaction.atomic():
        from django.db import connection

        # Native names are not unique: serialize this package/owner admission.
        if not verify_only:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (name + ":" + str(user.pk),),
                )
        registered = InstalledWorkflowPackage.objects.filter(
            package_hash=package_hash, owner=user
        ).first()
        if registered:
            fieldset = Fieldset.objects.get(pk=registered.fieldset_id, creator=user)
            labelset = LabelSet.objects.get(pk=registered.labelset_id, creator=user)
            if (
                fieldset.name != name
                or labelset.title != name
                or fieldset.description != description
                or labelset.description != description
            ):
                raise DefinitionDriftError(
                    "Installed definition headers were edited; preserve edits and use a new revision"
                )
            created = labels_created = False
        else:
            if verify_only:
                raise ValueError("Existing database workflow package is not registered")
            fieldset, created = Fieldset.objects.get_or_create(
                name=name, creator=user, defaults={"description": description}
            )
            labelset, labels_created = LabelSet.objects.get_or_create(
                title=name, creator=user, defaults={"description": description}
            )
            if (
                fieldset.description != description
                or labelset.description != description
            ):
                raise ValueError(
                    "Native definitions have conflicting package provenance"
                )
        if created:
            for definition in manifest["columns"]:
                native = {
                    k: definition[k]
                    for k in ("name", "query", "instructions", "display_order")
                }
                native["output_type"] = (
                    "workflow:" + package_hash + ":" + definition["key"]
                )
                native.update(controls)
                column = Column.objects.create(
                    fieldset=fieldset, creator=user, **native
                )
                column.full_clean()
                set_permissions_for_obj_to_user(user, column, [PermissionTypes.CRUD])
        else:
            # Preserve native UI experimentation. Reinstall must not silently
            # overwrite edits or call the altered configuration reproducible.
            observed = list(
                fieldset.columns.order_by("display_order").values(
                    "name",
                    "query",
                    "instructions",
                    "display_order",
                    "output_type",
                    *controls,
                )
            )
            expected = [
                {
                    **{
                        k: d[k]
                        for k in ("name", "query", "instructions", "display_order")
                    },
                    "output_type": "workflow:" + package_hash + ":" + d["key"],
                    **controls,
                }
                for d in manifest["columns"]
            ]
            if observed != expected:
                raise DefinitionDriftError(
                    "Native workflow definitions have changed; preserve edits and install a new package revision"
                )
        if labels_created:
            for definition in manifest["labels"]:
                native = {
                    k: definition[k]
                    for k in ("text", "label_type", "color", "description", "icon")
                }
                label = AnnotationLabel.objects.create(creator=user, **native)
                labelset.annotation_labels.add(label)
                set_permissions_for_obj_to_user(user, label, [PermissionTypes.CRUD])
        else:
            fields = ("text", "label_type", "color", "description", "icon")
            # Database collation can order case/punctuation differently from
            # Python. Compare the same definitions in one canonical order.
            observed = sorted(
                labelset.annotation_labels.values(*fields), key=lambda row: row["text"]
            )
            expected = sorted(
                ({k: d[k] for k in fields} for d in manifest["labels"]),
                key=lambda d: d["text"],
            )
            if observed != expected:
                raise DefinitionDriftError(
                    "Native workflow labels have changed; preserve edits and install a new package revision"
                )
        if verify_only:
            from opencontractserver.utils.permissioning import (
                get_users_permissions_for_obj,
            )

            for obj in (
                fieldset,
                labelset,
                *fieldset.columns.all(),
                *labelset.annotation_labels.all(),
            ):
                model_name = obj._meta.model_name
                if model_name is None:
                    raise ValueError("Workflow permission object has no model name")
                expected_permissions = {
                    action + "_" + model_name
                    for action in ("create", "read", "update", "remove")
                }
                if not expected_permissions.issubset(
                    get_users_permissions_for_obj(user, obj)
                ):
                    raise DefinitionDriftError(
                        "Existing database native workflow permissions have changed"
                    )
        else:
            InstalledWorkflowPackage.objects.get_or_create(
                package_hash=package_hash,
                owner=user,
                defaults={"fieldset": fieldset, "labelset": labelset},
            )
            for obj in (fieldset, labelset):
                set_permissions_for_obj_to_user(user, obj, [PermissionTypes.CRUD])
    return {
        "package_hash": package_hash,
        "identity": manifest["identity"],
        "version": manifest["version"],
        "fieldset_id": fieldset.pk,
        "labelset_id": labelset.pk,
        "columns": fieldset.columns.count(),
        "labels": labelset.annotation_labels.count(),
    }


def install_configured(*, verify_only=False):
    import json
    import os

    hashes = json.loads(os.environ.get("WORKFLOW_INSTALL_HASHES", "[]"))
    if not isinstance(hashes, list) or len(hashes) != len(set(hashes)):
        raise ValueError("Definition installation requires distinct package hashes")
    return [
        install_definitions(
            identity, os.environ["PILOT_USERNAME"], verify_only=verify_only
        )
        for identity in hashes
    ]
