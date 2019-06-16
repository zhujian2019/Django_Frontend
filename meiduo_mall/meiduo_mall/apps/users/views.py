import json
import logging
from meiduo_mall.utils.views import LoginRequiredJsonMixin

from django.contrib.auth import login, authenticate, logout
from meiduo_mall.utils.views import LoginRequiredMixin
from django.db import DatabaseError

from django.urls import reverse
from django.views import View
from django import http
from django.shortcuts import render, redirect
import re

# Create your views here.
from django_redis import get_redis_connection
from meiduo_mall.utils.response_code import RETCODE

from carts.utils import merge_cart_cookie_to_redis
from goods.models import SKU
from .models import User, Address

logger = logging.getLogger('django')


class UserBrowseHistory(LoginRequiredJsonMixin, View):
    '''用户浏览记录'''

    def get(self, request):
        '''
        获取浏览记录
        :param request:
        :return:
        '''
        # 1.链接redis
        redis_conn = get_redis_connection('history')

        # 2.获取所有的商品id
        sku_ids = redis_conn.lrange('history_%s' % request.user.id, 0, -1)

        # 根据sku_ids列表数据，查询出商品sku信息
        skus = []

        # 3.遍历，获取每一个商品id
        for sku_id in sku_ids:
            # 4.取出对应的商品
            sku = SKU.objects.get(id=sku_id)

            # 5.拼接，保存到list中
            skus.append({
                'id': sku.id,
                'name': sku.name,
                'default_image_url': sku.default_image_url,
                'price': sku.price
            })
        # 6.返回
        return http.JsonResponse({
            'code': RETCODE.OK,
            'errmsg': 'ok',
            'skus': skus
        })

    def post(self, request):
        '''
        用户的浏览记录保存
        :param request:
        :return:
        '''
        # 1.接收参数 json
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')

        # 2.校验参数
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku不存在')

        # 3.链接 redis， 创建 pl
        redis_conn = get_redis_connection('history')
        pl = redis_conn.pipeline()
        user_id = request.user.id

        # 4.执行 pl
        # 先去重: 这里给 0 代表去除所有的 sku_id
        pl.lrem('history_%s' % user_id, 0, sku_id)
        # 再存储
        pl.lpush('history_%s' % user_id, sku_id)
        # 最后截取: 界面有限, 只保留 5 个
        pl.ltrim('history_%s' % user_id, 0, 4)
        # 执行管道
        pl.execute()

        # 5.返回
        # 响应结果
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})





class ChangePasswordView(LoginRequiredMixin, View):
    '''修改密码'''

    def get(self, request):
        '''展示修改密码的界面'''
        return render(request, 'user_center_pass.html')

    def post(self, request):
        '''实现修改密码的逻辑'''
        # 接收参数
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        new_password2 = request.POST.get('new_password2')

        # 校验参数
        # 校验参数
        if not all([old_password, new_password, new_password2]):
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            request.user.check_password(old_password)
        except Exception as e:
            logger.error(e)
            return render(request, 'user_center_pass.html', {'origin_pwd_errmsg': '原始密码错误'})
        if not re.match(r'^[0-9A-Za-z]{8,20}$', new_password):
            return http.HttpResponseForbidden('密码最少8位，最长20位')
        if new_password != new_password2:
            return http.HttpResponseForbidden('两次输入的密码不一致')

        # 修改密码
        try:
            request.user.set_password(new_password)
            request.user.save()

        except Exception as e:
            logger.error(e)
            return render(request, 'user_center_pass.html', {'change_pwd_errmsg': '修改密码失败'})

        # 清理 状态保持 信息
        # 清理sessionid
        logout(request)
        response = redirect(reverse('users:login'))
        # 清理cookie
        response.delete_cookie('username')

        # 响应密码修改结果：重定向到登录界面
        return response


