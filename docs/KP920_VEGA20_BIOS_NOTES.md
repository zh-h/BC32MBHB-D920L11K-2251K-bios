# 鲲鹏 920 + Vega 20：BIOS 界面显示修改记录

- 日期：2026-10-31
- 主板：Kunpeng Desktop Board **D920L11K-2251K**（鲲鹏 920，板号 BC32MBHB）
- 固件：`firmware/original/BC32MBHB-D920L11K-2251K_1.0_2020-07-22.bin`，16 MiB，BIOS Version 1.0，EC 0.23，构建日期 2020-07-22
- 显卡：AMD **Vega 20**（Radeon Pro VII / Instinct MI50），PCI ID `1002:66A1`
- VBIOS：`113-D1640600-104`，104448 字节
- 目标：只修改主板 BIOS（不改显卡 VBIOS），让 Vega 20 在 BIOS POST/Setup 显示
- 当前定制版本：**1.0-3**
  `firmware/modified/BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin`
  （SHA-256 `5951f282a0ebb03a0e886a49a1623db4796257e8c755b7dfe7c4b0e2d20da330`）

状态：GOP 方案已实机验证（Radeon 520、Vega 20 的 BIOS POST/Setup 显示均正常；
Vega 20 下固件通过 GOP 交接 `simple-framebuffer`，随后 amdgpu 接管）。
1.0-3 的开机 LOGO 已实机验证：840x260 预补偿版显示正常、比例/大小合适。
BIOS Version 字段已改为 `1.0-3`；EC 0.23 保持原厂。
RX 5700 XT 因在 Kunpeng 上 PCIe 不枚举，不支持。

---

## 1. 当前定制版本 1.0-3

文件名格式：

```
BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin
```

原厂 **BIOS Version 是 `1.0`**；`1.0-3` 表示在原厂 1.0 上做第 3 个本地
定制构建，固件内 BIOS Version 字段也改为 `1.0-3`。

1.0-3 的改动：

- 保留原厂 1.68 pre-SoC15 `Arm64Gop` FFS **字节不变**，负责 Radeon 520 / Polaris；
- 在 inner DXE FV 末尾追加 post-SoC15 2.10 `Arm64Gop` FFS
  （GUID `92F10585-FB63-430F-8188-71FEEB2DDA5B`，UI 名 `ARM64Gop 2.10`），
  负责 Vega 20；
- 把开机 LOGO 从原 PowerLeader `300x95` BMP 替换为 Huawei LOGO
  （`images/Huawei-Logo.bmp`，`840x260` 24-bit，内容 `820x240`，
  黑底白字 + 红色花瓣）；LOGO FFS 扩容并重建 inner FV；
- 两个 PE 都保留 AMD 签名；
- **BIOS Version 字段 `1.0` → `1.0-3`**（版本信息块绝对 `0xBF0098`）；
  EC 版本 `0.23` 保持不变；
- 除 GOP/LOGO/BIOS Version 字段外，未改前 8 MiB 的 bootloader/IMU 和
  其他 FV 结构。

版本字段说明：

- EC 版本 `0.23`：独立嵌入式控制器固件，Setup 从 EC 读取，不随本镜像改变；
- 内核版本 `v2.70`：另一个内部组件版本，不是 BIOS Version；
- BIOS Version `1.0-3`：主 BIOS 固件版本，由原厂 `1.0` 改为 `1.0-3`；
  `dmidecode -s bios-version` 已实机确认显示 `1.0-3`。

版本号更新只需改 `scripts/rebuild_bios.py` 的 `CUSTOM_VERSION`（当前 3）；
脚本会自动更新文件名、BIOS Version 块（`0xBF0098`）、VersionInfoPeim
默认版本字符串和复制长度。标签需小于 8 字符（如 `1.0-4`、`1.0-10`）。

---

## 2. 问题与根因

### 2.1 现象

- Vega 20 在 Linux/OS 中正常（amdgpu），但 BIOS POST/Setup 无显示。
- 同一块主板插 Radeon 520（Polaris/Lexa）时，BIOS 界面正常。

### 2.2 根因

1. BIOS 是 EDK2 AArch64 固件，DXE 阶段通过 GOP 驱动提供显示。
2. BIOS 内的 `Arm64Gop`（GUID `43b59c81-9c5f-4021-b0f2-947db2191781`）与 AMD 官方
   `drivers/Arm64Gop_1_68.efi` **字节完全一致**。
