import sqlite3


DATABASE = "campus_market.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE)

    # Enable SQLite foreign-key enforcement
    connection.execute("PRAGMA foreign_keys = ON")

    connection.row_factory = sqlite3.Row

    return connection


def create_tables():

    connection = get_db_connection()


    # =====================================================
    # USERS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


    # =====================================================
    # PRODUCTS
    # =====================================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            seller_id INTEGER NOT NULL,

            name TEXT NOT NULL,

            price REAL NOT NULL,

            category TEXT NOT NULL,

            description TEXT NOT NULL,

            location TEXT NOT NULL,

            contact TEXT NOT NULL,

            image TEXT,

            featured INTEGER DEFAULT 0,

            sales_count INTEGER DEFAULT 0,

            interest_count INTEGER DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (seller_id)
            REFERENCES users (id)
        )
    """)


    # =====================================================
    # DATABASE MIGRATION
    #
    # This checks whether older databases are missing
    # newer product columns.
    # =====================================================

    columns = connection.execute(
        "PRAGMA table_info(products)"
    ).fetchall()


    column_names = [
        column["name"]
        for column in columns
    ]


    # -----------------------------------------------------
    # IMAGE
    # -----------------------------------------------------

    if "image" not in column_names:

        connection.execute("""
            ALTER TABLE products
            ADD COLUMN image TEXT
        """)


    # -----------------------------------------------------
    # FEATURED
    # -----------------------------------------------------

    if "featured" not in column_names:

        connection.execute("""
            ALTER TABLE products
            ADD COLUMN featured INTEGER DEFAULT 0
        """)


    # -----------------------------------------------------
    # SALES COUNT
    # -----------------------------------------------------

    if "sales_count" not in column_names:

        connection.execute("""
            ALTER TABLE products
            ADD COLUMN sales_count INTEGER DEFAULT 0
        """)


    # -----------------------------------------------------
    # INTEREST COUNT
    # -----------------------------------------------------

    if "interest_count" not in column_names:

        connection.execute("""
            ALTER TABLE products
            ADD COLUMN interest_count INTEGER DEFAULT 0
        """)


    # =====================================================
    # SAVE CHANGES
    # =====================================================

    connection.commit()

    connection.close()