# 鲲鹏 920 + Vega 20：BIOS 界面显示修改记录

- 日期：2026-10-31
- 主板：Kunpeng Desktop Board **D920L11K-2251K**（鲲鹏 920）
- 固件：`firmware/original/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22).bin`，16 MiB，版本 0.23 / 2020-07-22
- 显卡：AMD **Vega 20**（Radeon Pro VII / Instinct MI50），PCI ID `1002:66A1`
- VBIOS：`113-D1640600-104`，104448 字节
- 目标：只修改主板 BIOS（不改显卡 VBIOS），让 Vega 20 在 BIOS POST/Setup 显示
- 当前状态：**最小补丁镜像已生成并通过静态校验；用户决定跳过 Shell 测试，直接刷写；尚未实机刷写**

> 重要修正：早期方案给 device range 表补 `0x66A0–0x66AF` 并设置 family 0x070B，
> 以为 family 字节会选择 VegaM 初始化路径。复核反汇编后确认：**family 字节不是 handler
> 选择器**，只在 `Supported()` 里做 PCI 设备 ID 与 VBIOS ROM 设备 ID 的 same-family
> 比较；驱动 Start 是 VBIOS/ATOMBIOS 驱动的。真正需要的是让 `0x66A1` 在查找中命中。
> 因此改为**最小 16 字节名字表补丁**。

---

## 1. 问题与根因

### 1.1 现象

- Vega 20 在 Linux/OS 中正常（amdgpu），但 BIOS POST/Setup 无显示。
- 同一块主板插 Radeon 520（Polaris/Lexa）时，BIOS 界面正常。

### 1.2 根因

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

## 2. 驱动匹配逻辑（修正后的关键结论）

### 2.1 设备区间表

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

### 2.2 查找顺序

`0xB8D0` 的查找逻辑：

1. 对每个区间条目，先扫描它的 name array：
   - 如果 name entry 的 `devid` 等于目标设备 ID，**直接返回**，不再检查 range。
   - 扫描到 `devid == 0` 的结束项后，才检查 `start_devid ≤ devid ≤ end_devid`；
     在区间内则返回 family 和兜底名字。
2. 因此，只要把某条 name array 里的一个名字项改成 `0x66A1`，查找就会命中，
   即使该区间条目的 range 原本是别的设备。

### 2.3 family 字节的作用

- `0xB8D0` 把 `family_code` 的低/高字节写入输出，但 **Start 不调用这个查表函数**，
  也没有按 family index 分发初始化代码。
- `Supported()` 的 same-family 检查（`0x53AC`）会分别查 PCI 设备 ID 和 VBIOS ROM
  设备 ID，并比较 family 字节。由于两者都是 `0x66A1`，使用同一张修改后的表，
  family 字节相同即可通过。
- 初始化由 Start（`0x22A8`）读 VBIOS/ATOMBIOS 完成。**family 0x070B 不会选择
  VegaM 初始化路径**；早期方案的这一假设不成立。

---

## 3. 推荐补丁：最小 16 字节

只改 PE `0x1DD90` 的名字表项为：

```
a1 66 00 00 00 00 00 00 d0 91 01 00 00 00 00 00
```

即 `{devid=0x66A1, pad=0, name_str=0x191D0}`。

- 区间条目 `0x1D320` 保持不变（family `0x0107`，range `0x1304–0x131D`）。
- 查找 `0x66A1` 时，name array 首项命中，返回 family `0x0107` 和有效名字指针。
- `0x1305+` 的名字项不受影响；`0x1304` 的原名字项被覆盖，但 range 检查仍可兜底。
- Radeon 520 的 Polaris 区间完全未动。
- 显示名会显示为 “AMD Radeon VegaM Graphics”（仅外观）。

可选：把 PE Security 目录清零，做成未签名 PE（见 5.2）。

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