3. 该驱动用一张 16 字节/条的设备区间表匹配 AMD 显卡；表里没有 Vega 20 的
   `0x66A0–0x66AF`，也没有 Vega 10 的 `0x6860–0x687F`。
4. 显卡自带 VBIOS 只有 Legacy x86 VBIOS 和 **x86_64 EFI GOP**
   （`GOP AMD REV: 2.13`，machine `0x8664`，Tiano 压缩），**没有 ARM64 GOP**。
5. BIOS DXE 里没有 `EbcDxe`，EBC/其他架构的 GOP 也无法执行。
6. 因此固件没有任何驱动能为 Vega 20 建立 GOP → BIOS 没有可用的显示输出。

Radeon 520 能显示，是因为它的 Polaris 区间在表中。

---

## 3. 1.68 驱动的匹配逻辑

区间表基址 PE `0x1D210`（代码 `0xB9E0` 处字面量）。每条 16 字节：

```
u16 family_code;   // 低字节 group，高字节 family index
u16 start_devid;
u16 end_devid;
u16 pad;
u64 name_array_ptr;
```

名字表每条 16 字节：

```
u32 devid;
u32 pad;
u64 name_str_ptr;
```

关键条目：

| 用途 | PE 偏移 | 内容 |
|---|---|---|
| 拟复用区间 | `0x1D320` | family `0x0107`，range `0x1304–0x131D`，name array `0x1DD90` |
| 名字表首项 | `0x1DD90` | 原 id `0x1304`（`"KV SPECTRE MOBILE 35W"`），str `0x195B8` |
| 名字表第二项 | `0x1DDA0` | id `0x1305`，str `0x195D0` |
| VegaM 名字 | `0x1CF60` | id `0x6940`，str `0x191D0`（`"AMD Radeon VegaM Graphics"`） |

查找逻辑（`0xB8D0`）：

1. 对每个区间条目，先扫描它的 name array：
   - 如果 name entry 的 `devid` 等于目标设备 ID，**直接返回**，不再检查 range。
   - 扫描到 `devid == 0` 的结束项后，才检查 `start_devid ≤ devid ≤ end_devid`；
     在区间内则返回 family 和兜底名字。
2. 因此把某条 name array 里的一个名字项改成 `0x66A1`，查找就会命中，即使该
   区间条目的 range 原本是别的设备。

family 字节不是初始化 handler 选择器：`Start` 由 VBIOS/ATOMBIOS 驱动，
`Supported()` 只做 PCI 设备 ID 与 VBIOS ROM 设备 ID 的 same-family 比较。
开发中曾用最小 16 字节名字表补丁让旧 1.68 绑定 `0x66A1`，实机证明旧驱动的
Start 仍不能初始化 Vega 20（详见第 7.3 节），因此最终改用 2.10 驱动。

---

## 4. 固件结构与关键偏移

### 4.1 BIOS 顶层

| 区域 | 偏移 / 大小 |
|---|---|
| BIOS FV1 | `0x800000`，len `0x60000` |
| BIOS FV2（含压缩 DXE FV） | `0x860000`，len `0x320000` |
| BIOS FV3 | `0xb80000`，len `0x10000` |
| 版本/其他 FV | `0xbd0000`、`0xbf0000` |

### 4.2 压缩 DXE FV

| 项 | 原厂值 |
|---|---|
| 外层 FFS 文件 | 绝对 `0x983770`，GUID `9e21fd93-9c72-4c15-8c4b-e77f1db2d792`，type `0x0B`，原 size `0x1EC5A1` |
| GUIDed LZMA section | 绝对 `0x983788`，type `0x02`，原 size `0x1EC589`，GUID `ee4e5898-3914-4259-9d6e-dc7bd79403cf`，DataOffset `0x18`，attrs `0x01` |
| LZMA 头 | 绝对 `0x9837A0`：props `0x5D`，dict `0x01000000`，uncompressed size `0xDEA4C0` |
| 解压后 section stream | raw section（`0x19`, size `0x7C`）+ FV image（`0x17`, size `0xDEA444`） |
| 内层 FV | 解压后偏移 `0x80`，len `0xDEA440`，hdr `0x48` |
| Arm64Gop FFS（1.68） | 内层 FV 相对偏移 `0x9A51B8`，size `0x216F2`，type `0x07` |
| Arm64Gop PE32（1.68） | section body 偏移 `0x91A054`，大小 `0x216C0`（136896 字节） |

