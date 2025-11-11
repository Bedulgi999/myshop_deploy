import os
import sqlite3
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session
)
from werkzeug.utils import secure_filename
from email.mime.text import MIMEText
import smtplib

# -----------------------------
# 기본 설정 (한 폴더 구조)
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 모든 html/css/js/이미지를 한 폴더에 둘 때:
app = Flask(
    __name__,
    template_folder=".",   # 현재 폴더에서 템플릿 찾기
    static_folder=".",     # 현재 폴더에서 정적 파일 찾기
    static_url_path=""     # /파일명 으로 바로 접근 가능하게
)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

DB_PATH = os.path.join(BASE_DIR, "shop.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

SHOP_NAME = os.environ.get("SHOP_NAME", "DoveShop")


# -----------------------------
# 공용 함수
# -----------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def send_email(to_email: str, subject: str, body: str):
    print("📧 [테스트 모드] 메일 전송 생략")
    print("To:", to_email)
    print("Subject:", subject)
    print("Body:", body)
    return

    """
    Gmail SMTP로 메일 보내기
    Railway 환경변수:
      SMTP_EMAIL, SMTP_PASSWORD, ADMIN_EMAIL, SHOP_NAME
    """
    smtp_email = os.environ.get("SMTP_EMAIL")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_email or not smtp_password:
        print("❌ SMTP 설정 없음 - 메일 전송 스킵")
        print("받는 사람:", to_email)
        print("제목:", subject)
        print("내용:\n", body)
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_email
    msg["To"] = to_email

    try:
        s = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        s.login(smtp_email, smtp_password)
        s.send_message(msg)
        s.quit()
        print("📩 메일 전송 성공 ->", to_email)
    except Exception as e:
        print("❌ 메일 전송 실패:", e)


def login_required():
    return "user_id" in session


def admin_required():
    return session.get("is_admin") == 1


# -----------------------------
# DB 초기화
# -----------------------------
def init_db():
    conn = get_db()
    cur = conn.cursor()

    # 사용자
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0
    )
    """)

    # 상품
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price INTEGER,
        description TEXT,
        image TEXT
    )
    """)

    # 장바구니
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cart (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_id INTEGER
    )
    """)

    # 찜 목록
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wishlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_id INTEGER
    )
    """)

    # 주문
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_id INTEGER,
        phone TEXT,
        receipt TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )
    """)

    # 충전 요청
    cur.execute("""
    CREATE TABLE IF NOT EXISTS recharge_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )
    """)

    # 환불 요청
    cur.execute("""
    CREATE TABLE IF NOT EXISTS refund_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )
    """)

    # 거래 내역
    cur.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        amount INTEGER,
        description TEXT,
        status TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )
    """)

    # 기본 관리자 계정
    admin_exists = cur.execute("SELECT * FROM users WHERE is_admin=1").fetchone()
    if not admin_exists:
        cur.execute(
            "INSERT INTO users (username, password, is_admin, balance) VALUES (?, ?, 1, 0)",
            ("admin", "1234"),
        )
        print("✅ 기본 관리자 계정 생성됨: admin / 1234")

    conn.commit()
    conn.close()


# 앱 import될 때도 항상 DB 보장
init_db()


# -----------------------------
# 메인 페이지
# -----------------------------
@app.route("/")
def index():
    conn = get_db()
    products = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()

    balance = None
    if login_required():
        user = conn.execute(
            "SELECT balance FROM users WHERE id=?",
            (session["user_id"],)
        ).fetchone()
        balance = user["balance"] if user else 0

    return render_template("index.html", products=products, balance=balance)


