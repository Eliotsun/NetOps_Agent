from concurrent.futures import ThreadPoolExecutor, as_completed
from basic_util.agentutil import (
	HuaweiAgent, H3CAgent, HillStoneAgent, TopsecAgent,
	DptechAgent, RuijieAgent, MypowerAgent, NeusoftAgent,
	CiscoAgent, UNISAgent, NetScoutAgent, WLDeviceConnectError,
)
from configs.logmanage import log_run, log_error
import time

# ============================================================
# sysoid 前缀 -> Agent 类 映射表
# ============================================================
AGENT_MAP = {
	"1.3.6.1.4.1.2011":  HuaweiAgent,
	"1.3.6.1.4.1.25506": H3CAgent,
	"1.3.6.1.4.1.5651":  MypowerAgent,
	"1.3.6.1.4.1.4881":  RuijieAgent,
	"1.3.6.1.4.1.28557": HillStoneAgent,
	"1.3.6.1.4.1.14331": TopsecAgent,
	"1.3.6.1.4.1.31648": DptechAgent,
	"1.3.6.1.4.1.8596":  NeusoftAgent,
	"1.3.6.1.4.1.9":     CiscoAgent,
	"1.3.6.1.4.1.10519": UNISAgent,
	"1.3.6.1.4.1.26381": NetScoutAgent,
}


def _detect_agent_class(sysoid:str):
	"""根据 sysoid 前缀匹配合适的 Agent 类"""
	if not sysoid:
		return None
	for prefix, agent_cls in AGENT_MAP.items():
		if sysoid.startswith(prefix):
			return agent_cls
	return None


class DeviceResult:
	"""单台设备的采集+解析结果"""
	def __init__(self, device_name, status, data=None, error="", elapsed=0.0):
		self.device_name = device_name
		self.status = status       # "success" / "failed"
		self.data = data
		self.error = error
		self.elapsed = elapsed


class CollectionReport:
	"""一次采集任务的完整报告"""
	def __init__(self, description="", total=0, success_count=0, fail_count=0,
				 details=None, total_elapsed=0.0):
		self.description = description
		self.total = total
		self.success_count = success_count
		self.fail_count = fail_count
		self.details = details if details is not None else []
		self.total_elapsed = total_elapsed


def _collect_single_device_by_vendor(device, vendor_conf, username, password, url):
	"""按厂商配置采集单台设备，自动识别品牌"""
	device_name = device.get("name", "unknown")
	sysoid = device.get("sysoid", "")

	agent_class = _detect_agent_class(sysoid)
	if agent_class is None:
		return DeviceResult(
			device_name=device_name, status="failed",
			error="未知品牌 sysoid={}".format(sysoid),
		)

	# 取该品牌的采集配置，若未定义则跳过
	brand_conf = None
	for prefix, conf in vendor_conf.items():
		if sysoid.startswith(prefix):
			brand_conf = conf
			break

	if brand_conf is None:
		return DeviceResult(
			device_name=device_name, status="failed",
			error="未配置采集指令 brand={}".format(agent_class.__name__),
		)

	commands = brand_conf.get("commands", [])
	cmdwaits = brand_conf.get("cmdwaits", [])
	parser_func = brand_conf.get("parser_func")

	start = time.time()
	try:
		agent = agent_class(
			device=device,
			commandlist=commands,
			waitlist=cmdwaits,
			username=username,
			password=password,
			url=url,
		)
		raw_text = agent.get_agent_resp()
		parsed = parser_func(raw_text) if parser_func else raw_text

		elapsed = time.time() - start
		# log_run("[{}] 采集成功, 耗时{:.1f}s".format(device_name, elapsed))
		return DeviceResult(
			device_name=device_name, status="success",
			data=parsed, elapsed=elapsed,
		)
	except WLDeviceConnectError as e:
		elapsed = time.time() - start
		log_error("{} 连接失败: {}".format(device_name, str(e)))
		return DeviceResult(
			device_name=device_name, status="failed",
			error=str(e), elapsed=elapsed,
		)
	except Exception as e:
		elapsed = time.time() - start
		log_error("{} 采集异常: {}".format(device_name, str(e)), exc_info=True)
		return DeviceResult(
			device_name=device_name, status="failed",
			error="{}: {}".format(type(e).__name__, str(e)),
			elapsed=elapsed,
		)


def run_collection_by_vendor(devices, vendor_conf,
							 username="", password="", url="",
							 max_workers=10, description="",
							 on_complete=None):
	"""
	多品牌混合设备并发采集（按 sysoid 自动识别品牌）

	vendor_conf 格式:
		{
			"1.3.6.1.4.1.2011": {                          # sysoid 前缀
				"commands":    ["dis int transceiver verbose"],
				"cmdwaits":    ["10000"],
				"parser_func": HuaweiParser.parse_transceiver,  # 可选
			},
			"1.3.6.1.4.1.25506": {
				"commands":    ["display transceiver verbose"],
				"cmdwaits":    ["10000"],
				"parser_func": None,
			},
		}

	Agent 类自动从 AGENT_MAP 匹配，无需在配置中指定。
	"""
	total_start = time.time()
	log_run("网络参数采集-{} - {}台设备, 并发{}".format(description, len(devices), max_workers))

	results = []
	with ThreadPoolExecutor(max_workers=max_workers) as pool:
		future_map = {}
		for device in devices:
			future = pool.submit(
				_collect_single_device_by_vendor,
				device=device,
				vendor_conf=vendor_conf,
				username=username,
				password=password,
				url=url,
			)
			future_map[future] = device.get("name", "unknown")

		for future in as_completed(future_map):
			result = future.result()
			results.append(result)
			if on_complete:
				on_complete(result)
	total_elapsed = time.time() - total_start
	success_count = sum(1 for r in results if r.status == "success")
	fail_count = sum(1 for r in results if r.status == "failed")
	log_run("网络参数采集-{} - 完成 成功{}/{} 耗时{:.1f}s".format(
		description, success_count, len(devices), total_elapsed))

	return CollectionReport(
		description=description, total=len(devices),
		success_count=success_count, fail_count=fail_count,
		details=results, total_elapsed=total_elapsed,
	)
