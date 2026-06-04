from requests.exceptions import Timeout, RequestException, ConnectionError
from typing import Dict, List, Any
from configs.basicconfig import PROD
from configs.logmanage import log_error
import requests
import socket
import json


"""
涉及Agent采集器异常处理的工具箱
"""

# 常量
CHARSET_UTF8 = "utf-8"
CHARSET_GBK = "gbk"

# SNMP 相关常量
DEFAULT_SNMP_COMMUNITY = "ZHNM"




# ====================== 1. 定义自定义异常 ======================
class WLDeviceConnectError(Exception):
	"""自定义异常：设备连接失败"""
	def __init__(self, devicename, reason):
		self.devicename = devicename  # 设备IP
		self.reason = reason  # 连接失败原因
		super(WLDeviceConnectError, self).__init__("{}连接失败({})".format(devicename, reason))



# 处理解析Agent回显结果，及时处理抛出异常
def DealAgentRespTextWithException(devicename:str,resp_dict:dict):
	result = resp_dict["result"]
	# 提取连接失败相关信息
	loginfo = result.get("loginfo", "")
	errorinfo = result.get("errorinfo", "")
	# status = result.get("status", 1)  # 只要Agent有返回就是0
	# 判断是否连接失败
	if("connecting Failed" in loginfo or "connection_failed" in errorinfo):
		fail_reason = ":" + errorinfo
		# 抛出自定义连接异常
		raise WLDeviceConnectError(devicename,fail_reason)
	else:
		return resp_dict["result"]["message"]["1.1"]["lastcmdreturn"]



# 处理解析Agent回显结果，及时处理抛出异常
def Deal_AgentResp_WithException(devicename:str,resp:requests.Response) -> str:
	"""
	处理Agent响应结果，捕获JSON解析异常和连接异常，统一抛出WLDeviceConnectError
	:param devicename: 设备名称
	:param resp: Agent响应对象（需包含text属性）
	:return: 解析后的Agent回显结果（lastcmdreturn）
	:raise WLDeviceConnectError: JSON解析失败/设备连接失败时抛出，含详细失败原因
	"""
	# 第一步：解析resp.text为字典，捕获JSON解析异常
	try:
		resp_dict = json.loads(resp.text)
	except ValueError as e:
		# 补充JSON解析失败的详细信息：错误原因+原始文本片段
		raw_text = resp.text if resp.text else "空文本"  # 只取前100字符便于排查
		fail_reason = "Agent未响应(请确认是否被G01拦截)"
		log_error("{}解析Agent响应JSON失败:{}".format(devicename,str(e)))
		raise WLDeviceConnectError(devicename, fail_reason)
	# 第二步：解析成功后，处理连接失败逻辑
	result = resp_dict["result"]
	loginfo = result.get("loginfo", "")
	errorinfo = result.get("errorinfo", "")
	# 判断是否连接失败
	if "Algorithm negotiation fail" in loginfo and "connection_failed" in errorinfo:
		fail_reason = "SSH算法协商失败：需补充加密算法aes256_ctr/aes128_ctr/HMAC sha2_256"
		raise WLDeviceConnectError(devicename, fail_reason)
	elif "connecting Failed" in loginfo or "connection_failed" in errorinfo:
		fail_reason = ":" + errorinfo
		raise WLDeviceConnectError(devicename, fail_reason)
	else:
		return resp_dict["result"]["message"]["1.1"]["lastcmdreturn"]


def Deal_SNMP_Resp_WithException(ip:str,resp:requests.Response) -> dict:
	"""
	处理SNMP响应结果，捕获JSON解析异常和连接异常，统一抛出WLDeviceConnectError
	:param ip: 设备IP地址
	:param resp: SNMP响应对象（需包含text属性）
	:return: 解析后的SNMP响应数据
	:raise WLDeviceConnectError: JSON解析失败/设备连接失败时抛出，含详细失败原因
	"""
	# 第一步：解析resp.text为字典，捕获JSON解析异常
	try:
		resp_dict = json.loads(resp.text)
	except ValueError as e:
		# 补充JSON解析失败的详细信息：错误原因+原始文本片段
		raw_text = resp.text if resp.text else "空文本"  # 只取前100字符便于排查
		fail_reason = "SNMP Agent未响应(请确认是否被G01拦截)"
		log_error("{}解析SNMP响应JSON失败:{}".format(ip,str(e)))
		raise WLDeviceConnectError(ip, fail_reason)
	# 第二步：解析成功后，处理响应结果
	if "data" not in resp_dict:
		fail_reason = "SNMP响应格式错误：缺少data字段"
		raise WLDeviceConnectError(ip, fail_reason)
	
	return resp_dict




