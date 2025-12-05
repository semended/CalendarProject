from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_login import LoginManager, login_user, current_user, logout_user, login_required
import os
import base64
from werkzeug.utils import secure_filename

from db_requests import *

app = Flask(__name__, template_folder='templates')
app.secret_key = '(*#HF(@#*hqED*(QH@#OhlihO(#*'

# Настройки для загрузки аватарок
UPLOAD_FOLDER = 'static/user_avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def allowed_file(filename):
	return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Создаем папку для аватарок если ее нет
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
		return render_template('start.html')
	else:
		# Обработка авторизации
		slug = request.form.get('slug')
		password = request.form.get('password')
		user = get_user_by_slug(slug)

		if user is None:
			# Такой пользователь не найден
			print('Пользователь не найден -> ' + slug)
			return render_template('start.html', error='Неправильный логин')
		elif user.password != password:
			# Введён неправильный пароль
			print('Неправильный пароль -> ', user.id)
			return render_template('start.html', error='Неправильный пароль')

		# Урааа всё хорошо
		login_user(User(user.id))
		return redirect(url_for('main_page'))


# страница регистрации - нужно добавить поля
@app.route('/registration', methods=['GET', 'POST'])
def register_page():
	if request.method == 'GET':
		return render_template('register.html')
	else:
		user_dict = request.form.to_dict()

		if get_user_by_slug(user_dict['slug']) is not None:
			return render_template('register.html', error='Пользователь с таким ID уже существует!')

		# Устанавливаем значения по умолчанию для новой модели БД
		user_dict['role_id'] = 3
		user_dict['avatar_url'] = "-1"
		user_dict['confirmed'] = False
		user_dict['organization'] = False
		user_dict['url'] = user_dict.get('url', 'https://example.com')

		add_user(user_dict)
		user = get_user_by_slug(user_dict['slug'])
		login_user(User(user.id))
		return redirect(url_for('main_page'))


@app.route('/main', methods=['GET', 'POST'])
@login_required
def main_page():
	print('Зашёл в main_page. User_id ->', current_user.get_id())
	if request.method == 'GET':
		user = get_user_by_id(int(current_user.get_id()))  # Преобразовать в int
		if user is None:
			# Пользователь не найден, разлогиниваем
			logout_user()
			return redirect(url_for('start_page'))
		print(user.avatar_url)
		return render_template('main.html', active_page='all_projects', user=user)
	else:
		# Добавить обработку создания проекта
		return render_template('main.html')


@app.route('/user/<user_id>')
def user_page(user_id):
	print('Зашёл в user_page. User_id ->', current_user.get_id())
	# Получаем данные пользователя из базы
	user = get_user_by_id(int(user_id))  # Преобразовать в int
	if user is None:
		return render_template('notFound.html')
	return render_template('profile.html', user=user)


@app.route('/user/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
	print('Зашёл в settings. User_id ->', current_user.get_id())

	# Получаем пользователя
	user_id = int(current_user.get_id())
	user = get_user_by_id(user_id)

	if user is None:
		logout_user()
		return redirect(url_for('start_page'))

	if request.method == 'POST':
		# Обработка сохранения настроек
		user_dict = request.form.to_dict()

		# Обработка удаления аватара
		if user_dict.get('remove_avatar') == 'true':
			# Удаляем файл аватара если он существует
			if user.avatar_url and user.avatar_url != "":
				# Создаем полный путь к файлу
				avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], user.avatar_url + 'jpg')
				print(f"Пытаемся удалить аватар: {avatar_path}")
				if os.path.exists(avatar_path):
					try:
						os.remove(avatar_path)
						print(f"Файл удален: {avatar_path}")
					except Exception as e:
						print(f"Ошибка удаления файла: {e}")
				else:
					print(f"Файл не существует: {avatar_path}")

			# Устанавливаем пустую строку в БД
			update_user_avatar(user_id, "")
			return redirect(url_for('settings_page'))

		# Обработка кропнутого изображения (base64)
		cropped_image = user_dict.get('cropped_image')
		if cropped_image and cropped_image.startswith('data:image'):
			try:
				print("Начинаем обработку cropped_image")
				# Декодируем base64
				header, encoded = cropped_image.split(',', 1)
				image_data = base64.b64decode(encoded)

				# Генерируем имя файла: user_<id>_avatar.jpg
				filename = f"user_{user_id}_avatar.jpg"
				filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
				print(f"Сохраняем файл как: {filepath}")

				# Сохраняем файл
				with open(filepath, 'wb') as f:
					f.write(image_data)
				print(f"Файл успешно сохранен: {filepath}")

				# Удаляем старый файл если он есть
				if user.avatar_url and user.avatar_url != "":
					old_avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], user.avatar_url + 'jpg')
					print(f"Проверяем старый файл: {old_avatar_path}")
					if os.path.exists(old_avatar_path) and old_avatar_path != filepath:
						try:
							os.remove(old_avatar_path)
							print(f"Старый файл удален: {old_avatar_path}")
						except Exception as e:
							print(f"Ошибка удаления старого файла: {e}")

				# Обновляем поле avatar_url в БД (только имя файла без расширения)
				user_dict['avatar_url'] = f"user_{user_id}_avatar."
				print(f"Обновляем avatar_url в БД: {user_dict['avatar_url']}")

			except Exception as e:
				print(f"Ошибка сохранения аватара: {e}")
				import traceback
				traceback.print_exc()

		# Обработка загрузки файла через input type="file"
		elif 'avatar' in request.files:
			file = request.files['avatar']
			if file and allowed_file(file.filename):
				try:
					print(f"Начинаем обработку файла: {file.filename}")
					# Генерируем имя файла: user_<id>_avatar.jpg
					filename = f"user_{user_id}_avatar.jpg"
					filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
					print(f"Сохраняем файл как: {filepath}")

					# Сохраняем файл
					file.save(filepath)
					print(f"Файл успешно сохранен: {filepath}")

					# Удаляем старый файл если он есть
					if user.avatar_url and user.avatar_url != "":
						old_avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], user.avatar_url + 'jpg')
						print(f"Проверяем старый файл: {old_avatar_path}")
						if os.path.exists(old_avatar_path) and old_avatar_path != filepath:
							try:
								os.remove(old_avatar_path)
								print(f"Старый файл удален: {old_avatar_path}")
							except Exception as e:
								print(f"Ошибка удаления старого файла: {e}")

					# Обновляем поле avatar_url в БД (только имя файла без расширения)
					user_dict['avatar_url'] = f"user_{user_id}_avatar."
					print(f"Обновляем avatar_url в БД: {user_dict['avatar_url']}")

				except Exception as e:
					print(f"Ошибка сохранения файла аватара: {e}")
					import traceback
					traceback.print_exc()

		# Обновляем данные пользователя
		print(f"Обновляем пользователя с данными: {user_dict}")
		update_user(user_id, user_dict)

		return redirect(url_for('settings_page'))

	# GET запрос - показываем страницу настроек
	return render_template('settings.html', user=user)


@app.route('/<path:invalid_path>')
def not_found(invalid_path):
	return render_template('notFound.html')


if __name__ == '__main__':
	app.run(port=8080, host='127.0.0.1')
