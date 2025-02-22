#-*- coding: utf-8 -*-

from os import urandom
from re import compile
from time import time as epoch_time
from typing import Any, Tuple

from flask import Blueprint, g, request

from backend.custom_exceptions import (AccessUnauthorized, InvalidKeyValue,
                                       InvalidTime, InvalidURL, KeyNotFound,
                                       NotificationServiceInUse,
                                       NotificationServiceNotFound,
                                       ReminderNotFound, UsernameInvalid,
                                       UsernameTaken, UserNotFound)
from backend.notification_service import (NotificationService,
                                          NotificationServices)
from backend.reminders import Reminders, reminder_handler, test_reminder
from backend.static_reminders import StaticReminders
from backend.templates import Template, Templates
from backend.users import User, register_user

api = Blueprint('api', __name__)
api_key_map = {}
color_regex = compile(r'#[0-9a-f]{6}')

"""
AUTHENTICATION:
	After making a POST /auth/login request, you'll receive an api_key in the output.
	From then on, make all requests with the url parameter api_key, where the value is the string you received.
	One hour after logging in, the api key expires and you are required to login again to get a new api_key.

	If no api key is supplied or it is invalid, 401 'ApiKeyInvalid' is returned.
	If the api key supplied has expired, 401 'ApiKeyExpired' is returned.
"""

def return_api(result: Any, error: str=None, code: int=200) -> Tuple[dict, int]:
	return {'error': error, 'result': result}, code

def auth(method):
	"""Used as decorator and, if applied to route, restricts the route to authorized users and supplies user specific info
	"""
	def wrapper(*args,**kwargs):
		hashed_api_key = hash(request.values.get('api_key',''))
		if not hashed_api_key in api_key_map:
			return return_api({}, 'ApiKeyInvalid', 401)
		
		exp = api_key_map[hashed_api_key]['exp']
		if exp <= epoch_time():
			return return_api({}, 'ApiKeyExpired', 401)
		
		# Api key valid
		g.hashed_api_key = hashed_api_key
		g.exp = exp
		g.user_data = api_key_map[hashed_api_key]['user_data']
		return method(*args, **kwargs)

	wrapper.__name__ = method.__name__
	return wrapper

def error_handler(method):
	"""Catches the errors that can occur in the endpoint and returns the correct api error
	"""
	def wrapper(*args, **kwargs):
		try:
			return method(*args, **kwargs)
		except (UsernameTaken, UsernameInvalid, UserNotFound,
				AccessUnauthorized,
				ReminderNotFound, NotificationServiceNotFound, NotificationServiceInUse,
				InvalidTime, InvalidURL,
				KeyNotFound, InvalidKeyValue) as e:
			return return_api(**e.api_response)

	wrapper.__name__ = method.__name__
	return wrapper

def extract_key(values: dict, key: str, check_existence: bool=True) -> Any:
	value: str = values.get(key)
	if check_existence and value is None:
		raise KeyNotFound(key)
		
	if value is not None:
		# Check value and optionally convert
		if key == 'time':
			try:
				value = int(value)
			except (ValueError, TypeError):
				raise InvalidKeyValue(key, value)
				
		elif key == 'repeat_interval':
			try:
				value = int(value)
				if value <= 0:
					raise ValueError
			except (ValueError, TypeError):
				raise InvalidKeyValue(key, value)
			
		elif key == 'sort_by':
			if not value in Reminders.sort_functions:
				raise InvalidKeyValue(key, value)
				
		elif key == 'repeat_quantity':
			if not value in ("years", "months", "weeks", "days", "hours", "minutes"):
				raise InvalidKeyValue(key, value)
				
		elif key in ('username', 'password', 'new_password', 'title', 'url',
					'text', 'query'):
			if not isinstance(value, str):
				raise InvalidKeyValue(key, value)
				
		elif key == 'color':
			if not color_regex.search(value):
				raise InvalidKeyValue(key, value)

		elif key == 'notification_services':
			if not value:
				raise KeyNotFound(key)
			if not isinstance(value, list):
				raise InvalidKeyValue(key, value)
			for v in value:
				if not isinstance(v, int):
					raise InvalidKeyValue(key, value)

	else:
		if key == 'sort_by':
			value = 'time'
		
		elif key == 'text':
			value = ''
				
	return value

#===================
# Authentication endpoints
#===================