# 封装发送Agent的Post请求意外情况处理
def Post_With_Timeout(agent_url:str, headers:dict, agent_data:dict):
	"""
	带超时控制的POST请求（适配stream=True）
	"""
	CONNECT_TIMEOUT = 10  # 连接超时：10秒
	READ_TIMEOUT = 200    # 读取超时：200秒（适配stream=True）
	error_prefix = "请求{}失败".format(agent_data["1.1"]["RESNAME"])
	try:
		# 发送POST请求，添加timeout
		resp = requests.post(url=agent_url,headers=headers,data=json.dumps(agent_data),stream=True,timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
		# 给流式响应添加socket层读取超时
		if hasattr(resp, 'raw') and resp.raw is not None:
			# 逐层获取socket对象
			fp = getattr(resp.raw, '_fp', None)
			if fp is not None:
				fp_sock = getattr(fp, 'fp', None)
				if fp_sock is not None:
					sock = getattr(fp_sock, '_sock', None)
					if sock is not None:
						sock.settimeout(READ_TIMEOUT)
		return resp
	except ConnectionError as e:
		# 判断是否是连接重置异常
		if("Connection reset by peer" in str(e)):
			raise WLDeviceConnectError(devicename=agent_data["1.1"]["RESNAME"],reason=":TCP连接被分行端重置，详情：Connection reset by peer")
		else:
			raise WLDeviceConnectError(devicename=agent_data["1.1"]["RESNAME"],reason=":连接异常，详情：{}".format(str(e)))
	except Timeout as e:
		raise WLDeviceConnectError(devicename=agent_data["1.1"]["RESNAME"],reason=":连接超时(连接{}秒/读取{}秒)".format(CONNECT_TIMEOUT, READ_TIMEOUT))
	except RequestException as e:
		raise RequestException("{}：请求异常，详情：{}".format(error_prefix, str(e)))
	except socket.timeout as e:			# 单独捕获流式读取的socket超时
		raise WLDeviceConnectError(devicename=agent_data["1.1"]["RESNAME"],reason=":读取响应体超时({}秒)".format(READ_TIMEOUT))
		# raise Timeout("{}：读取响应体超时（{}秒），详情：{}".format(error_prefix, READ_TIMEOUT, str(e)))
	except Exception as e:				# 兜底捕获未预期异常
		raise Exception("{}：未知错误，详情：{}".format(error_prefix, str(e)))


def SNMP_Post_With_Timeout(snmp_url:str, headers:dict, snmp_data:dict):
	"""
	带超时控制的SNMP POST请求
	"""
	CONNECT_TIMEOUT = 10  # 连接超时：10秒
	READ_TIMEOUT = 30     # 读取超时：30秒（SNMP请求通常较快）
	ip = snmp_data.get("ip", "unknown")
	error_prefix = "SNMP请求{}失败".format(ip)
	try:
		# 发送POST请求，添加timeout
		resp = requests.post(url=snmp_url,headers=headers,data=json.dumps(snmp_data),timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))

		return resp
	except ConnectionError as e:
		# 判断是否是连接重置异常
		if("Connection reset by peer" in str(e)):
			raise WLDeviceConnectError(devicename=ip,reason=":TCP连接被重置，详情：Connection reset by peer")
		else:
			raise WLDeviceConnectError(devicename=ip,reason=":连接异常，详情：{}".format(str(e)))
	except Timeout as e:
		raise WLDeviceConnectError(devicename=ip,reason=":连接超时(连接{}秒/读取{}秒)".format(CONNECT_TIMEOUT, READ_TIMEOUT))
	except RequestException as e:
		raise RequestException("{}：请求异常，详情：{}".format(error_prefix, str(e)))
	except Exception as e:                # 兜底捕获未预期异常
		raise Exception("{}：未知错误，详情：{}".format(error_prefix, str(e)))