class UpdateTitleAddressView(LoginRequiredJsonMixin, View):
    '''设置地址标题'''

    def put(self, request, address_id):
        '''设置地址标题'''
        # 接收参数：地址标题
        json_dict = json.loads(request.body.decode())
        title = json_dict.get('title')

        try:
            # 查询地址
            address = Address.objects.get(id=address_id)
            # 设置新的地址标题
            address.title = title
            address.save()
        except Exception as e:
            logger.error(e)
            return http.JsonResponse({
                'code': RETCODE.DBERR,
                'errmsg': '设置地址标题失败'
            })

        # 响应删除地址结果
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '设置地址标题成功'})


class DefaultAddressView(LoginRequiredJsonMixin, View):
    '''设置默认地址'''

    def put(self, request, address_id):
        '''设置默认地址'''
        try:
            # 接收参数，查询地址
            address = Address.objects.get(id=address_id)

            # 设置地址为默认地址
            request.user.default_address = address
            request.user.save()

        except Exception as e:
            logger.error(e)
            return http.JsonResponse({
                'code': RETCODE.DBERR,
                'errmsg': '设置默认地址失败'
            })

        # 响应设置默认地址结果
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '设置默认地址成功'})


class UpdateDestroyAddressView(LoginRequiredJsonMixin, View):
    '''修改和删除地址'''

    def delete(self, request, address_id):
        '''删除地址'''
        try:
            # 查询要删除的地址
            address = Address.objects.get(id=address_id)

            # 将地址逻辑删除设置为True
            address.is_deleted = True
            address.save()

        except Exception as e:
            logger.error(e)
            return http.JsonResponse({
                'code': RETCODE.DBERR,
                'errmsg': '删除地址失败'
            })

        # 响应删除地址结果
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除地址成功'})

    def put(self, request, address_id):
        '''修改地址'''
        # 接收参数
        json_dict = json.loads(request.body.decode())
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')

        # 校验参数
        if not all([receiver, province_id, city_id, district_id, place, mobile]):
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return http.HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')

        # 判断地址是否存在，并更新地址信息
        try:
            # filter 得到一个查询集
            Address.objects.filter(id=address_id).update(
                user=request.user,
                title=receiver,
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email
            )

        except Exception as e:
            logger.error(e)
            return http.JsonResponse({
                'code': RETCODE.DBERR,
                'errmsg': '更新地址失败'
            })

        # 构造响应数据
        # get 得到一个对象
        address = Address.objects.get(id=address_id)
        address_dict = {
            "id": address.id,
            "title": address.title,
            "receiver": address.receiver,
            "province": address.province.name,
            "city": address.city.name,
            "district": address.district.name,
            "place": address.place,
            "mobile": address.mobile,
            "tel": address.tel,
            "email": address.email
        }

        # 响应更新地址结果
        return http.JsonResponse({'code': RETCODE.OK,
                                  'errmsg': '更新地址成功',
                                  'address': address_dict})


class AddressView(LoginRequiredMixin, View):
    '''用户收货地址'''

    def get(self, request):
        '''提供地址管理界面'''
        # 获取所有的地址
        addresses = Address.objects.filter(user=request.user, is_deleted=False)

        # 创建空的列表
        address_dict_list = []

        # 遍历
        for address in addresses:
            address_dict = {
                "id": address.id,
                "title": address.title,
                "receiver": address.receiver,
                "province": address.province.name,
                "city": address.city.name,
                "district": address.district.name,
                "place": address.place,
                "mobile": address.mobile,
                "tel": address.tel,
                "email": address.email
            }

            # 将默认地址移动到最前面
            default_address = request.user.default_address
            if default_address.id == address.id:
                # 查询集 addresses 没有 insert 方法
                address_dict_list.insert(0, address_dict)
            else:
                address_dict_list.append(address_dict)

        context = {
            'default_address_id': request.user.default_address_id,
            'addresses': address_dict_list,
        }

        return render(request, 'user_center_site.html', context)


