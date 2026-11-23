# SynoFan — 群晖版风扇调速套件

SynoFan 是开源风扇调速程序 [NiuFan](https://github.com/LiuFudi/NiuFan) 的群晖（DSM 7 / SA6400 等 x86_64 机型）移植，以官方 `.spk` 套件形式安装。它读取 CPU / 显卡 / 硬盘 / SuperIO 温度，按每路独立温度曲线控制 SuperIO 风扇（`it8625` 等 hwmon 控制器），并带失效保护。

> 上游为 [LiuFudi/NiuFan](https://github.com/LiuFudi/NiuFan)，本仓库是其 fork，改动集中在 `spk/`（群晖打包与鉴权）、`build-spk.sh`、`tools/synofan-super-setup.sh` 与 `package/app/server/fancontrold.py` 的少量兼容改动。许可沿用 **GPL-3.0**。

## 与原版（飞牛 fnOS）的差异

| 项目 | 原版 NiuFan | 本移植 SynoFan |
|---|---|---|
| 运行平台 | 飞牛 fnOS | 群晖 DSM 7 |
| 网页入口 | fnOS 网关注入身份 | DSM 桌面入口 + 独立密码登录 |
| 鉴权 | 依赖网关 `X-Trim-*` 头 | 守护进程自鉴权（PBKDF2 + 会话 Cookie） |
| 提权 | 网关注入 root | `sudo` helper（`/usr/local/sbin/synofan-super`） |
| 进程连接 | fnOS 网关直连 Unix socket | 群晖 nginx 桥接 `/webman/3rdparty/synofan/api/` → Unix socket |
| 打包 | `.fpk` | `.spk` |

## 安装

前置：目标机需已有可用的 `hwmon` 风扇控制器（`sensors -u` 能看到 `pwm1`），且已停用系统的 `fancontrol` / RR `sensors.service`（安装脚本会自动停用并迁移曲线）。

```sh
# 1) 一次性提权（root 执行，写入 sudo helper 与 sudoers 白名单）
sudo sh tools/synofan-super-setup.sh

# 2) 安装套件（DSM 7 未签名第三方包，只能以 package 用户运行，提权经 helper）
sudo /usr/syno/bin/synopkg install dist/synofan-x86_64-2.2.5-2.spk
```

首次启动守护进程会生成随机初始密码：

```sh
sudo cat /var/packages/synofan/etc/initial_password
```

用该密码在网页登录后**必须**设置新密码（≥8 位）。登录方式：DSM 桌面打开「SynoFan」图标，或直接访问 `https://<NAS>:5001/webman/3rdparty/synofan/`。

## 回滚 / 卸载

```sh
sudo /usr/syno/bin/synopkg uninstall synofan
```

卸载会移除 nginx 桥接并重启 nginx；守护进程停止后 `pwm1_enable` 自动回到 BIOS 自动模式，风扇由主板接管，无过热风险。

如需恢复系统自带 fancontrol：

```sh
sudo systemctl enable sensors.service && sudo systemctl start sensors.service
```

原曲线备份保留在 `/var/packages/synofan/etc/fancontrol.backup`（卸载前）。

## 构建

在 macOS 上（需 `sips` 生成图标，纯 POSIX `tar`）：

```sh
bash build-spk.sh   # 产物 dist/synofan-x86_64-2.2.5-2.spk
```

产物为未压缩 PAX 外层 tar（DSM 要求），内层 `package.tgz` 为 gzip。

## 目录说明

```
spk/
  conf/privilege,resource    DSM 7 权限（run-as: package）
  dsm/synoauth.py            守护进程自鉴权（登录/改密/会话）
  dsm/dsm-auth.js            前端 fetch 拦截登录弹窗
  nginx.conf                 nginx 桥接 /api/ → Unix socket
  scripts/*                  pre/post inst、start-stop-status
  ui/*                       DSM 桌面外壳（iframe 指向网页）
build-spk.sh                 打包脚本
tools/synofan-super-setup.sh 一次性提权安装
```

## 许可

Copyright (C) 2026 LiuFudi 及 SynoFan 贡献者，GPL-3.0-or-later。详见 [LICENSE](LICENSE)。
