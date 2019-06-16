# 添加一个Mixin扩展类， 帮助我们判定用户是否登录
from django import http
from django.contrib.auth.decorators import login_required

from meiduo_mall.utils.response_code import RETCODE
from django.utils.decorators import wraps


class LoginRequiredMixin(object):
    # 重写as_view
    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view()
        return login_required(view)


def login_required_json(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return http.JsonResponse({
                'code': RETCODE.SESSIONERR,
                'errmsg': '用户未登录'
            })

        else:
            return view(request, *args, **kwargs)

    return wrapper


class LoginRequiredJsonMixin(object):
    # 重写as_view
    @classmethod
    def as_view(cls, **initkwargs):
        view = super().as_view()
        view2 = login_required_json(view)
        return view2
