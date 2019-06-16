import json

from decimal import Decimal

from django import http
from django.core.paginator import Paginator, EmptyPage
from django.db import transaction
from django.shortcuts import render

# Create your views here.
from django.utils import timezone
from django.views import View
from django_redis import get_redis_connection

from meiduo_mall.utils.views import LoginRequiredMixin

from goods.models import SKU
from meiduo_mall.utils.response_code import RETCODE

from meiduo_mall.utils.views import LoginRequiredJsonMixin
from orders.models import OrderInfo, OrderGoods
from users.models import Address
import logging

logger = logging.getLogger('django')


class OrderCommentView(LoginRequiredMixin, View):
    """订单商品评价"""

    def get(self, request):
        """展示商品评价页面"""
        # 接收参数
        order_id = request.GET.get('order_id')
        # 校验参数
        try:
            OrderInfo.objects.get(order_id=order_id,
                                  user=request.user)
        except OrderInfo.DoesNotExist:
            return http.HttpResponseNotFound('订单不存在')

        # 查询订单中未被评价的商品信息
        try:
            uncomment_goods = OrderGoods.objects.filter(order_id=order_id,
                                                        is_commented=False)
        except Exception:
            return http.HttpResponseServerError('订单商品信息出错')

        # 构造待评价商品数据
        uncomment_goods_list = []
        for goods in uncomment_goods:
            uncomment_goods_list.append({
                'order_id': goods.order.order_id,
                'sku_id': goods.sku.id,
                'name': goods.sku.name,
                'price': str(goods.price),
                'default_image_url': goods.sku.default_image_url,
                'comment': goods.comment,
                'score': goods.score,
                'is_anonymous': str(goods.is_anonymous),
            })

        # 渲染模板
        context = {
            'uncomment_goods_list': uncomment_goods_list
        }
        return render(request, 'goods_judge.html', context)

    def post(self, request):
        """评价订单商品"""
        # 接收参数
        json_dict = json.loads(request.body.decode())
        order_id = json_dict.get('order_id')
        sku_id = json_dict.get('sku_id')
        score = json_dict.get('score')
        comment = json_dict.get('comment')
        is_anonymous = json_dict.get('is_anonymous')
        # 校验参数
        if not all([order_id, sku_id, score, comment]):
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            OrderInfo.objects.filter(order_id=order_id,
                                     user=request.user,
                                     status=OrderInfo.ORDER_STATUS_ENUM['UNCOMMENT'])
        except OrderInfo.DoesNotExist:
            return http.HttpResponseForbidden('参数order_id错误')
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('参数sku_id错误')
        if is_anonymous:
            if not isinstance(is_anonymous, bool):
                return http.HttpResponseForbidden('参数is_anonymous错误')

        # 保存订单商品评价数据
        OrderGoods.objects.filter(order_id=order_id,
                                  sku_id=sku_id,
                                  is_commented=False).update(
            comment=comment,
            score=score,
            is_anonymous=is_anonymous,
            is_commented=True
        )

        # 累计评论数据
        sku.comments += 1
        sku.save()
        sku.goods.comments += 1
        sku.goods.save()

        # 如果所有订单商品都已评价，则修改订单状态为已完成
        if OrderGoods.objects.filter(order_id=order_id,
                                     is_commented=False).count() == 0:
            OrderInfo.objects.filter(order_id=order_id).update(status=OrderInfo.ORDER_STATUS_ENUM['FINISHED'])

        return http.JsonResponse({'code': RETCODE.OK,
                                  'errmsg': '评价成功'})


