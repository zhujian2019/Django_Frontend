from celery_tasks.main import celery_app
from meiduo_mall.libs.yuntongxun.ccp_sms import CCP


@celery_app.task(bind=True, name='send_sms_code', retry_backoff=3)
def send_sms_code(self, mobile, sms_code):
    '''
    发送短信
    :param self:
    :return:
    '''
    try:
        result = CCP().send_template_sms(mobile, [sms_code, 5], 1)
    except Exception as e:

        raise self.retry(exc=e, max_retries=3)

    if result != 0:
        raise self.retry(exec=Exception('发送短信失败'), max_retries=3)
    return result

