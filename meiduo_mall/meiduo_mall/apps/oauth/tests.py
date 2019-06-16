from django.test import TestCase
from itsdangerous import TimedJSONWebSignatureSerializer
from django.conf import settings
# Create your tests here.


if __name__ == '__main__':
    import os

    os.environ['DJANGO_SETTINGS_MODULE'] = 'meiduo_mall.meiduo_mall.settings.dev'

    serializer = TimedJSONWebSignatureSerializer(
        settings.SECRET_KEY,
        expires_in=300

    )


    dict = {
        'name': 'zs'
    }


    token = serializer.dumps(dict).decode()

    print(token)