class UserOrderInfoView(LoginRequiredMixin, View):
    '''我的订单'''

    def get(self, request, page_num):
        '''提供我的订单页面'''
        user = request.user
        # 查询订单
        orders = user.orderinfo_set.all().order_by('-create_time')
        # 遍历所有订单
        for order in orders:
            # 绑定订单状态
            order.status_name = OrderInfo.ORDER_STATUS_CHOICES[order.status - 1][1]
            # 绑定支付方式
            order.pay_method_name = OrderInfo.PAY_METHODS_CHOICES[order.pay_method - 1][1]
            order.sku_list = []
            # 查询订单商品
            order_goods = order.skus.all()
            # 遍历订单商品
            for order_good in order_goods:
                sku = order_good.sku
                sku.count = order_good.count
                sku.amount = sku.price * sku.count
                order.sku_list.append(sku)

        # 分页
        page_num = int(page_num)
        try:
            paginator = Paginator(orders, 2)
            page_orders = paginator.page(page_num)
            total_page = paginator.num_pages
        except EmptyPage:
            return http.HttpResponseNotFound('订单不存在')

        context = {
            'page_orders': page_orders,
            'total_page': total_page,
            'page_num': page_num
        }

        return render(request, 'user_center_order.html', context=context)


class OrderSuccessView(LoginRequiredMixin, View):
    '''提交订单成功'''

    def get(self, request):
        order_id = request.GET.get('order_id')
        payment_amount = request.GET.get('payment_amount')
        pay_method = request.GET.get('pay_method')

        context = {
            'order_id': order_id,
            'payment_amount': payment_amount,
            'pay_method': pay_method
        }

        return render(request, 'order_success.html', context=context)


class OrderCommitView(LoginRequiredJsonMixin, View):
    '''订单提交'''

    def post(self, request):
        '''保存订单信息和订单商品信息'''
        # 获取当前要保存的订单数据
        json_dict = json.loads(request.body.decode())
        address_id = json_dict.get('address_id')
        pay_method = int(json_dict.get('pay_method'))

        # 校验参数
        if not all([address_id, pay_method]):
            return http.HttpResponseForbidden('缺少必传参数')
        # 判断address_id是否合法
        try:
            address = Address.objects.get(id=address_id)
        except Exception as e:
            logger.error(e)
            return http.HttpResponseForbidden('参数address_id有误')

        # 判断pay_method是否合法
        if pay_method not in [OrderInfo.PAY_METHODS_ENUM['CASH'],
                              OrderInfo.PAY_METHODS_ENUM['ALIPAY']]:
            # if pay_method not in [1, 2]:
            return http.HttpResponseForbidden('参数pay_method有误')

        # 获取登录用户
        user = request.user
        # 生成订单编号：年月日时分秒+用户编号
        order_id = timezone.localtime().strftime('%Y%m%d%H%M%S') + ('%09d' % user.id)

        # 显式的开启一个事务
        with transaction.atomic():
            # 创建事务保存点
            save_id = transaction.savepoint()

            # 暴力回滚
            try:
                # 保存订单的基本信息 OrderInfo (一)
                order = OrderInfo.objects.create(
                    order_id=order_id,
                    user=user,
                    address=address,
                    total_count=0,
                    total_amount=Decimal('0'),
                    freight=Decimal('10.00'),
                    pay_method=pay_method,
                    status=OrderInfo.ORDER_STATUS_ENUM['UNPAID']
                    if pay_method == OrderInfo.PAY_METHODS_ENUM['ALIPAY']
                    else OrderInfo.ORDER_STATUS_ENUM['UNSEND']
                )

                # 从redis读取购物车中被勾选中的商品信息
                redis_conn = get_redis_connection('carts')
                item_dict = redis_conn.hgetall('carts_%s' % user.id)
                cart_selected = redis_conn.smembers('selected_%s' % user.id)
                carts = {}
                for sku_id in cart_selected:
                    carts[int(sku_id)] = int(item_dict[sku_id])
                # 获取选中的商品id
                sku_ids = carts.keys()

                # 遍历购物车中被勾选的商品信息
                for sku_id in sku_ids:
                    # TODO1:增加一个死循环
                    while True:
                        # 查询 SKU 信息
                        sku = SKU.objects.get(id=sku_id)

                        # TODO2:读取原始库存
                        origin_stock = sku.stock
                        origin_sales = sku.sales

                        # 判断 SKU 库存
                        sku_count = carts[sku.id]

                        # if sku_count > sku.stock:
                        # TODO3:增加代码
                        if sku_count > origin_stock:
                            # 事务回滚
                            transaction.savepoint_rollback(save_id)
                            return http.JsonResponse({
                                'code': RETCODE.STOCKERR,
                                'errmsg': '库存不足'
                            })

                        # 模拟延迟
                        # import time
                        # time.sleep(5)

                        # SKU减少库存，增加销量
                        # sku.stock -= sku_count
                        # sku.sales += sku_count
                        # sku.save()

                        # TODO4:乐观锁更新库存和销量
                        # 计算差值
                        new_stock = origin_stock - sku_count
                        new_sales = origin_sales + sku_count
                        result = SKU.objects.filter(
                            id=sku_id,
                            stock=origin_stock
                        ).update(stock=new_stock, sales=new_sales)
                        # 如果下单失败，但是库存足够时
                        # 继续下单，直到下单成功或者库存不足为止
                        if result == 0:
                            continue

                        # 修改SPU销量
                        sku.goods.sales += sku_count
                        sku.goods.save()

                        # 保存订单商品信息 OrderGoods(多)
                        OrderGoods.objects.create(
                            order=order,
                            sku=sku,
                            count=sku_count,
                            price=sku.price,
                        )

                        # 保存商品订单中的总价和总数量
                        order.total_count += sku_count
                        order.total_amount += (sku_count * sku.price)

                        # TODO5:增加的代码
                        # 下单成功或者失败就跳出循环
                        break

                # 添加邮费和保存订单信息
                order.total_amount += order.freight
                order.save()

            except Exception as e:
                logger.error(e)
                transaction.savepoint_rollback(save_id)
                return http.JsonResponse({
                    'code': RETCODE.DBERR,
                    'errmsg': '下单失败'
                })

        # 提交订单成功，显式的提交一次事务
        transaction.savepoint_commit(save_id)

        # 清除购物车中已结算的商品
        pl = redis_conn.pipeline()
        pl.hdel('carts_%s' % user.id, *cart_selected)
        pl.srem('selected_%s' % user.id, *cart_selected)
        # 执行管道
        pl.execute()

        # 响应提交订单结果
        return http.JsonResponse({
            'code': RETCODE.OK,
            'errmsg': '下单成功',
            'order_id': order.order_id
        })


