from django import http
from django.core.paginator import Paginator, EmptyPage
from django.shortcuts import render

# Create your views here.
from django.views import View

from goods.utils import get_categories
from goods import para
from goods.models import GoodsCategory, SKU, GoodsVisitCount
from goods.utils import get_breadcrumb, get_goods_and_spec
from meiduo_mall.utils.response_code import RETCODE
from django.utils import timezone
import datetime
import logging

from orders.models import OrderGoods

logger = logging.getLogger('django')


class GoodsCommentView(View):
    '''订单商品评价信息'''

    def get(self, request, sku_id):
        # 获取被评价的订单商品信息
        order_goods_list = OrderGoods.objects.filter(sku_id=sku_id, is_commented=True).order_by('-create_time')[:30]
        # 序列化
        comment_list = []
        for order_goods in order_goods_list:
            username = order_goods.order.user.username
            comment_list.append({
                'username': username[0] + '***' + username[-1] if order_goods.is_anonymous else username,
                'comment': order_goods.comment,
                'score': order_goods.score,
            })

        return http.JsonResponse({
            'code': RETCODE.OK,
            'errmsg': 'ok',
            'comment_list': comment_list
        })


class DetailVisitView(View):
    def post(self, request, category_id):
        '''
        保存当前分类商品访问量
        :param request:
        :param category_id:
        :return:
        '''
        # 1.category_id查询对应的商品类别
        try:
            category = GoodsCategory.objects.get(id=category_id)

        except GoodsCategory.DoesNotExist:
            return http.HttpResponseForbidden('此类商品不存在')

        # 2.获取当前时间
        # 先获取时间对象
        t = timezone.localtime()
        # 根据时间对象拼接日期的字符串形式:
        today_str = '%d-%02d-%02d' % (t.year, t.month, t.day)
        # 将字符串转为日期格式:
        today_date = datetime.datetime.strptime(today_str, '%Y-%m-%d')

        # 3.根据当前时间，查询是否已经当前商品记录
        try:
            # 将今天的日期传入进去, 获取该商品今天的访问量:
            # 查询今天该类别的商品的访问量
            counts_data = category.goodsvisitcount_set.get(date=today_date)
        except GoodsVisitCount.DoesNotExist:
            # 如果该类别的商品在今天没有过访问记录，就新建一个访问记录
            counts_data = GoodsVisitCount()

        # 4.如果没有，创建一个新的记录
        # 5.如果有则更新
        try:
            # 更新模型类对象里面的属性: category 和 count
            counts_data.category = category
            counts_data.count += 1
            counts_data.save()
        except Exception as e:
            logger.error(e)
            return http.HttpResponseServerError('服务器异常')

        # 6.返回:
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class DetailView(View):
    '''商品详情页'''

    def get(self, request, sku_id):
        '''
        返回商品详情页
        :param request:
        :param sku_id:
        :return:
        '''
        # 提取sku_id,获取对应的商品
        try:
            sku = SKU.objects.filter(id=sku_id)

        except SKU.DoesNotExist:
            return render(request, '404.html')

        # 查询商品频道分类
        categories = get_categories()

        # 调用封装的函数, 根据 sku_id 获取对应的
        # 1. 类别( sku )
        # 2. 商品( goods )
        # 3. 商品规格( spec )
        data = get_goods_and_spec(sku_id, request)

        # 渲染页面
        context = {
            'categories': categories,
            'goods': data.get('goods'),
            'specs': data.get('goods_specs'),
            'sku': data.get('sku')
        }
        return render(request, 'detail.html', context)


class HotGoodsView(View):
    '''商品热销排行'''

    def get(self, request, category_id):
        '''提供商品热销排行 JSON 数据'''
        # 根据销量倒序
        skus = SKU.objects.filter(category_id=category_id,
                                  is_launched=True).order_by('-sales')[:2]

        # 序列化
        hot_skus = []
        for sku in skus:
            hot_skus.append({
                'id': sku.id,
                'default_image_url': sku.default_image_url,
                'name': sku.name,
                'price': sku.price
            })

        return http.JsonResponse({
            'cdoe': RETCODE.OK,
            'errmsg': 'ok',
            'hot_skus': hot_skus
        })


class ListView(View):
    '''商品列表页'''

    def get(self, request, category_id, page_num):
        '''提供商品列表页'''
        # 判断 category_id 是否正确
        try:
            # 获取三级菜单分类信息
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return http.HttpResponseForbidden('GoodsCategory 不存在')

        # 查询商品频道分类
        categories = get_categories()
        # 查询面包屑导航
        breadcrumb = get_breadcrumb(category)

        # 增加代码部分：
        # 接收 sort 参数：如果用户不传，就是默认的排序规则
        sort = request.GET.get('sort', 'default')

        # 按照排序规则查询该分类商品SKU信息
        if sort == 'price':
            # 按照价格由低到高
            sortkind = 'price'
        elif sort == 'hot':
            # 按照销量由低到高
            sortkind = '-sales'
        else:
            # 'price'和'sales'以外的所有排序方式都归为’default‘
            sort = 'default'
            sortkind = 'create_time'

        # 获取当前分类并且上架的商品(并且对商品按照字段进行排序)
        skus = SKU.objects.filter(category=category,
                                  is_launched=True).order_by(sortkind)
        # 创建分页器：每页N条记录
        # 列表页每页商品数据量
        # GOODS_LIST_LIMIT = 5
        paginator = Paginator(skus, para.GOODS_LIST_LIMIT)
        # 获取每页商品数据
        try:
            page_skus = paginator.page(page_num)
        except EmptyPage:
            # 如果 page_num 不正确，默认给用户404
            return http.HttpResponseNotFound('empty page')

        # 获取列表页总页数
        total_page = paginator.num_pages

        # 渲染页面
        context = {
            'categories': categories,  # 频道分类
            'breadcrumb': breadcrumb,  # 面包屑导航
            'sort': sort,  # 排序字段
            'category': category,  # 第三级分类
            'page_skus': page_skus,  # 分页后数据
            'total_page': total_page,  # 总页数
            'page_num': page_num,  # 当前页码

        }

        # 返回页面
        return render(request, 'list.html', context)