# -----------------------------
# 회원 가입 / 로그인 / 로그아웃
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            flash("아이디와 비밀번호를 입력해주세요.")
            return redirect(url_for("register"))

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )
            conn.commit()
            flash("회원가입 성공! 로그인 해주세요.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("이미 존재하는 아이디입니다.")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            flash("로그인 성공!")

            if user["is_admin"] == 1:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("index"))
        else:
            flash("아이디 또는 비밀번호가 올바르지 않습니다.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("로그아웃 되었습니다.")
    return redirect(url_for("index"))


# -----------------------------
# 마이페이지
# -----------------------------
@app.route("/mypage")
def mypage():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    uid = session["user_id"]

    user = conn.execute(
        "SELECT username, balance, is_admin FROM users WHERE id=?",
        (uid,)
    ).fetchone()

    order_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM orders WHERE user_id=?",
        (uid,)
    ).fetchone()["cnt"]

    return render_template(
        "mypage.html",
        user=user,
        order_count=order_count
    )


# -----------------------------
# 장바구니
# -----------------------------
@app.route("/cart")
def cart():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    rows = conn.execute("""
        SELECT c.id AS cart_id, p.id AS product_id, p.name, p.price, p.image
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id=?
        ORDER BY c.id DESC
    """, (session["user_id"],)).fetchall()

    total = sum(row["price"] for row in rows) if rows else 0
    return render_template("cart.html", items=rows, total=total)


@app.route("/cart/add/<int:pid>")
def add_cart(pid):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute(
        "INSERT INTO cart (user_id, product_id) VALUES (?, ?)",
        (session["user_id"], pid)
    )
    conn.commit()
    flash("장바구니에 담았습니다.")
    return redirect(request.referrer or url_for("index"))


@app.route("/cart/remove/<int:cart_id>")
def remove_cart(cart_id):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute(
        "DELETE FROM cart WHERE id=? AND user_id=?",
        (cart_id, session["user_id"])
    )
    conn.commit()
    flash("장바구니에서 삭제되었습니다.")
    return redirect(url_for("cart"))


@app.route("/cart/checkout", methods=["POST"])
def cart_checkout():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    uid = session["user_id"]

    items = conn.execute("""
        SELECT c.id AS cart_id, p.id AS product_id, p.name, p.price
        FROM cart c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id=?
    """, (uid,)).fetchall()

    if not items:
        flash("장바구니가 비어 있습니다.")
        return redirect(url_for("cart"))

    total_price = sum(row["price"] for row in items)
    user = conn.execute(
        "SELECT balance FROM users WHERE id=?",
        (uid,)
    ).fetchone()
    balance = user["balance"] if user else 0

    if balance < total_price:
        flash("잔액이 부족합니다. 충전 후 이용해주세요.")
        return redirect(url_for("recharge"))

    # 주문 생성
    for row in items:
        conn.execute("""
            INSERT INTO orders (user_id, product_id, status)
            VALUES (?, ?, 'paid')
        """, (uid, row["product_id"]))

    # 거래 내역
    conn.execute("""
        INSERT INTO transactions (user_id, type, amount, description, status)
        VALUES (?, 'purchase', ?, ?, 'completed')
    """, (uid, total_price, f"장바구니에서 {len(items)}개 상품 구매"))

    # 잔액 차감
    conn.execute(
        "UPDATE users SET balance = balance - ? WHERE id=?",
        (total_price, uid)
    )

    # 장바구니 비우기
    conn.execute("DELETE FROM cart WHERE user_id=?", (uid,))
    conn.commit()

    flash("주문이 완료되었습니다.")
    return redirect(url_for("orders"))


# -----------------------------
# 찜 목록
# -----------------------------
@app.route("/wishlist")
def wishlist():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    rows = conn.execute("""
        SELECT w.id AS wid, p.id AS pid, p.name, p.price, p.image
        FROM wishlist w
        JOIN products p ON w.product_id = p.id
        WHERE w.user_id=?
        ORDER BY w.id DESC
    """, (session["user_id"],)).fetchall()

    return render_template("wishlist.html", items=rows)