# 基类：仅封装通用常量和工具方法，新增字符集默认配置
# class SSHDeviceAgentBase:
class SSHDeviceAgentBase:
	"""网络设备Agent SSH请求基类"""
	def __init__(self, device: Dict, commandlist: List, waitlist:List, username: str, password: str, url: str, charset_type: str = CHARSET_UTF8):
		# 通用参数初始化
		self.device = device
		self.command = commandlist
		self.cmdwait = waitlist
		self.username = username
		self.password = password
		self.url = url
		# 通用请求头（所有厂商共用）
		self.common_headers = {"Content-Type": "application/json;charset=utf-8","Connection": "close"}
		# 字符集默认配置_不填写默认utf-8
		self.charset_name = charset_type
		# 通用请求数据模板（引入字符集配置）
		self.common_request_template = {
			"1.1": {
				"Excuttype": "runcommandonnewdevice",
				"clearbuffer": "true",
				"setcheckArp": "FALSE",
				"RESNAME": self.device["name"],
				"IP": self.device["manageaddress"],
				"username": self.username,
				"password": self.password,
				"cmd": [],
				"cmdWait": [],
				"moreword": ["1qaz2wsx"],
				"chekCommand": "false",
				"charsetName": self.charset_name  # 关联字符集配置
			}
		}

	def get_agent_url(self) -> str:
		"""通用URL构造方法（所有厂商默认逻辑）"""
		AGENT_API_PATH = "/AgentServiceWL/Rest/handMessageListWS"
		TEST_SSH_AGENT_URL = "http://10.229.72.54:9023{}".format(AGENT_API_PATH)
		return "{}{}".format(self.url,AGENT_API_PATH) if PROD else TEST_SSH_AGENT_URL




class MypowerAgent(SSHDeviceAgentBase):
	"""迈普设备Agent请求类[完成]"""
	def get_agent_resp(self) -> str:
		"""迈普设备完整请求逻辑"""
		# 1. 构造URL
		agent_url = self.get_agent_url()
		# 2. 构造请求数据
		mypower_data = self.gen_mypower_data()
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=mypower_data)
		resp.encoding = CHARSET_UTF8	# 必须指定编码，否则多线程调用requests自动检测编码，大量耗时
		device_config = Deal_AgentResp_WithException(devicename=self.device["name"],resp=resp)
		return device_config

	def get_enable_agent_resp(self, enable_pass) -> str:
		"""迈普设备完整请求逻辑"""
		# 1. 构造URL
		agent_url = self.get_agent_url()
		# 2. 构造请求数据
		mypower_data = self.gen_mypower_data()
		mypower_data["1.1"]["addEnablepassword"] = enable_pass
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=mypower_data)
		resp.encoding = CHARSET_UTF8	# 必须指定编码，否则多线程调用requests自动检测编码，大量耗时
		device_config = Deal_AgentResp_WithException(devicename=self.device["name"],resp=resp)
		return device_config		

	def gen_mypower_data(self) -> Dict:
		MYPOWER_PREFIX = ["\n", "more off"] 				# 迈普专属前置指令常量
		MYPOWER_CMDWAIT = ["1000", "1000"]
		# 构造请求数据
		mypower_data = self.common_request_template.copy()
		device_name = self.device["name"]
		mypower_data["1.1"]["singlemoreword"] = "{}\S*#|\S*{}#".format(device_name[:2],device_name[-2:]) # 修改singlemoreword规则
		mypower_data["1.1"]["charsetName"] = CHARSET_UTF8 		# 修改迈普字符集配置_CHARSET_UTF8
		mypower_data["1.1"]["cmd"].extend(MYPOWER_PREFIX) 		# 迈普cmd拼接（前置指令+业务指令）
		mypower_data["1.1"]["cmd"].extend(self.command)
		mypower_data["1.1"]["cmd"].append("\n")
		mypower_data["1.1"]["cmdWait"].extend(MYPOWER_CMDWAIT)
		mypower_data["1.1"]["cmdWait"].extend(self.cmdwait)			# 迈普cmd等待时间
		return mypower_data




