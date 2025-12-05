import os
import base64
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_login import LoginManager, login_user, current_user, logout_user, login_required

from db_requests import *

app = Flask(__name__, template_folder='templates')
app.secret_key = '(*#HF(@#*hqED*(QH@#OhlihO(#*'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'start_page'


class User:
	def __init__(self, user_id, active=True):
		self.user_id = user_id
		self.active = active

	def is_authenticated(self):
		return True

	def is_active(self):
		return self.active

	def is_anonymous(self):
		return False

	def get_id(self):
		# Должен возвращать строку, если верить дипсику
		return str(self.user_id)


@login_manager.user_loader
def load_user(user_id):
	user_id_int = int(user_id)
	user = User(user_id_int)
	if user and user.is_active():
		return user
	return None


@app.route('/logout')
def exit_page():
	# Заканчиваем текущую сессию
	logout_user()
	return redirect(url_for('start_page'))


@app.route('/', methods=['GET', 'POST'])
def start_page():
	print('Зашёл в start_page. User_id ->', current_user.get_id())

	if current_user.get_id() is not None:
		return redirect(url_for('main_page'))

	if request.method == 'GET':
		# Получаем текст ошибки из query-параметра, если он есть
		error = request.args.get('error')
		return render_template('start.html', error=error)
	else:
		if request.form.get('name') is None:
			# Обработка авторизации
			slug = request.form.get('slug')
			password = request.form.get('password')
			user = get_user_by_slug(slug)
			if user is None:
				# Такой пользователь не найден
				print('Пользователь не найден -> ' + slug)
				return redirect(url_for('start_page', error='Пользователь не найден. Проверьте ID или зарегистрируйтесь.'))
			elif user.password != password:
				# Введён неправильный пароль
				print('Неправильный пароль -> ', user.id)
				return redirect(url_for('start_page', error='Неверный пароль. Попробуйте ещё раз.'))

			# Урааа всё хорошо
			login_user(User(user.id))
			return redirect(url_for('main_page'))
		else:
			# Обработка регистрации
			slug = request.form.get('slug')
			if get_user_by_slug(slug) is not None:
				# Пользователь с таким slug уже есть
				return redirect(url_for('main_page'))

			# ДОРАБОТАТЬ
			user_id = add_user(None)
			login_user(User(user_id))

			return redirect(url_for('user_page'))


# страница регистрации - нужно добавить поля
@app.route('/registration', methods=['GET', 'POST'])
def register_page():
	if request.method == 'GET':
		return render_template('register.html')
	else:
		user_dict = request.form.to_dict()
		user_dict['email'] = 'replace@me.please'
		user_dict['role_id'] = 1
		user_dict['avatar_url'] = '-1.jpg'
		user_dict['confirmed'] = False
		if get_user_by_slug(user_dict['slug']) != None:
			return render_template('register.html', error='Пользователь с таким ID уже существует!')
		add_user(user_dict)
		user = get_user_by_slug(user_dict['slug'])
		login_user(User(user.id))
		return redirect(url_for('main_page'))


@app.route('/main', methods=['GET', 'POST'])
@login_required
def main_page():
	print('Зашёл в main_page. User_id ->', current_user.get_id())
	if request.method == 'GET':
		user = get_user_by_id(current_user.get_id())
		print(user.avatar_url)
		return render_template('main.html', active_page='all_projects', user=user)
	else:
		# Добавить обработку создания проекта
		return render_template('main.html')


@app.route('/user/<user_id>')
def user_page(user_id):
	print('Зашёл в user_page. User_id ->', current_user.get_id())
	# Получаем данные пользователя из базы
	user = get_user_by_id(user_id)
	return render_template('profile.html', user=user)


@app.route('/user/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
	print('Зашёл в settings. User_id ->', current_user.get_id())
	if request.method == 'POST':
		user_dict = request.form.to_dict()
		# Обработка удаления аватара
		if user_dict.get('remove_avatar') == 'true':
			user_dict['avatar_url'] = ""
			# Удалить файл, если существует
			user = get_user_by_id(current_user.get_id())
			if user and user.avatar_url:
				filepath = user.avatar_url.lstrip('/')
				if os.path.exists(filepath):
					os.remove(filepath)
		# Обработка кропнутого изображения
		elif user_dict.get('cropped_image'):
			cropped_data = user_dict['cropped_image']
			if cropped_data.startswith('data:image'):
				# Декодировать base64
				header, encoded = cropped_data.split(',', 1)
				image_data = base64.b64decode(encoded)
				# Сохранить как файл
				user_id = current_user.get_id()
				filename = f"user_{user_id}_avatar.jpg"
				filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
				os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
				with open(filepath, 'wb') as f:
					f.write(image_data)
				user_dict['avatar_url'] = f"/{filepath}"
		# Обработка файла аватара
		elif 'avatar' in request.files:
			file = request.files['avatar']
			if file and allowed_file(file.filename):
				filename = secure_filename(file.filename)
				# Создать уникальное имя файла
				user_id = current_user.get_id()
				ext = filename.rsplit('.', 1)[1].lower()
				filename = f"user_{user_id}_avatar.{ext}"
				filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
				os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
				file.save(filepath)
				user_dict['avatar_url'] = f"/{filepath}"
		update_user(current_user.get_id(), user_dict)
		flash('Настройки сохранены', 'success')
		return redirect(url_for('settings_page'))
	user = get_user_by_id(current_user.get_id())
	return render_template('settings.html', user=user)


@app.route('/<path:invalid_path>')
def not_found(invalid_path):
	return render_template('notFound.html')


if __name__ == '__main__':
	app.run(port=8080, host='127.0.0.1')