### 4.3 1.0-3 追加的 2.10 FFS

| 项 | 值 |
|---|---|
| 插入位置 | inner FV `0xE755B8`（最后一个 FFS 的对齐末尾） |
| FFS GUID | `92F10585-FB63-430F-8188-71FEEB2DDA5B` |
| UI 名 | `ARM64Gop 2.10` |
| PE32 section | type `0x10`，size `0x18E34`（PE `0x18E30`） |
| UI section | type `0x15`，size `0x20` |
| FFS size | `0x18E6C`，header checksum `0x7C`，File checksum `0xAA` |
| inner FV 新长度 | `0xE8E440`；block map `0x3A391 × 0x40`；header checksum `0x6DD0` |
| inner stream | FV image section size `0xE8E444`，总长 `0xE8E4C0` |
| outer section / FFS | `0x1EDD63` / `0x1EDD7B`；FV2 余量 `0xEB15`（60,181 字节） |

### 4.4 BIOS Version 字段修改

- 版本信息块绝对 `0xBF0098`：8 字节字段 `1.0` → `1.0-3`
  （`31 2e 30 00 00 00 00 00` → `31 2e 30 2d 33 00 00 00`）。
- VersionInfoPeim 的默认 BIOS Version 字符串 `1.0`（绝对 `0x89B144`）
  改为 `1.0-3`；同处构建 HOB 时只复制 4 字节，已把复制长度指令
  （绝对 `0x897D2C`，`mov x2, #4`）改为 `mov x2, len(tag)+1`，
  修复 `1.0-` 截断。
- 该 HOB 是 Setup 动态 BIOS Version 和 SMBIOS Type 0 BIOS Version 的来源；
  `dmidecode -s bios-version` 已实机确认显示 `1.0-3`。
- EC 版本字段绝对 `0xBF0058` 保持 `0.23`；EC 版本由 PlatformSetupDxe
  通过 `Get EC Version` 从 EC 读取，和 BIOS 字符串无关。
- 内核版本 `v2.70` 及 BIOS Revision/Firmware Revision `0.23` 不做修改。
- **Setup 静态 HII 标题不修改**，仍显示 `Byosoft ByoCore BIOS V1.0`；
  标题和 BIOS Version 字段是两套独立字符串，本次只改 HOB/BIOS Version
  字段。此前尝试扩展 HII 标题包未能达到预期，相关改动已全部撤销。

### 4.5 1.0-3 开机 LOGO 替换

| 项 | 值 |
|---|---|
| FFS GUID | `7BB28B99-61BB-11D5-9A5D-0090273FC14D`（freeform） |
| 原 FFS size | `0x14E4E`（85,582 字节） |
| 新 FFS size | `0x9FFCE`（655,310 字节）；增量 `0x8B180` = 4,451 × `0x80` |
| raw section | type `0x19`，BMP body `655,254` 字节；另含一个 26 字节 raw padding section |
| inner FV 偏移 | `0x8A30A4`（BMP raw section body） |
| 原图 | 300x95 24-bit BMP，黑底 PowerLeader LOGO |
| 新图 | `images/Huawei-Logo.bmp`，840x260 24-bit BMP，内容 820x240 |
| 源图 | `images/Huawei-Logo.wine.png`（3000x2000，透明背景） |
| 新 BMP SHA-256 | `8944e3ebd1b135d90af3e1b1dfeb7c7229b3f12e861f3727af548dfcc21393dd` |

- 从源 PNG 裁到 alpha 内容，重新着色为黑底白字 + 红色花瓣，缩放到
  820x240 后居中放进 840x260 画布（水平 10px、垂直 10px 边距）；
- 实测固件 GOP 宽度为 1024（1024 宽图正好占满屏幕），4:3 GOP 在 4K
  显示器上被横向拉伸 4/3；因此 BMP 内容按约 3.42:1 预补偿（820x240），
  经显示器拉伸后恢复源图约 4.54:1，实际占屏幕宽度约 80%；
