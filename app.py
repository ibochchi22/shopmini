from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file,jsonify,  render_template_string
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet
import os
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from datetime import datetime, timedelta


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

# Создаем папку для загрузок
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# Модели базы данных
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    orders = db.relationship('Order', backref='user', lazy=True)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)  # ✅ Новое поле


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(200))
    is_archived = db.Column(db.Boolean, default=False)  # 👈 добавлено
    order_items = db.relationship('OrderItem', backref='product', lazy=True)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    kurs = db.Column(db.Float, nullable=False, default=12200.0)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)

class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)




# ==============================
# 🔧 Вспомогательные функции
# ==============================

def get_kurs():
    kurs_setting = Setting.query.filter_by(key='kurs').first()
    try:
        return float(kurs_setting.value)
    except:
        return 12200.0  # курс по умолчанию


def round_price(value):
    """Округляем до ближайших 100 сум для красивых цен."""
    return round(value / 100) * 100


# Далее уже идут твои маршруты Flask
# Например:
# @app.route('/')
# def index():
#     ...



def round_price(value):
    """Округляем до ближайших 100 сум для красивых цен."""
    return round(value / 100) * 100



# Инициализация базы данных
with app.app_context():
    db.create_all()
    # Создаем админа по умолчанию
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', password=generate_password_hash('admin123'), role='admin')
        db.session.add(admin)
        db.session.commit()

# Декораторы для проверки прав
def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def admin_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            flash('Доступ запрещен', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# Главная страница
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    kurs = get_kurs()
    banners = Banner.query.all()
    products = Product.query.all()

    # Пересчитываем цену по курсу
    for p in products:
        p.price = round_price(p.price * kurs)

    return render_template('index.html', products=products, banners=banners)


# Регистрация
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Пользователь уже существует', 'danger')
            return redirect(url_for('register'))
        
        user = User(username=username, password=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна!', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Вход
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            flash('Вход выполнен успешно!', 'success')
            
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
        
        flash('Неверный логин или пароль', 'danger')
    
    return render_template('login.html')

# Выход
@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

@app.route('/cart')
@login_required
def cart():
    kurs = get_kurs()
    cart_items = session.get('cart', {})
    products = []
    total = 0

    for product_id, quantity in cart_items.items():
        product = Product.query.get(int(product_id))
        if product:
            price_uzs = round_price(product.price * kurs)
            products.append({'product': product, 'quantity': quantity, 'price_uzs': price_uzs})
            total += price_uzs * quantity

    return render_template('cart.html', products=products, total=total)


@app.route('/admin/banners')
def admin_banners():
    banners = Banner.query.all()
    return render_template('admin/banners.html', banners=banners)

# ===== Добавление баннера =====
@app.route('/admin/add_banner', methods=['POST'])
def add_banner():
    file = request.files.get('banner')
    if file and file.filename:
        os.makedirs('static/banners', exist_ok=True)
        filename = secure_filename(file.filename)
        path = os.path.join('static/banners', filename)
        file.save(path)

        new_banner = Banner(filename=filename)
        db.session.add(new_banner)
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

# ===== Удаление баннера =====
@app.route('/admin/delete_banner/<int:banner_id>', methods=['POST'])
def delete_banner(banner_id):
    banner = Banner.query.get_or_404(banner_id)
    try:
        os.remove(os.path.join('static/banners', banner.filename))
    except:
        pass
    db.session.delete(banner)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))




# Добавить в корзину
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    quantity = int(request.args.get('quantity', 1))  # <- берём из запроса
    if 'cart' not in session:
        session['cart'] = {}
    session['cart'][str(product_id)] = session['cart'].get(str(product_id), 0) + quantity
    session.modified = True
    return jsonify(success=True, cart_count=sum(session['cart'].values()))

# Удалить из корзины
@app.route('/remove_from_cart/<int:product_id>')
@login_required
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    product_id_str = str(product_id)
    
    if product_id_str in cart:
        del cart[product_id_str]
        session['cart'] = cart
        flash('Товар удален из корзины', 'info')
    
    return redirect(url_for('cart'))

# Оформить заказ
@app.route('/checkout')
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash('Корзина пуста', 'warning')
        return redirect(url_for('cart'))
    
    order = Order(user_id=session['user_id'], kurs=get_kurs())
    db.session.add(order)
    db.session.flush()
    
    for product_id, quantity in cart.items():
        order_item = OrderItem(order_id=order.id, product_id=int(product_id), quantity=quantity)
        db.session.add(order_item)
    
    db.session.commit()
    session['cart'] = {}
    flash('Заказ успешно оформлен!', 'success')
    return redirect(url_for('profile'))

