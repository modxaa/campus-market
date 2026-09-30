from flask import Flask, render_template, request, redirect, url_for, session
from flask_wtf.csrf import CSRFProtect
from database import create_tables, get_db_connection
from dotenv import load_dotenv

import os
import uuid

from datetime import datetime, timedelta

from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import httpx


# =========================
# LOAD ENVIRONMENT VARIABLES
# =========================

load_dotenv()


# =========================
# FLASK APP
# =========================

app = Flask(__name__)


SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not configured. Set SECRET_KEY in the environment before starting the application."
    )

app.secret_key = SECRET_KEY

# Protect all POST/PUT/PATCH/DELETE requests against CSRF.
csrf = CSRFProtect(app)

# =========================================================
# SESSION SETTINGS
# =========================================================

# Keep users logged in for up to 30 days.
app.permanent_session_lifetime = timedelta(days=30)

# Refresh the permanent session lifetime when the user
# continues using the website.
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

# Basic browser/session security settings.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"

# Limit uploaded request size to 5 MB.
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


# =========================
# SUPABASE STORAGE
# =========================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
SUPABASE_BUCKET = "product-images"


def supabase_headers(content_type=None):

    headers = {
        "apikey": SUPABASE_SECRET_KEY
    }

    if content_type:
        headers["Content-Type"] = content_type

    return headers


def supabase_storage_configured():

    return bool(
        SUPABASE_URL
        and SUPABASE_SECRET_KEY
    )


# =========================
# IMAGE UPLOAD SETTINGS
# =========================

UPLOAD_FOLDER = "static/uploads"

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


os.makedirs(
    app.config["UPLOAD_FOLDER"],
    exist_ok=True
)


def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def create_safe_filename(filename):

    # Keep the original extension but generate a unique name so
    # two sellers cannot overwrite each other's uploaded images.
    extension = filename.rsplit(".", 1)[1].lower()
    return f"{uuid.uuid4().hex}.{extension}"


def upload_product_image(image):

    """Upload an image to Supabase Storage.

    The current Supabase sb_secret_ API keys are API keys, not JWTs.
    Therefore this backend sends the key only in the ``apikey`` header
    instead of ``Authorization: Bearer``.
    """

    safe_name = create_safe_filename(
        secure_filename(image.filename)
    )

    if supabase_storage_configured():

        file_bytes = image.read()

        content_type = image.mimetype or "application/octet-stream"

        upload_url = (
            f"{SUPABASE_URL}/storage/v1/object/"
            f"{SUPABASE_BUCKET}/{safe_name}"
        )

        response = httpx.post(
            upload_url,
            headers={
                "apikey": SUPABASE_SECRET_KEY,
                "Content-Type": content_type,
                "x-upsert": "false"
            },
            content=file_bytes,
            timeout=30
        )

        print("===== SUPABASE UPLOAD DEBUG =====")
        print("SUPABASE STATUS:", response.status_code)
        print("SUPABASE RESPONSE:", response.text)
        print("=================================")

        if response.status_code >= 400:
            raise Exception(
                f"Supabase returned HTTP {response.status_code}: "
                f"{response.text}"
            )

        return (
            f"{SUPABASE_URL}/storage/v1/object/public/"
            f"{SUPABASE_BUCKET}/{safe_name}"
        )

    image.save(
        os.path.join(
            app.config["UPLOAD_FOLDER"],
            safe_name
        )
    )

    return safe_name


def delete_product_image(image_value):

    """Delete a stored product image when possible."""

    if not image_value:
        return

    if supabase_storage_configured() and image_value.startswith(SUPABASE_URL):

        marker = f"/storage/v1/object/public/{SUPABASE_BUCKET}/"

        if marker in image_value:
            storage_path = image_value.split(marker, 1)[1]

            try:
                delete_url = (
                    f"{SUPABASE_URL}/storage/v1/object/"
                    f"{SUPABASE_BUCKET}"
                )

                response = httpx.request(
                    "DELETE",
                    delete_url,
                    headers=supabase_headers("application/json"),
                    json={"prefixes": [storage_path]},
                    timeout=30
                )

                response.raise_for_status()

            except Exception as error:
                print(
                    f"Supabase image delete failed: {type(error).__name__}: {error}",
                    flush=True
                )

        return

    local_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        image_value
    )

    if os.path.isfile(local_path):
        try:
            os.remove(local_path)
        except OSError:
            pass


# =========================
# PASSWORD HELPER
# =========================

