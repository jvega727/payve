from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from functools import wraps
import jwt
import datetime
from datetime import datetime as dt

# Configuración centralizada
class Config:
    SECRET_KEY = "mi_secreto_muy_complejo"
    SQLALCHEMY_DATABASE_URI = "sqlite:///pagos.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# Inicialización de la aplicación
app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

# Modelos de base de datos
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=dt.utcnow)
    user = db.relationship('User', backref=db.backref('payments', lazy=True))

# Crear las tablas si no existen
with app.app_context():
    db.create_all()

# Ruta principal
@app.route('/')
def home():
    return "¡Bienvenido a la plataforma de pagos!"

# Funciones reutilizables
def get_user_by_name(name):
    user = User.query.filter_by(name=name).first()
    if not user:
        return None, jsonify({"error": f"El usuario {name} no existe"}), 404
    return user, None

# Decorador para proteger rutas con token
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"error": "Token faltante"}), 401
        try:
            data = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "El token ha expirado"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token inválido"}), 401
        user, error = get_user_by_name(data['user'])
        if error:
            return error
        return f(user, *args, **kwargs)
    return decorated

# Rutas de usuario
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if not data or 'name' not in data:
        return jsonify({"error": "El JSON enviado no es válido o falta el campo 'name'"}), 400
    if len(data['name']) > 80 or data['name'].strip() == "":
        return jsonify({"error": "El campo 'name' debe tener entre 1 y 80 caracteres"}), 400
    if User.query.filter_by(name=data['name']).first():
        return jsonify({"error": f"El usuario {data['name']} ya existe"}), 400
    user = User(name=data['name'])
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": f"Usuario {data['name']} registrado con éxito"}), 201

@app.route('/delete_user', methods=['POST'])
def delete_user():
    data = request.json
    if not data or 'name' not in data:
        return jsonify({"error": "El JSON enviado no es válido o falta el campo 'name'"}), 400
    user, error = get_user_by_name(data['name'])
    if error:
        return error
    Payment.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": f"Usuario {data['name']} y sus pagos eliminados"}), 200

@app.route('/update_user', methods=['PUT'])
def update_user():
    data = request.json
    if not data or 'name' not in data or 'new_name' not in data:
        return jsonify({"error": "El JSON enviado no es válido o faltan campos"}), 400
    user, error = get_user_by_name(data['name'])
    if error:
        return error
    user.name = data['new_name']
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": f"El nombre {data['new_name']} ya está en uso"}), 400
    return jsonify({"message": f"Usuario actualizado a {data['new_name']}"}), 200

@app.route('/users', methods=['GET'])
def list_users():
    users = User.query.all()
    users_list = [{"id": user.id, "name": user.name} for user in users]
    return jsonify({"users": users_list}), 200

# Rutas de pagos
@app.route('/process_payment', methods=['POST'])
def process_payment():
    data = request.json
    if not data or 'amount' not in data or 'name' not in data:
        return jsonify({"error": "El JSON enviado no es válido o faltan campos"}), 400
    if data['amount'] <= 0:
        return jsonify({"error": "El monto debe ser mayor a 0"}), 400
    user, error = get_user_by_name(data['name'])
    if error:
        return error
    payment = Payment(amount=data['amount'], user_id=user.id)
    db.session.add(payment)
    db.session.commit()
    return jsonify({"status": "success", "message": f"Pago de ${data['amount']} registrado"}), 200

@app.route('/payments', methods=['POST'])
def list_payments():
    data = request.json
    if not data or 'name' not in data:
        return jsonify({"error": "El nombre del usuario es obligatorio"}), 400
    user, error = get_user_by_name(data['name'])
    if error:
        return error
    payments = Payment.query.filter_by(user_id=user.id).all()
    payments_list = [{"id": p.id, "amount": p.amount, "date": p.created_at.isoformat()} for p in payments]
    return jsonify({"payments": payments_list}), 200

@app.route('/payments_by_date', methods=['POST'])
def payments_by_date():
    data = request.json
    start_date = dt.fromisoformat(data['start_date'])
    end_date = dt.fromisoformat(data['end_date'])
    user, error = get_user_by_name(data['name'])
    if error:
        return error
    payments = Payment.query.filter(Payment.user_id == user.id, Payment.created_at.between(start_date, end_date)).all()
    payments_list = [{"id": p.id, "amount": p.amount, "date": p.created_at.isoformat()} for p in payments]
    return jsonify({"payments": payments_list}), 200

# Ruta protegida
@app.route('/protected', methods=['GET'])
@token_required
def protected(user):
    return jsonify({"message": f"Acceso concedido a {user.name}"}), 200

# Ruta para login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    user, error = get_user_by_name(data['name'])
    if error:
        return error
    token = jwt.encode({"user": user.name, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}, Config.SECRET_KEY, algorithm="HS256")
    return jsonify({"token": token}), 200

# Ejecutar el servidor
if __name__ == '__main__':
    app.run(debug=True, port=8000)

