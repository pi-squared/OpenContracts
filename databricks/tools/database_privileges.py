"""Read effective retained-state access independently of grant authority."""


def privilege_gaps(cursor, schema, *, role=None):
    """Read missing access for a bound role, or this connection's current user.

    This policy performs only catalog reads. Callers own grants, transaction
    safety, fresh readback and refusal when any required access is missing.
    """
    subject = "current_user" if role is None else "%s"
    principal = () if role is None else (role,)
    cursor.execute(
        f"SELECT has_schema_privilege({subject},%s,'USAGE')",
        (*principal, schema),
    )
    schema_missing = cursor.fetchone() != (True,)
    cursor.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n "
        "ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind IN ('r','p') "
        "AND NOT (has_table_privilege({role},c.oid,'SELECT') "
        "AND has_table_privilege({role},c.oid,'INSERT') "
        "AND has_table_privilege({role},c.oid,'UPDATE') "
        "AND has_table_privilege({role},c.oid,'DELETE'))".format(role=subject),
        (schema, *principal * 4),
    )
    tables = tuple(row[0] for row in cursor.fetchall())
    cursor.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n "
        "ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind='S' "
        "AND NOT (has_sequence_privilege({role},c.oid,'SELECT') "
        "AND (has_sequence_privilege({role},c.oid,'USAGE') "
        "OR has_sequence_privilege({role},c.oid,'UPDATE')))".format(role=subject),
        (schema, *principal * 3),
    )
    return {
        "schema": schema_missing,
        "tables": tables,
        "sequences": tuple(row[0] for row in cursor.fetchall()),
    }
