# BC32MBHB / D920L11K-2251K BIOS 修改说明

## 1. 固件身份

| 项目 | 值 |
|---|---|
| BIOS 项目 / 板代码 | **HuaweiDesktopCRBBC32MBHB**（CRB + **BC32MBHB**） |
| 产品 / 主板名 | **Kunpeng Desktop Board D920L11K-2251K** |
| DMI 板版本 | **XYABC** |
| BIOS 厂商 | **Byosoft** |
| BIOS Version | **1.0** |
| BIOS Release | **0.23** |
| 构建日期 | **2020.07.22** |
| DMI 日期 | **08/13/2020** |
| 平台 | **Hi1620_L_D920 / ARM1620** |
| 显卡 | AMD **Vega 20**，PCI ID `1002:66A1` |
| 显卡 VBIOS | `113-D1640600-104` |

`BC32MBHB` 是固件项目名 `HuaweiDesktopCRBBC32MBHB` 里的板代码（CRB + BC32MBHB）；
DMI 里报告的产品/主板名是 `Kunpeng Desktop Board D920L11K-2251K`。

---

## 2. 文件说明（重点）

**无 `-min` 后缀的文件是原始固件；带 `-min` / `-min-unsigned` 的是修改版。**

| 文件 | 是否修改 | 用途 | SHA-256 |
|---|---|---|---|
| `firmware/original/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22).bin` | **原始，未修改** | 原始固件备份 / 恢复 | `e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704` |
| `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min.bin` | **修改版** | 首选刷写 | `602a60d31ff16627c7906ab2c61cce92bd7b67724fded1640012e8696ac75775` |
| `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min-unsigned.bin` | **修改版（PE 未签名）** | 签名策略拒绝首选时的备用 | `b59a567ee0630caadfbed58bcf2b2b63c2662670f3fda479a8a8346e0e159b06` |
| `drivers/Arm64Gop_vega20_min.efi` | 补丁驱动 | 最小 16 字节补丁后的 GOP | `2725856b67db87eab2db93e7a15d803d3ef6515b3c5aa539d24def2b9aff7871` |
| `drivers/Arm64Gop_vega20_min_unsigned.efi` | 补丁驱动（未签名） | 备用 GOP | `39b41680c4180bb08336ecbdc5bca70817496b788e2d70930a32872bf19b1039` |
| `drivers/Arm64Gop_1_68.efi` | 原始 AMD 驱动 | 参考 / 构建源 | `22021e0a5a47cff0d48dd86161eb540a786604898b81da41c8b06983f762372f` |
| `reference/vbios.rom` | 显卡 VBIOS dump | 分析参考 | `ebd54002f79215bcb77c575ae8f1feec3b24ec9b34aa69ccb37143e7cc421222` |
| `reference/AMD.RadeonProVII.16384.200818.rom` | 参考 VBIOS | 对照分析 | — |
| `reports/*.report.txt` | 校验报告 | UEFIExtract 结构检查 | — |
| `scripts/build_patched_gop_min.py` | 构建脚本 | 生成最小补丁驱动 | — |
| `scripts/rebuild_bios.py` | 构建脚本 | 解压/替换/重压缩/重建 BIOS | — |
| `docs/FLASH_GUIDE.md` | 文档 | 刷写步骤 | — |
| `docs/KP920_VEGA20_BIOS_NOTES.md` | 文档 | 完整分析记录 | — |

文件名含空格和括号，终端/编程器软件里要加引号，例如：

```bash
"firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min.bin"
```

## 目录结构

```text
.
├── README.md
├── firmware/
│   ├── original/     # 原始固件（未修改）
│   └── modified/     # 修改版镜像（-min / -min-unsigned）
├── drivers/          # AMD 原始 GOP、补丁 GOP
├── scripts/          # 构建/重建脚本
├── docs/             # 刷写指南、完整分析记录
├── reference/        # 显卡 VBIOS / 参考 ROM
└── reports/          # UEFIExtract 校验报告
```

---

## 3. 修改内容

- 只改 BIOS 内压缩 DXE FV 里的 `Arm64Gop` PE：
  - PE 相对偏移 `0x1DD90` 的 16 字节名字表项改为 `0x66A1`。
  - 设备区间表、family 字节、其他设备条目都不动。
- 驱动 Start 走 VBIOS/ATOMBIOS；family 字节不是初始化 handler 选择器。
- BIOS 版本字段未改，刷入后仍报告 0.23 / 1.0。
- 原 AMD PE 带 Authenticode 签名；最小补丁会使其失效。
  `-min-unsigned` 版本把 PE Security 目录清零（未签名），作为备用。
- 未改前 8 MiB 的 bootloader/IMU、其他 FV 和 BIOS 版本区。
- FV / FFS / LZMA 已自检，UEFIExtract 结构与原镜像一致。

---

## 4. 刷写顺序

1. **首选**：刷
   `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min.bin`。
2. 如果 BIOS 能启动、但 Vega 20 仍无显示，而 OS 仍能启动：
   刷 `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min-unsigned.bin`。
3. 如果完全不能启动：用编程器恢复原始固件：
   `firmware/original/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22).bin`。
4. 如果两个修改版都不显示：恢复原始固件，走兜底方案
   （Radeon 520 用于 BIOS 显示 + Vega 20 用于 OS，或串口/BMC）。

刷写要点：

- 写入**完整 16 MiB 镜像**，写后读回校验 SHA-256。
- 先完全断电，再取/装 SPI 芯片；注意芯片电压和方向。
- 首次刷完只插 Vega 20，开机等待内存/IMU 训练，按 F2 进 Setup。
- 芯片已可插拔，失败可恢复；但没有第二份 BIOS，原始备份是关键。

---

## 5. 主要风险

- 这是 UDK2014/ATOMBIOS 时代的旧 AArch64 GOP；即使绑定成功，
  Start 能否初始化 Vega 20 仍未知。
- PE 签名失效；如果平台策略拒绝，试 `-min-unsigned`。
- 启动链是否对 BIOS 区做签名/哈希未完全确认；若完全不能启动，恢复原镜像。
- 最小补丁覆盖了 `0x1304` 的名字项（原区间检查仍可兜底），
  `0x1305+` 和 Radeon 520 的 Polaris 区间不受影响。
- 显示名可能显示为 “AMD Radeon VegaM Graphics”，仅外观。

---

## 6. 详细文档

- 刷写步骤：`docs/FLASH_GUIDE.md`
- 完整分析、偏移、补丁字节、风险：`docs/KP920_VEGA20_BIOS_NOTES.md`
