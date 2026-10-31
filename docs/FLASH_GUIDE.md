# 直接刷写指南（1.0-3）

当前定制版本为 `1.0-3`：原厂 BIOS Version 为 `1.0`，固件内 BIOS Version
字段已改为 `1.0-3`；`-3` 是本地第 3 个定制构建。EC 版本 `0.23` 保持原厂，
不做修改。

## 1. 刷哪个文件

**`firmware/modified/BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin`**

- 保留原厂 1.68 pre-SoC15 GOP FFS **字节不变**（Radeon 520 / Polaris）；
- 在 inner DXE FV 末尾追加 2.10 post-SoC15 GOP FFS
  （GUID `92F10585-...`），负责 Vega 20；
- 开机 LOGO 替换为 `images/Huawei-Logo.bmp`
  （840x260 24-bit；实机 GOP 为 1024 宽、4:3，4K 显示器会横向拉伸，
  因此按约 3.42:1 预补偿；显示后约 4.54:1、约 80% 屏宽）；
- 两个 PE 都保留 AMD 签名；FV/FFS/block map/LZMA 均自检通过；
- 不修改 EC 版本（0.23）；BIOS Version 字段已从 `1.0` 改为 `1.0-3`，
  `dmidecode -s bios-version` 实机确认显示 `1.0-3`；
- RX 5700 XT 在 Kunpeng 上不被 PCIe 枚举（电气/链路不兼容），本镜像不支持；
- RX 6000（RDNA2）主流 ID 不在 2.10 设备表内，本次不支持。

SHA-256：

```
5951f282a0ebb03a0e886a49a1623db4796257e8c755b7dfe7c4b0e2d20da330
```

## 2. 刷写步骤

> **BIOS 内置固件升级（已实机验证）**：把
> `firmware/modified/BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin`
> 复制到 U 盘，在 BIOS Setup 的固件升级功能中选择文件名
> `BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin` 刷写
> （U 盘界面只显示文件名，没有 `firmware/modified/` 路径）。
> 不需要拆 SPI 芯片或用编程器；已实机验证该方式可用。具体菜单名称和
> 支持的升级介质以主板 Setup 为准。下面的 SPI 编程器步骤作为离线/恢复
> 方式保留。

1. 确认原厂备份仍在：
   - `firmware/original/BC32MBHB-D920L11K-2251K_1.0_2020-07-22.bin`
   - SHA-256 `e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704`
2. 完全断电、拔电源线，取出 SPI 芯片。
3. 确认芯片型号、电压与编程器/转接座匹配（本板资料为 W25Q128JWSQ，1.8 V；
   以实际芯片丝印为准）。
4. 写入**完整 16 MiB 镜像**（不是只写 BIOS 区），写后读回校验 SHA-256。
5. 芯片装回，接好目标显卡和显示器，开机；首次启动可能比平时久。
6. 按 F2 进 BIOS Setup，确认画面是否在目标显卡上出现。
7. 完整镜像会覆盖 NVRAM；若 OS 启动项丢失，可在 Setup/Boot Manager 重新选择，
   或从 ESP 启动。

## 3. 结果判断

### 3.1 正常显示

Radeon 520 或 Vega 20 的显示器出现 BIOS POST/Setup 画面即成功。
进入 Linux 后 Vega 20 下应能看到 `simple-framebuffer.0` / `simpledrm`，
随后 amdgpu 接管（`VEGA20 0x1002:0x66A1`，ATOM BIOS `113-D1640600-104`）。

### 3.2 能启动，但 BIOS/Setup 无显示

按顺序检查：

1. 读回芯片确认当前确实是 `1.0-3` 镜像（SHA-256 匹配）。
2. 确认显示器和线缆接在目标显卡上，Vega 20 使用其 DP/HDMI 输出。
3. 若仍无显示：记录卡型、`lspci`、`dmesg`/amdgpu，恢复原厂镜像后排查。

### 3.3 完全不能启动