@api.route('/auth/login', methods=['POST'])
@error_handler
def api_login():
	"""
	Endpoint: /auth/login
	Description: Login to a user account
	Requires being logged in: No
	Methods:
		POST:
			Parameters (body):
				username (required): the username of the user account
				password (required): the password of the user account
			Returns:
				200:
					The apikey to use for further requests and expiration time (epoch)
				400:
					KeyNotFound: One of the required parameters was not given
				401:
					PasswordInvalid: The password given is not correct for the user account
				404:
					UsernameNotFound: The username was not found
	"""
	data = request.get_json()

	# Check if required keys are given
	username = extract_key(data, 'username')
	password = extract_key(data, 'password')

	# Check credentials
	user = User(username, password)

	# Login valid
	while True:
		api_key = urandom(16).hex() # <- length api key / 2
		hashed_api_key = hash(api_key)
		if not hashed_api_key in api_key_map:
			break
	exp = epoch_time() + 3600
	api_key_map.update({
		hashed_api_key: {
			'exp': exp,
			'user_data': user
		}
	})

	result = {'api_key': api_key, 'expires': exp}
	return return_api(result)

@api.route('/auth/logout', methods=['POST'])
@error_handler
@auth
def api_logout():
	"""
	Endpoint: /auth/logout
	Description: Logout of a user account
	Requires being logged in: Yes
	Methods:
		POST:
			Returns:
				200:
					Logout successful
	"""
	api_key_map.pop(g.hashed_api_key)
	return return_api({})

@api.route('/auth/status', methods=['GET'])
@error_handler
@auth
def api_status():
	"""
	Endpoint: /auth/status
	Description: Get current status of login
	Requires being logged in: Yes
	Methods:
		GET:
			Returns:
				200:
					The username of the logged in account and the expiration time of the api key (epoch)
	"""
	result = {
		'expires': api_key_map[g.hashed_api_key]['exp'],
		'username': api_key_map[g.hashed_api_key]['user_data'].username
	}
	return return_api(result)

#===================
# User endpoints
#===================

@api.route('/user/add', methods=['POST'])
@error_handler
def api_add_user():
	"""
	Endpoint: /user/add
	Description: Create a new user account
	Requires being logged in: No
	Methods:
		POST:
			Parameters (body):
				username (required): the username of the new user account
				password (required): the password of the new user account
			Returns:
				201:
					The user id of the new user account
				400:
					KeyNotFound: One of the required parameters was not given
					UsernameInvalid: The username given is not allowed
					UsernameTaken: The username given is already in use
	"""
	data = request.get_json()

	# Check if required keys are given
	username = extract_key(data, 'username')
	password = extract_key(data, 'password')
	
	# Add user
	user_id = register_user(username, password)
	return return_api({'user_id': user_id}, code=201)
		
@api.route('/user', methods=['PUT', 'DELETE'])
@error_handler
@auth
def api_manage_user():
	"""
	Endpoint: /user
	Description: Manage a user account
	Requires being logged in: Yes
	Methods:
		PUT:
			Description: Change the password of the user account
			Parameters (body):
				new_password (required): the new password of the user account
			Returns:
				200:
					Password updated successfully
				400:
					KeyNotFound: One of the required parameters was not given
		DELETE:
			Description: Delete the user account
			Returns:
				200:
					Account deleted successfully
	"""
	if request.method == 'PUT':
		data = request.get_json()
		
		# Check if required key is given
		new_password = extract_key(data, 'new_password')
		
		# Edit user
		g.user_data.edit_password(new_password)
		return return_api({})
	
	elif request.method == 'DELETE':
		# Delete user
		g.user_data.delete()
		api_key_map.pop(g.hashed_api_key)
		return return_api({})

#===================
# Notification service endpoints
#===================

@api.route('/notificationservices', methods=['GET', 'POST'])
@error_handler
@auth
def api_notification_services_list():
	"""
	Endpoint: /notificationservices
	Description: Manage the notification services
	Requires being logged in: Yes
	Methods:
		GET:
			Description: Get a list of all notification services
			Returns:
				200:
					The id, title and url of every notification service
		POST:
			Description: Add a notification service
			Parameters (body):
				title (required): the title of the notification service
				url (required): the apprise url of the notification service
			Returns:
				200:
					The id of the new notification service
				400:
					KeyNotFound: One of the required parameters was not given
	"""
	services: NotificationServices = g.user_data.notification_services
	
	if request.method == 'GET':
		result = services.fetchall()
		return return_api(result)
		
	elif request.method == 'POST':
		data = request.get_json()
		title = extract_key(data, 'title')
		url = extract_key(data, 'url')
		result = services.add(title=title,
							url=url).get()
		return return_api(result, code=201)