| 项 | 值 |
|---|---|
| 外层 FFS 文件 | 绝对 `0x983770`，GUID `9e21fd93-9c72-4c15-8c4b-e77f1db2d792`，type `0x0B`，原 size `0x1EC5A1` |
| GUIDed LZMA section | 绝对 `0x983788`，type `0x02`，原 size `0x1EC589`，GUID `ee4e5898-3914-4259-9d6e-dc7bd79403cf`，DataOffset `0x18`，attrs `0x01` |
| LZMA 头 | 绝对 `0x9837A0`：props `0x5D`，dict `0x01000000`，uncompressed size `0xDEA4C0` |
| 解压后 section stream | raw section（`0x19`, size `0x7C`）+ FV image（`0x17`, size `0xDEA444`） |
| 内层 FV | 解压后偏移 `0x80`，len `0xDEA440`，hdr `0x48`，checksum `0xD6DA` |
| Arm64Gop FFS | 内层 FV 相对偏移 `0x91A038`，size `0x216F2`，type `0x07`，header checksum `0x68`，File byte `0xAA` |
| Arm64Gop PE32 | section body 偏移 `0x91A054`，大小 `0x216C0`（136896 字节） |
| FV2 尾部空闲 | 原 FFS 结束 `0xB6FD11`；对齐后约 `0x102E8` 字节 |

---

## 5. 已完成的工作

### 5.1 最小补丁驱动

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `drivers/Arm64Gop_vega20_min.efi` | 136,896 | `2725856b67db87eab2db93e7a15d803d3ef6515b3c5aa539d24def2b9aff7871` |
| `drivers/Arm64Gop_vega20_min_unsigned.efi` | 136,896 | `39b41680c4180bb08336ecbdc5bca70817496b788e2d70930a32872bf19b1039` |

- 最小补丁：PE `0x1DD90` → `0x66A1` 名字项；PE checksum 重算。
- unsigned 变体：同上，并把 PE Security 目录（文件偏移 `0x1F560`，size `0x2160`）
  清零，PE 变为未签名。

### 5.2 BIOS 镜像

| 文件 | 大小 | SHA-256 | 说明 |
|---|---:|---|---|
| `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min.bin` | 16,777,216 | `602a60d31ff16627c7906ab2c61cce92bd7b67724fded1640012e8696ac75775` | 首选：最小补丁，签名失效 |
| `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min-unsigned.bin` | 16,777,216 | `b59a567ee0630caadfbed58bcf2b2b63c2662670f3fda479a8a8346e0e159b06` | 备用：最小补丁 + PE 未签名 |
| `firmware/original/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22).bin` | 16,777,216 | `e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704` | 原始备份 |

构建流程：

1. 解压完整的内层 LZMA section stream（`0xDEA4C0` 字节）。
2. 定位内层 Arm64Gop FFS/PE32，替换 PE（大小不变）。
3. 重新压缩完整 stream：LZMA1（lc=3/lp=0/pb=2，dict 16 MiB），
   header 的 uncompressed size 显式写 `0xDEA4C0`。
4. 重建外层 GUIDed section 和 FFS；新 section 更小，因此：
   - 缩小外层 FFS size；
   - 更新 Size 字段和 Header checksum；
   - 原 FFS 尾部释放区填 `0xFF`；
   - File checksum 字节保持 `0xAA`。
5. 自检：
   - 所有 FV/FFS header checksum；
   - 解压回读，确认输出 PE 与补丁驱动一致；
   - UEFIExtract 结构检查：与原镜像一样只有两条告警，无额外 section 告警；
   - diff：只改 `0x983780–0xB6FD10` 的外层 FFS 区域。

### 5.3 早期 48 字节 family 变体（已删除）

- 早期曾生成 `Arm64Gop_vega20_fam1..7.efi` / `KP920-2251K-BD-fam1..7.bin`。
- 这些版本给 range 表补 `0x66A0–0x66AF` 并设置 family `0x0Bxx`。复核确认 family
  不是初始化 handler 选择器，且 48 字节补丁会改变 `0x1306+` 的 family 并覆盖
  `0x1304/0x1305` 的名字项；**已全部删除**，不再使用。

### 5.4 未完成

- **尚未实机刷写**；
- 尚无 Vega 20 在 BIOS 中成功显示的证据。

---

## 6. 直接刷写方案（用户决定跳过 Shell 测试）

详见 `docs/FLASH_GUIDE.md`。顺序：

1. 首选 `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min.bin`。
2. 若 BIOS 能启动但 Vega 20 仍无显示，而 OS 仍能启动：
   换 `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min-unsigned.bin`。
3. 若完全不能启动：恢复原镜像。
4. 若 unsigned 仍无显示：恢复原镜像，走兜底（Radeon 520 显示 BIOS + Vega 20
   用于 OS，或串口/BMC，或寻找其他 AArch64 GOP）。

---

## 7. 风险与限制

