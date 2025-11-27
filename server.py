from pydoc import render_doc

from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_login import LoginManager, login_user, current_user, logout_user, login_required
import sqlite3 as sq

from db_requests import *

app = Flask(__name__, template_folder='templates')
app.secret_key = '(*#HF(@#*hqED*(QH@#OhlihO(#*'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'start_page'

conn = sq.connect(database='database.db', check_same_thread=False)

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
  user = User(get_user_by_slug('MaximDestroyer')['id'])
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
    if request.form.get('name') is None:
      # Обработка авторизации
      slug = request.form.get('slug')
      password = request.form.get('password')
      user = get_user_by_slug(slug)
      if user is None:
        # Такой пользователь не найден
        return redirect(url_for('start_page'))
      elif user['password'] != password:
        # Введён неправильный пароль
        return redirect(url_for('start_page'))

      # Урааа всё хорошо
      login_user(User(user['id']))
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

@app.route('/main', methods=['GET', 'POST'])
@login_required
def main_page():
  print('Зашёл в main_page. User_id ->', current_user.get_id())
  if request.method == 'GET':
    return render_template('main.html')
  else:
    #Добавить обработку создания проекта
    return render_template('main.html')


@app.route('/user/<user_id>')
def user_page(user_id):
    print('Зашёл в user_page. User_id ->', current_user.get_id())
    # Получаем данные пользователя из базы
    user = get_user_by_id(user_id)
    return render_template('profile.html', user=user)


@app.route('/user/settings')
@login_required
def settings_page():
  print('Зашёл в settings. User_id ->', current_user.get_id())
  return render_template('settings.html')

@app.route('/<path:invalid_path>')
def not_found(invalid_path):
    return render_template('notFound.html')

if __name__ == '__main__':
  app.run(port=8080, host='127.0.0.1')
