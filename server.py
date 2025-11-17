import flask_login
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__, template_folder="templates")


@app.route('/', methods=['GET', 'POST'])
def start_page():
  if request.method == 'GET':
    return render_template('start.html')
  else:
    #Добавить обработку регистрации/авторизации
    return  render_template('start.html')


@app.route('/main', methods=['GET', 'POST'])
def main_page():
  if request.method == 'GET':
    return render_template('main.html')
  else:
    #Добавить обработку создания проекта
    return render_template('main.html')


@app.route('/user/<user_id>')
def user_page(user_id):
  return render_template('profile.html')


@app.route('/user/settings')
def settings_page():
  return render_template('settings.html')

@app.route('/<path:invalid_path>')
def not_found(invalid_path):
    return render_template('notFound.html')

if __name__ == '__main__':
  app.run(port=8080, host='127.0.0.1')
