import time
import functools
import logging
from typing import Any, Callable



# ------------------------------
# 1. 打印函数执行时间（最常用）
# ------------------------------
def timing_decorator(func):
	"""
	装饰器：统计函数执行时间
	Args: func: 被装饰的函数
	Returns: 装饰后的函数
	"""
	def wrapper(*args, **kwargs):
		start_time = time.time()
		result = func(*args, **kwargs)
		end_time = time.time()
		execution_time = end_time - start_time
		print("{} 执行时间: {:.6f} 秒".format(func.__name__,execution_time))
		return result
	return wrapper




# ------------------------------
# 2. 打印函数入参和返回值
# ------------------------------
def log_args(func: Callable) -> Callable:
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		print(" 调用 {}".format(func.__name__))
		print(" 参数: args={}, kwargs={}".format(args,kwargs))
		result = func(*args, **kwargs)
		print(" 返回: {}".format(result))
		return result
	return wrapper

# ------------------------------
# 3. 捕获异常（防止程序崩溃）
# ------------------------------
def catch_error(func: Callable) -> Callable:
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except Exception as e:
			print(" [{}]出错: {}: {}".format(func.__name__, type(e).__name__, str(e)))
			return None  # 出错返回 None
	return wrapper


# ------------------------------
# 4. 限制函数执行次数
# ------------------------------
def limit_run(max_count: int = 1):
	def decorator(func: Callable):
		count = 0
		@functools.wraps(func)
		def wrapper(*args, **kwargs):
			nonlocal count
			if count >= max_count:
				print(" {} 已达到最大执行次数 {}，不再执行".format(func.__name__, max_count))
				return None
			count += 1
			return func(*args, **kwargs)
		return wrapper
	return decorator



# ------------------------------
# 5. 缓存函数结果（加速重复调用）
# ------------------------------
def cache(func: Callable):
	cache_dict = {}
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		key = (args, frozenset(kwargs.items()))
		if key not in cache_dict:
			cache_dict[key] = func(*args, **kwargs)
		return cache_dict[key]
	return wrapper



# ------------------------------
# 6. 重试机制（失败自动重试）
# ------------------------------
def retry(max_retries: int = 3, delay: float = 1):
	def decorator(func: Callable):
		@functools.wraps(func)
		def wrapper(*args, **kwargs):
			for i in range(max_retries):
				try:
					return func(*args, **kwargs)
				except Exception as e:
					print(" 第 {} 次重试 {}, 错误: {}".format(i+1, func.__name__, str(e)))
					time.sleep(delay)
			print(" 重试 {} 次失败".format(max_retries))
			return None
		return wrapper
	return decorator



# ------------------------------
# 7. 单例模式装饰器（类专用）
# ------------------------------
def singleton(cls):
	instances = {}
	@functools.wraps(cls)
	def get_instance(*args, **kwargs):
		if cls not in instances:
			instances[cls] = cls(*args, **kwargs)
		return instances[cls]
	return get_instance




# ------------------------------
# 8. 强制检查参数类型
# ------------------------------
def type_check(func: Callable) -> Callable:
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		annotations = func.__annotations__
		# 检查位置参数
		for idx, (arg_name, arg_type) in enumerate(annotations.items()):
			if arg_name == "return":
				continue
			if idx < len(args) and not isinstance(args[idx], arg_type):
				raise TypeError("参数 {} 必须是 {} 类型".format(arg_name, arg_type))
		return func(*args, **kwargs)
	return wrapper