@api.route('/notificationservices/<int:n_id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_notification_service(n_id: int):
	"""
	Endpoint: /notificationservices/<n_id>
	Description: Manage a specific notification service
	Requires being logged in: Yes
	URL Parameters:
		<n_id>:
			The id of the notification service
	Methods:
		GET:
			Returns:
				200:
					All info about the notification service
				404:
					No notification service found with the given id
		PUT:
			Description: Edit the notification service
			Parameters (body):
				title: The new title of the entry.
				url: The new apprise url of the entry.
			Returns:
				200:
					Notification service updated successfully
				400:
					The apprise url is invalid
				404:
					No notification service found with the given id
		DELETE:
			Description: Delete the notification service
			Returns:
				200:
					Notification service deleted successfully
				404:
					No notification service found with the given id
	"""
	service: NotificationService = g.user_data.notification_services.fetchone(n_id)
	
	if request.method == 'GET':
		result = service.get()
		return return_api(result)
		
	elif request.method == 'PUT':
		data = request.get_json()
		title = extract_key(data, 'title', check_existence=False)
		url = extract_key(data, 'url', check_existence=False)
	
		result = service.update(title=title,
						url=url)
		return return_api(result)
		
	elif request.method == 'DELETE':
		service.delete()
		return return_api({})

#===================
# Library endpoints
#===================

@api.route('/reminders', methods=['GET', 'POST'])
@error_handler
@auth
def api_reminders_list():
	"""
	Endpoint: /reminders
	Description: Manage the reminders
	Requires being logged in: Yes
	Methods:
		GET:
			Description: Get a list of all reminders
			Parameters (url):
				sort_by: how to sort the result. Allowed values are 'title', 'title_reversed', 'time' and 'time_reversed'
			Returns:
				200:
					The id, title, text, time, repeat_quantity, repeat_interval and color of each reminder
		POST:
			Description: Add a reminder
			Parameters (body):
				title (required): the title of the reminder
				time (required): the UTC epoch timestamp that the reminder should be sent at
				notification_services (required): array of the id's of the notification services to use to send the notification
				text: the body of the reminder
				repeat_quantity ('years', 'months', 'weeks', 'days', 'hours', 'minutes'): The quantity of the repeat_interval
				repeat_interval: The number of the interval
				color: The hex code of the color of the reminder, which is shown in the web-ui
			Returns:
				200:
					The info about the new reminder entry
				400:
					KeyNotFound: One of the required parameters was not given
				404:
					NotificationServiceNotFound: One of the notification services was not found
	"""
	reminders: Reminders = g.user_data.reminders
	
	if request.method == 'GET':
		sort_by = extract_key(request.values, 'sort_by', check_existence=False)
		result = reminders.fetchall(sort_by=sort_by)
		return return_api(result)
	
	elif request.method == 'POST':
		data = request.get_json()
		title = extract_key(data, 'title')
		time = extract_key(data, 'time')
		notification_services = extract_key(data, 'notification_services')
		text = extract_key(data, 'text', check_existence=False)
		repeat_quantity = extract_key(data, 'repeat_quantity', check_existence=False)
		repeat_interval = extract_key(data, 'repeat_interval', check_existence=False)
		color = extract_key(data, 'color', check_existence=False)

		result = reminders.add(title=title,
								time=time,
								notification_services=notification_services,
								text=text,
								repeat_quantity=repeat_quantity,
								repeat_interval=repeat_interval,
								color=color)
		return return_api(result.get(), code=201)

@api.route('/reminders/search', methods=['GET'])
@error_handler
@auth
def api_reminders_query():
	"""
	Endpoint: /reminders/search
	Description: Search through the list of reminders
	Requires being logged in: Yes
	Methods:
		GET:
			Parameters (url):
				query (required): The search term
			Returns:
				200:
					The search results, listed like GET /reminders
				400:
					KeyNotFound: One of the required parameters was not given
	"""
	query = extract_key(request.values, 'query')

	result = g.user_data.reminders.search(query)
	return return_api(result)

@api.route('/reminders/test', methods=['POST'])
@error_handler
@auth
def api_test_reminder():
	"""
	Endpoint: /reminders/test
	Description: Test send a reminder draft
	Requires being logged in: Yes
	Methods:
		GET:
			Parameters (body):
				title (required): The title of the entry.
				notification_service (required): The new id of the notification service to use to send the reminder.
				text: The body of the reminder.
			Returns:
				201:
					The reminder is sent (doesn't mean it works, just that it was sent)
				400:
					KeyNotFound: One of the required parameters was not given
				404:
					NotificationServiceNotFound: The notification service given was not found
	"""
	data = request.get_json()
	title = extract_key(data, 'title')
	notification_services = extract_key(data, 'notification_services')
	text = extract_key(data, 'text', check_existence=False)

	test_reminder(title, notification_services, text)
	return return_api({}, code=201)

@api.route('/reminders/<int:r_id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_get_reminder(r_id: int):
	"""
	Endpoint: /reminders/<r_id>
	Description: Manage a specific reminder
	Requires being logged in: Yes
	URL Parameters:
		<r_id>:
			The id of the reminder
	Methods:
		GET:
			Returns:
				200:
					All info about the reminder
				404:
					No reminder found with the given id
		PUT:
			Description: Edit the reminder
			Parameters (body):
				title: The new title of the entry.
				time: The new UTC epoch timestamp the the reminder should be send.
				notification_services: Array of the new id's of the notification services to use to send the reminder.
				text: The new body of the reminder.
				repeat_quantity ('years', 'months', 'weeks', 'days', 'hours', 'minutes'): The new quantity of the repeat_interval.
				repeat_interval: The new number of the interval.
				color: The new hex code of the color of the reminder, which is shown in the web-ui.
			Returns:
				200:
					Reminder updated successfully
				404:
					ReminderNotFound: No reminder found with the given id
					NotificationServiceNotFound: One of the notification services was not found
		DELETE:
			Description: Delete the reminder
			Returns:
				200:
					Reminder deleted successfully
				404:
					No reminder found with the given id
	"""
	reminders: Reminders = g.user_data.reminders
	if request.method == 'GET':
		result = reminders.fetchone(r_id).get()
		return return_api(result)

	elif request.method == 'PUT':
		data = request.get_json()
		title = extract_key(data, 'title', check_existence=False)
		time = extract_key(data, 'time', check_existence=False)
		notification_services = extract_key(data, 'notification_services', check_existence=False)
		text = extract_key(data, 'text', check_existence=False)
		repeat_quantity = extract_key(data, 'repeat_quantity', check_existence=False)
		repeat_interval = extract_key(data, 'repeat_interval', check_existence=False)
		color = extract_key(data, 'color', check_existence=False)

		result = reminders.fetchone(r_id).update(title=title,
												time=time,
												notification_services=notification_services,
												text=text,
												repeat_quantity=repeat_quantity,
												repeat_interval=repeat_interval,
												color=color)
		return return_api(result)

	elif request.method == 'DELETE':
		reminders.fetchone(r_id).delete()
		return return_api({})

#===================
# Template endpoints
#===================

@api.route('/templates', methods=['GET', 'POST'])
@error_handler
@auth
def api_get_templates():
	"""
	Endpoint: /templates
	Description: Manage the templates
	Requires being logged in: Yes
	Methods:
		GET:
			Description: Get a list of all templates
			Returns:
				200:
					The id, title, text and color of every template
		POST:
			Description: Add a template
			Parameters (body):
				title (required): the title of the template
				notification_services (required): array of the id's of the notification services to use to send the notification
				text: the body of the template
				color: the hex code of the color of the template, which is shown in the web-ui
			Returns:
				200:
					The info about the new template entry
				400:
					KeyNotFound: One of the required parameters was not given
				404:
					NotificationServiceNotFound: One of the notification services was not found
	"""
	templates: Templates = g.user_data.templates
	
	if request.method == 'GET':
		result = templates.fetchall()
		return return_api(result)
	
	elif request.method == 'POST':
		data = request.get_json()
		title = extract_key(data, 'title')
		notification_services = extract_key(data, 'notification_services')
		text = extract_key(data, 'text', check_existence=False)
		color = extract_key(data, 'color', check_existence=False)
		
		result = templates.add(title=title,
								notification_services=notification_services,
								text=text,
								color=color)
		return return_api(result.get(), code=201)

@api.route('/templates/<int:t_id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_get_template(t_id: int):
	"""
	Endpoint: /templates/<t_id>
	Description: Manage a specific template
	Requires being logged in: Yes
	URL Parameters:
		<t_id>:
			The id of the template
	Methods:
		GET:
			Returns:
				200:
					All info about the template
				404:
					No template found with the given id
		PUT:
			Description: Edit the template
			Parameters (body):
				title: The new title of the entry.
				notification_services: The new array of id's of the notification services to use to send the reminder.
				text: The new body of the template.
				color: The new hex code of the color of the template.
			Returns:
				200:
					Template updated successfully
				404:
					TemplateNotFound: No template found with the given id
					NotificationServiceNotFound: One of the notification services was not found
		DELETE:
			Description: Delete the template
			Returns:
				200:
					Template deleted successfully
				404:
					No template found with the given id
	"""
	template: Template = g.user_data.templates.fetchone(t_id)
	
	if request.method == 'GET':
		result = template.get()
		return return_api(result)
		
	elif request.method == 'PUT':
		data = request.get_json()
		title = extract_key(data, 'title', check_existence=False)
		notification_services = extract_key(data, 'notification_services', check_existence=False)
		text = extract_key(data, 'text', check_existence=False)
		color = extract_key(data, 'color', check_existence=False)
		
		result = template.update(title=title,
								notification_services=notification_services,
								text=text,
								color=color)
		return return_api(result)

	elif request.method == 'DELETE':
		template.delete()
		return return_api({})

#===================
# Static reminder endpoints
#===================

@api.route('/staticreminders', methods=['GET', 'POST'])
@error_handler
@auth
def api_static_reminders_list():
	"""
	Endpoint: /staticreminders
	Description: Manage the static reminders
	Requires being logged in: Yes
	Methods:
		GET:
			Description: Get a list of all static reminders
			Returns:
				200:
					The id, title, text and color of each static reminder
		POST:
			Description: Add a static reminder
			Parameters (body):
				title (required): the title of the static reminder
				notification_services (required): array of the id's of the notification services to use to send the notification
				text: the body of the static reminder
				color: The hex code of the color of the static reminder, which is shown in the web-ui
			Returns:
				200:
					The info about the new static reminder entry
				400:
					KeyNotFound: One of the required parameters was not given
				404:
					NotificationServiceNotFound: One of the notification services was not found
	"""	
	reminders: StaticReminders = g.user_data.static_reminders
	
	if request.method == 'GET':
		result = reminders.fetchall()
		return return_api(result)
	
	elif request.method == 'POST':
		data = request.get_json()
		title = extract_key(data, 'title')
		notification_services = extract_key(data, 'notification_services')
		text = extract_key(data, 'text', check_existence=False)
		color = extract_key(data, 'color', check_existence=False)
		
		result = reminders.add(title=title,
			 					notification_services=notification_services,
								text=text,
								color=color)
		return return_api(result.get(), code=201)

@api.route('/staticreminders/<int:r_id>', methods=['GET', 'POST', 'PUT', 'DELETE'])
@error_handler
@auth
def api_get_static_reminder(r_id: int):
	"""
	Endpoint: /staticreminders/<r_id>
	Description: Manage a specific static reminder
	Requires being logged in: Yes
	URL Parameters:
		<r_id>:
			The id of the static reminder
	Methods:
		GET:
			Returns:
				200:
					All info about the static reminder
				404:
					No static reminder found with the given id
		POST:
			Description: Trigger the static reminder
			Returns:
				200:
					Static reminder triggered successfully
		PUT:
			Description: Edit the static reminder
			Parameters (body):
				title: The new title of the static reminder.
				notification_services: The new array of id's of the notification services to use to send the reminder.
				text: The new body of the static reminder.
				color: The new hex code of the color of the static reminder, which is shown in the web-ui.
			Returns:
				200:
					Static reminder updated successfully
				404:
					ReminderNotFound: No static reminder found with the given id
					NotificationServiceNotFound: One of the notification services was not found
		DELETE:
			Description: Delete the static reminder
			Returns:
				200:
					Static reminder deleted successfully
				404:
					No static reminder found with the given id
	"""
	reminders: StaticReminders = g.user_data.static_reminders
	if request.method == 'GET':
		result = reminders.fetchone(r_id).get()
		return return_api(result)

	elif request.method == 'POST':
		reminders.trigger_reminder(r_id)
		return return_api({})

	elif request.method == 'PUT':
		data = request.get_json()
		title = extract_key(data, 'title', check_existence=False)
		notification_services = extract_key(data, 'notification_services', check_existence=False)
		text = extract_key(data, 'text', check_existence=False)
		color = extract_key(data, 'color', check_existence=False)
		
		result = reminders.fetchone(r_id).update(title=title,
												notification_services=notification_services,
												text=text,
												color=color)
		return return_api(result)

	elif request.method == 'DELETE':
		reminders.fetchone(r_id).delete()
		return return_api({})