- 新 BMP body 655,254 字节，LOGO FFS 从 `0x14E4E` 扩到 `0x9FFCE`；为使
  后续所有 FFS 的 `0x80` 对齐残差保持不变，增加 28 字节对齐填充，使
  FFS 大小增量 `0x8B180` 为 `0x80` 的整数倍；
- 扩容后重建 inner FV（`0xDEA440` → `0xE8E440`），后续 FFS 整体按原有
  对齐平移；raw section 无校验和，FFS header checksum 已重算；
- inner FV 距 3-byte FV image section 的 16 MiB 上限还有 `1,514,432`
  字节余量；
- **尺寸调试记录**：1792x403 24-bit（BMP 2.17 MB，解码缓冲约 2.9 MB）
  实机 LOGO 黑屏但系统能进 OS；1024x230 24-bit 能显示，但宽度占满且被
  压扁；因此改用 840x260、内容 820x240 的 4:3→16:9 预补偿版本。
- **实机验证（2026-10-31）**：840x260 预补偿版本显示正常，比例正确、
  大小合适，宽度约屏幕 80%，不再黑屏或占满。

---

## 5. AMD post-SoC15 ARM64Gop 2.10

- 来源：AMD 官方 AArch64 GOP 包（含 pre-SoC15 1.68 与 post-SoC15 2.10），
  见于 edk2-rockchip non-OSI：
  `edk2-rockchip-non-osi/Drivers/AMD/Gop/AArch64/`。
- 文件：`drivers/ARM64Gop_2_10.efi`
  - 大小：101,936 字节（`0x18E30`）
  - SHA-256：`c0b47fe3a16718666565e0a19a9d85d0eccbff2a8c71145cc082a5abc6bb4259`
  - PE32+ AArch64，DXE driver
  - 带 AMD Authenticode：Security 目录 `0x16C00` / `0x2230`，PE checksum `0x24A69`
- 设备表（PE `0x15B40`，6 字节/条）：

| family | 范围 | 说明 |
|---|---|---|
| `0x0110` | `0x6860–0x687F` | Vega 10 |
| `0x0210` | `0x69A0–0x69AF` | Vega 12 |
| `0x0310` | `0x66A0–0x66AF` | **Vega 20** |
| `0x0111` 等 | 其他 | Navi/后续 ASIC |

- 与旧 1.68 不同：2.10 是 **post-SoC15** 驱动，设备表原生包含 Vega 10/12/20；
  不需要改名字表/设备表，PE 签名保持完整。
- 限制：post-SoC15 表里没有 Polaris `0x67C0–0x67FF` / `0x6980–0x699F` 等，
  所以 Radeon 520 由保留的原 1.68 驱动负责。

---

## 6. 1.0-3 的构建方式

`scripts/rebuild_bios.py` 默认（也是唯一）构建当前版本 1.0-3：

1. 读取原厂镜像，校验 SHA-256 为原厂镜像，检查 FV2/外层 FFS/GUIDed LZMA
   section 结构。
2. 解压 inner LZMA stream，定位原 1.68 Arm64Gop FFS（inner `0x9A51B8`，
   size `0x216F2`），确认 PE SHA 为 `22021e0a...`，**字节不变**。
3. 把版本信息块 BIOS Version 字段 `1.0` 改为 `1.0-3`（§4.4）；替换/扩容
   开机 LOGO（§4.5），后续 FFS 按原有 `0x80` 对齐整体平移；EC 版本
   `0.23` 不变。
4. 新建 2.10 FFS（GUID `92F10585-...`，UI `ARM64Gop 2.10`）：
   PE32 section `0x10` + UI section `0x15`，FFS 大小 `0x18E6C`。
5. 追加到 inner FV 最后一个文件的对齐末尾 `0xE755B8`；FV 长度按块表 `0x40`
   对齐到 `0xE8E440`，block map `0x3A391 × 0x40`，重算 FV header checksum。
6. 重新压缩 inner stream（LZMA1，lc=3/lp=0/pb=2，dict 16 MiB），重建外层
   GUIDed/LZMA section 和 FFS，更新外层 FFS size/checksum，释放尾部填 `0xFF`。
   本次 outer section `0x1EDD63`、outer FFS `0x1EDD7B`，FV2 余量
   `0xEB15`（60,181 字节）。