@app.route("/wishlist/add/<int:pid>")
def add_wishlist(pid):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    exist = conn.execute("""
        SELECT id FROM wishlist
        WHERE user_id=? AND product_id=?
    """, (session["user_id"], pid)).fetchone()
    if not exist:
        conn.execute(
            "INSERT INTO wishlist (user_id, product_id) VALUES (?, ?)",
            (session["user_id"], pid)
        )
        conn.commit()
        flash("찜 목록에 추가되었습니다.")
    else:
        flash("이미 찜 목록에 있는 상품입니다.")
    return redirect(request.referrer or url_for("index"))


@app.route("/wishlist/remove/<int:wid>")
def remove_wishlist(wid):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute(
        "DELETE FROM wishlist WHERE id=? AND user_id=?",
        (wid, session["user_id"])
    )
    conn.commit()
    flash("찜 목록에서 삭제되었습니다.")
    return redirect(url_for("wishlist"))


# -----------------------------
# 주문 목록
# -----------------------------
@app.route("/orders")
def orders():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    rows = conn.execute("""
        SELECT o.id, o.status, o.created_at,
               p.name AS product_name, p.price
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.user_id=?
        ORDER BY o.id DESC
    """, (session["user_id"],)).fetchall()
    return render_template("orders.html", orders=rows)


