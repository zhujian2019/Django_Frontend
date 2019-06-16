import random

from django.shortcuts import render
from django import http

# Create your views here.
from django.views import View
from django_redis import get_redis_connection

from meiduo_mall.libs.captcha.captcha import *

from meiduo_mall.utils.response_code import RETCODE

from meiduo_mall.libs.yuntongxun.ccp_sms import CCP

from . import para
import logging
logger = logging.getLogger('django')



class SMSCodeView(View):
    '''
    短信验证
    '''
    def get(self, request, mobile):
        '''
        接收参数，校验参数，生成短信验证码，发送，返回
        :param request:
        :param mobile:
        :return:
        '''
        # 2.1链接redis
        redis_conn = get_redis_connection('verify_code')
        send_flag = redis_conn.get('send_flag_%s' % mobile)
        if send_flag:
            return http.JsonResponse({'code': RETCODE.THROTTLINGERR, 'errmsg': '发送短信过于频繁'})


        # 1.接收参数  使用接口文档
        image_code_client = request.GET.get('image_code')
        uuid = request.GET.get('image_code_id')


        # 2.校验（全局是否为空 + uuid检验 + 图形验证码校验）
        if not all([image_code_client, uuid]):
            return http.JsonResponse({
                'code': RETCODE.NECESSARYPARAMERR,
                'errmsg': '缺少必传参数'
            })

        # 2.2取出图形验证码，判断是否存在（过期）
        image_code_server = redis_conn.get('img_%s' % uuid)
        if image_code_server is None:
            return http.JsonResponse({
                'code': RETCODE.IMAGECODEERR,
                'errmsg': '图形验证码错误'
            })
        # 2.3删除图形验证码
        try:
            redis_conn.delete('img_%s' % uuid)
        except Exception as e:
            logger.error(e)
        # 2.4比较（前端和redis）图形验证码
        if image_code_client.lower() != image_code_server.decode().lower():
            return http.JsonResponse({
                'code': RETCODE.IMAGECODEERR,
                'errmsg': '输入的图形验证码有误'
            })

        # 3.生成短信验证码
        sms_code = '%06d' % random.randint(0, 999999)
        logger.info(sms_code)

        # 创建管道
        pl = redis_conn.pipeline()

        # 4.保存到redis中
        pl.setex('sms_%s' % mobile, para.SMS_CODE_REDIS_EXPIRES, sms_code)

        # 重新写入send_flag
        # 60s内是否重复发送的标记
        # SEND_SMS_CODE_INTERVAL = 60(s)
        pl.setex('send_flag_%s' % mobile, para.SEND_SMS_CODE_INTERVAL, 1)

        # 执行管道
        pl.execute()

        # 5.发送短信验证码（调用云通讯接口） 要钱的
        # CCP().send_template_sms(mobile, [sms_code, 5], 1)
        from celery_tasks.sms.tasks import send_sms_code
        send_sms_code.delay(mobile, sms_code)


        # 6.返回（code + errmsg）
        return http.JsonResponse({
            'code': RETCODE.OK,
            'errmsg': 'ok'
        })


class ImageCodeView(View):
    '''
    图形验证码
    '''

    def get(self, request, uuid):
        '''
        接收uuid，生成图形验证码，返回并保存
        :param request:
        :param uuid:
        :return:
        '''
        # 1.生成图片验证码    文本+图片
        text, image = captcha.generate_captcha()

        # 2.获取redis链接对象
        redis_conn = get_redis_connection('verify_code')

        # 3.保存图形验证码，设置图形验证码有效期，单位：秒
        # redis_conn.setex(key, expire_time, value)
        # redis_conn.setex('img_%s' % uuid, 300, text)
        redis_conn.setex('img_%s' % uuid, para.IMAGE_CODE_REDIS_EXPIRES, text)

        # 4.响应图片验证码
        return http.HttpResponse(image, content_type='image/jpg')