class UNISAgent(SSHDeviceAgentBase):
	"""紫光设备Agent请求类"""
	def get_agent_resp(self) -> str:
		"""紫光设备完整请求逻辑"""
		UNIS_PREFIX = ["\n", "screen-length disable"]  # 紫光专属前置指令
		UNIS_CMDWAIT = ["1000", "3000"]
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据（完整可见的差异化配置）
		unis_data = self.common_request_template.copy()
		device_name = self.device["name"]
		unis_data["1.1"]["singlemoreword"] = "\S*<{}\S*>|\S*<\S*{}>".format(device_name[:2], device_name[-2:])
		unis_data["1.1"]["charsetName"] = CHARSET_UTF8	# 紫光专属：配置编码utf8
		unis_data["1.1"]["cmd"].extend(UNIS_PREFIX) 	# 紫光专属：cmd拼接（前置指令+业务指令）
		unis_data["1.1"]["cmd"].extend(self.command)
		unis_data["1.1"]["cmd"].append("\n")
		unis_data["1.1"]["cmdWait"].extend(UNIS_CMDWAIT)
		unis_data["1.1"]["cmdWait"].extend(self.cmdwait)		# 紫光cmd等待时间
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=unis_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=device_name,resp=resp)
		return device_config




class HuaweiAgent(SSHDeviceAgentBase):
	"""华为设备Agent请求类"""
	def get_agent_resp(self) -> str:
		HUAWEI_PREFIX = ["\n", "screen-len 0 temp"]
		HUAWEI_CMDWAIT = ["1000", "1000"]
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据
		huawei_data = self.common_request_template.copy()
		device_name = self.device["name"]
		huawei_data["1.1"]["singlemoreword"] = "\S*<{}\S*>|\S*<\S*{}>".format(device_name[:2], device_name[-2:])
		huawei_data["1.1"]["charsetName"] = CHARSET_GBK
		huawei_data["1.1"]["cmd"].extend(HUAWEI_PREFIX) 	# 华为cmd拼接（前置指令+业务指令）
		huawei_data["1.1"]["cmd"].extend(self.command)
		huawei_data["1.1"]["cmd"].append("\n")
		huawei_data["1.1"]["cmdWait"].extend(HUAWEI_CMDWAIT)
		huawei_data["1.1"]["cmdWait"].extend(self.cmdwait)
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=huawei_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=device_name,resp=resp)
		return device_config




class H3CAgent(SSHDeviceAgentBase):
	"""华三设备Agent请求类"""
	def get_agent_resp(self) -> str:
		H3C_PREFIX = ["\n", "screen-length disable"]
		H3C_CMDWAIT = ["1000", "3000"]
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据
		h3c_data = self.common_request_template.copy()
		device_name = self.device["name"]
		h3c_data["1.1"]["singlemoreword"] = "\S*<{}\S*>|\S*<\S*{}>".format(device_name[:2], device_name[-2:])
		h3c_data["1.1"]["charsetName"] = CHARSET_GBK
		h3c_data["1.1"]["cmd"].extend(H3C_PREFIX) 				# 华三cmd拼接（前置指令+业务指令）
		h3c_data["1.1"]["cmd"].extend(self.command)
		h3c_data["1.1"]["cmd"].append("\n")
		h3c_data["1.1"]["cmdWait"].extend(H3C_CMDWAIT)
		h3c_data["1.1"]["cmdWait"].extend(self.cmdwait)
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=h3c_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=device_name,resp=resp)
		return device_config




class TopsecAgent(SSHDeviceAgentBase):
	"""天融信设备Agent请求类"""
	def get_agent_resp(self) -> str:
		TOPSEC_PREFIX = ["\n"]
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据
		topsec_data = self.common_request_template.copy()
		device_name = self.device["name"]
		topsec_data["1.1"]["singlemoreword"] = "{}\S*#".format(device_name[:2])
		topsec_data["1.1"]["charsetName"] = CHARSET_UTF8
		topsec_data["1.1"]["cmd"].extend(TOPSEC_PREFIX) 	# 天融信cmd拼接（前置指令+业务指令）
		topsec_data["1.1"]["cmd"].extend(self.command)
		topsec_data["1.1"]["cmd"].append("\n")
		topsec_data["1.1"]["cmdWait"].append("1000")
		topsec_data["1.1"]["cmdWait"].extend(self.cmdwait)
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=topsec_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=device_name,resp=resp)
		return device_config