# -----------------------------
# 상품 개별 구매 요청 (전화번호 + 영수증 + 이메일)
# -----------------------------
@app.route("/order/<int:product_id>", methods=["GET", "POST"])
def order(product_id):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    product = conn.execute(
        "SELECT * FROM products WHERE id=?",
        (product_id,)
    ).fetchone()
    if not product:
        return "상품을 찾을 수 없습니다.", 404

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        receipt = request.files.get("receipt")

        receipt_filename = None
        if receipt and allowed_file(receipt.filename):
            filename = secure_filename(receipt.filename)
            receipt_filename = f"receipt_{product_id}_{filename}"
            receipt.save(os.path.join(UPLOAD_FOLDER, receipt_filename))

        # DB에 주문 저장
        conn.execute("""
            INSERT INTO orders (user_id, product_id, phone, receipt, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (session["user_id"], product_id, phone, receipt_filename))
        conn.commit()

        # 관리자/사용자에게 메일
        admin_email = os.environ.get("ADMIN_EMAIL") or os.environ.get("SMTP_EMAIL")
        user_email = os.environ.get("USER_TEST_EMAIL")  # 실제로는 회원 이메일 컬럼이 있으면 좋지만, 지금은 옵션

        # 관리자용 메일
        body_admin = (
            f"[{SHOP_NAME}] 새 구매 요청이 도착했습니다.\n\n"
            f"상품명: {product['name']}\n"
            f"가격: {product['price']}원\n"
            f"구매자: {session.get('username')}\n"
            f"전화번호: {phone}\n"
            f"영수증 파일명: {receipt_filename if receipt_filename else '없음'}\n"
        )
        if admin_email:
            send_email(admin_email, f"[{SHOP_NAME}] 새 구매 요청", body_admin)

        # 사용자용 메일 (선택적)
        if user_email:
            body_user = (
                f"[{SHOP_NAME}] 구매 요청이 접수되었습니다.\n\n"
                f"상품명: {product['name']}\n"
                f"가격: {product['price']}원\n"
                f"입력하신 전화번호: {phone}\n\n"
                "관리자가 확인 후 별도로 안내드립니다."
            )
            send_email(user_email, f"[{SHOP_NAME}] 구매 요청 접수 안내", body_user)

        flash("구매 요청이 전송되었습니다! 관리자가 확인 후 처리합니다.")
        return redirect(url_for("order_complete", order_id=conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]))

    return render_template("order.html", product=product)


@app.route("/order_complete/<int:order_id>")
def order_complete(order_id):
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    row = conn.execute("""
        SELECT o.id, o.status, o.created_at,
               p.name AS product_name, p.price
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.id=? AND o.user_id=?
    """, (order_id, session["user_id"])).fetchone()
    if not row:
        return "주문을 찾을 수 없습니다.", 404
    return render_template("order_complete.html", order=row)


# -----------------------------
# 충전 / 환불 / 거래 내역
# -----------------------------
@app.route("/recharge", methods=["GET", "POST"])
def recharge():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    uid = session["user_id"]

    if request.method == "POST":
        amount_str = request.form.get("amount", "0").strip()
        try:
            amount = int(amount_str)
        except ValueError:
            amount = 0

        if amount <= 0:
            flash("올바른 금액을 입력해주세요.")
            return redirect(url_for("recharge"))

        conn.execute("""
            INSERT INTO recharge_requests (user_id, amount, status)
            VALUES (?, ?, 'pending')
        """, (uid, amount))
        conn.execute("""
            INSERT INTO transactions (user_id, type, amount, description, status)
            VALUES (?, 'recharge_request', ?, '충전 요청', 'pending')
        """, (uid, amount))
        conn.commit()

        # 관리자 & 사용자에게 메일
        admin_email = os.environ.get("ADMIN_EMAIL") or os.environ.get("SMTP_EMAIL")
        user_email = os.environ.get("USER_TEST_EMAIL")  # 실제 회원 이메일이 있다면 거기로

        if admin_email:
            body_admin = (
                f"[{SHOP_NAME}] 새 충전 요청\n\n"
                f"사용자: {session.get('username')}\n"
                f"금액: {amount}원\n"
            )
            send_email(admin_email, f"[{SHOP_NAME}] 충전 요청", body_admin)

        if user_email:
            body_user = (
                f"[{SHOP_NAME}] 충전 요청이 접수되었습니다.\n\n"
                f"요청 금액: {amount}원\n"
                "관리자가 확인 후 승인하면 잔액에 반영됩니다."
            )
            send_email(user_email, f"[{SHOP_NAME}] 충전 요청 접수 안내", body_user)

        flash("충전 요청이 전송되었습니다.")
        return redirect(url_for("recharge"))

    user = conn.execute(
        "SELECT balance FROM users WHERE id=?",
        (uid,)
    ).fetchone()
    balance = user["balance"] if user else 0

    rows = conn.execute("""
        SELECT id, amount, status, created_at
        FROM recharge_requests
        WHERE user_id=?
        ORDER BY id DESC
    """, (uid,)).fetchall()

    return render_template("recharge.html", balance=balance, requests=rows)


@app.route("/refund", methods=["GET", "POST"])
def refund():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    uid = session["user_id"]

    user = conn.execute(
        "SELECT balance FROM users WHERE id=?",
        (uid,)
    ).fetchone()
    balance = user["balance"] if user else 0

    if request.method == "POST":
        amount_str = request.form.get("amount", "0").strip()
        try:
            amount = int(amount_str)
        except ValueError:
            amount = 0

        if amount <= 0 or amount > balance:
            flash("올바른 환불 금액을 입력해주세요. (잔액 이내)")
            return redirect(url_for("refund"))

        conn.execute("""
            INSERT INTO refund_requests (user_id, amount, status)
            VALUES (?, ?, 'pending')
        """, (uid, amount))
        conn.execute("""
            INSERT INTO transactions (user_id, type, amount, description, status)
            VALUES (?, 'refund_request', ?, '환불 요청', 'pending')
        """, (uid, amount))
        conn.commit()

        # 관리자 / 사용자 메일 (옵션)
        admin_email = os.environ.get("ADMIN_EMAIL") or os.environ.get("SMTP_EMAIL")
        user_email = os.environ.get("USER_TEST_EMAIL")

        if admin_email:
            body_admin = (
                f"[{SHOP_NAME}] 새 환불 요청\n\n"
                f"사용자: {session.get('username')}\n"
                f"금액: {amount}원\n"
            )
            send_email(admin_email, f"[{SHOP_NAME}] 환불 요청", body_admin)

        if user_email:
            body_user = (
                f"[{SHOP_NAME}] 환불 요청이 접수되었습니다.\n\n"
                f"요청 금액: {amount}원\n"
                "관리자가 확인 후 처리됩니다."
            )
            send_email(user_email, f"[{SHOP_NAME}] 환불 요청 접수 안내", body_user)

        flash("환불 요청이 전송되었습니다.")
        return redirect(url_for("refund"))

    rows = conn.execute("""
        SELECT id, amount, status, created_at
        FROM refund_requests
        WHERE user_id=?
        ORDER BY id DESC
    """, (uid,)).fetchall()

    return render_template("refund.html", balance=balance, requests=rows)


@app.route("/transactions")
def transactions():
    if not login_required():
        return redirect(url_for("login"))
    conn = get_db()
    rows = conn.execute("""
        SELECT id, type, amount, description, status, created_at
        FROM transactions
        WHERE user_id=?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()
    return render_template("transactions.html", rows=rows)


# -----------------------------
# 관리자: 로그인 & 대시보드
# -----------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        conn = get_db()
        user = conn.execute("""
            SELECT * FROM users
            WHERE username=? AND password=? AND is_admin=1
        """, (username, password)).fetchone()

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            flash("관리자 로그인 성공!")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("관리자 계정이 아니거나 비밀번호가 틀렸습니다.")
    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("admin_login"))
    conn = get_db()

    product_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM products"
    ).fetchone()["cnt"]

    order_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM orders"
    ).fetchone()["cnt"]

    pending_recharges = conn.execute(
        "SELECT COUNT(*) AS cnt FROM recharge_requests WHERE status='pending'"
    ).fetchone()["cnt"]

    pending_refunds = conn.execute(
        "SELECT COUNT(*) AS cnt FROM refund_requests WHERE status='pending'"
    ).fetchone()["cnt"]

    products = conn.execute(
        "SELECT * FROM products ORDER BY id DESC"
    ).fetchall()

    return render_template(
        "admin_dashboard.html",
        product_count=product_count,
        order_count=order_count,
        pending_recharges=pending_recharges,
        pending_refunds=pending_refunds,
        products=products
    )