7. 自检：
   - 136 个 inner FFS、FV/FFS header checksum；
   - block map 乘积等于 FvLength；
   - 旧 1.68 PE SHA `22021e0a...` 不变；
   - 新 2.10 PE SHA `c0b47fe3...`；
   - BIOS Version 字段为 `1.0-3`；EC 0.23 保持原厂；
   - 输出开机 LOGO 与 `images/Huawei-Logo.bmp` 逐字节一致；
   - LZMA 解压回读、outer/inner 结构检查；
   - diff 位于 outer FFS 和版本信息块 `0xBF0098` 字段。

产物：

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `firmware/modified/BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin` | 16,777,216 | `5951f282a0ebb03a0e886a49a1623db4796257e8c755b7dfe7c4b0e2d20da330` |

---

## 7. 实机验证

### 7.1 测试环境

- 主板：Kunpeng Desktop Board **D920L11K-2251K**（板号 BC32MBHB），aarch64。
- 测试时主要只插 **Vega 20**（`06:00.0`，`1002:66A1`）；OS 中 amdgpu 加载为 `card0`。
- 编程器写完整 16 MiB；SPI 芯片可插拔。
- 原厂镜像备份 SHA-256：`e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704`。

### 7.2 1.0-3 结果

- **Radeon 520**：原 1.68 驱动正常显示，行为与原厂一致。
- **Vega 20**：BIOS POST/Setup 画面正常；内核日志出现
  `simple-framebuffer.0` / `simpledrm`，证明固件 GOP 已初始化并向 OS 交接
  framebuffer；随后 amdgpu 接管（`VEGA20 0x1002:0x66A1`，
  ATOM BIOS `113-D1640600-104`）。
- **Radeon 520 + Vega 20 同插**：两张卡的 BIOS 显示均正常；BIOS 控制台可能
  只挂在其中一块显示器，属于 BDS/ConSplitter 选择，以 OS 下 amdgpu 为准。
- 1.0-3 的 GOP 部分沿用已实机验证的方案；开机 LOGO 已实机验证：
  840x260 预补偿版显示正常、比例/大小合适、约 80% 屏宽；
  BIOS Version 字段已改为 `1.0-3`，EC 版本 `0.23` 保持原厂；
  `dmidecode -s bios-version` 已实机确认为 `1.0-3`。
- **刷写方式**：BIOS Setup 内置固件升级已实机验证可用（无需编程器）；
  把镜像复制到 U 盘后，在升级界面选择文件名
  `BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin`（没有目录路径）。
  SPI 编程器方式保留用于离线刷写/恢复。

### 7.3 开发过程中的验证结论

- 固件 DXE 内含 `DxeImageVerificationLib`（SecurityStubDxe，
  GUID `F80697E9-7FD6-4665-8646-88E33EF71DFC`），会校验带签名的 PE。
- 改坏原 1.68 PE 的 Authenticode 后实机**完全不能启动**；把 Security 目录
  清零后能进 DXE，但 BIOS 仍无 Vega 20 显示。说明签名策略生效，且旧 1.68
  驱动的 Start 不能初始化 Vega 20，问题不在重建/刷写方式。
- 只改未签名 PE 字符串并重压缩/重建外层 FFS 的镜像能正常启动，证明
  LZMA/FFS/FV 重建和刷写链路正确，平台没有对 BIOS 区做强制整体签名/哈希。
- 因此最终方案是保留原 1.68（签名完整）并追加原生支持 Vega 20 的 2.10
  （签名完整），两者互不替换。

### 7.4 RX 5700 XT（不支持）

- 只插 RX 5700 XT：开机 **1 长 8 短蜂鸣（显示测试失败）**，无法启动。
- 双卡（RX 5700 XT + 520）：能进 Linux，但 `lspci` 只看到 520，没有
  `1002:731f`；root port 后的总线为空。
- 对调插槽后 520 在第一槽 x16（`04:00.0`）正常；RX 在第二槽仍不枚举。
- 把 root port target 强制改为 Gen2、Gen1 后，`LnkSta` 始终
  `2.5GT/s x1, DLActive-`，链路完全没建立。
- 该卡在另一块 x86 主板上正常，说明是 RX 与 Kunpeng 的 **PCIe 电气/链路层
  不兼容**，不是 GOP/BIOS 能解决的问题；本平台不支持。

