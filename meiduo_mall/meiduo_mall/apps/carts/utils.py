import base64
import pickle

from django_redis import get_redis_connection


def merge_cart_cookie_to_redis(request, response, user):
    '''
    登录后合并cookie购物车数据到redis
    :param request: 本次请求对象，获取cookie中的数据
    :param user: 登录用户信息，获取user_id
    :param response: 本次响应对象，清楚cookie中的数据
    :return: response
    '''
    # 获取cookie中的购物数据
    cookie_cart = request.COOKIES.get('carts')
    # cookie中没有数据就响应结果
    if not cookie_cart:
        return response

    # 解密
    cart_dict = pickle.loads(base64.b64decode(cookie_cart.encode()))

    new_dict = {}
    new_add = []
    new_remove = []

    # 同步cookie中的购物车数据
    for sku_id, item in cart_dict.items():
        new_dict[sku_id] = item['count']

        if item['selected']:
            new_add.append(sku_id)
        else:
            new_remove.append(sku_id)
    # 将new_cart_dict写入到redis数据库中
    redis_conn = get_redis_connection('carts')
    pl = redis_conn.pipeline()
    pl.hmset('carts_%s' % user.id, new_dict)
    # 将勾选状态同步到redis数据库中
    if new_add:
        pl.sadd('selected_%s' % user.id, *new_add)
    if new_remove:
        pl.srem('selected_%s' % user.id, *new_remove)

    pl.execute()

    # 清楚cookie
    response.delete_cookie('carts')

    # 返回
    return response