# -----------------------------
# 관리자: 상품 관리
# -----------------------------
@app.route("/admin/add", methods=["GET", "POST"])
def admin_add():
    if not admin_required():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price_str = request.form.get("price", "0").strip()
        desc = request.form.get("desc", "").strip()
        image_url = request.form.get("image_url", "").strip()
        file = request.files.get("image_file")

        try:
            price = int(price_str)
        except ValueError:
            price = 0

        if not name or price <= 0:
            flash("상품명과 가격을 올바르게 입력하세요.")
            return redirect(url_for("admin_add"))

        image_path = ""
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(save_path)
            # /uploads/... 으로 접근
            image_path = f"/uploads/{filename}"
        elif image_url:
            image_path = image_url

        conn = get_db()
        conn.execute("""
            INSERT INTO products (name, price, description, image)
            VALUES (?, ?, ?, ?)
        """, (name, price, desc, image_path))
        conn.commit()
        flash("상품이 등록되었습니다.")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_product_manage.html")


@app.route("/admin/delete/<int:pid>")
def admin_delete(pid):
    if not admin_required():
        return redirect(url_for("admin_login"))
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    flash("상품이 삭제되었습니다.")
    return redirect(url_for("admin_dashboard"))


# -----------------------------
# 관리자: 충전/환불 승인
# -----------------------------
@app.route("/admin/recharge")
def admin_recharge():
    if not admin_required():
        return redirect(url_for("admin_login"))
    conn = get_db()
    rows = conn.execute("""
        SELECT r.id, r.user_id, u.username, r.amount, r.status, r.created_at
        FROM recharge_requests r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.id DESC
    """).fetchall()
    return render_template("admin_recharge.html", rows=rows)


