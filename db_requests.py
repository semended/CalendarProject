def get_user_by_slug(slug):
	user = {'id': 0,
					'slug': 'MaximDestroyer',
					'name': 'Максим',
					'surname': 'Ленчевский',
					'patronymic': 'Игоревич',
					'password': '111',
					'role_id': 0,
					'avatar_url': None,
					'organization': False,
					'confirmed': False,
					'created_at': 0}
	if slug == 'MaximDestroyer':
		return user
	return None

def add_user(user):
	return 0

