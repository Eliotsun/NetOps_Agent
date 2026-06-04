# -*- coding: utf-8 -*-
from configs.basicconfig import PATH
from configs.logmanage import log_error
import textfsm
import re
import os


PARSE_TEMPLATE_PATH = os.path.join(PATH, "Template", "parse_template")



def Parse_With_Template(template_path, raw_text):
	"""
	公共方法：使用TextFSM模板解析原始文本
	:param template_path: 模板文件完整路径
	:param raw_text: 设备原始输出文本
	:return: 解析结果列表（空列表表示解析失败/无结果）
	"""
	try:
		with open(template_path, "r", encoding="utf-8") as f:
			template = textfsm.TextFSM(f)
			return template.ParseTextToDicts(raw_text)
	except FileNotFoundError:
		log_error("模板文件不存在：{}".format(template_path))
		return []
	except Exception as e:
		log_error("解析模板失败：{}，模板路径：{}".format(str(e), template_path))
		return []


# -------------------------- 华为（Huawei）厂商解析类 --------------------------
class HuaweiParser:
	"""华为设备配置解析类（聚合所有华为相关解析方法）"""
	@staticmethod
	def parse_version(raw_text):
		parsed_dict = {"Version":""}
		if(raw_text != ""):
			template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_version.template")
			result = Parse_With_Template(template_path, raw_text)
			if(result != []):
				for k,v in result[0].items():
					if(v != ""):
						v = v.strip("()")
						parsed_dict["Version"] = v
						break
		return parsed_dict

	@staticmethod
	def parse_patch(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_patch.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_ds_static_route(raw_text):
		"""解析华为配置-静态路由"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_ds_static.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_transceiver(raw_text):
		"""
		解析 dis int transceiver verbose 回显
		TextFSM 模板处理单行字段，regex 后处理续行合并多通道值
		返回: [{interface, transceiver_type, temperature_c, bias_current_ma, rx_power_dbm, ...}]
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_transceiver.template")
		result = Parse_With_Template(template_path, raw_text)
		if not result:
			return result

		# 过滤空记录（模板首次 Record）、key 转小写、类型转换
		records = []
		for r in result:
			if not r.get("INTERFACE"):
				continue
			rec = {k.lower(): v or "" for k, v in r.items()}
			for f in ("temperature_c", "voltage_v"):
				if rec.get(f):
					rec[f] = float(rec[f])
			for f in ("bias_high_ma", "bias_low_ma", "rx_high_dbm", "rx_low_dbm", "tx_high_dbm", "tx_low_dbm"):
				if rec.get(f):
					rec[f] = float(rec[f])
			records.append(rec)

		if not records:
			return records

		# 按接口切块，从原始文本提取续行的多通道值
		blocks = re.split(r"\n\s*(?=\S+\s+transceiver information:)", raw_text.strip())

		for i, rec in enumerate(records):
			if i >= len(blocks):
				break
			blk = blocks[i]
			for key, label in (
				("bias_current_ma", r"Bias Current \(mA\)"),
				("rx_power_dbm", r"Current RX Power \(dBm\)"),
				("tx_power_dbm", r"Current TX Power \(dBm\)"),
			):
				m = re.search(
					r"{}\s*:\s*([\d.|-]+)\s*\(Lane\w+\|Lane\w+\)[ \t]*\n\s+([\d.|-]+)\s*\(Lane\w+\|Lane\w+\)"
					.format(label), blk
				)
				first = re.search(r"{}\s*:\s*([\d.|-]+)".format(label), blk)
				if first:
					vals = first.group(1).split("|")
					if m:
						vals += m.group(2).split("|")
					rec[key] = [float(v) for v in vals] if len(vals) > 1 else float(vals[0])
		return records
	
	
	@staticmethod
	def parse_config_static_route(raw_text):
		"""解析华为配置-静态路由"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_staticroute.template")
		return Parse_With_Template(template_path, raw_text)		

	@staticmethod
	def parse_config_vbdif(raw_text):
		"""解析华为配置-VBDIF-
		（基于BD的三层逻辑接口，VXLAN三成互通与网关）
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_vbdif.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_config_vpn_instance(raw_text):
		"""解析华为配置-VPN实例"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_vpn_instance.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_policy(raw_text):
		"""解析华为防火墙配置策略信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_fw.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_address_book(raw_text):
		"""解析华为防火墙配置地址薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_rangeset.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_service_set(raw_text):
		"""解析华为防火墙配置端口薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_service.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_service_group(raw_text):
		"""解析华为防火墙配置端口组信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_group.template")
		return Parse_With_Template(template_path, raw_text)			

	@staticmethod
	def parse_firewall_ipv4_route(raw_text):
		"""
		解析华为防火墙IPv4路由信息
		对应指令：display ip route
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_firewall_route_ipv4.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_ipv6_route(raw_text):
		"""
		解析华为防火墙IPv6路由信息
		对应指令：display ipv6 route
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_firewall_route_ipv6.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_policy_hitcount(raw_text):
		"""
		解析华为设备策略命中数
		对应指令：display security-policy rule all
		:return: 解析结果列表
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_hitcount.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_ipv4_route(raw_text):
		"""
		解析华为设备IPv4路由信息
		对应指令：dis ip routing-table vpn-instance <vpn_name> / 
				dis ip routing-table protocol static
		:return: 解析结果列表
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "huawei", "huawei_route_v4.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_ipv6_route(raw_text):
		"""
		解析华为设备IPv6路由信息
		对应指令：dis ipv6 routing-table vpn-instance <vpn_name>
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH,"huawei", "huawei_route_v6.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_ipv6_route_simple(raw_text):
		"""
		解析华为设备IPv6路由信息
		对应指令：dis ipv6 routing-table vpn-instance <vpn_name> simple
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH,"huawei", "huawei_route_v6_simple.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_vpn_instance_list(raw_text):
		"""
		解析华为设备vpn实例信息_目前仅过滤得到ipv4相关
		对应指令：dis ip vpn-instance
		"""
		filter_list = ['MGMT']
		pattern = re.compile(r'\s+(?!Address-family)(\S+)\s+(?:\S+:\S+|\s*)\s+(IPv4|IPv6)\s*$',re.MULTILINE)
		vpn_matches = pattern.findall(raw_text)
		ipv4_vpn_names = list({name for name, version in vpn_matches if version == 'IPv4'}) 
		ipv4_vpn_list = [vpn_name for vpn_name in ipv4_vpn_names if vpn_name not in filter_list]
		return ipv4_vpn_list




# -------------------------- H3C厂商解析类 --------------------------
class H3CParser:
	"""H3C设备配置解析类（聚合所有H3C相关解析方法）"""	
	@staticmethod
	def parse_version(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "h3c", "h3c_version.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_policy_hitcount(raw_text):
		"""
		解析H3C设备策略命中数
		对应指令：dis security-policy statistics ip
		优先使用主模板，解析失败则尝试备模板
		:return: 解析结果列表
		"""
		# 主模板解析
		main_template = os.path.join(PARSE_TEMPLATE_PATH,"h3c", "h3c_hitcount.template")
		parsed_result = Parse_With_Template(main_template, raw_text)
		# 主模板无结果则用备模板
		if not parsed_result:
			standby_template = os.path.join(PARSE_TEMPLATE_PATH,"h3c", "h3c_hitcount_standby.template")
			parsed_result = Parse_With_Template(standby_template, raw_text)
		
		# 标记H3C命中数 - Packetscount
		for parse_record in parsed_result:
			parse_record["Hitcount"] = parse_record["Packetscount"]
		return parsed_result
	
	@staticmethod
	def parse_firewall_policy(raw_text):
		"""解析H3C防火墙配置策略信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "h3c", "h3c_fw.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_address_book(raw_text):
		"""解析H3C防火墙配置地址薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "h3c", "h3c_rangeset.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_service_set(raw_text):
		"""解析H3C防火墙配置地址薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "h3c", "h3c_service.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_schedule(raw_text):
		"""解析H3C防火墙配置地址薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "h3c", "h3c_schedule.template")
		return Parse_With_Template(template_path, raw_text)						

	@staticmethod
	def parse_firewall_ipv4_route(raw_text):
		"""
		解析H3C防火墙IPv4路由信息
		对应指令：display ip route
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "h3c", "h3c_firewall_route_ipv4.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_ipv6_route(raw_text):
		"""
		解析H3C防火墙IPv6路由信息
		对应指令：display ipv6 route
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "h3c", "h3c_firewall_route_ipv6.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_ipv4_route(raw_text):
		"""
		解析H3C设备IPv4路由信息 --> 漏扫路由采集
		对应指令：dis ip routing-table vpn-instance <vpn_name>
		:return: 解析结果列表
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "h3c", "h3c_route_v4.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_ipv6_route(raw_text):
		"""
		解析H3C设备IPv6路由信息 --> 漏扫路由采集
		对应指令：dis ipv6 routing-table vpn-instance <vpn_name>
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH,"h3c", "h3c_route_v6.template")
		return Parse_With_Template(template_path, raw_text)




# -------------------------- Hillstone（山石）厂商解析类 --------------------------
class HillstoneParser:
	"""Hillstone（山石）设备配置解析类（聚合所有山石相关解析方法）"""
	@staticmethod
	def parse_version(raw_text):
		parsed_result = []
		if(raw_text != ""):
			template_path = os.path.join(PARSE_TEMPLATE_PATH, "hillstone","hillstone_version.template")
			rawresult = Parse_With_Template(template_path=template_path,raw_text=raw_text)
			if(rawresult != []):
				thisversion = {"Version":""}
				tmp = rawresult[0]['BootFile'].strip(".bin")
				tmplist = tmp.split('-')
				addflag = False
				for t in tmplist:
					if(rawresult[0]["Version"] in t):
						addflag = True
						thisversion["Version"] = t
					elif(addflag):
						thisversion["Version"] = thisversion["Version"]+"-"+t
				if(thisversion["Version"] != ""):
					parsed_result.append(thisversion)
		return parsed_result

	@staticmethod
	def parse_reduce_policy(raw_text):
		"""解析下线Hillstone防火墙配置策略信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "hillstone", "hillstone_reduce_fw.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_reduce_address_book(raw_text):
		"""解析下线Hillstone防火墙配置地址薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "hillstone", "hillstone_reduce_rangeset.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_policy(raw_text):
		"""解析下线Hillstone防火墙策略信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "hillstone", "hillstone_fw.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_address_book(raw_text):
		"""解析下线Hillstone防火墙配置地址薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "hillstone", "hillstone_rangeset.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_service_set(raw_text):
		"""解析下线Hillstone防火墙配置端口信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "hillstone", "hillstone_service.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_aggregate(raw_text):
		"""解析下线Hillstone防火墙配置aggregate信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "hillstone", "hillstone_aggregate.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_rawtext(raw_text):
		"""解析下线Hillstone防火墙配置原始文本信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "hillstone", "hillstone_raw.template")
		return Parse_With_Template(template_path, raw_text)		

	@staticmethod
	def parse_firewall_schedule(raw_text):
		"""解析下线Hillstone防火墙配置schedule信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "hillstone", "hillstone_schedule.template")
		return Parse_With_Template(template_path, raw_text)												

	@staticmethod
	def parse_firewall_ipv4_route(raw_text):
		"""
		解析Hillstone防火墙IPv4路由
		对应指令：show policy hit-count
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH,"hillstone", "hillstone_firewall_route_ipv4.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_ipv6_route(raw_text):
		"""
		解析Hillstone防火墙IPv4路由
		对应指令：show policy hit-count
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH,"hillstone", "hillstone_firewall_route_ipv6.template")
		return Parse_With_Template(template_path, raw_text)		

	@staticmethod
	def parse_policy_hitcount(raw_text):
		"""
		解析Hillstone设备策略命中数
		对应指令：show policy hit-count
		:return: 解析结果列表
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH,"hillstone", "hillstone_hitcount.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_interfaces(raw_text):
		"""
		解析Hillstone设备接口信息
		对应指令：show interface
		提取字段：接口名(INTERFACE)、IPv4地址/掩码(IPv4Address)、区域名(ZONE)
		"""
		# 统一的正则表达式模式，处理各种格式变化
		# 支持：基本格式、带有Vsys和F列的格式、带有IPv6地址列的格式
		interface_pattern = re.compile(
			r'^(\S+)'  # 接口名
			r'\s+([\d\.]+/\d+)'  # IPv4地址/掩码
			r'(?:\s+(?:[0-9a-fA-F:.]+/\d+|N/A))?'  # 可选的IPv6地址/前缀或N/A
			r'\s+(\S+)'  # 区域名
			r'(?:\s+\S+)?'  # 可选的Vsys列
			r'\s+[UDK]\s+[UDK]\s+[UDK]\s+[UDK]'  # 四个状态字段
			r'\s+([0-9a-fA-F\.:-]+)'  # MAC地址（允许--------------格式）
			r'(?:\s+[NSEV])?'  # 可选的F列（标志）
			r'.*$'  # 剩余部分（描述）
		)

		# 需要跳过的行关键字
		skip_keywords = {
			'H:physical state', '=', '-', 'Interface name', 
			'N:Not shared', 'IPv4 address/mask'
		}

		parsed_result = []

		for line in raw_text.splitlines():
			line = line.strip()
			# 跳过表头、分隔线、状态说明行、空行
			if not line or any(line.startswith(kw) for kw in skip_keywords):
				continue

			match = interface_pattern.match(line)
			if match:
				interface_name = match.group(1).strip()
				ipv4_mask = match.group(2).strip()
				zone_name = match.group(3).strip()
				
				if ipv4_mask:  # 过滤空IP
					parsed_result.append({
						"INTERFACE": interface_name,
						"IPv4Address": ipv4_mask,
						"ZONE": zone_name
					})

		return parsed_result