def is_password_hash(password):

    return (
        password.startswith("scrypt:")
        or password.startswith("pbkdf2:")
    )


# =========================
# DATABASE
# =========================

create_tables()


# =========================================================
# CREATE LAST 7 DAYS
# =========================================================

def get_last_seven_days():

    today = datetime.now().date()

    days = []

    for number in range(6, -1, -1):

        day = today - timedelta(days=number)

        days.append(day)

    return days


# =========================
# HOME
# =========================

@app.route("/")
def home():

    connection = get_db_connection()

    trending_products = connection.execute(
        """
        SELECT
            products.*,
            users.phone AS seller_phone

        FROM products

        JOIN users
        ON products.seller_id = users.id

        ORDER BY products.created_at DESC

        LIMIT 6
        """
    ).fetchall()

    connection.close()

    return render_template(
        "index.html",
        trending_products=trending_products
    )


# =========================
# TRENDING PRODUCTS
# =========================

@app.route("/trending")
def trending():

    connection = get_db_connection()

    products = connection.execute(
        """
        SELECT
            products.*,
            users.phone AS seller_phone

        FROM products

        JOIN users
        ON products.seller_id = users.id

        ORDER BY products.created_at DESC

        LIMIT 6
        """
    ).fetchall()

    connection.close()

    return render_template(
        "products.html",
        products=products,
        search=""
    )


