# 导入 Celery 类
import os

from celery import Celery

if not os.getenv('DJANGO_SETTINGS_MODULE'):
    os.environ['DJANGO_SETTINGS_MODULE'] = 'meiduo_mall.settings.dev'
# 创建 celery 对象
# 需要添加一个参数,是个字符串, 内容随意添加
celery_app = Celery('meiduo')

# 给 celery 添加配置
# 里面的参数为我们创建的 config 配置文件:
celery_app.config_from_object('celery_tasks.config')


# 自动发现任务
celery_app.autodiscover_tasks([
    'celery_tasks.sms',
    'celery_tasks.email'
])

