# 直接刷写指南（1.0-4）

当前定制版本为 `1.0-4`：原厂 BIOS Version 为 `1.0`，固件内 BIOS Version
字段已改为 `1.0-4`；`-4` 是本地第 4 个定制构建。EC 版本 `0.23` 保持原厂，
不做修改。

此版本还修复了两个固件问题，刷入后 Linux 不再需要
`arm64.nompam` 和 `initcall_blacklist=hisi_ddrc_pmu_module_init`：

- DSDT 的 4 个 `HISI0233` DDRC PMU 设备改为 `HISI9999`，避免
  `hisi_uncore_ddrc_pmu` 读 `DDRC_VERSION` 挂死；
- BL31 两个入口写入 MPAM stub，初始化 `MPAM3_EL3`。

## 1. 刷哪个文件

**`firmware/modified/BC32MBHB-D920L11K-2251K_1.0-4_2020-07-22.bin`**

- 保留原厂 1.68 pre-SoC15 GOP FFS **字节不变**（Radeon 520 / Polaris）；
- 在 inner DXE FV 末尾追加 2.10 post-SoC15 GOP FFS
  （GUID `92F10585-...`），负责 Vega 20；
- 开机 LOGO 替换为 `images/Huawei-Logo.bmp`
  （840x260 24-bit；实机 GOP 为 1024 宽、4:3，4K 显示器会横向拉伸，
  因此按约 3.42:1 预补偿；显示后约 4.54:1、约 80% 屏宽）；
- 两个 PE 都保留 AMD 签名；FV/FFS/block map/LZMA 均自检通过；
- 不修改 EC 版本（0.23）；BIOS Version 字段已从 `1.0` 改为 `1.0-4`，
  `dmidecode -s bios-version` 实机确认显示 `1.0-4`；
- **DDRC PMU 修复**：DSDT 4 个 `HISI0233` → `HISI9999`，重算 DSDT
  checksum；`hisi_uncore_ddrc_pmu` 不再匹配/自动加载；
- **MPAM 修复**：FIP 内 BL31 两个入口写入 stub，设置
  `MPAM3_EL3 = 0x8000000000000000`（MPAMEN=1，TRAPLOWER=0）；
  只改 BL31 内 32 字节；
- RX 5700 XT 在 Kunpeng 上不被 PCIe 枚举（电气/链路不兼容），本镜像不支持；
- RX 6000（RDNA2）主流 ID 不在 2.10 设备表内，本次不支持。

SHA-256：

```
b6916035b2c7d5f84e537a6d38972dcd77a32f7c02d5a0806f6b3f30b37be19e
```

## 2. 刷写步骤

> **BIOS 内置固件升级（Step 1 已实机验证）**：把
> `firmware/modified/BC32MBHB-D920L11K-2251K_1.0-4_2020-07-22.bin`
> 复制到 U 盘，在 BIOS Setup 的固件升级功能中选择文件名
> `BC32MBHB-D920L11K-2251K_1.0-4_2020-07-22.bin` 刷写
> （U 盘界面只显示文件名，没有 `firmware/modified/` 路径）。
> 1.0-3 → 1.0-4 的 DDRC 测试镜像已实机验证可用。
> **最终镜像含 BL31 修改，建议用 SPI 编程器写整片**：同版本内置升级
> 可能被 `VersionCheck` 拒绝，且编程器能确保 BL31 区域写入。若走内置
> 升级，刷后必须读回核对 BL31 `0xBB328D/0xBB33A5/0xBBB08D`。
> 具体菜单名称和升级介质以主板 Setup 为准。

1. 用编程器做一次**当前 SPI 全片备份**（含 NVRAM/启动项）。
2. 确认原厂备份仍在：
   - `firmware/original/BC32MBHB-D920L11K-2251K_1.0_2020-07-22.bin`
   - SHA-256 `e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704`