@app.route("/admin/recharge/approve/<int:req_id>")
def admin_recharge_approve(req_id):
    if not admin_required():
        return redirect(url_for("admin_login"))
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM recharge_requests WHERE id=?",
        (req_id,)
    ).fetchone()
    if not row:
        flash("충전 요청을 찾을 수 없습니다.")
        return redirect(url_for("admin_recharge"))

    if row["status"] != "pending":
        flash("이미 처리된 요청입니다.")
        return redirect(url_for("admin_recharge"))

    user_id = row["user_id"]
    amount = row["amount"]

    # 잔액 증가
    conn.execute(
        "UPDATE users SET balance = balance + ? WHERE id=?",
        (amount, user_id)
    )
    # 요청 상태 변경
    conn.execute(
        "UPDATE recharge_requests SET status='approved' WHERE id=?",
        (req_id,)
    )
    # 거래 내역 기록
    conn.execute("""
        INSERT INTO transactions (user_id, type, amount, description, status)
        VALUES (?, 'recharge', ?, '충전 승인', 'completed')
    """, (user_id, amount))
    conn.commit()

    # 사용자에게 메일 (USER_TEST_EMAIL 사용)
    user_email = os.environ.get("USER_TEST_EMAIL")
    if user_email:
        body = (
            f"[{SHOP_NAME}] 충전이 승인되었습니다.\n\n"
            f"충전 금액: {amount}원\n"
            "이용해주셔서 감사합니다."
        )
        send_email(user_email, f"[{SHOP_NAME}] 충전 승인 안내", body)

    flash("충전이 승인되었습니다.")
    return redirect(url_for("admin_recharge"))


@app.route("/admin/refunds")
def admin_refunds():
    if not admin_required():
        return redirect(url_for("admin_login"))
    conn = get_db()
    rows = conn.execute("""
        SELECT r.id, r.user_id, u.username, r.amount, r.status, r.created_at
        FROM refund_requests r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.id DESC
    """).fetchall()
    return render_template("admin_refunds.html", rows=rows)


@app.route("/admin/refunds/approve/<int:req_id>")
def admin_refunds_approve(req_id):
    if not admin_required():
        return redirect(url_for("admin_login"))
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM refund_requests WHERE id=?",
        (req_id,)
    ).fetchone()

    if not row:
        flash("환불 요청을 찾을 수 없습니다.")
        return redirect(url_for("admin_refunds"))

    if row["status"] != "pending":
        flash("이미 처리된 요청입니다.")
        return redirect(url_for("admin_refunds"))

    user_id = row["user_id"]
    amount = row["amount"]

    user = conn.execute(
        "SELECT balance FROM users WHERE id=?",
        (user_id,)
    ).fetchone()
    balance = user["balance"] if user else 0

    if balance < amount:
        conn.execute(
            "UPDATE refund_requests SET status='failed' WHERE id=?",
            (req_id,)
        )
        conn.execute("""
            INSERT INTO transactions (user_id, type, amount, description, status)
            VALUES (?, 'refund', ?, '환불 실패(잔액 부족)', 'failed')
        """, (user_id, amount))
        conn.commit()
        flash("잔액이 부족하여 환불을 처리할 수 없습니다.")
        return redirect(url_for("admin_refunds"))

    # 잔액 차감
    conn.execute(
        "UPDATE users SET balance = balance - ? WHERE id=?",
        (amount, user_id)
    )
    # 요청 상태 변경
    conn.execute(
        "UPDATE refund_requests SET status='approved' WHERE id=?",
        (req_id,)
    )
    # 거래 내역 기록
    conn.execute("""
        INSERT INTO transactions (user_id, type, amount, description, status)
        VALUES (?, 'refund', ?, '환불 승인', 'completed')
    """, (user_id, amount))
    conn.commit()

    # 사용자에게 메일 (옵션)
    user_email = os.environ.get("USER_TEST_EMAIL")
    if user_email:
        body = (
            f"[{SHOP_NAME}] 환불이 승인되었습니다.\n\n"
            f"환불 금액: {amount}원\n"
        )
        send_email(user_email, f"[{SHOP_NAME}] 환불 승인 안내", body)

    flash("환불이 승인되었습니다.")
    return redirect(url_for("admin_refunds"))


# -----------------------------
# 엔트리 포인트
# -----------------------------
if __name__ == "__main__":
    # 로컬 테스트용
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)

