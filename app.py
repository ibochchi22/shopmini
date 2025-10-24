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
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)

class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)


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
    # Проверка: если пользователь не вошёл
    if 'user_id' not in session:
        return redirect(url_for('login'))
    banners = Banner.query.all() 
    products = Product.query.all()
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

# Корзина
@app.route('/cart')
@login_required
def cart():
    cart_items = session.get('cart', {})
    products = []
    total = 0
    
    for product_id, quantity in cart_items.items():
        product = Product.query.get(int(product_id))
        if product:
            products.append({'product': product, 'quantity': quantity})
            total += product.price * quantity
    
    return render_template('cart.html', products=products, total=total)

@app.route('/admin/banners')
def admin_banners():
    banners = Banner.query.all()
    return render_template('admin_dashboard', banners=banners)

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
    
    order = Order(user_id=session['user_id'])
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
    users = User.query.all()
    products = Product.query.all()
    orders = Order.query.order_by(Order.created_at.desc()).all()
    banners = Banner.query.all()
    return render_template('admin/dashboard.html', users=users, products=products, orders=orders, banners=banners)

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

# Печать заказов в PDF
# --------------------------
# 1️⃣ HTML чек с диалогом печати
# --------------------------
@app.route('/admin/print_order/<int:order_id>')
@admin_required
def print_order(order_id):
    from flask import render_template_string
    from datetime import datetime

    order = Order.query.get_or_404(order_id)
    total = sum(item.product.price * item.quantity for item in order.items)

    html_template = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Номенклатура заказа №{{ order.id }}</title>
        <style>
            @page {
                size: A5 portrait;
                margin: 8mm;
            }

            body {
                font-family: "DejaVu Sans", sans-serif;
                color: #000;
                margin: 0;
                padding: 0;
                font-size: 11px;
                line-height: 1.3;
            }

            .document {
                width: 100%;
                padding: 5px 10px;
                box-sizing: border-box;
            }

            h2 {
                text-align: center;
                font-size: 14px;
                margin-bottom: 6px;
                border-bottom: 1px solid #000;
                padding-bottom: 3px;
            }

            .info {
                margin-top: 5px;
                margin-bottom: 10px;
                font-size: 11px;
                line-height: 1.4;
            }

            table {
                width: 100%;
                border-collapse: collapse;
                border: 1px solid #000;
                margin-top: 5px;
            }

            th, td {
                border: 1px solid #000;
                padding: 3px 4px;
                text-align: center;
                font-size: 10.5px;
            }

            th {
                background: #f4f4f4;
                font-size: 11px;
            }

            td:nth-child(2) {
                text-align: left;
            }

            tfoot td {
                font-weight: bold;
                text-align: right;
            }

            .footer {
                margin-top: 12px;
                text-align: right;
                font-size: 10.5px;
                border-top: 1px dashed #000;
                padding-top: 6px;
            }

            @media print {
                body {
                    margin: 0;
                }
                .document {
                    width: 100%;
                    padding: 0;
                }
            }
        </style>
    </head>
    <body onload="window.print()">
        <div class="document">
            <h2>НОМЕНКЛАТУРА ЗАКАЗА №{{ order.id }}</h2>

            <div class="info">
                <b>Дата:</b> {{ order.created_at.strftime('%d.%m.%Y %H:%M') }}<br>
                <b>Клиент:</b> {{ order.user.username }}
            </div>

            <table>
                <thead>
                    <tr>
                        <th>№</th>
                        <th>Наименование</th>
                        <th>Кол-во</th>
                        <th>Цена</th>
                        <th>Сумма</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in order.items %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td>{{ item.product.name }}</td>
                        <td>{{ item.quantity }}</td>
                        <td>{{ "{:,.0f}".format(item.product.price) }} UZS</td>
                        <td>{{ "{:,.0f}".format(item.product.price * item.quantity) }} UZS</td>
                    </tr>
                    {% endfor %}
                </tbody>
                <tfoot>
                    <tr>
                        <td colspan="4">ИТОГО:</td>
                        <td>{{ "{:,.0f}".format(total) }} UZS</td>
                    </tr>
                </tfoot>
            </table>

            <div class="footer">
                Подпись продавца: _______________________<br><br>
                Спасибо за покупку!
            </div>
        </div>
    </body>
    </html>
    """

    return render_template_string(html_template, order=order, total=total)


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





if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True, port=8080)