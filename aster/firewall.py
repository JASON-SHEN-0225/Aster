"""Windows 防火墙规则：Aster 需要 TCP + UDP 入站（HTTP 与 HTTPS 双端口）。"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .util import is_admin

RULE_PREFIX = "Aster"


def rule_names(port: int, https_port: Optional[int] = None) -> tuple[str, str]:
    return (f"{RULE_PREFIX} TCP {port}", f"{RULE_PREFIX} UDP {port}")


def https_rule_name(https_port: int) -> str:
    return f"{RULE_PREFIX} TCP {https_port}"


def firewall_commands(port: int, https_port: Optional[int] = None) -> list[list[str]]:
    tcp, udp = rule_names(port)
    cmds = [
        [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={tcp}", "dir=in", "action=allow", "protocol=TCP",
            f"localport={port}", "profile=private,domain",
        ],
        [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={udp}", "dir=in", "action=allow", "protocol=UDP",
            f"localport={port}", "profile=private,domain",
        ],
    ]
    if https_port and https_port != port:
        cmds.append(
            [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={https_rule_name(https_port)}", "dir=in", "action=allow",
                "protocol=TCP", f"localport={https_port}", "profile=private,domain",
            ]
        )
    return cmds


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except Exception as exc:
        return 1, str(exc)


def add_firewall_rules(port: int, https_port: Optional[int] = None) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "当前系统不是 Windows，无需添加防火墙规则。"
    if not is_admin():
        return False, "需要管理员权限。"
    messages = []
    ok = True
    for cmd in firewall_commands(port, https_port):
        code, out = _run(cmd)
        messages.append(out.strip())
        ok = ok and code == 0
    return ok, "\n".join(msg for msg in messages if msg)


def elevate_script(port: int, https_port: Optional[int] = None) -> Path:
    """生成一个可自提权的 PowerShell 脚本，供用户点 UAC 时使用。"""
    https_port = https_port or (port + 1)
    script = f"""# 以管理员身份为 Aster 添加 Windows 防火墙入站规则
$ErrorActionPreference = 'Continue'
$port = {int(port)}
$https = {int(https_port)}
netsh advfirewall firewall add rule name="Aster TCP $port" dir=in action=allow protocol=TCP localport=$port profile=private,domain
netsh advfirewall firewall add rule name="Aster UDP $port" dir=in action=allow protocol=UDP localport=$port profile=private,domain
if ($https -ne $port) {{
  netsh advfirewall firewall add rule name="Aster TCP $https" dir=in action=allow protocol=TCP localport=$https profile=private,domain
}}
Write-Host ''
Write-Host "Aster 防火墙规则已添加（TCP $port / TCP $https / UDP $port）。按回车关闭..."
[void][System.Console]::ReadLine()
"""
    path = Path(tempfile.gettempdir()) / f"aster-firewall-{port}.ps1"
    path.write_text("\ufeff" + script, encoding="utf-8")
    return path


def request_elevation(port: int, https_port: Optional[int] = None) -> tuple[bool, str]:
    """弹出 UAC，让用户确认添加规则。"""
    if os.name != "nt":
        return False, "仅 Windows 支持。"
    script = elevate_script(port, https_port)
    safe_script = str(script).replace("'", "''")
    ps = (
        "Start-Process powershell -Verb RunAs -ArgumentList "
        f"'-NoProfile','-ExecutionPolicy','Bypass','-File','{safe_script}'"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return True, f"已请求管理员权限，请在弹出的 UAC 窗口点「是」。\n脚本：{script}"
        return False, (proc.stderr or proc.stdout or "UAC 请求失败").strip()
    except Exception as exc:
        return False, str(exc)


def firewall_hint(port: int, https_port: Optional[int] = None) -> str:
    tcp, udp = rule_names(port)
    https_port = https_port or (port + 1)
    https_name = https_rule_name(https_port)
    return (
        "如果手机无法访问，请以管理员身份运行一次：\n"
        "  打开 Aster.exe → 设置 → 配置 Windows 防火墙\n"
        "手动命令：\n"
        f'  netsh advfirewall firewall add rule name="{tcp}" dir=in action=allow protocol=TCP localport={port} profile=private,domain\n'
        f'  netsh advfirewall firewall add rule name="{udp}" dir=in action=allow protocol=UDP localport={port} profile=private,domain\n'
        f'  netsh advfirewall firewall add rule name="{https_name}" dir=in action=allow protocol=TCP localport={https_port} profile=private,domain'
    )