# class HillStoneAgent(SSHDeviceAgentBase):
# 	"""山石设备Agent请求类"""
# 	def get_agent_resp(self) -> str:
# 		HILLSTONE_PREFIX = ["\n","terminal length 0","ter len 0","terminal width 512"]
# 		# 1. 构造URL（通用方法）
# 		agent_url = self.get_agent_url()
# 		# 2. 构造请求数据
# 		hillstone_data = self.common_request_template.copy()
# 		device_name = self.device["name"]
# 		hillstone_data["1.1"]["singlemoreword"] = "{}\S*#|\S*{}#".format(device_name[:2],device_name[-2:])
# 		hillstone_data["1.1"]["charsetName"] = CHARSET_UTF8
# 		hillstone_data["1.1"]["cmd"].extend(HILLSTONE_PREFIX) 	# 山石cmd拼接（前置指令+业务指令）
# 		hillstone_data["1.1"]["cmd"].extend(self.command)
# 		hillstone_data["1.1"]["cmd"].append("\n")
# 		hillstone_data["1.1"]["cmdWait"].extend(["1000", "1000", "1000", "1000"])
# 		hillstone_data["1.1"]["cmdWait"].extend(self.cmdwait)
# 		# 3. 获取配置
# 		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=hillstone_data)
# 		resp.encoding = CHARSET_UTF8
# 		device_config = Deal_AgentResp_WithException(devicename=device_name,resp=resp)
# 		return device_config



class HillStoneAgent(SSHDeviceAgentBase):
	"""山石设备Agent请求类"""
	HILLSTONE_PREFIX = ["\n", "terminal length 0", "ter len 0", "terminal width 512"]
	DEFAULT_PREFIX_WAIT = ["1000", "1000", "1000", "1000"]

	def _build_hillstone_request_data(self) -> Dict:
		"""
		私有方法：构造请求数据
		返回：req_data
		"""
		device_name = self.device["name"]
		# 复制模板
		req_data = self.common_request_template.copy()
		req_section = req_data["1.1"]
		# 基础配置
		req_section["singlemoreword"] = "{}\S*#|\S*{}#".format(device_name[:2], device_name[-2:])
		req_section["charsetName"] = CHARSET_UTF8
		# 拼接命令
		req_section["cmd"].extend(self.HILLSTONE_PREFIX)
		req_section["cmd"].extend(self.command)
		req_section["cmd"].append("\n")
		# 拼接等待时间
		req_section["cmdWait"].extend(self.DEFAULT_PREFIX_WAIT)
		req_section["cmdWait"].extend(self.cmdwait)
		return req_data

	def get_agent_resp(self) -> str:
		"""标准等待时间获取设备响应"""
		# 1. 构造统一请求数据
		agent_url = self.get_agent_url()
		hillstone_data = self._build_hillstone_request_data()
		# 2. 标准请求：Post_With_Timeout
		resp = Post_With_Timeout(agent_url=agent_url, headers=self.common_headers, agent_data=hillstone_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=self.device["name"], resp=resp)
		return device_config

	def get_longwait_agent_resp(self) -> str:
		"""
		长等待时间获取设备响应
		不设任何超时异常处理，仅限定极特殊设备_ctld
		"""
		agent_url = self.get_agent_url()
		hillstone_data = self._build_hillstone_request_data()
		resp = requests.post(url=agent_url, headers=self.common_headers, data=json.dumps(hillstone_data),stream=False)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=self.device["name"], resp=resp)
		return device_config




class RuijieAgent(SSHDeviceAgentBase):
	"""锐捷设备Agent请求类"""
	def get_agent_resp(self) -> str:
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据		
		ruijie_data = self.gen_ruijie_data()
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=ruijie_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=self.device["name"],resp=resp)
		return device_config

	def get_enable_agent_resp(self, enable_pass) -> str:
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据		
		ruijie_data = self.gen_ruijie_data()
		ruijie_data["1.1"]["addEnablepassword"] = enable_pass
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=ruijie_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=self.device["name"],resp=resp)
		return device_config		

	def gen_ruijie_data(self) -> Dict:
		RUIJIE_PREFIX = ["\n", "terminal length 0"]
		RUIJIE_CMDWAIT = ["1000", "3000"]
		ruijie_data = self.common_request_template.copy()
		device_name = self.device["name"]
		ruijie_data["1.1"]["singlemoreword"] = "{}\S*#|\S*{}#".format(device_name[:2],device_name[-2:])
		ruijie_data["1.1"]["charsetName"] = CHARSET_UTF8
		ruijie_data["1.1"]["cmd"].extend(RUIJIE_PREFIX) 	# 锐捷cmd拼接（前置指令+业务指令）
		ruijie_data["1.1"]["cmd"].extend(self.command)
		ruijie_data["1.1"]["cmd"].append("\n")
		ruijie_data["1.1"]["cmdWait"].extend(RUIJIE_CMDWAIT)
		ruijie_data["1.1"]["cmdWait"].extend(self.cmdwait)
		return ruijie_data




