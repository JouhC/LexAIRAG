def assert_table_exists(conn, table_name: str, schema: str = "public"):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.{table_name}",))
        regclass = cur.fetchone()[0]
        if regclass is None:
            raise RuntimeError(f"Missing table: {schema}.{table_name}")


def assert_index_exists(conn, index_name: str, schema: str = "public"):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.{index_name}",))
        regclass = cur.fetchone()[0]
        if regclass is None:
            raise RuntimeError(f"Missing index: {schema}.{index_name}")


def assert_function_exists(conn, func_name: str, arg_types=(), schema: str = "public"):
    """
    arg_types example: ('bigint', 'text') if you need to disambiguate overloads.
    """
    with conn.cursor() as cur:
        if arg_types:
            cur.execute(
                """
                SELECT 1
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = %s
                  AND p.proname = %s
                  AND p.proargtypes = (
                      SELECT array_agg(t.oid ORDER BY t.oid)
                      FROM unnest(%s::regtype[]) rt
                      JOIN pg_type t ON t.oid = rt
                  )
                """,
                (schema, func_name, list(arg_types)),
            )
        else:
            cur.execute(
                """
                SELECT 1
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = %s AND p.proname = %s
                """,
                (schema, func_name),
            )

        if cur.fetchone() is None:
            raise RuntimeError(f"Missing function: {schema}.{func_name}")


def assert_trigger_exists(conn, trigger_name: str, table_name: str, schema: str = "public"):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM pg_trigger tg
            JOIN pg_class c ON tg.tgrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE tg.tgname = %s
              AND c.relname = %s
              AND n.nspname = %s
              AND NOT tg.tgisinternal
            """,
            (trigger_name, table_name, schema),
        )
        if cur.fetchone() is None:
            raise RuntimeError(
                f"Missing trigger: {trigger_name} on {schema}.{table_name}"
            )


def assert_constraint_exists(conn, table_name: str, constraint_name: str, schema: str = "public"):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM pg_constraint con
            JOIN pg_class rel ON con.conrelid = rel.oid
            JOIN pg_namespace nsp ON rel.relnamespace = nsp.oid
            WHERE con.conname = %s
              AND rel.relname = %s
              AND nsp.nspname = %s
            """,
            (constraint_name, table_name, schema),
        )
        if cur.fetchone() is None:
            raise RuntimeError(
                f"Missing constraint: {constraint_name} on {schema}.{table_name}"
            )