# =========================
# REGISTER
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    error = None

    if request.method == "POST":

        phone = request.form["phone"].strip()

        password = request.form["password"]

        category = request.form["category"]


        # =========================
        # NORMALIZE PHONE NUMBER
        # =========================

        if phone.startswith("+263"):

            phone = "0" + phone[4:]

        elif phone.startswith("263"):

            phone = "0" + phone[3:]


        # =========================
        # VALIDATE PHONE NUMBER
        # =========================

        if not (
            len(phone) == 10
            and phone.startswith("07")
            and phone.isdigit()
        ):

            error = (
                "Invalid Zimbabwe phone number. "
                "Example: 0771234567."
            )

            return render_template(
                "register.html",
                error=error
            )


        # =========================
        # VALIDATE PASSWORD
        # =========================

        has_letter = any(
            character.isalpha()
            for character in password
        )

        has_number = any(
            character.isdigit()
            for character in password
        )


        if (
            len(password) < 8
            or not has_letter
            or not has_number
        ):

            error = (
                "Password must be at least "
                "8 characters and contain "
                "at least one letter and "
                "one number."
            )

            return render_template(
                "register.html",
                error=error
            )


        # =========================
        # HASH PASSWORD
        # =========================

        hashed_password = generate_password_hash(
            password
        )


        # =========================
        # SAVE USER
        # =========================

        connection = get_db_connection()


        try:

            connection.execute(
                """
                INSERT INTO users
                (
                    phone,
                    password,
                    category
                )

                VALUES (?, ?, ?)
                """,
                (
                    phone,
                    hashed_password,
                    category
                )
            )

            connection.commit()


        except Exception:

            connection.close()

            error = (
                "An account with this "
                "phone number already exists."
            )

            return render_template(
                "register.html",
                error=error
            )


        connection.close()


        return redirect(
            url_for("login")
        )


    return render_template(
        "register.html",
        error=error
    )


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        phone = request.form["phone"].strip()

        password = request.form["password"]


        connection = get_db_connection()


        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE phone = ?
            """,
            (phone,)
        ).fetchone()


        if not user:

            connection.close()

            return "Invalid phone number or password."


        stored_password = user["password"]

        password_correct = False


        # =========================
        # NEW HASHED PASSWORD
        # =========================

        if is_password_hash(
            stored_password
        ):

            try:

                password_correct = check_password_hash(
                    stored_password,
                    password
                )

            except ValueError:

                password_correct = False


        # =========================
        # OLD PASSWORD MIGRATION
        # =========================

        else:

            if stored_password == password:

                password_correct = True


                new_password_hash = generate_password_hash(
                    password
                )


                connection.execute(
                    """
                    UPDATE users

                    SET password = ?

                    WHERE id = ?
                    """,
                    (
                        new_password_hash,
                        user["id"]
                    )
                )


                connection.commit()


        connection.close()


        if password_correct:

            # Keep the user logged in for the configured
            # permanent session lifetime.
            session.permanent = True

            session["user_id"] = user["id"]

            session["phone"] = user["phone"]

            return redirect(
                url_for("dashboard")
            )


        return "Invalid phone number or password."


    return render_template(
        "login.html"
    )


# =========================
# ADMIN LOGIN
# =========================

@app.route(
    "/admin-login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form["username"]

        password = request.form["password"]


        admin_username = os.getenv(
            "ADMIN_USERNAME"
        )

        admin_password = os.getenv(
            "ADMIN_PASSWORD"
        )


        if (
            username == admin_username
            and password == admin_password
        ):

            # Keep the admin logged in for the configured
            # permanent session lifetime.
            session.permanent = True

            session["admin"] = True

            return redirect(
                url_for("admin_dashboard")
            )


        return "Invalid admin username or password."


    return render_template(
        "admin_login.html"
    )


# =========================
# ADMIN DASHBOARD
# =========================

@app.route("/admin-dashboard")
def admin_dashboard():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    connection = get_db_connection()

    total_users = connection.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    total_sellers = connection.execute(
        """
        SELECT COUNT(*) FROM users
        WHERE category IS NOT NULL AND category != ''
        """
    ).fetchone()[0]

    total_products = connection.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    featured_products = connection.execute(
        "SELECT COUNT(*) FROM products WHERE featured = 1"
    ).fetchone()[0]

    total_interests = connection.execute(
        "SELECT COALESCE(SUM(interest_count), 0) FROM products"
    ).fetchone()[0]

    total_sales = connection.execute(
        "SELECT COALESCE(SUM(sales_count), 0) FROM products"
    ).fetchone()[0]

    seller_percentage = (
        round((total_sellers / total_users) * 100, 1)
        if total_users > 0 else 0
    )

    featured_percentage = (
        round((featured_products / total_products) * 100, 1)
        if total_products > 0 else 0
    )

    category_data = connection.execute(
        """
        SELECT category, COUNT(*) AS total
        FROM users
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY total DESC
        """
    ).fetchall()

    top_products = connection.execute(
        """
        SELECT name, interest_count, sales_count, featured
        FROM products
        ORDER BY interest_count DESC, sales_count DESC, created_at DESC
        LIMIT 5
        """
    ).fetchall()

    recent_users = connection.execute(
        """
        SELECT phone, category, created_at
        FROM users
        ORDER BY created_at DESC
        LIMIT 5
        """
    ).fetchall()

    recent_products = connection.execute(
        """
        SELECT products.name, products.category, products.price,
               products.created_at, users.phone AS seller_phone
        FROM products
        JOIN users ON products.seller_id = users.id
        ORDER BY products.created_at DESC
        LIMIT 5
        """
    ).fetchall()

    last_seven_days = get_last_seven_days()

    user_growth_rows = connection.execute(
        """
        SELECT date(created_at) AS day, COUNT(*) AS total
        FROM users
        WHERE date(created_at) >= date('now', '-6 days')
        GROUP BY date(created_at)
        ORDER BY day ASC
        """
    ).fetchall()

    product_growth_rows = connection.execute(
        """
        SELECT date(created_at) AS day, COUNT(*) AS total
        FROM products
        WHERE date(created_at) >= date('now', '-6 days')
        GROUP BY date(created_at)
        ORDER BY day ASC
        """
    ).fetchall()

    user_growth_lookup = {
        row["day"]: row["total"] for row in user_growth_rows
    }

    product_growth_lookup = {
        row["day"]: row["total"] for row in product_growth_rows
    }

    user_growth = []
    product_growth = []

    for day in last_seven_days:
        day_string = day.isoformat()

        user_growth.append({
            "date": day_string,
            "label": day.strftime("%a"),
            "total": user_growth_lookup.get(day_string, 0)
        })

        product_growth.append({
            "date": day_string,
            "label": day.strftime("%a"),
            "total": product_growth_lookup.get(day_string, 0)
        })

    today_string = datetime.now().date().isoformat()

    users_today = connection.execute(
        """
        SELECT COUNT(*) FROM users
        WHERE date(created_at) = ?
        """,
        (today_string,)
    ).fetchone()[0]

    products_today = connection.execute(
        """
        SELECT COUNT(*) FROM products
        WHERE date(created_at) = ?
        """,
        (today_string,)
    ).fetchone()[0]

    connection.close()

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_sellers=total_sellers,
        total_products=total_products,
        featured_products=featured_products,
        total_interests=total_interests,
        total_sales=total_sales,
        seller_percentage=seller_percentage,
        featured_percentage=featured_percentage,
        category_data=category_data,
        top_products=top_products,
        recent_users=recent_users,
        recent_products=recent_products,
        user_growth=user_growth,
        product_growth=product_growth,
        users_today=users_today,
        products_today=products_today
    )


# =========================
# ADMIN USERS
# =========================

@app.route("/admin-users")
def admin_users():

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    connection = get_db_connection()


    users = connection.execute(
        """
        SELECT
            id,
            phone,
            category,
            created_at

        FROM users

        ORDER BY created_at DESC
        """
    ).fetchall()


    connection.close()


    return render_template(
        "admin_users.html",
        users=users
    )


# =========================
# DELETE USER
# =========================

@app.route(
    "/admin-users/delete/<int:user_id>",
    methods=["POST"]
)
def delete_user(user_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    connection = get_db_connection()


    products_to_delete = connection.execute(
        "SELECT image FROM products WHERE seller_id = ?",
        (user_id,)
    ).fetchall()

    for product in products_to_delete:
        delete_product_image(product["image"])


    connection.execute(
        """
        DELETE FROM users
        WHERE id = ?
        """,
        (user_id,)
    )


    connection.commit()

    connection.close()


    return redirect(
        url_for("admin_users")
    )


# =========================
# ADMIN PRODUCTS
# =========================

@app.route("/admin-products")
def admin_products():

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    connection = get_db_connection()


    products = connection.execute(
        """
        SELECT
            products.*,
            users.phone AS seller_phone

        FROM products

        JOIN users
        ON products.seller_id = users.id

        ORDER BY products.created_at DESC
        """
    ).fetchall()


    connection.close()


    return render_template(
        "admin_products.html",
        products=products
    )


# =========================
# FEATURE / UNFEATURE PRODUCT
# =========================

@app.route(
    "/admin-products/toggle-featured/<int:product_id>",
    methods=["POST"]
)
def toggle_featured(product_id):

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    connection = get_db_connection()

    product = connection.execute(
        "SELECT featured FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()

    if product:
        new_status = 0 if product["featured"] else 1

        connection.execute(
            """
            UPDATE products
            SET featured = ?
            WHERE id = ?
            """,
            (new_status, product_id)
        )
        connection.commit()

    connection.close()

    return redirect(url_for("admin_products"))


# =========================
# DELETE PRODUCT - ADMIN
# =========================

@app.route(
    "/admin-products/delete/<int:product_id>",
    methods=["POST"]
)
def delete_product(product_id):

    if not session.get("admin"):

        return redirect(
            url_for("admin_login")
        )


    connection = get_db_connection()


    product = connection.execute(
        "SELECT image FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()

    if product:
        delete_product_image(product["image"])

    connection.execute(
        """
        DELETE FROM products
        WHERE id = ?
        """,
        (product_id,)
    )


    connection.commit()

    connection.close()


    return redirect(
        url_for("admin_products")
    )


# =========================
# USER DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    return render_template(
        "dashboard.html"
    )


# =========================
# PRODUCTS + SEARCH
# =========================

@app.route("/products")
def products():

    search = request.args.get(
        "search",
        ""
    ).strip()


    connection = get_db_connection()


    if search:

        search_value = f"%{search}%"


        products = connection.execute(
            """
            SELECT
                products.*,
                users.phone AS seller_phone

            FROM products

            JOIN users
            ON products.seller_id = users.id

            WHERE
                products.name LIKE ?
                OR products.category LIKE ?
                OR products.description LIKE ?
                OR products.location LIKE ?

            ORDER BY products.created_at DESC
            """,
            (
                search_value,
                search_value,
                search_value,
                search_value
            )
        ).fetchall()


    else:

        products = connection.execute(
            """
            SELECT
                products.*,
                users.phone AS seller_phone

            FROM products

            JOIN users
            ON products.seller_id = users.id

            ORDER BY products.created_at DESC
            """
        ).fetchall()


    connection.close()


    return render_template(
        "products.html",
        products=products,
        search=search
    )


# =========================
# PRODUCT DETAILS
# =========================

@app.route(
    "/product/<int:product_id>"
)
def product_details(product_id):

    connection = get_db_connection()


    product = connection.execute(
        """
        SELECT
            products.*,
            users.phone AS seller_phone

        FROM products

        JOIN users
        ON products.seller_id = users.id

        WHERE products.id = ?
        """,
        (product_id,)
    ).fetchone()


    connection.close()


    if not product:

        return "Product not found.", 404


    return render_template(
        "product_details.html",
        product=product
    )


# =========================
# MY PRODUCTS
# =========================

@app.route("/my-products")
def my_products():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    connection = get_db_connection()


    products = connection.execute(
        """
        SELECT *
        FROM products

        WHERE seller_id = ?

        ORDER BY created_at DESC
        """,
        (session["user_id"],)
    ).fetchall()


    connection.close()


    return render_template(
        "my_products.html",
        products=products
    )


# =========================
# ADD PRODUCT
# =========================

@app.route(
    "/add-product",
    methods=["GET", "POST"]
)
def add_product():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if request.method == "POST":

        name = request.form["name"]

        price = request.form["price"]

        category = request.form["category"]

        description = request.form["description"]

        location = request.form["location"]

        contact = request.form["contact"]


        image = request.files.get(
            "image"
        )


        image_filename = None


        if image and image.filename:

            if not allowed_file(
                image.filename
            ):

                return (
                    "Invalid image type. "
                    "Please upload PNG, JPG, "
                    "JPEG, GIF, or WEBP."
                )


            try:
                image_filename = upload_product_image(image)
            except Exception as error:
                print(
                    f"Supabase image upload failed: {type(error).__name__}: {error}",
                    flush=True
                )
                return "Image upload failed. Please try again."


        connection = get_db_connection()


        connection.execute(
            """
            INSERT INTO products
            (
                seller_id,
                name,
                price,
                category,
                description,
                location,
                contact,
                image
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                name,
                price,
                category,
                description,
                location,
                contact,
                image_filename
            )
        )


        connection.commit()

        connection.close()


        return redirect(
            url_for("products")
        )


    return render_template(
        "add_product.html"
    )


