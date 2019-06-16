import os

if not os.getenv('DJANGO_SETTINGS_MODULE'):
    os.environ['DJANGO_SETTINGS_MODULE'] = 'meiduo_mall.settings.dev'

import django

django.setup()

import time

from django.conf import settings
from django.template import loader

from contents.models import ContentCategory
from goods.utils import get_categories


def generate_static_index_html():
    '''生成静态的主页html文件'''
    print('%s: gengerate_static_index_html' % time.ctime())

    # 获取商品频道和分类
    categories = get_categories()

    # 广告内容
    contents = {}
    content_categories = ContentCategory.objects.all()
    for cat in content_categories:
        contents[cat.key] = cat.content_set.filter(status=True).order_by('sequence')

    # 渲染模板
    context = {
        'categories': categories,
        'contents': contents
    }

    # 获取首页模板文件
    template = loader.get_template('index.html')
    # 渲染首页模板文件
    html_text = template.render(context)
    # 将首页html字符串写入到指定目录，命名’index.html‘
    file_path = os.path.join(settings.STATICFILES_DIRS[0], 'index.html')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_text)


if __name__ == '__main__':
    generate_static_index_html()
