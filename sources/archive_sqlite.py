import sqlite3
from pathlib import Path

home_dir = Path.home()

# ----------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------
master_db_path = Path(home_dir, "battery_profiles/master.db")      # will be created/overwritten
folder_with_dbs = Path(home_dir, "battery_profiles/to_archive")

db_patterns = ["*.db", "*.sqlite"]
source_files = []
for pat in db_patterns:
    source_files.extend(folder_with_dbs.glob(pat))
source_files.sort()


# ----------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------
def get_table_info(conn, table):
    """Return list of (cid, name, type, notnull, dflt_value, pk) for a table."""
    cur = conn.execute(f"PRAGMA table_info('{table}')")
    return cur.fetchall()

def get_foreign_keys(conn, table):
    """Return list of (id, seq, table, from, to, on_update, on_delete, match)."""
    cur = conn.execute(f"PRAGMA foreign_key_list('{table}')")
    return cur.fetchall()

def copy_table(master_cur, src_cur, table, pk_offset, fk_map):
    """
    Insert rows from src_cur into master_cur, applying pk/fk offsets.
    pk_offset: dict {pk_column: offset_int}
    fk_map:   dict {fk_column: (referenced_table, referenced_pk_column, offset_int)}
    """
    # Get column names
    cols = [info[1] for info in get_table_info(src_cur.connection, table)]
    col_list = ", ".join(cols)

    # Build SELECT expression applying offsets where needed
    select_expr = []
    for col in cols:
        if col in pk_offset:
            select_expr.append(f"{col} + {pk_offset[col]} AS {col}")
        elif col in fk_map:
            _, _, off = fk_map[col]
            select_expr.append(f"{col} + {off} AS {col}")
        else:
            select_expr.append(col)
    select_clause = ", ".join(select_expr)

    # Perform insertion
    sql = f"INSERT INTO {table} ({col_list}) SELECT {select_clause} FROM src.{table}"
    master_cur.execute(sql)

# ----------------------------------------------------------------------
# MAIN MERGE LOGIC
# ----------------------------------------------------------------------
# 1️⃣ Create (or clear) the master DB using the schema from the first source
first_src = source_files[0]
with sqlite3.connect(first_src) as src_conn, \
     sqlite3.connect(master_db_path) as master_conn:

    # Copy the entire schema (tables, indexes, triggers, etc.)
    src_conn.backup(master_conn)   # copies everything, we'll delete data later
    master_cur = master_conn.cursor()
    master_cur.execute("DELETE FROM sqlite_sequence")  # reset autoincrement counters

    # Remove all data from the master (keep schema only)
    for tbl in master_cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        master_cur.execute(f"DELETE FROM {tbl[0]}")
    master_conn.commit()

# 2️⃣ Process each source DB
for src_path in source_files:
    print(f"🔄 Merging {src_path.name}")

    with sqlite3.connect(master_db_path) as master_conn, \
         sqlite3.connect(src_path) as src_conn:

        master_cur = master_conn.cursor()
        src_cur    = src_conn.cursor()

        # Attach source as 'src' for convenience (optional)
        master_cur.execute("ATTACH DATABASE ? AS src", (str(src_path),))

        # Determine PK offsets for every table
        pk_offsets = {}   # {table: {pk_col: offset}}
        fk_offsets = {}   # {table: {fk_col: (ref_table, ref_pk, offset)}}

        # Gather list of tables (ignore sqlite internal tables)
        tables = [row[0] for row in master_cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]

        for tbl in tables:
            # Primary key detection
            pk_info = [c for c in get_table_info(src_conn, tbl) if c[5] > 0]  # pk flag >0
            pk_offsets[tbl] = {}
            for col in pk_info:
                pk_col = col[1]
                # Find current max in master for this PK column
                cur_max = master_cur.execute(
                    f"SELECT IFNULL(MAX({pk_col}),0) FROM {tbl}"
                ).fetchone()[0]
                pk_offsets[tbl][pk_col] = cur_max

            # Foreign key detection
            fk_info = get_foreign_keys(src_conn, tbl)
            fk_offsets[tbl] = {}
            for fk in fk_info:
                fk_col = fk[3]          # column in this table
                ref_tbl = fk[2]         # referenced table
                ref_pk  = fk[4]         # column in referenced table
                # Offset for the referenced PK (must already be computed)
                offset = pk_offsets[ref_tbl][ref_pk]
                fk_offsets[tbl][fk_col] = (ref_tbl, ref_pk, offset)

        # Now copy each table applying the calculated offsets
        for tbl in tables:
            copy_table(master_cur, src_cur, tbl,
                       pk_offsets[tbl],
                       fk_offsets[tbl])

        master_conn.commit()
        master_cur.execute("DETACH src")

print("\n✅ Merge complete! The combined database is at:", master_db_path.resolve())
