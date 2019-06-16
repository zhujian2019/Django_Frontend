from meiduo_mall import settings
from itsdangerous import BadData
from itsdangerous import TimedJSONWebSignatureSerializer

def generate_access_token(openid):
    '''

    :param openid:
    :return:
    '''
    # 创建对象
    serializer = TimedJSONWebSignatureSerializer(
        settings.dev.SECRET_KEY,
        expires_in=300

    )
    data = {'openid': openid}
    token = serializer.dumps(data)
    return token.decode()


def check_access_token(access_token):
    # 创建对象
    serializer = TimedJSONWebSignatureSerializer(
        settings.dev.SECRET_KEY,
        expires_in=300
    )


    try:
        data = serializer.loads(access_token)
    except BadData:
        return None
    else:
        return data.get('openid')