---

## 8. 风险与限制

- **RX 5700 XT**：2.10 设备表覆盖 Navi 10，但平台 PCIe 不枚举，实际不支持。
- **RX 6000（RDNA2）**：主流 ID 不在 2.10 设备表内，本次不支持。
- **签名策略**：两个 PE 都保留 AMD 签名；若以后换驱动，需保持签名完整或按
  平台策略处理。
- **恢复**：芯片可插拔，原厂镜像 `e900c384...` 可随时用编程器恢复。
- **刷完整镜像会覆盖 NVRAM**：若 OS 启动项丢失，可在 Setup/Boot Manager
  重新选择或从 ESP 启动。

---

## 9. 复现命令

```bash
# 构建当前版本 1.0-3（固定输出）
python3 scripts/rebuild_bios.py

# 结构检查
uefiextract "firmware/modified/BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin" report
```

> 可重复性：脚本每次都从原厂镜像（`--src` 默认）重建，**不会读取上一次
> 输出**；同一源镜像、同一驱动和同一 libLZMA 下重复运行输出 SHA-256 相同
> （本机多次验证为 `5951f282a0ebb03a0e886a49a1623db4796257e8c755b7dfe7c4b0e2d20da330`）。
> 源镜像只读；写盘在全部自检通过之后才发生。换 Python/liblzma 版本可能改变
> 压缩字节从而改变哈希，但解压后的内容与结构校验不变。若输出文件已存在且
> 内容不同，脚本会拒绝覆盖；确认覆盖时加 `--force`。

---

## 10. 文件清单

| 文件 | 用途 |
|---|---|
| `firmware/original/BC32MBHB-D920L11K-2251K_1.0_2020-07-22.bin` | 原始固件备份（`e900c384...`） |
| `firmware/modified/BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin` | 当前定制版本；Radeon 520 + Vega 20（`5951f282...`） |
| `drivers/Arm64Gop_1_68.efi` | 原厂 pre-SoC15 AArch64 GOP（与 BIOS 内原 PE 字节一致，`22021e0a...`） |
| `drivers/ARM64Gop_2_10.efi` | AMD post-SoC15 AArch64 GOP，原生 Vega 10/12/20（`c0b47fe3...`） |
| `images/Huawei-Logo.wine.png` | 开机 LOGO 源图（3000x2000，透明背景） |
| `images/Huawei-Logo.bmp` | 固件用 840x260 24-bit 开机 LOGO（`8944e3eb...`） |
| `reference/vbios.rom` | Vega 20 显卡 VBIOS dump |
| `reference/AMD.RadeonProVII.16384.200818.rom` | 参考 VBIOS |
| `reports/BC32MBHB-D920L11K-2251K_1.0_2020-07-22.bin.report.txt` | 原厂镜像 UEFIExtract 结构报告 |
| `reports/BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin.report.txt` | 1.0-3 镜像 UEFIExtract 结构报告 |
| `scripts/rebuild_bios.py` | 解压/追加 GOP/替换版本与 LOGO/重压缩/重建镜像，带自检 |
| `docs/FLASH_GUIDE.md` | 直接刷写步骤 |

---

## 11. 参考链接

- AMD 官方 AArch64 GOP（pre-SoC15 1.68）：`https://download.amd.com/drivers/Arm64Gop_1_68.efi`
- AMD AArch64 release notes：`https://www.amd.com/en/support/kb/release-notes/rn-aar`
- AMD post-SoC15 AArch64 GOP（含 `ARM64Gop_2_10.efi`，edk2-rockchip non-OSI）：
  `https://atomgit.com/mainline-rock/edk2-rk3588/tree/824e6c12168a51cf72470fb43da60642e835198f/edk2-rockchip-non-osi`
- Ampere ARM64 社区讨论：`https://community.amperecomputing.com/t/aarch64-uefi-driver-for-amd-gpus-for-graphics-output-during-boot/791`
- AArch64 option ROM 构建参考：`https://www.workofard.com/2020/12/aarch64-option-roms-for-amd-gpus/`
- UEFIRomExtract：`https://github.com/andyvand/UEFIRomExtract`
- Tiano 解压源码：`https://github.com/sstjohn/python-eficompressor`
