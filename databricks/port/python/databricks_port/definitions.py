"""Install trusted versioned Fieldsets and LabelSets only, preserving native edits."""


def install_definitions(package_hash, username):
    from databricks_port.workflows import package, resolve_response_model

    manifest, _ = package(package_hash)
    for column in manifest["columns"]:
        resolve_response_model("workflow:" + package_hash + ":" + column["key"])

    from django.contrib.auth import get_user_model
    from django.db import transaction

    from opencontractserver.annotations.models import AnnotationLabel, LabelSet
    from opencontractserver.extracts.models import Column, Fieldset
    from opencontractserver.types.enums import PermissionTypes
    from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

    user = get_user_model().objects.get(username=username)
    name = manifest["identity"] + " " + manifest["version"] + " · " + package_hash[:12]
    controls = {
        name: Column._meta.get_field(name).get_default()
        for name in (
            "task_name",
            "extract_is_list",
            "must_contain_text",
            "match_text",
            "limit_to_label",
            "is_manual_entry",
        )
    }
    description = (
        "Workflow package SHA-256: " + package_hash + "\nOwner: " + manifest["owner"]
    )
    with transaction.atomic():
        from django.db import connection

        # Native names are not unique: serialize this package/owner admission.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (name + ":" + str(user.pk),),
            )
        registry_key = "workflow-definitions:" + package_hash + ":" + str(user.pk)
        import json

        with connection.cursor() as cursor:
            cursor.execute("SELECT value FROM port_meta WHERE key=%s", (registry_key,))
            row = cursor.fetchone()
        registered = json.loads(row[0]) if row else None
        if registered:
            fieldset = Fieldset.objects.get(pk=registered["fieldset_id"], creator=user)
            labelset = LabelSet.objects.get(pk=registered["labelset_id"], creator=user)
            if (
                fieldset.name != name
                or labelset.title != name
                or fieldset.description != description
                or labelset.description != description
            ):
                raise ValueError(
                    "Installed definition headers were edited; preserve edits and use a new revision"
                )
            created = labels_created = False
        else:
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
                raise ValueError(
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
            observed = list(labelset.annotation_labels.order_by("text").values(*fields))
            expected = sorted(
                ({k: d[k] for k in fields} for d in manifest["labels"]),
                key=lambda d: d["text"],
            )
            if observed != expected:
                raise ValueError(
                    "Native workflow labels have changed; preserve edits and install a new package revision"
                )
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO port_meta(key,value) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (
                    registry_key,
                    json.dumps(
                        {"fieldset_id": fieldset.pk, "labelset_id": labelset.pk}
                    ),
                ),
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


def install_configured():
    import json
    import os

    hashes = json.loads(os.environ.get("WORKFLOW_INSTALL_HASHES", "[]"))
    if not isinstance(hashes, list) or len(hashes) != len(set(hashes)):
        raise ValueError("Definition installation requires distinct package hashes")
    return [
        install_definitions(identity, os.environ["PILOT_USERNAME"])
        for identity in hashes
    ]