class NeusoftAgent(SSHDeviceAgentBase):
	"""东软设备Agent请求类[完成]"""
	def get_agent_resp(self) -> str:
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据
		if self.device.get("sysoid") == "1.3.6.1.4.1.8596.1":
			neusoft_data = self.gen_fw5200_data()
		# elif(fwtype == 2):
		# 	neusoft_data["1.1"]["deviceType"] = "FW5800-XH" ??
		else:
			neusoft_data = self.common_request_template.copy()
			neusoft_data["1.1"]["singlemoreword"] = "----\\s+(More)\\s+----|.+>"
			neusoft_data["1.1"]["moreword"] = ["----\\s+(More)\\s+----"]
			neusoft_data["1.1"]["delword"] = ["----\\s+(More)\\s+----", "\\[42D"]
			neusoft_data["1.1"].pop("cmdWait")
			neusoft_data["1.1"].pop("charsetName")
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=neusoft_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=self.device["name"],resp=resp)
		return device_config	

	def gen_fw5200_data(self) -> dict:
		"""仅针对FW5200型号生成结构体"""
		# 2. 构造请求数据
		neusoft_data = self.common_request_template.copy()
		neusoft_data["1.1"]["deviceType"] = "FW5200"
		neusoft_data["1.1"]["chekCommand"] = "false"
		neusoft_data["1.1"]["setmoreEnhance"] = "true" 
		neusoft_data["1.1"]["cmd"].extend(self.command)
		neusoft_data["1.1"].pop("cmdWait")
		neusoft_data["1.1"].pop("moreword")
		neusoft_data["1.1"].pop("charsetName")
		# neusoft_data["1.1"].pop("clearbuffer")
		# neusoft_data["1.1"].pop("setcheckArp")
		return neusoft_data	




class DptechAgent(SSHDeviceAgentBase):
	"""迪普设备Agent请求类"""
	def get_agent_resp(self) -> str:
		DPTECH_PREFIX = ["\n", "terminal line 0"]
		DPTECH_CMDWAIT = ["1000", "1000"]
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据
		dptech_data = self.common_request_template.copy()
		device_name = self.device["name"]
		dptech_data["1.1"]["singlemoreword"] = "<{}\S*>".format(device_name[0:2])
		dptech_data["1.1"]["charsetName"] = CHARSET_UTF8
		dptech_data["1.1"]["cmd"].extend(DPTECH_PREFIX)
		dptech_data["1.1"]["cmd"].extend(self.command)
		dptech_data["1.1"]["cmd"].append("\n")
		dptech_data["1.1"]["cmdWait"].extend(DPTECH_CMDWAIT)
		dptech_data["1.1"]["cmdWait"].extend(self.cmdwait)
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=dptech_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=device_name,resp=resp)
		return device_config





class NetScoutAgent(SSHDeviceAgentBase):
	"""网寻设备Agent请求类"""
	def get_agent_resp(self) -> str:
		NETSCOUT_PREFIX = ["\n", "show state"]
		NETSCOUT_CMDWAIT = ["1000", "3000"]
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据
		netscout_data = self.common_request_template.copy()
		device_name = self.device["name"]
		netscout_data["1.1"]["singlemoreword"] = "{}\S*#|\S*{}#|>".format(device_name[:2],device_name[-2:])
		netscout_data["1.1"]["charsetName"] = CHARSET_UTF8
		netscout_data["1.1"]["cmd"].extend(NETSCOUT_PREFIX)
		netscout_data["1.1"]["cmd"].extend(self.command)
		netscout_data["1.1"]["cmd"].append("logout")
		netscout_data["1.1"]["cmdWait"].extend(NETSCOUT_CMDWAIT)
		netscout_data["1.1"]["cmdWait"].extend(self.cmdwait)
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=netscout_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=device_name,resp=resp)
		return device_config




	