class CreateAddressView(LoginRequiredJsonMixin, View):
    '''新增地址'''

    def post(self, request):
        '''实现新增地址逻辑'''

        # 获取地址个数
        count = request.user.addresses.count()
        # 判断地址个数
        if count >= 20:
            return http.JsonResponse({
                'code': RETCODE.THROTTLINGERR,
                'errmsg': '超过地址数量上限'
            })

        # 接收参数
        json_dict = json.loads(request.body.decode())
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')

        # 校验参数
        if not all([receiver, province_id, city_id, district_id, place, mobile]):
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return http.HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')

        # 保存地址信息
        try:
            address = Address.objects.create(
                user=request.user,
                title=receiver,
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email
            )

            # 设置默认地址
            if not request.user.default_address:
                request.user.default_address = address
                request.user.save()

        except Exception as e:
            logger.error(e)
            return http.JsonResponse({
                'code': RETCODE.DBERR,
                'errmsg': '新增地址失败'
            })

        # 新增地址成功，将新增的地址响应给前端实现局部刷新
        address_dict = {
            'id': address.id,
            "title": address.title,
            "receiver": address.receiver,
            "province": address.province.name,
            "city": address.city.name,
            "district": address.district.name,
            "place": address.place,
            "mobile": address.mobile,
            "tel": address.tel,
            "email": address.email

        }

        # 响应保存结果
        return http.JsonResponse({
            'code': RETCODE.OK,
            'errmsg': '新增地址成功',
            'address': address_dict
        })


class VerifyEmailView(View):
    '''验证邮箱'''

    def get(self, request):
        '''
        实现邮箱验证逻辑
        :param request:
        :return:
        '''
        # 1.接收token
        token = request.GET.get('token')

        # 2.校验
        if not token:
            return http.HttpResponseForbidden('缺少token')

        # 3.将token解码
        user = User.check_verify_email_token(token)
        if not user:
            return http.HttpResponseForbidden('无效的token')

        # 4.修改email_active
        try:
            user.email_active = True
            user.save()
        except Exception as e:
            logger.error(e)
            return http.HttpResponseForbidden('激活邮件失败')

        # 5.返回
        return redirect(reverse('users:info'))


class EmailView(LoginRequiredJsonMixin, View):
    '''添加邮箱'''

    def put(self, request):
        '''实现添加邮箱逻辑'''
        # 接收参数
        json_dict = json.loads(request.body.decode())
        email = json_dict.get('email')

        # 校验参数
        if not email:
            return http.HttpResponseForbidden('缺少email参数')
        if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return http.HttpResponseForbidden('参数email有误')

        # 赋值 email 字段
        try:
            request.user.email = email  # 赋值位置不能发生改变
            request.user.save()
        except Exception as e:
            logger.error(e)

            return http.JsonResponse({
                'code': RETCODE.DBERR,
                'errmsg': '添加邮箱失败'
            })

        # 导入:
        from celery_tasks.email.tasks import send_verify_email
        # 用定义好的函数替换原来的字符串:
        verify_url = request.user.generate_verify_email_url()
        # 发送验证链接:
        send_verify_email.delay(email, verify_url)

        # 响应添加邮箱结果
        return http.JsonResponse({
            'code': RETCODE.OK,
            'errmsg': '添加邮箱成功'
        })


class UserInfoView(LoginRequiredMixin, View):
    """用户中心"""

    def get(self, request):
        """

        :param request:
        :return:
        """
        # if request.user.is_authenticated:
        #
        #     return render(request, 'user_center_info.html')
        #
        # else:
        #     return http.HttpResponse('error')


        # 将用户信息进行拼接
        context = {
            'username': request.user.username,
            'mobile': request.user.mobile,
            'email': request.user.email,
            'email_active': request.user.email_active

        }

        return render(request, 'user_center_info.html', context=context)


class LogoutView(View):
    def get(self, request):
        """实现退出登录逻辑"""

        # 清理 session
        logout(request)

        # 退出登录，重定向到登录页
        response = redirect(reverse('contents:index'))

        # 退出登录时清除 cookie 中的 username
        response.delete_cookie('username')

        # 返回响应
        return response


