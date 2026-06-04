"""
华为网络设备指令采集工具

用法示例:
    from device_collector import collect_device_commands

    success, results = collect_device_commands(
        host='10.202.66.110',
        username='abcadmin',
        password='#Vp417938kb',
        commands=['screen-len 0 temp', 'dis current-configuration'],
        encoding='UTF-8',
        timeout=30
    )

    if success:
        for r in results:
            print("[{}] ({}s)".format(r['command'], r['duration_seconds']))
            print(r['output'])
"""

import subprocess
import os
import re
import logging
from typing import List, Dict, Tuple, Optional


def _safe_decode(data: bytes) -> str:
    """尝试 UTF-8 解码，失败则用 GBK 回退。"""
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return data.decode('gbk')
        except UnicodeDecodeError:
            return data.decode('utf-8', errors='replace')

logger = logging.getLogger(__name__)


def collect_device_commands(
    host: str,
    username: str,
    password: str,
    commands: List[str],
    netagent_path: str = '/home/emapp/fwflask/foreign_sdk/go_agent/netagent_linux',
    encoding: str = 'UTF-8',
    timeout: int = 30,
    enable: bool = False,
    enable_pass: str = '',
) -> Tuple[bool, List[Dict]]:
    """
    对一台网络设备执行指令采集

    Parameters
    ----------
    host : str
        设备管理IP地址
    username : str
        SSH登录用户名
    password : str
        SSH登录密码
    commands : List[str]
        要执行的指令列表，例如 ['screen-len 0 temp', 'dis current-configuration']
    netagent_path : str, optional
        netagent_linux 二进制文件路径 (default: /home/emapp/fwflask/foreign_sdk/go_agent)
    encoding : str, optional
        设备输出编码，UTF-8 或 GBK (default: UTF-8)
    timeout : int, optional
        每条指令超时秒数 (default: 30)
    enable_pass : str, optional
        Enable 密码（Cisco 等设备需要提权时使用）

    Returns
    -------
    Tuple[bool, List[Dict]]
        返回 (success, results)，其中 results 每项格式为:
        {
            'command':          str,    # 执行的指令
            'output':           str,    # 指令执行输出（已清洗，保留首尾提示符）
            'duration_seconds': float,  # 指令执行耗时（秒）
            'error':            str,    # 错误信息，成功则为空
        }

        - success=True 时，results 顺序与 commands 一一对应
        - success=False 时，results[0]['error'] 包含错误描述
    """
    if not commands:
        logger.error("commands 不能为空")
        return False, [{'command': '', 'output': '', 'duration_seconds': 0.0, 'error': 'commands list is empty'}]

    args = [netagent_path]
    args.extend(['-host', host])
    args.extend(['-user', username])
    args.extend(['-pass', password])
    args.extend(['-cmd', ','.join(commands)])
    args.extend(['-encoding', encoding])
    args.extend(['-timeout', str(timeout)])
    if enable:
        args.extend(['-enable'])
    if enable_pass:
        args.extend(['-enable-pass', enable_pass])

    logger.info("Executing: {}".format(' '.join(args)))

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        msg = "netagent_linux not found at {}".format(netagent_path)
        logger.error(msg)
        return False, [{'command': '', 'output': '', 'duration_seconds': 0.0, 'error': msg}]
    except Exception as e:
        logger.error("Execution failed: {}".format(e))
        return False, [{'command': '', 'output': '', 'duration_seconds': 0.0, 'error': str(e)}]

    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout + 10)
        stdout = _safe_decode(stdout_bytes) if stdout_bytes else ''
        stderr = _safe_decode(stderr_bytes) if stderr_bytes else ''
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout_bytes, stderr_bytes = proc.communicate()
        stdout = _safe_decode(stdout_bytes) if stdout_bytes else ''
        stderr = _safe_decode(stderr_bytes) if stderr_bytes else ''
        # 检测密码过期
        if stderr and ('password is already expired' in stderr.lower() or 'change now' in stderr.lower()):
            friendly_msg = "[密码过期] 用户 {}@{} 的SSH密码已过期，设备拒绝登录，请联系网络管理员更新密码".format(username, host)
            logger.error(friendly_msg)
            return False, [{'command': '', 'output': '', 'duration_seconds': 0.0, 'error': friendly_msg}]
        extra = _clean_error_output(stderr, username, host) if stderr else ''
        msg = "Command execution timeout ({}s). {}".format(timeout + 10, extra)
        logger.error(msg)
        return False, [{'command': '', 'output': '', 'duration_seconds': 0.0, 'error': msg}]

    if proc.returncode != 0:
        err = stderr.strip() if stderr else "exit code {}".format(proc.returncode)
        logger.error("Command failed: {}".format(err))
        # 检测认证失败
        auth_keywords = ['authentication failed', 'unable to authenticate', '用户名或密码错误', 'password may be incorrect']
        if any(kw in err.lower() for kw in auth_keywords):
            friendly_msg = "[认证失败] SSH 登录 {}@{} 失败，请检查用户名和密码是否正确".format(username, host)
            logger.error(friendly_msg)
            return False, [{'command': '', 'output': '', 'duration_seconds': 0.0, 'error': friendly_msg}]
        # 检测密码过期
        if 'password is already expired' in err or 'Change now' in err:
            friendly_msg = "[密码过期] 用户 {}@{} 的SSH密码已过期，设备拒绝登录或进入受限模式，请联系网络管理员更新密码".format(username, host)
            logger.error(friendly_msg)
            return False, [{'command': '', 'output': '', 'duration_seconds': 0.0, 'error': friendly_msg}]
        friendly_msg = _clean_error_output(stderr, username, host)
        return False, [{'command': '', 'output': '', 'duration_seconds': 0.0, 'error': friendly_msg}]

    # 解析执行时间和输出
    results = _parse_stdout_stderr(stdout, stderr, commands)
    return True, results


