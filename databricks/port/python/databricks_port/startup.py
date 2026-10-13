"""Initialize owned state or verify a retained database before serving requests."""

from databricks_port.lakebase import bootstrap, database_mode


def initialize():
    bootstrap()
    import django
    from databricks_port.definitions import install_configured
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connection, transaction

    if database_mode() == "existing":
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            django.setup()
            from django.db.migrations.executor import MigrationExecutor

            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            if executor.migration_plan(executor.loader.graph.leaf_nodes()):
                raise ValueError(
                    "Existing database has pending migrations; the retained owner must migrate separately"
                )
            user_model = get_user_model()
            try:
                user = user_model.objects.get(username=settings.PILOT_USERNAME)
            except user_model.DoesNotExist as error:
                raise ValueError("Existing database pilot user is missing") from error
            if not user.is_active:
                raise ValueError("Existing database pilot user is inactive")
            return install_configured(verify_only=True)
    django.setup()
    call_command("migrate", interactive=False, verbosity=1)
    user, created = get_user_model().objects.get_or_create(
        username=settings.PILOT_USERNAME
    )
    if created:
        user.is_staff = True
        user.is_superuser = True
        user.is_usage_capped = False
        user.set_unusable_password()
        user.save()
    return install_configured()
