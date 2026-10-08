from databricks_port.lakebase import connection_params
from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLWrapper


class DatabaseWrapper(PostgreSQLWrapper):
    def get_connection_params(self):
        params = super().get_connection_params()
        params.update(connection_params())
        return params