1. 用编程器恢复原厂镜像。
2. 核对写入的是完整 16 MiB 镜像、SHA-256 与上表一致。
3. 确认 SPI 芯片型号/电压和编程器设置正确。

### 3.4 刷回

始终可直接写回：

```
# 原厂
"firmware/original/BC32MBHB-D920L11K-2251K_1.0_2020-07-22.bin"
SHA-256 e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704
```

## 4. 1.0-3 这个镜像改了什么

- 保留原 1.68 `Arm64Gop` FFS（inner `0x9A51B8`，size `0x216F2`）**字节不变**；
- 在 inner FV 末尾追加新的 2.10 FFS：
  - GUID `92F10585-FB63-430F-8188-71FEEB2DDA5B`；
  - PE32 section type `0x10`，size `0x18E34`（2.10 PE `0x18E30`）；
  - UI section type `0x15`，`ARM64Gop 2.10`；
  - FFS size `0x18E6C`，header checksum `0x7C`，File checksum 字节 `0xAA`；
- inner FV 扩容到 `0xE8E440`，block map `0x3A391 × 0x40`；
- 重新压缩后 outer section `0x1EDD63`、outer FFS `0x1EDD7B`，FV2 余量
  60,181 字节；
- **开机 LOGO 替换**：GUID `7BB28B99-61BB-11D5-9A5D-0090273FC14D` 的
  freeform FFS 从 `0x14E4E` 扩容到 `0x9FFCE`（BMP body `655,254` 字节，
  另含对齐 padding）；raw section body 在 inner `0x8A30A4`，后续 FFS
  按原有 `0x80` 对齐整体平移；
- 新 LOGO 为 `840x260` 24-bit BMP（内容 `820x240`，黑底白字 + 红色花瓣），
  4:3 GOP 经 4K 拉伸后约 80% 屏宽、比例正常；**已实机验证**；
- **BIOS Version 字段 `1.0` → `1.0-3`**（版本信息块绝对 `0xBF0098`，
  VersionInfoPeim 默认字符串/复制长度同步修改）；EC 版本 `0.23` 字符串不变；
- **Setup 静态 HII 标题不修改**，仍显示 `Byosoft ByoCore BIOS V1.0`；
  标题和 BIOS Version 字段是独立字符串；
- 2.10 PE 保留 AMD Authenticode（Security 目录 `0x16C00` / `0x2230`）和
  PE checksum `0x24A69`；设备表 `0x15B40` 含 Vega 20 范围 `0x66A0–0x66AF`；
- 除 GOP/LOGO 外，未改前 8 MiB 的 bootloader/IMU 和其他 FV 结构；
  NVRAM 区与构建时一致；
- 外层 GUIDed LZMA section/FFS 重建，FV/FFS header checksum 和解压回读均自检
  通过；diff 只出现在 outer FFS 区域。

## 5. 注意事项

- **2.10 不含 Polaris**：Radeon 520 由保留的原 1.68 驱动负责，两个 GOP 并存。
- **RX 5700 XT**：实测在 Kunpeng 上不被 PCIe 枚举（Gen3/2/1 target 均
  `LnkSta 2.5GT/s x1, DLActive-`），是 PCIe 电气/链路不兼容，不是 GOP 问题；
  本平台不支持。
- RX 6000（RDNA2）主流 ID 不在 2.10 设备表内，本次不支持。
- EC 版本 `0.23` 是独立 EC 固件，不随本 BIOS 镜像改变；
  BIOS Version 字段为 `1.0-3`。
- 刷完整镜像会覆盖 NVRAM；OS 启动项可能需要在 Setup/Boot Manager 重新选择。
- 刷写前确认编程器电压/芯片型号，避免损坏芯片。

## 6. 版本号更新

只改 `scripts/rebuild_bios.py` 里的 `CUSTOM_VERSION`（当前为 `3`），重新构建
即可。脚本会自动更新文件名、BIOS Version 字段（`0xBF0098`）、
VersionInfoPeim 默认版本字符串和复制长度；标签总长度需小于 8 字符
（如 `1.0-4`、`1.0-10` 可以，超长会报错）。