- **PE 签名**：原 AMD PE 带 Authenticode（Security 目录 `0x1F560`，size `0x2160`）。
  最小补丁会使其失效；Secure Boot 已关闭，通常不校验，但平台策略仍可能拒绝。
  unsigned 变体是备用路径。
- **最大实际风险**：这是 UDK2014/ATOMBIOS 时代的旧 AArch64 GOP，表里连 Vega 10
  都没有；即使绑定成功，Start 能否初始化 Vega 20 仍未知。
- **启动链校验**：只验证了 FV/FFS 层；未确认 IMU/SBL 是否对 BIOS 区做签名/哈希。
  没有第二份 BIOS 副本（镜像最后 4 MiB 为空白）；刷坏用编程器恢复原镜像。
- **最小补丁副作用**：覆盖了 `0x1304` 的名字项（range 兜底仍可用），`0x1305+`
  不受影响；Radeon 520 的 Polaris 区间未动。
- **显示名**：可能显示为 “AMD Radeon VegaM Graphics”，仅外观。
- **未实测**：以上镜像尚未在实机验证；文档中的“完成”指构建和静态校验完成。

---

## 8. VBIOS x64 GOP 2.13 分析（参考）

从 `reference/vbios.rom` 的 `0xEA50` 处用 EFI/Tiano 解压器解出 x86_64 GOP：

- 压缩头：CompressedSize `0xAC5B`，OrigSize `0x12300`
- 解压后：74,496 字节，PE32+ x86_64，`GOP AMD REV: 2.13`
- 设备表是 **6 字节/条**：`u16 family_code; u16 start; u16 end`
- Vega 10（`0x6860–0x687F`）：`0x0110`
- Vega 12（`0x69A0–0x69AF`）：`0x0210`
- Vega 20（`0x66A0–0x66AF`）：`0x0310`

这确认卡自带 GOP 支持 Vega 20，但它是 x86_64 代码，不能直接在 AArch64 上执行。
x64 的 family 编码也不能直接套到 AArch64 1.68；AArch64 的 family 字节本身不是
初始化 handler 选择器。

---

## 9. 文件清单

| 文件 | 用途 |
|---|---|
| `firmware/original/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22).bin` | 原始固件备份 |
| `reference/vbios.rom` | 显卡 VBIOS dump |
| `drivers/Arm64Gop_1_68.efi` | AMD 官方 AArch64 GOP（与 BIOS 内 PE 字节一致） |
| `drivers/Arm64Gop_vega20_min.efi` | 最小补丁驱动（首选） |
| `drivers/Arm64Gop_vega20_min_unsigned.efi` | 最小补丁 + 去签名（备用） |
| `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min.bin` | 首选修改镜像 |
| `firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min-unsigned.bin` | 备用修改镜像 |
| `scripts/build_patched_gop_min.py` | 生成最小补丁/unsigned 驱动 |
| `scripts/rebuild_bios.py` | 解压/替换/重压缩/重建镜像，带自检 |
| `docs/FLASH_GUIDE.md` | 直接刷写步骤 |

早期 fam 相关文件（驱动、镜像、测试脚本、旧 report）已删除。
哈希见第 5 节和 `docs/FLASH_GUIDE.md`。

---

## 10. 复现命令

```bash
# 最小补丁驱动 + unsigned 变体
python3 scripts/build_patched_gop_min.py

# 首选镜像
python3 scripts/rebuild_bios.py --patched drivers/Arm64Gop_vega20_min.efi \
  --out "firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min.bin"

# 备用 unsigned 镜像
python3 scripts/rebuild_bios.py --patched drivers/Arm64Gop_vega20_min_unsigned.efi \
  --out "firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min-unsigned.bin"

# 结构检查
uefiextract "firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min.bin" report
```

---

## 11. 参考链接

- AMD 官方 AArch64 GOP：`https://download.amd.com/drivers/Arm64Gop_1_68.efi`
- AMD AArch64 release notes：`https://www.amd.com/en/support/kb/release-notes/rn-aar`
- Ampere ARM64 社区讨论：`https://community.amperecomputing.com/t/aarch64-uefi-driver-for-amd-gpus-for-graphics-output-during-boot/791`
- AArch64 option ROM 构建参考：`https://www.workofard.com/2020/12/aarch64-option-roms-for-amd-gpus/`
- UEFIRomExtract：`https://github.com/andyvand/UEFIRomExtract`
- Tiano 解压源码：`https://github.com/sstjohn/python-eficompressor`