class OrderSettlementView(LoginRequiredMixin, View):
    """结算订单"""

    def get(self, request):
        """提供订单结算页面"""
        # 获取登录用户
        user = request.user
        # 查询地址信息
        try:
            addresses = Address.objects.filter(user=request.user,
                                               is_deleted=False)
        except Address.DoesNotExist:
            # 如果地址为空，渲染模板时会判断，并跳转到地址编辑页面
            address = None

        # 从redis购物车中查询出被勾选的商品信息
        redis_conn = get_redis_connection('carts')
        item_dict = redis_conn.hgetall('carts_%s' % user.id)
        cart_selected = redis_conn.smembers('selected_%s' % user.id)

        cart = {}
        for sku_id in cart_selected:
            cart[int(sku_id)] = int(item_dict[sku_id])

        # 准备初始值
        total_count = 0
        total_amount = Decimal(0.00)
        # 查询商品信息
        skus = SKU.objects.filter(id__in=cart.keys())
        for sku in skus:
            sku.count = cart[sku.id]
            sku.amount = sku.count * sku.price
            # 计算总数量和总金额
            total_count += sku.count
            total_amount += sku.amount

        # 补充运费
        freight = Decimal('10.00')

        # 渲染界面
        context = {
            'addresses': addresses,
            'skus': skus,
            'total_count': total_count,
            'total_amount': total_amount,
            'freight': freight,
            'payment_amount': total_amount + freight
        }

        return render(request, 'place_order.html', context=context)
