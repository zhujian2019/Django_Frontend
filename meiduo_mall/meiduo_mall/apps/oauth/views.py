import re

from QQLoginTool.QQtool import OAuthQQ
from django import http
from django.contrib.auth import login
from django.db import DatabaseError
from django.shortcuts import render, redirect

# Create your views here.
from django.urls import reverse
from django.views import View
from django_redis import get_redis_connection

from carts.utils import merge_cart_cookie_to_redis
from meiduo_mall import settings
from meiduo_mall.utils.response_code import RETCODE

from oauth.models import OAuthQQUser
import logging

from oauth.utils import generate_access_token, check_access_token
from users.models import User

logger = logging.Logger('django')


class QQUserView(View):
    def post(self, request):
        '''

        :param request:
        :return:
        '''
        # 1.接收参数
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        sms_code_client = request.POST.get('sms_code')
        access_token = request.POST.get('access_token')

        # 2.校验参数
        # 判断参数是否齐全
        if not all([mobile, password, sms_code_client]):
            return http.HttpResponseForbidden('缺少必传参数')

        # 判断手机号是否合法
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('请输入正确的手机号码')

        # 判断密码是否合格
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('请输入8-20位的密码')

        # 创建 redis 链接对象:
        redis_conn = get_redis_connection('verify_code')
        # 从 redis 中获取 sms_code 值:
        sms_code_server = redis_conn.get('sms_%s' % mobile)
        # 判断获取出来的有没有:
        if sms_code_server is None:
            # 如果没有, 直接返回:
            return render(request, 'oauth_callback.html', {'sms_code_errmsg': '无效的短信验证码'})
        # 如果有, 则进行判断:
        if sms_code_client != sms_code_server.decode():
            # 如果不匹配, 则直接返回:
            return render(request, 'oauth_callback.html', {'sms_code_errmsg': '输入短信验证码有误'})

        # 调用我们自定义的函数, 检验传入的 access_token 是否正确:
        # 错误提示放在 sms_code_errmsg 位置
        openid = check_access_token(access_token)
        if not openid:
            return render(request, 'oauth_callback.html', {'openid_errmsg': '无效的openid'})

        # 3.在user表中添加新用户(先查后增)
        try:
            user = User.objects.get(mobile=mobile)
        except User.DoesNotExist:
            # 创建新用户
            user = User.objects.create_user(username=mobile, password=password, mobile=mobile)

        else:
            # 校验密码
            if not user.check_password(password):
                return render(request, 'oauth_callback.html', {'openid_errmsg': '用户名或密码错误'})

        # 4.在OAuthQQUser表中增加用户
        try:
            OAuthQQUser.objects.create(openid=openid, user=user)
        except DatabaseError:
            return render(request, 'oauth_callback.html', {'qq_login_errmsg': 'QQ登录失败'})
        # 5.状态保持
        login(request, user)

        # 6.设置cookie
        next = request.GET.get('state')
        response = redirect(next)
        response.set_cookie('username', user.username, max_age=3600 * 24 * 15)
        reponse = merge_cart_cookie_to_redis(request, response, user)

        # 7.返回
        return response

    def get(self, request):
        '''

        :param request:
        :return:
        '''
        # 1.接收code参数
        code = request.GET.get('code')
        # 2.判断code是否存在
        if not code:
            return http.HttpResponseForbidden('缺少code')

        oauth = OAuthQQ(client_id=settings.dev.QQ_CLIENT_ID,
                        client_secret=settings.dev.QQ_CLIENT_SECRET,
                        redirect_uri=settings.dev.QQ_REDIRECT_URI)
        # 3.获取access_token
        # 4.获取openid
        try:
            # 携带 code 向 QQ服务器 请求 access_token
            access_token = oauth.get_access_token(code)

            # 携带 access_token 向 QQ服务器 请求 openid
            openid = oauth.get_open_id(access_token)

        except Exception as e:
            # 如果上面获取 openid 出错, 则验证失败
            logger.error(e)
            # 返回结果
            return http.HttpResponseServerError('OAuth2.0认证失败')

        # 5.判断表中是否存在
        try:
            oauth_user = OAuthQQUser.objects.get(openid=openid)
        except OAuthQQUser.DoesNotExist:
            # 如果 openid 没绑定美多商城用户
            # 调用我们封装好的方法, 对 openid 进行加密, 生成 access_token 字符串
            access_token = generate_access_token(openid)
            # 拿到 access_token 字符串后, 拼接字典
            context = {'access_token': access_token}
            # 返回响应, 重新渲染
            return render(request, 'oauth_callback.html', context)

        else:
            # 如果 openid 已绑定美多商城用户
            # 6.获取用户
            qq_user = oauth_user.user
            # 7.状态保持
            login(request, qq_user)
            # 8.重定向并设置cookie
            response = redirect(reverse('contents:index'))

            response.set_cookie('username', qq_user.username, max_age=3600 * 24 * 15)

            response = merge_cart_cookie_to_redis(request, response, qq_user)

            return response


class QQURLView(View):
    def get(self, request):
        '''

        :param request:
        :return:
        '''
        # 1.接收参数
        next = request.GET.get('next')

        # 2.创建QQLoginTool对象
        oauth = OAuthQQ(
            client_id=settings.dev.QQ_CLIENT_ID,
            client_secret=settings.dev.QQ_CLIENT_SECRET,
            redirect_uri=settings.dev.QQ_REDIRECT_URI,
            state=next
        )

        # 3.获取url
        login_url = oauth.get_qq_url()

        # 4.返回对象
        return http.JsonResponse({
            'code': RETCODE.OK,
            'errmsg': 'OK',
            'login_url': login_url
        })