class LoginView(View):
    '''登录界面'''

    def get(self, request):
        '''

        :param request:
        :return:
        '''
        return render(request, 'login.html')

    def post(self, request):
        '''
        登录逻辑
        :param request:
        :return:
        '''
        # 1.接收参数
        username = request.POST.get('username')
        password = request.POST.get('password')
        # remembered 这个参数可以是 None 或是 'on'
        remembered = request.POST.get('remembered')

        # 2.校验参数
        if not all([username, password]):
            return http.HttpResponseForbidden('缺少必传参数')

        # 判断用户名是否是5-20个字符
        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return http.HttpResponseForbidden('请输入正确的用户名或手机号')

        # 判断密码是否是8-20个数字
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('密码最少8位，最长20位')

        # 3.认证信息
        user = authenticate(username=username, password=password)
        if user is None:
            return render(request, 'login.html', {'account_errmsg': '用户名或密码错误'})

        # 4.状态保持
        login(request, user)

        # 5.判断状态保持周期
        if remembered != 'on':
            # 不记住用户：浏览器会话结束就过期
            request.session.set_expiry(0)
        else:
            # 记住用户：None 表示两周后过期
            request.session.set_expiry(None)

        # 6.跳转首页

        next = request.GET.get('next')

        if next:
            response = redirect(next)

        else:
            response = redirect(reverse('contents:index'))

        # 在响应对象中设置用户名信息.
        # 将用户名写入到 cookie，有效期 15 天
        response.set_cookie('username', user.username, max_age=3600 * 24 * 15)

        response = merge_cart_cookie_to_redis(request, response, user)

        # 返回响应结果
        return response


class MobileCountView(View):
    def get(self, request, mobile):
        count = User.objects.filter(mobile=mobile).count()
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'count': count})


class UsernameCountView(View):
    def get(self, request, username):
        '''

        :param request:
        :param username:
        :return:
        '''
        count = User.objects.filter(username=username).count()
        return http.HttpResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'count': count})


class RegisterView(View):
    """用户注册"""

    def get(self, request):
        """
        提供注册界面
        :param request: 请求对象
        :return: 注册界面
        """
        return render(request, 'register.html')

    def post(self, request):
        """
        实现用户注册,将用户信息保存到数据库
        :param request: 请求对象
        :return: 注册结果
        """
        # 1.接收参数
        username = request.POST.get('username')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        mobile = request.POST.get('mobile')
        sms_code_client = request.POST.get('sms_code')
        allow = request.POST.get('allow')

        # 2.校验参数
        # 2.1全局校验
        # 判断参数是否齐全
        if not all([username, password, password2, mobile, sms_code_client, allow]):
            return http.HttpResponseForbidden('缺少必传参数')

        # 2.2单个查看
        # 判断用户名是否是5-20个字符
        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return http.HttpResponseForbidden('请输入5-20个字符的用户名')
        # 判断密码是否是8-20个数字
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('请输入8-20位的密码')
        # 判断两次密码是否一致
        if password != password2:
            return http.HttpResponseForbidden('两次输入的密码不一致')
        # 判断手机号是否合法
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('请输入正确的手机号码')
        # 判断是否勾选用户协议
        if allow != 'on':
            return http.HttpResponseForbidden('请勾选用户协议')

        # 进行短信验证校验
        # 获取 redis 链接对象
        redis_conn = get_redis_connection('verify_code')
        # 从 redis 中获取保存的 sms_code
        sms_code_server = redis_conn.get('sms_%s' % mobile)
        # 判断 sms_code_server 是否存在
        if sms_code_server is None:
            # 不存在直接返回, 说明服务器的过期了, 超时
            return render(request, 'register.html', {'sms_code_errmsg': '无效的短信验证码'})
        # 如果 sms_code_server 存在, 则对比两者:
        if sms_code_client != sms_code_server.decode():
            # 对比失败, 说明短信验证码有问题, 直接返回:
            return render(request, 'register.html', {'sms_code_errmsg': '输入短信验证码有误'})

        # 3.保存到数据库
        try:
            user = User.objects.create_user(username=username, password=password, mobile=mobile)
        except DatabaseError:
            return render(request, 'register.html', {'register_errmsg': '注册失败'})

        # 5.状态保持: session
        login(request, user)

        # 4.跳转到首页
        # return http.HttpResponse('保存成功，后续再写')
        # 响应注册结果
        # return redirect(reverse('contents:index'))
        # 生成一个cookie返回
        response = redirect(reverse('contents:index'))
        response.set_cookie('username', user.username, max_age=3600 * 24 * 15)

        return response