3. 完全断电、拔电源线，取出 SPI 芯片。
4. 确认芯片型号、电压与编程器/转接座匹配（本板资料为 W25Q128JWSQ，1.8 V；
   以实际芯片丝印为准）。
5. 写入**完整 16 MiB 镜像**（不是只写 BIOS 区），写后读回校验 SHA-256。
6. 芯片装回，接好目标显卡和显示器，开机；首次启动可能比平时久。
7. 按 F2 进 BIOS Setup，确认画面是否在目标显卡上出现。
8. 完整镜像会覆盖 NVRAM；若 OS 启动项丢失，可在 Setup/Boot Manager 重新选择，
   或从 ESP 启动。

## 3. 结果判断

### 3.1 正常显示

Radeon 520 或 Vega 20 的显示器出现 BIOS POST/Setup 画面即成功。
进入 Linux 后 Vega 20 下应能看到 `simple-framebuffer.0` / `simpledrm`，
随后 amdgpu 接管（`VEGA20 0x1002:0x66A1`，ATOM BIOS `113-D1640600-104`）。

最终 1.0-4 镜像已实机验证：从 U 盘启动、GRUB 去掉两个参数可正常启动。
去掉两个内核参数后再检查：

```bash
cat /proc/cmdline          # 不应再有 arm64.nompam / initcall_blacklist
ls /sys/bus/acpi/devices | grep -E 'HISI9999|HISI0233'   # 只有 HISI9999
lsmod | grep hisi_uncore_ddrc                            # 应为空
journalctl -k -b --no-pager | grep -iE 'mpam|ddrc'       # 无挂死/无 ddrc 加载
```

### 3.2 能启动，但 BIOS/Setup 无显示

按顺序检查：

1. 读回芯片确认当前确实是 `1.0-4` 镜像（SHA-256 匹配）。
2. 确认显示器和线缆接在目标显卡上，Vega 20 使用其 DP/HDMI 输出。
3. 若仍无显示：记录卡型、`lspci`、`dmesg`/amdgpu，恢复原厂镜像后排查。

### 3.3 完全不能启动

1. 若刚刷了含 BL31 补丁的最终镜像，先用编程器写回当前 SPI 全片备份或原厂镜像。
2. 核对写入的是完整 16 MiB 镜像、SHA-256 与上表一致。
3. 确认 SPI 芯片型号/电压和编程器设置正确。
4. 若只是 DDRC 修复导致内核启动问题，可在 GRUB 临时加回
   `initcall_blacklist=hisi_ddrc_pmu_module_init` 或
   `arm64.nompam` 排查。

### 3.4 刷回

始终可直接写回：

```
# 原厂
"firmware/original/BC32MBHB-D920L11K-2251K_1.0_2020-07-22.bin"
SHA-256 e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704
```

## 4. 1.0-4 这个镜像改了什么

- 保留原 1.68 `Arm64Gop` FFS（inner `0x9A51B8`，size `0x216F2`）**字节不变**；
- 在 inner FV 末尾追加新的 2.10 FFS：
  - GUID `92F10585-FB63-430F-8188-71FEEB2DDA5B`；
  - PE32 section type `0x10`，size `0x18E34`（2.10 PE `0x18E30`）；
  - UI section type `0x15`，`ARM64Gop 2.10`；
  - FFS size `0x18E6C`，header checksum `0x7C`，File checksum 字节 `0xAA`；
- inner FV 扩容到 `0xE8E440`，block map `0x3A391 × 0x40`；
- 重新压缩后 outer section `0x1EDFC0`、outer FFS `0x1EDFD8`，FV2 余量
  59,576 字节；
- **开机 LOGO 替换**：GUID `7BB28B99-61BB-11D5-9A5D-0090273FC14D` 的
  freeform FFS 从 `0x14E4E` 扩容到 `0x9FFCE`（BMP body `655,254` 字节，
  另含对齐 padding）；raw section body 在 inner `0x8A30A4`，后续 FFS
  按原有 `0x80` 对齐整体平移；