# Профиль пользователя
@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    return render_template('profile.html', user=user, orders=orders)

# Админ-панель
@app.route('/admin')
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_products = Product.query.count()
    total_orders = Order.query.count()

    # Пример — онлайн пользователи за последние 5 минут
    online_users = User.query.filter(User.last_active >= datetime.utcnow() - timedelta(minutes=5)).count()

    return render_template(
        'admin/dashboard.html',
        total_users=total_users,
        total_products=total_products,
        total_orders=total_orders,
        online_users=online_users
    )


# Добавить пользователя
@app.route('/admin/add_user', methods=['POST'])
@admin_required
def add_user():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'user')
    
    if User.query.filter_by(username=username).first():
        flash('Пользователь уже существует', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    user = User(username=username, password=generate_password_hash(password), role=role)
    db.session.add(user)
    db.session.commit()
    flash('Пользователь добавлен', 'success')
    return redirect(url_for('admin_dashboard'))

# Изменить пользователя
@app.route('/admin/edit_user/<int:user_id>', methods=['POST'])
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    username = request.form.get('username')
    password = request.form.get('password')
    
    if username and username != user.username:
        if User.query.filter_by(username=username).first():
            flash('Логин уже занят', 'danger')
            return redirect(url_for('admin_dashboard'))
        user.username = username
    
    if password:
        user.password = generate_password_hash(password)
    
    db.session.commit()
    flash('Данные пользователя обновлены', 'success')
    return redirect(url_for('admin_dashboard'))

# Добавить товар
@app.route('/admin/add_product', methods=['POST'])
@admin_required
def add_product():
    name = request.form.get('name')
    price = float(request.form.get('price'))
    image = request.files.get('image')
    
    image_path = None
    if image and image.filename:
        filename = secure_filename(image.filename)
        image_path = os.path.join('uploads', filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    product = Product(name=name, price=price, image=image_path)
    db.session.add(product)
    db.session.commit()
    flash('Товар добавлен', 'success')
    return redirect(url_for('admin_dashboard'))

# Удалить товар
@app.route('/admin/delete_product/<int:product_id>')
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash('Товар удален', 'success')
    return redirect(url_for('admin_dashboard'))

# Обновить статус заказа
@app.route('/admin/update_order/<int:order_id>/<status>')
@admin_required
def update_order(order_id, status):
    order = Order.query.get_or_404(order_id)
    if status in ['confirmed', 'cancelled']:
        order.status = status
        db.session.commit()
        flash('Статус заказа обновлен', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/print_order/<int:order_id>')
@admin_required
def print_order(order_id):
    order = Order.query.get_or_404(order_id)

    # курс и округление
    kurs = order.kurs or get_kurs()

    # рассчитываем общую сумму с округлением
    total = 0
    items_data = []
    for item in order.items:
        price_uzs = round_price(item.product.price * kurs)
        summa = round_price(price_uzs * item.quantity)
        total += summa
        items_data.append({
            'name': item.product.name,
            'quantity': item.quantity,
            'price': price_uzs,
            'summa': summa
        })

    # izoh
    izoh_setting = Setting.query.filter_by(key='izoh').first()
    izoh = izoh_setting.value if izoh_setting else "Yukingizni tekshirib oling, 3 kundan so‘ng javob berilmaydi!"

    html_template = """
    <!DOCTYPE html>
    <html lang="uz">
    <head>
        <meta charset="UTF-8">
        <title>Chek №{{ order.id }}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
        <style>
            @page { size: A5 portrait; margin: 8mm; }

            body {
                font-family: "DejaVu Sans", sans-serif;
                font-size: 11px;
                color: #111;
                background: #f9fafb;
                margin: 0;
                padding: 0;
            }

            .container {
                width: 100%;
                background: #fff;
                box-shadow: 0 0 6px rgba(0,0,0,0.1);
                border-radius: 6px;
                padding: 12px 16px;
                box-sizing: border-box;
            }

            .header {
                text-align: center;
                font-weight: 800;
                font-size: 14px;
                color: #1e293b;
                margin-bottom: 2px;
                letter-spacing: 0.3px;
            }

            .sub-header {
                text-align: center;
                font-size: 10.5px;
                color: #6b7280;
                margin-bottom: 8px;
            }

            .divider {
                border-bottom: 1px dashed #d1d5db;
                margin: 8px 0;
            }

            .info {
                font-size: 11px;
                line-height: 1.5;
                margin-bottom: 6px;
                color: #111827;
            }

            .info i {
                color: #2563eb;
                width: 14px;
                text-align: center;
                margin-right: 4px;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 5px;
                font-size: 10.5px;
            }

            th, td {
                border: 1px solid #e5e7eb;
                padding: 4px 3px;
                text-align: center;
            }

            th {
                background: #f3f4f6;
                font-weight: 700;
                color: #1e293b;
            }

            td:nth-child(2) {
                text-align: left;
            }

            .total {
                margin-top: 10px;
                text-align: right;
                font-weight: bold;
                border-top: 1px solid #9ca3af;
                padding-top: 6px;
                font-size: 11.5px;
            }

            .total i {
                color: #16a34a;
                margin-right: 4px;
            }

            .footer {
                margin-top: 10px;
                font-size: 10.5px;
                border-top: 1px dashed #ccc;
                padding-top: 6px;
                line-height: 1.4;
                color: #111827;
            }

            .footer i {
                color: #2563eb;
                margin-right: 4px;
            }

            .note {
                margin-top: 6px;
                text-align: center;
                font-size: 9.8px;
                color: #555;
            }

            @media print {
                body { background: #fff; }
                .container { box-shadow: none; border-radius: 0; }
            }
        </style>
    </head>
    <body onload="window.print()">
        <div class="container">
            <div class="header"><i class="fa-solid fa-store text-primary"></i> Строй Март 0111</div>
            <div class="sub-header">
                <i class="fa-solid fa-phone"></i> +998 88 202 0111 &nbsp;&nbsp; 
                <i class="fa-solid fa-coins"></i> Kurs: {{ "{:,.0f}".format(kurs) }}
            </div>

            <div class="divider"></div>

            <div class="info">
                <p><i class="fa-solid fa-user"></i> <b>Mijoz:</b> {{ order.user.username }}</p>
                <p><i class="fa-solid fa-receipt"></i> <b>Chek №:</b> {{ order.id }}</p>
                <p><i class="fa-solid fa-calendar-days"></i> <b>Sana:</b> {{ order.created_at.strftime('%d.%m.%Y %H:%M:%S') }}</p>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>№</th>
                        <th>Mahsulot nomi</th>
                        <th>Miqdor</th>
                        <th>Birlik</th>
                        <th>Narx</th>
                        <th>Summa</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in items %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td>{{ item.name }}</td>
                        <td>{{ item.quantity }}</td>
                        <td>Дона</td>
                        <td>{{ "{:,.0f}".format(item.price) }}</td>
                        <td>{{ "{:,.0f}".format(item.summa) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>

            <div class="total">
                <i class="fa-solid fa-wallet"></i> Jami: {{ "{:,.0f}".format(total) }} UZS<br>
                <i class="fa-solid fa-money-bill-wave"></i> To‘lov: {{ "{:,.0f}".format(total) }} UZS
            </div>

            <div class="footer">
                <p><i class="fa-solid fa-pen-to-square"></i> <b>Izoh:</b> {{ izoh }}</p>
                <p><i class="fa-solid fa-mobile-screen"></i> Buyurtma mobil ilovadan yuborilgan</p>
            </div>

            <div class="note">
                <i class="fa-solid fa-heart text-danger"></i> Rahmat xaridingiz uchun!
            </div>
        </div>
    </body>
    </html>
    """

    return render_template_string(
        html_template,
        order=order,
        total=total,
        izoh=izoh,
        items=items_data,
        kurs=kurs
    )





# --------------------------
# 2️⃣ Красивый PDF чек
# --------------------------
@app.route('/admin/view_order_pdf/<int:order_id>')
@admin_required
def view_order_pdf(order_id):
    order = Order.query.get_or_404(order_id)

    # 📘 Поддержка кириллицы
    font_path = os.path.join("static", "fonts", "DejaVuSans.ttf")
    pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer, pagesize=A5,
        rightMargin=10*mm, leftMargin=10*mm,
        topMargin=10*mm, bottomMargin=10*mm
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    title = styles["Title"]

    elements = []

    # Заголовок
    elements.append(Paragraph("<b>ЧЕК ЗАКАЗА</b>", title))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(f"Дата: {order.created_at.strftime('%d.%m.%Y %H:%M')}", normal))
    elements.append(Paragraph(f"Заказ № <b>{order.id}</b>", normal))
    elements.append(Paragraph(f"Покупатель: <b>{order.user.username}</b>", normal))
    elements.append(Spacer(1, 10))

    # Таблица товаров
    data = [["Наименование", "Кол-во", "Цена", "Сумма"]]
    total = 0
    for item in order.items:
        subtotal = item.product.price * item.quantity
        data.append([item.product.name, str(item.quantity),
                     f"{item.product.price:,.0f} UZS",
                     f"{subtotal:,.0f} UZS"])
        total += subtotal

    table = Table(data, colWidths=[60*mm, 15*mm, 25*mm, 30*mm])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "DejaVuSans", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 10))

    # Итог
    elements.append(Paragraph(f"<b>ИТОГО:</b> {total:,.0f} UZS", styles["Heading3"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<b>Спасибо за покупку!</b>", normal))
    elements.append(Spacer(1, 5))
    elements.append(Paragraph("Ждём вас снова!", normal))

    pdf.build(elements)

    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=False,
                     download_name=f"order_{order.id}.pdf")



@app.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.order_by(Product.id.desc()).all()
    return render_template('admin/products.html', products=products)



# ====== Редактирование товара ======
@app.route('/admin/edit_product/<int:product_id>', methods=['POST'])
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    name = request.form.get('name')
    price = request.form.get('price')
    image = request.files.get('image')

    if name:
        product.name = name
    if price:
        product.price = float(price)

    if image and image.filename:
        filename = secure_filename(image.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(image_path)
        product.image = os.path.join('uploads', filename)

    db.session.commit()
    flash('Товар обновлен успешно', 'success')
    return redirect(url_for('admin_products'))


# ====== Архивация товара ======
@app.route('/admin/archive_product/<int:product_id>')
@admin_required
def archive_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_archived = True
    db.session.commit()
    flash('Товар перенесен в архив', 'info')
    return redirect(url_for('admin_products'))


# ====== Восстановление товара ======
@app.route('/admin/unarchive_product/<int:product_id>')
@admin_required
def unarchive_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_archived = False
    db.session.commit()
    flash('Товар восстановлен', 'success')
    return redirect(url_for('admin_products'))



# ====== Настройки админ-панели (Izoh + Kurs) ======
@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    izoh_setting = Setting.query.filter_by(key='izoh').first()
    kurs_setting = Setting.query.filter_by(key='kurs').first()

    if request.method == 'POST':
        new_izoh = request.form.get('izoh', '').strip()
        new_kurs = request.form.get('kurs', '').strip()

        # Izoh
        if izoh_setting:
            izoh_setting.value = new_izoh
        else:
            db.session.add(Setting(key='izoh', value=new_izoh))

        # Kurs
        try:
            kurs_value = float(new_kurs.replace(',', '.'))
        except:
            kurs_value = 12200.0  # значение по умолчанию
        if kurs_setting:
            kurs_setting.value = str(kurs_value)
        else:
            db.session.add(Setting(key='kurs', value=str(kurs_value)))

        db.session.commit()
        flash('Настройки успешно обновлены!', 'success')
        return redirect(url_for('admin_settings'))

    izoh = izoh_setting.value if izoh_setting else "Yukingizni tekshirib oling, 3 kundan so‘ng javob berilmaydi!"
    kurs = kurs_setting.value if kurs_setting else "12200"

    return render_template('admin/settings.html', izoh=izoh, kurs=kurs)



@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/orders')
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    kurs = get_kurs()  # 🔹 получаем курс из базы
    return render_template('admin/orders.html', orders=orders, kurs=kurs)


@app.before_request
def update_last_active():
    # Не выполняем для статических/файлов, health-check или когда нет user_id
    if 'user_id' not in session:
        return

    # Игнорируем, если это запрос к статике
    if request.endpoint and request.endpoint.startswith('static'):
        return

    try:
        user = User.query.get(session['user_id'])
        if not user:
            return
        now = datetime.utcnow()
        # Обновляем only если прошло >30 секунд (чтобы не писать постоянно)
        if not user.last_active or (now - user.last_active).total_seconds() > 30:
            user.last_active = now
            db.session.commit()
    except Exception:
        # на случай проблем с БД — не ломаем страницу
        db.session.rollback()





if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True, port=8080)