# -------------------------- 迪普厂商解析类 --------------------------
class DptechParser:
	"""Dptech（迪普）配置解析类（聚合所有相关解析方法）"""
	@staticmethod
	def parse_version(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH,"dptech", "dptech_version.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_policy(raw_text):
		"""解析下线Dptech防火墙策略信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "dptech", "dptech_fw.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_address_set(raw_text):
		"""解析下线Dptech防火墙地址薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "dptech", "dptech_range.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_service_set(raw_text):
		"""解析下线Dptech防火墙地址薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "dptech", "dptech_service.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_schedule(raw_text):
		"""解析下线Dptech防火墙schedule信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "dptech", "dptech_schedule.template")
		return Parse_With_Template(template_path, raw_text)						

	@staticmethod
	def parse_firewall_ipv4_route(raw_text):
		"""
		解析迪普防火墙IPv4路由信息
		对应指令：show ip route
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "dptech", "dptech_firewall_route_ipv4.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_ipv6_route(raw_text):
		"""
		解析迪普防火墙IPv6路由信息
		对应指令：show ipv6 route
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "dptech", "dptech_firewall_route_ipv6.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_zoneinfo(raw_text):
		"""
		解析迪普防火墙Zone
		对应指令：show security-zone *
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "dptech", "dptech_firewall_zoneinfo.template")
		return Parse_With_Template(template_path, raw_text)




# -------------------------- UNIS厂商解析类 --------------------------
class UNISParser:
	"""UNIS设备配置解析类（聚合所有UNIS相关解析方法）"""	
	@staticmethod
	def parse_version(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "unis", "unis_version.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_wireless_domain(raw_text):
		"""解析紫光无线路由器域名domain配置"""
		parsed_dict = {}
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "unis", "unis_domain.template")
		parsed_domain = Parse_With_Template(template_path, raw_text)
		if(parsed_domain != []):
			parsed_dict = parsed_domain[0]
			matchmain = re.findall(r'apply\s+(\S+)',parsed_dict["DomainText"])
			matchsub = re.findall(r'backup\s+(\S+)',parsed_dict["DomainText"])
			parsed_dict["MDomainText"] = "未配置" if matchmain==[] else matchmain[0]
			parsed_dict["SDomainText"] = "未配置" if matchsub==[] else matchsub[0]
		return parsed_dict

	@staticmethod
	def parse_wireless_multidialer(raw_text):
		"""解析紫光无线路由器多播列表multidialer配置"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "unis", "unis_multidialer.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_wireless_rsrp(raw_text):
		"""
		解析紫光无线路由器RSRP值
		对应指令：display cellular | include RSRP
		"""
		rsrp_sinr_dict = {}
		rsrp_mregex = r'RSRP\s*:\s*(-\d+)\s*dBm'
		matchlist = re.findall(rsrp_mregex,raw_text,re.MULTILINE)
		if(matchlist):
			rsrp_sinr_dict['rsrp'] = matchlist[0]
		return rsrp_sinr_dict

	@staticmethod
	def parse_static_routes(raw_text):
		"""
		解析紫光设备配置静态路由
		对应指令：dis ip routing-table protocol static
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "unis", "unis_route_v4.template")
		return Parse_With_Template(template_path, raw_text)



# -------------------------- Ruijie厂商解析类 --------------------------
class RuijieParser:
	"""Ruijie设备配置解析类（聚合所有Ruijie相关解析方法）"""	
	@staticmethod
	def parse_version(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "ruijie", "ruijie_version.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_wireless_domain(raw_text):
		"""解析锐捷无线路由器域名domain配置"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "ruijie", "ruijie_domain.template")
		parsed_domain = Parse_With_Template(template_path, raw_text)
		return parsed_domain[0] if parsed_domain else {}

	@staticmethod
	def parse_wireless_rsrp(raw_text):
		"""
		解析锐捷无线路由器RSRP值
		对应指令：show cellular info radio
		"""
		rsrp_sinr_dict = {}
		rsrp_mregex = r'(RSRP)[ ]*=[ ]*(-\d+)dBm'
		rsrp_result = re.findall(rsrp_mregex,raw_text,re.MULTILINE)
		if(rsrp_result):
			rsrp_sinr_dict["rsrp"] = rsrp_result[0][1]
		else:
			rsrp_sregex = r'(RSRP_MAIN)[ ]*=[ ]*(-\d+)dBm'
			rsrp_result = re.findall(rsrp_sregex,raw_text,re.MULTILINE)
			if(rsrp_result):
				rsrp_sinr_dict["rsrp"] = rsrp_result[0][1]
		return rsrp_sinr_dict	