- 新 LOGO 为 `840x260` 24-bit BMP（内容 `820x240`，黑底白字 + 红色花瓣），
  4:3 GOP 经 4K 拉伸后约 80% 屏宽、比例正常；**已实机验证**；
- **BIOS Version 字段 `1.0` → `1.0-4`**（版本信息块绝对 `0xBF0098`，
  VersionInfoPeim 默认字符串/复制长度同步修改）；EC 版本 `0.23` 字符串不变；
- **Setup 静态 HII 标题不修改**，仍显示 `Byosoft ByoCore BIOS V1.0`；
  标题和 BIOS Version 字段是独立字符串；
- 2.10 PE 保留 AMD Authenticode（Security 目录 `0x16C00` / `0x2230`）和
  PE checksum `0x24A69`；设备表 `0x15B40` 含 Vega 20 范围 `0x66A0–0x66AF`；
- **DDRC PMU ACPI 修复**：DSDT body inner `0x60DA4C`、长度 `0x7EE7`；
  4 个 `HISI0233`（DSDT rel `0x77DD/0x7894/0x794B/0x7A04`）改为
  `HISI9999`，DSDT checksum（offset 9）重算；`_CRS` 和表长不变；
- **BL31 MPAM 修复**：FIP `0xBB0000`，BL31 `0xBB3235..0xBBD326`；
  两处初始化序列 `FF4403D5 000080D2 40111ED5`（abs `0xBB3289`、
  `0xBB33A1`）的 `mov x0,#0` 改为 `BL` 到 stub（abs `0xBBB08D`）；
  stub 设置 `MPAM3_EL3`；BL31 内只改 32 字节；
- 除 GOP/LOGO/DSDT/BL31 外，未改前 8 MiB 的 bootloader/IMU 和其他 FV
  结构；NVRAM 区与构建时一致；
- 外层 GUIDed LZMA section/FFS 重建，FV/FFS header checksum 和解压回读均自检
  通过；diff 只出现在 outer FFS、版本信息块 `0xBF0098` 和 BL31 区间。

## 5. 注意事项

- **2.10 不含 Polaris**：Radeon 520 由保留的原 1.68 驱动负责，两个 GOP 并存。
- **RX 5700 XT**：实测在 Kunpeng 上不被 PCIe 枚举（Gen3/2/1 target 均
  `LnkSta 2.5GT/s x1, DLActive-`），是 PCIe 电气/链路不兼容，不是 GOP 问题；
  本平台不支持。
- RX 6000（RDNA2）主流 ID 不在 2.10 设备表内，本次不支持。
- EC 版本 `0.23` 是独立 EC 固件，不随本 BIOS 镜像改变；
  BIOS Version 字段为 `1.0-4`。
- **BL31 修改风险**：EL3 代码写错会导致主板无法启动，只能用 SPI 编程器
  恢复；刷前保留当前 SPI 全片备份。
- **DDRC PMU 被禁用**：4 个 DDRC 设备 HID 改为 `HISI9999`，DDRC PMU
  事件不可用（与之前 blacklist 一致）。
- **内置升级限制**：同版本重刷可能被 `VersionCheck` 拒绝；最终含 BL31
  的镜像建议用编程器，或刷后读回核对 BL31 字节。
- 刷完整镜像会覆盖 NVRAM；OS 启动项可能需要在 Setup/Boot Manager 重新选择。
- 刷写前确认编程器电压/芯片型号，避免损坏芯片。

## 6. 版本号更新

只改 `scripts/rebuild_bios.py` 里的 `CUSTOM_VERSION`（当前为 `4`），重新构建
即可。脚本会自动更新文件名、BIOS Version 字段（`0xBF0098`）、
VersionInfoPeim 默认版本字符串和复制长度；标签总长度需小于 8 字符
（如 `1.0-4`、`1.0-10` 可以，超长会报错）。
DDRC HID 和 BL31 MPAM 修复是当前构建的固定步骤，不随版本号开关。
