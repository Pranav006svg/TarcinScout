import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

POSTGRESQL_URL = os.getenv("POSTGRESQL_URL")
SQLITE_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'college_contacts.db')

def migrate():
    print("--- Starting PostgreSQL Schema Seeding & Migration ---")
    if not POSTGRESQL_URL:
        print("ERROR: POSTGRESQL_URL is not set in .env file.")
        return

    print("Connecting to PostgreSQL...")
    try:
        pg_conn = psycopg2.connect(POSTGRESQL_URL)
        pg_cursor = pg_conn.cursor()
    except Exception as e:
        print(f"ERROR: Failed to connect to PostgreSQL: {e}")
        return

    # 1. Create table in PostgreSQL
    print("Seeding/creating table in PostgreSQL...")
    create_table_query = """
    CREATE TABLE IF NOT EXISTS college_contacts (
        id SERIAL PRIMARY KEY,
        college_name TEXT,
        website_url TEXT,
        person_name TEXT,
        role TEXT,
        department TEXT,
        email TEXT,
        phone TEXT,
        address TEXT,
        source_url TEXT,
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        pg_cursor.execute(create_table_query)
        pg_conn.commit()
        print("SUCCESS: Table 'college_contacts' seeded in PostgreSQL database.")
    except Exception as e:
        pg_conn.rollback()
        print(f"ERROR: Failed to create table: {e}")
        pg_conn.close()
        return

    # 2. Check if SQLite database exists and has data to migrate
    if os.path.exists(SQLITE_DB_PATH):
        print(f"Found existing SQLite database at {SQLITE_DB_PATH}. Checking for records to migrate...")
        try:
            sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='college_contacts';")
            if sqlite_cursor.fetchone():
                sqlite_cursor.execute("SELECT college_name, website_url, person_name, role, department, email, phone, address, source_url, scraped_at FROM college_contacts;")
                rows = sqlite_cursor.fetchall()
                if rows:
                    print(f"Found {len(rows)} records in SQLite. Checking if PostgreSQL has data...")
                    
                    # Check if there are records in PostgreSQL
                    pg_cursor.execute("SELECT COUNT(*) FROM college_contacts;")
                    pg_count = pg_cursor.fetchone()[0]
                    if pg_count > 0:
                        print(f"PostgreSQL already has {pg_count} records. Skipping data migration to prevent duplicates.")
                    else:
                        insert_query = """
                        INSERT INTO college_contacts (
                            college_name, website_url, person_name, role, department, email, phone, address, source_url, scraped_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """
                        for row in rows:
                            pg_cursor.execute(insert_query, row)
                        pg_conn.commit()
                        print(f"SUCCESS: Migrated {len(rows)} records from SQLite to PostgreSQL!")
                else:
                    print("SQLite table 'college_contacts' is empty. Nothing to migrate.")
            else:
                print("SQLite database does not contain 'college_contacts' table.")
            sqlite_conn.close()
        except Exception as e:
            print(f"WARNING: SQLite migration failed: {e}")
    else:
        print("No local SQLite database found. Skipping data migration.")

    pg_cursor.close()
    pg_conn.close()
    print("--- Migration and Seeding Complete! ---")

if __name__ == "__main__":
    migrate()
