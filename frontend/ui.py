#-*- coding: utf-8 -*-

import logging
from flask import Blueprint, render_template

ui = Blueprint('ui', __name__)

methods = ['GET']

@ui.errorhandler(404)
def not_found(e):
	return render_template('page_not_found.html', url_prefix=logging.URL_PREFIX)

@ui.route('/', methods=methods)
def ui_login():
	return render_template('login.html', url_prefix=logging.URL_PREFIX)

@ui.route('/reminders', methods=methods)
def ui_reminders():
	return render_template('reminders.html', url_prefix=logging.URL_PREFIX)