class CiscoAgent(SSHDeviceAgentBase):
	"""思科设备Agent请求类"""
	def get_agent_resp(self) -> str:
		CISCO_PREFIX = ["\n", "terminal length 0"]
		CISCO_CMDWAIT = ["1000", "3000"]
		# 1. 构造URL（通用方法）
		agent_url = self.get_agent_url()
		# 2. 构造请求数据
		cisco_data = self.common_request_template.copy()
		device_name = self.device["name"]
		cisco_data["1.1"]["singlemoreword"] = "{}\S*#|\S*{}#|\S*>".format(device_name[:2],device_name[-2:])
		cisco_data["1.1"]["charsetName"] = CHARSET_UTF8
		cisco_data["1.1"]["cmd"].extend(CISCO_PREFIX)
		cisco_data["1.1"]["cmd"].extend(self.command)
		cisco_data["1.1"]["cmd"].append("\n")
		cisco_data["1.1"]["cmdWait"].extend(CISCO_CMDWAIT)
		cisco_data["1.1"]["cmdWait"].extend(self.cmdwait)
		# 3. 获取配置
		resp = Post_With_Timeout(agent_url=agent_url,headers=self.common_headers,agent_data=cisco_data)
		resp.encoding = CHARSET_UTF8
		device_config = Deal_AgentResp_WithException(devicename=device_name,resp=resp)
		return device_config



class SNMPDeviceAgentBase:
	"""SNMP设备Agent请求基类"""
	def __init__(self, agent_url:str, community:str = DEFAULT_SNMP_COMMUNITY):
		"""
		初始化SNMP设备Agent
		:param ip: 设备IP地址
		:param community: SNMP社区字符串
		"""
		self.url = agent_url
		self.community = community
		self.headers = {"Content-Type": "application/json;charset=utf-8"}
	
	def get_snmp_url(self) -> str:
		"""
		根据区域标签获取SNMP URL
		:param tag: 区域标签（BJ/NM/FH）
		:return: SNMP URL
		"""
		SNMP_API_PATH = "/AgentServiceWL/Rest/snmpWalk"
		TEST_SNMP_AGENT_URL = "http://10.229.72.54:9023{}".format(SNMP_API_PATH)		
		return "{}{}".format(self.url,SNMP_API_PATH) if PROD else TEST_SNMP_AGENT_URL
	
	def walk_oid_info(self, ip:str, oid:str) -> Any:
		"""
		执行SNMP walk操作获取OID信息
		:param oid: SNMP OID
		:param tag: 区域标签（BJ/NM/FH）
		:return: 采集到的数据或错误信息
		"""
		# 获取SNMP URL
		snmp_url = self.get_snmp_url()
		
		# 构造请求数据
		post_data = {"ip": ip,"community": self.community,"oid": oid}
		
		try:
			# 发送SNMP请求
			response = SNMP_Post_With_Timeout(snmp_url, self.headers, post_data)
			
			# 处理响应
			response_data = Deal_SNMP_Resp_WithException(ip, response)
			
			# 检查响应数据
			if not response_data['data']:
				return response_data.get('msg', 'No data')
			else:
				return response_data['data']
		except WLDeviceConnectError as e:
			# 捕获设备连接错误
			log_error("SNMP请求{}失败: {}".format(ip, str(e)))
			return "Connection error: {}".format(str(e))
		except Exception as e:
			# 捕获其他异常
			log_error("SNMP请求{}失败: {}".format(ip, str(e)))
			return "Error: {}".format(str(e))



# 便捷函数：直接执行SNMP walk操作
def walk_oid_info_interface(ip: str, oid: str, snmp_url: str, community: str = DEFAULT_SNMP_COMMUNITY) -> Any:
	"""
	执行SNMP walk操作获取OID信息
	:param ip: 设备IP地址
	:param oid: SNMP OID
	:param tag: 区域标签（BJ/NM/FH）
	:param community: SNMP社区字符串
	:return: 采集到的数据或错误信息
	"""
	snmp_agent = SNMPDeviceAgentBase(agent_url=snmp_url, community=community)
	return snmp_agent.walk_oid_info(ip=ip, oid=oid)