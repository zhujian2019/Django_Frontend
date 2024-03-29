import re

from django.contrib.auth.backends import ModelBackend

from users.models import User

import logging
logger = logging.getLogger('django')






def get_user_by_account(account):

    try:
        if re.match(r'^1[3-9]\d{9}$', account):
            user = User.objects.get(mobile=account)

        else:
            user = User.objects.get(username=account)

    except Exception as e:
        logger.error(e)

        return None

    else:
        return user

class UsernameMobileAuthBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):

        user = get_user_by_account(username)

        if user and user.check_password(password):
             return user


