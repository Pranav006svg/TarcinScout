import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

POSTGRESQL_URL = os.getenv("POSTGRESQL_URL")

def get_db_connection():
    """Establishes connection to the PostgreSQL database."""
    if not POSTGRESQL_URL:
        raise ValueError("POSTGRESQL_URL environment variable is not set in .env")
    return psycopg2.connect(POSTGRESQL_URL)

def create_table():
    """Creates the college_contacts table and adds missing columns if they do not exist."""
    query_create = """
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
        session_id TEXT,
        college_type TEXT,
        custom_notes TEXT,
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(query_create)
                # Alter queries for backward compatibility with existing databases
                cursor.execute("ALTER TABLE college_contacts ADD COLUMN IF NOT EXISTS session_id TEXT;")
                cursor.execute("ALTER TABLE college_contacts ADD COLUMN IF NOT EXISTS college_type TEXT;")
                cursor.execute("ALTER TABLE college_contacts ADD COLUMN IF NOT EXISTS custom_notes TEXT;")
        conn.close()
        print("SUCCESS: PostgreSQL connection established and table verified/updated.")
    except Exception as e:
        print(f"DATABASE INITIALIZATION WARNING: Could not connect to PostgreSQL. Reason: {e}")
        print("Make sure your Aiven service is active, DNS has propagated, and network connection is available.")

def insert_contact(data):
    """
    Inserts a single contact dictionary into the database.
    """
    query = """
    INSERT INTO college_contacts (
        college_name, website_url, person_name, role, department, email, phone, address, source_url, session_id, college_type, custom_notes, scraped_at
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """
    conn = get_db_connection()
    scraped_at = datetime.now()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (
                    data.get('college_name'),
                    data.get('website_url'),
                    data.get('person_name'),
                    data.get('role'),
                    data.get('department'),
                    data.get('email'),
                    data.get('phone'),
                    data.get('address'),
                    data.get('source_url'),
                    data.get('session_id'),
                    data.get('college_type'),
                    data.get('custom_notes'),
                    scraped_at
                ))
    finally:
        conn.close()

def get_all_contacts(session_id=None):
    """Fetches all contact records ordered by insertion time, scoped to session_id if provided."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if session_id:
                cursor.execute("SELECT * FROM college_contacts WHERE session_id = %s ORDER BY id DESC", (session_id,))
            else:
                cursor.execute("SELECT * FROM college_contacts ORDER BY id DESC")
            rows = cursor.fetchall()
            contacts = []
            for row in rows:
                c = dict(row)
                if isinstance(c.get('scraped_at'), datetime):
                    c['scraped_at'] = c['scraped_at'].strftime('%Y-%m-%d %H:%M:%S')
                contacts.append(c)
            return contacts
    finally:
        conn.close()

def delete_duplicates(session_id=None):
    """
    Deletes duplicate contact entries based on:
    - Same email AND phone AND person_name (when present).
    Keeps the earliest entry (the one with the lowest id).
    Scoped to session_id if provided.
    """
    if session_id:
        query = """
        DELETE FROM college_contacts 
        WHERE session_id = %s AND id NOT IN (
            SELECT MIN(id) 
            FROM college_contacts 
            WHERE session_id = %s
            GROUP BY 
                COALESCE(email, ''), 
                COALESCE(phone, ''), 
                COALESCE(person_name, ''), 
                COALESCE(role, '')
        );
        """
        params = (session_id, session_id)
    else:
        query = """
        DELETE FROM college_contacts 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM college_contacts 
            GROUP BY 
                COALESCE(email, ''), 
                COALESCE(phone, ''), 
                COALESCE(person_name, ''), 
                COALESCE(role, '')
        );
        """
        params = ()
        
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                deleted_count = cursor.rowcount
                return deleted_count
    finally:
        conn.close()

def clear_database(session_id=None):
    """Clears records from the college_contacts table, scoped to session_id if provided."""
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                if session_id:
                    cursor.execute("DELETE FROM college_contacts WHERE session_id = %s;", (session_id,))
                else:
                    cursor.execute("DELETE FROM college_contacts;")
                return cursor.rowcount
    finally:
        conn.close()

def delete_contact(contact_id, session_id=None):
    """Deletes a single contact by id, scoped to session_id if provided."""
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                if session_id:
                    cursor.execute("DELETE FROM college_contacts WHERE id = %s AND session_id = %s;", (contact_id, session_id))
                else:
                    cursor.execute("DELETE FROM college_contacts WHERE id = %s;", (contact_id,))
                return cursor.rowcount
    finally:
        conn.close()

def delete_college(college_name, session_id=None):
    """Deletes all contacts belonging to a specific college, scoped to session_id if provided."""
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                if session_id:
                    cursor.execute("DELETE FROM college_contacts WHERE college_name = %s AND session_id = %s;", (college_name, session_id))
                else:
                    cursor.execute("DELETE FROM college_contacts WHERE college_name = %s;", (college_name,))
                return cursor.rowcount
    finally:
        conn.close()