# =========================
# EDIT PRODUCT
# =========================

@app.route(
    "/edit-product/<int:product_id>",
    methods=["GET", "POST"]
)
def edit_product(product_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    connection = get_db_connection()


    product = connection.execute(
        """
        SELECT *
        FROM products

        WHERE
            id = ?
            AND seller_id = ?
        """,
        (
            product_id,
            session["user_id"]
        )
    ).fetchone()


    if not product:

        connection.close()

        return (
            "Product not found or "
            "you do not have permission "
            "to edit it."
        )


    if request.method == "POST":

        name = request.form["name"]

        price = request.form["price"]

        category = request.form["category"]

        description = request.form["description"]

        location = request.form["location"]

        contact = request.form["contact"]


        image = request.files.get(
            "image"
        )


        image_filename = product["image"]


        if image and image.filename:

            if not allowed_file(
                image.filename
            ):

                connection.close()

                return (
                    "Invalid image type. "
                    "Please upload PNG, JPG, "
                    "JPEG, GIF, or WEBP."
                )


            try:
                image_filename = upload_product_image(image)
            except Exception as error:
                print(
                    f"Supabase image upload failed: {type(error).__name__}: {error}",
                    flush=True
                )
                connection.close()
                return "Image upload failed. Please try again."


        connection.execute(
            """
            UPDATE products

            SET
                name = ?,
                price = ?,
                category = ?,
                description = ?,
                location = ?,
                contact = ?,
                image = ?

            WHERE
                id = ?
                AND seller_id = ?
            """,
            (
                name,
                price,
                category,
                description,
                location,
                contact,
                image_filename,
                product_id,
                session["user_id"]
            )
        )


        connection.commit()

        connection.close()


        return redirect(
            url_for("my_products")
        )


    connection.close()


    return render_template(
        "edit_product.html",
        product=product
    )


# =========================
# DELETE PRODUCT - SELLER
# =========================

@app.route(
    "/my-products/delete/<int:product_id>",
    methods=["POST"]
)
def delete_my_product(product_id):

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    connection = get_db_connection()


    product = connection.execute(
        """
        SELECT image
        FROM products
        WHERE id = ? AND seller_id = ?
        """,
        (product_id, session["user_id"])
    ).fetchone()

    if product:
        delete_product_image(product["image"])

    connection.execute(
        """
        DELETE FROM products

        WHERE
            id = ?
            AND seller_id = ?
        """,
        (
            product_id,
            session["user_id"]
        )
    )


    connection.commit()

    connection.close()


    return redirect(
        url_for("my_products")
    )


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("home")
    )


# =========================
# UPLOAD SIZE ERROR
# =========================

@app.errorhandler(413)
def request_entity_too_large(error):

    return "File is too large. Please upload an image smaller than 5 MB.", 413


# =========================
# START APPLICATION
# =========================

if __name__ == "__main__":

    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1"
    )