import os
import psycopg
from config import settings

def create_connection():
    try:
        print(settings.DATABASE_URL)
        conn = psycopg.connect(
            dbname=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            host=settings.DB_HOST,
            port=settings.DB_PORT,
        )
        print("✅ Connection successful!")
        conn.autocommit = True
        return conn
    except Exception as e:
        print("❌ Connection failed:", e)

def close_connection(conn):
    if conn:
        conn.close()
        print("Connection closed.")

def initialize_db(conn):
    create_decisions_sql = """
    CREATE TABLE IF NOT EXISTS decisions (
        id          BIGSERIAL PRIMARY KEY,
        case_no     TEXT NOT NULL UNIQUE,    -- "G.R. No. 161796"
        division    TEXT,                    -- "THIRD DIVISION"
        title       TEXT,                    -- may be real title later; for now what you have
        created_at  TIMESTAMPTZ DEFAULT NOW(),
        updated_at  TIMESTAMPTZ DEFAULT NOW()
    );
    """

    with conn.cursor() as cur:
        cur.execute(create_decisions_sql)

def chunks_table_init(conn):
    create_chunks_sql = """
    CREATE TABLE IF NOT EXISTS decision_chunks (
        id              BIGSERIAL PRIMARY KEY,

        -- FK via decision_id for efficient joins
        decision_id     BIGINT NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,

        -- your metadata
        case_no         TEXT NOT NULL,     -- denormalized for convenience/debug
        section         TEXT,              -- 'PREAMBLE', 'FACTS', 'RULING', etc.
        chunk_index     INT NOT NULL,      -- 0,1,2,... within that case
        text            TEXT NOT NULL,

        -- for later / RAG
        token_count     INT,               -- optional (fill when you tokenize)
        embedding       VECTOR(1024),      -- BGE-M3 embedding

        created_at      TIMESTAMPTZ DEFAULT NOW(),
        updated_at      TIMESTAMPTZ DEFAULT NOW()
    );
    """

    with conn.cursor() as cur:
        cur.execute(create_chunks_sql)

def indexes_table_init(conn):
    create_indexes_sql = """
    -- Vector ANN index (tune lists as your corpus grows)
    CREATE INDEX IF NOT EXISTS idx_decision_chunks_embedding
    ON decision_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

    -- Navigate within a decision
    CREATE INDEX IF NOT EXISTS idx_decision_chunks_decision_idx
    ON decision_chunks (decision_id, chunk_index);

    CREATE INDEX IF NOT EXISTS idx_decision_chunks_case_no
    ON decision_chunks (case_no);

    CREATE INDEX IF NOT EXISTS idx_decisions_case_no
    ON decisions (case_no);
    """

    with conn.cursor() as cur:
        cur.execute(create_indexes_sql)

def auto_update_updateat(conn):
    trigger_fn_sql = """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """

    with conn.cursor() as cur:
        cur.execute(trigger_fn_sql)

    triggers_sql = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = 'trg_decisions_set_updated_at'
        ) THEN
            CREATE TRIGGER trg_decisions_set_updated_at
            BEFORE UPDATE ON decisions
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger WHERE tgname = 'trg_decision_chunks_set_updated_at'
        ) THEN
            CREATE TRIGGER trg_decision_chunks_set_updated_at
            BEFORE UPDATE ON decision_chunks
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
        END IF;
    END $$;
    """

    with conn.cursor() as cur:
        cur.execute(triggers_sql)

def unique_constraint_decision_chunks(conn):
    query = """
    DO $$
    BEGIN
        ALTER TABLE decision_chunks
        ADD CONSTRAINT unique_decision_chunk
        UNIQUE (case_no, section, chunk_index);
    EXCEPTION WHEN duplicate_object THEN
        -- constraint already exists, do nothing
    END $$;
    """
    with conn.cursor() as cur:
        cur.execute(query)

def main():
    conn = create_connection()
    if conn:
        initialize_db(conn)
        chunks_table_init(conn)
        indexes_table_init(conn)
        auto_update_updateat(conn)
        unique_constraint_decision_chunks(conn)
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully.")

if __name__ == "__main__":
    main()