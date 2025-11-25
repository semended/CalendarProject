def get_user_by_slug(slug):
    user = {
        'id': 0,
        'slug': 'MaximDestroyer',
        'name': 'Максим',
        'surname': 'Ленчевский', 
        'patronymic': 'Игоревич',
        'password': '111',
        'role_id': 0,
        'avatar_url': None,
        'organization': False,
        'confirmed': False,
        'created_at': 0,
        'position': 'Full-stack разработчик',
        'company': 'IT & Technology',
        'workplace': 'Acme Corp',
        'bio': 'Full-stack разработчик с опытом работы в веб-разработке. Увлекаюсь современными технологиями и созданием удобных интерфейсов.',
        'last_login': '12:34 PM (Москва, MSK)'
    }
    if slug == 'MaximDestroyer':
        return user
    return None

def get_user_by_id(user_id):
    return get_user_by_slug('MaximDestroyer')

def add_user(user):
    return 0