# -------------------------- Mypower厂商解析类 --------------------------
class MypowerParser:
	"""迈普设备配置解析类（聚合所有迈普相关解析方法）"""	
	@staticmethod
	def parse_version(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "mypower", "mypower_version.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_wireless_domain(raw_text):
		"""解析迈普无线路由器域名domain配置"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "mypower", "mypower_domain.template")
		parsed_domain = Parse_With_Template(template_path, raw_text)
		return parsed_domain[0] if parsed_domain else {}

	@staticmethod
	def parse_wireless_multidialer(raw_text):
		"""解析迈普无线路由器多播列表multidialer配置"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "mypower", "mypower_multidialer.template")
		parsed_domain = Parse_With_Template(template_path, raw_text)
		return parsed_domain[0] if parsed_domain else {}

	@staticmethod
	def parse_wireless_rsrp(raw_text):
		"""
		解析迈普无线路由器RSRP值
		对应指令：show fastcellular 1/0 phy radio
		"""
		rsrp_sinr_dict = {}
		rsrp_mregex = r'(RSRP)[ \S]*\s*=\s*(-\d+)dBm'
		rsrp_result = re.findall(rsrp_mregex,raw_text,re.MULTILINE)
		if(rsrp_result):
			rsrp_sinr_dict["rsrp"] = rsrp_result[0][1]
		else:
			rsrp_sregex = r'(RSRP)[ ]*:[ ]*(-\d+)dBm'
			rsrp_result = re.findall(rsrp_sregex,raw_text,re.MULTILINE)
			if(rsrp_result):
				rsrp_sinr_dict["rsrp"] = rsrp_result[0][1]
		return rsrp_sinr_dict





# -------------------------- Neusoft厂商解析类 --------------------------
class NeusoftParser:
	"""东软设备配置解析类（聚合所有东软相关解析方法）"""	
	@staticmethod
	def parse_version(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_version.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_policy(raw_text):
		"""解析东软防火墙配置策略信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_fw.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_address_book(raw_text):
		"""解析东软防火墙配置地址薄信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_rangeset.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_address_group(raw_text):
		"""解析东软防火墙配置地址组信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_rangeset_group.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_service_set(raw_text):
		"""解析东软防火墙配置端口服务信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_service.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_rawtext(raw_text):
		"""解析东软防火墙配置原始文本信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_raw.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_ipv4_route(raw_text):
		"""
		解析Neusoft防火墙IPv4路由信息
		对应指令：show route
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_firewall_route.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_ipv6_route(raw_text):
		"""
		解析Neusoft防火墙IPv4路由信息
		对应指令：show route
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_firewall_route_ipv6.template")
		return Parse_With_Template(template_path, raw_text)		

	@staticmethod
	def parse_zoneinfo(raw_text):
		"""
		解析Neusoft防火墙Zone信息
		对应指令：show zone
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_firewall_zoneinfo.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_zonedetail(raw_text):
		"""
		解析Neusoft防火墙Zone详细信息
		对应指令：show zone <zonename>
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "neusoft", "neusoft_firewall_zonedetail.template")
		return Parse_With_Template(template_path, raw_text)



# -------------------------- Topsec厂商解析类 --------------------------
class TopsecParser:
	"""Topsec设备配置解析类（聚合所有天融信相关解析方法）"""	
	@staticmethod
	def parse_version(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_version_1.template")		
		parsed_result = Parse_With_Template(template_path, raw_text)
		if(parsed_result == []):
			template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_version_2.template")
			parsed_result = Parse_With_Template(template_path, raw_text)
		return parsed_result

	@staticmethod
	def parse_zoneinfo(raw_text):
		"""
		解析Topsec防火墙Zone信息
		对应指令：define area show
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_firewall_zoneinfo.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_policy(raw_text):
		"""解析天融信防火墙配置策略信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_fw_1.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_address_host(raw_text):
		"""解析天融信防火墙配置地址信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_rangeset_1_1.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_address_range(raw_text):
		"""解析天融信防火墙配置地址信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_rangeset_1_2.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_address_group(raw_text):
		"""解析天融信防火墙配置地址组信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_rangeset_1_3.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_address_subnet(raw_text):
		"""解析天融信防火墙配置地址掩码信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_rangeset_1_4.template")
		return Parse_With_Template(template_path, raw_text)			

	@staticmethod
	def parse_firewall_service_set(raw_text):
		"""解析天融信防火墙配置端口服务信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_service_1_2.template")
		return Parse_With_Template(template_path, raw_text)			

	@staticmethod
	def parse_firewall_service_group(raw_text):
		"""解析天融信防火墙配置端口服务组信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_service_1_1.template")
		return Parse_With_Template(template_path, raw_text)		

	@staticmethod
	def parse_firewall_rawtext(raw_text):
		"""解析天融信防火墙配置原始文本信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_raw_1.template")
		return Parse_With_Template(template_path, raw_text)	

	@staticmethod
	def parse_firewall_schedule(raw_text):
		"""解析天融信防火墙配置schedule信息"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_schedule.template")
		return Parse_With_Template(template_path, raw_text)			

	@staticmethod
	def parse_firewall_ipv4_route(raw_text):
		"""
		解析天融信防火墙IPv4路由信息
		对应指令：network route show
		"""
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "topsec", "topsec_firewall_route_ipv4.template")
		return Parse_With_Template(template_path, raw_text)


# -------------------------- ZCTT厂商解析类 --------------------------
class ZCTTParser:
	"""ZCTT设备配置解析类（聚合所有中创相关解析方法）"""	
	@staticmethod
	def parse_version(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "zctt", "zctt_version.template")
		return Parse_With_Template(template_path, raw_text)



# -------------------------- Netscout厂商解析类 --------------------------
class NetscoutParser:
	"""Netscout设备配置解析类（聚合所有中创相关解析方法）"""	
	@staticmethod
	def parse_version_5010(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "netscout", "netscout5010_version.template")
		return Parse_With_Template(template_path, raw_text)



# -------------------------- Cisco厂商解析类 --------------------------
class CiscoParser:
	"""Cisco设备配置解析类（聚合所有思科相关解析方法）"""	
	@staticmethod
	def parse_version(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "cisco", "cisco_version.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_access(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "cisco", "cisco_access.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_policy(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "cisco", "cisco_fw.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_object(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "cisco", "cisco_object.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_interface(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "cisco", "cisco_interface.template")
		return Parse_With_Template(template_path, raw_text)


# -------------------------- Fortinet厂商解析类 --------------------------
class FortinetParser:
	"""Fortinet设备配置解析类（聚合所有飞塔相关解析方法）"""	
	@staticmethod
	def parse_firewall_policy(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "fortinet", "fortinet_fw.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_address_set(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "fortinet", "fortinet_rangeset.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_address_group(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "fortinet", "fortinet_groupset.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_service_set(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "fortinet", "fortinet_customservice.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_service_group(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "fortinet", "fortinet_groupservice.template")
		return Parse_With_Template(template_path, raw_text)


# -------------------------- Juniper厂商解析类 --------------------------
class JuniperParser:
	"""Juniper设备配置解析类（聚合所有Juniper相关解析方法）"""	
	@staticmethod
	def parse_firewall_policy(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "juniper", "juniper_fw.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_address_set(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "juniper", "juniper_range.template")
		return Parse_With_Template(template_path, raw_text)

	@staticmethod
	def parse_firewall_service_set(raw_text):
		template_path = os.path.join(PARSE_TEMPLATE_PATH, "juniper", "juniper_service.template")
		return Parse_With_Template(template_path, raw_text)