def _parse_stdout_stderr(stdout: str, stderr: str, commands: List[str]) -> List[Dict]:
    """
    解析 Go 程序的 stdout/stderr，提取每条指令的输出和执行时间
    """
    results = []
    for cmd in commands:
        results.append({
            'command': cmd,
            'output': '',
            'duration_seconds': 0.0,
            'error': '',
        })

    # 从 stderr 中提取每条指令的执行时间
    if stderr:
        time_pattern = re.compile(r'\[EXEC_TIME\] (.+): ([\d.]+)s')
        for line in stderr.split('\n'):
            m = time_pattern.search(line)
            if m:
                cmd_name = m.group(1).strip()
                duration = float(m.group(2))
                for r in results:
                    if r['command'] == cmd_name:
                        r['duration_seconds'] = duration
                        break

    # 从 stdout 解析每条指令的输出
    # Go 程序输出格式：
    #   === Command: <cmd> ===
    #   <output内容>
    #   === End ===
    if stdout:
        block_pattern = re.compile(
            r'=== Command: (.+?) ===\n(.*?)\n=== End ===',
            re.DOTALL
        )
        for m in block_pattern.finditer(stdout):
            cmd_name = m.group(1).strip()
            cmd_output = m.group(2).strip()
            for r in results:
                if r['command'] == cmd_name:
                    r['output'] = cmd_output
                    break

    return results


def _clean_error_output(stderr: str, username: str, host: str) -> str:
    lines = stderr.split('\n')
    keyLines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if 'hex=' in line or 'rawHex=' in line:
            continue
        if line.startswith('[WAIT] ') or line == '[WAIT]':
            continue
        if line.startswith('[EXEC_TIME]'):
            continue
        keyLines.append(line)
    if keyLines:
        return ' | '.join(keyLines[-30:])
    return "SSH execution failed (see stderr for details)"


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    success, results = collect_device_commands(
        host='10.204.30.250',
        username='wgsedf',
        password='test',
        commands=['terminal length 0', 'dis version'],
        encoding='UTF-8',
        timeout=30,
        enable_pass="EXFW01@GASD!!@#"
    )

    if success:
        for r in results:
            print("命令: {}".format(r['command']))
            print("耗时: {}s".format(r['duration_seconds']))
            print("输出:\n{}\n".format(r['output']))
    else:
        print("失败: {}".format(results[0]['error']))