# 直接刷写指南（Vega 20 最小补丁版）

## 1. 刷哪个文件

### 首选

**`firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min.bin`**

- 最小 16 字节补丁：只把 Arm64Gop PE 的名字表项 `0x1DD90` 改成 `0x66A1`。
- 设备区间表、family 字节、其他设备条目都不动。
- 驱动 Start 走 VBIOS/ATOMBIOS；family 字节不是初始化 handler 选择器。
- 原 AMD PE 的 Authenticode 签名会因字节改动而失效；Secure Boot 已关闭，通常不会据此拒绝加载。

SHA-256：

```
602a60d31ff16627c7906ab2c61cce92bd7b67724fded1640012e8696ac75775
```

### 备用（签名策略拒绝首选时）

**`firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min-unsigned.bin`**

- 与首选相同的 16 字节补丁，并把 PE Security 目录清零（PE 变成未签名）。
- 如果首选能启动但 Vega 20 仍不亮、而 OS 仍能启动，说明可能是签名/镜像校验问题，换这个再刷。

SHA-256：

```
b59a567ee0630caadfbed58bcf2b2b63c2662670f3fda479a8a8346e0e159b06
```

### 不要刷

- 旧的 fam1..7 / `KP920-2251K-BD-vega20.bin` 等文件已经删除；
  如果从别处拿到同名旧文件，不要刷——它们基于早期的错误 family 假设。
- 除非有明确的新结论，否则不要混用。

---

## 2. 刷写步骤

1. 确认原镜像备份仍在：
   - `firmware/original/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22).bin`
   - SHA-256 `e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704`
2. 完全断电、拔电源线，取出 SPI 芯片。
3. 确认芯片型号、电压（3.3V / 1.8V）与编程器/转接座匹配。
4. 写入**完整 16 MiB 镜像**（不是只写 BIOS 区），写后读回校验。
5. 芯片装回，只插 **Vega 20**，开机；首次启动可能比平时久。
6. 按 F2 进 BIOS Setup，确认画面是否在 Vega 20 上出现。

---

## 3. 结果判断

### 3.1 BIOS 画面正常出现在 Vega 20

完成。进入 Setup 检查各菜单，再启动 OS 确认 amdgpu 正常。

### 3.2 能进 OS，但 BIOS/Setup 仍无显示

说明补丁驱动没有被加载、被镜像校验拒绝，或者 Start 初始化失败。按顺序：

1. 关机，换刷 **`firmware/modified/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-min-unsigned.bin`**，再试一次。
2. 若仍无显示：恢复原镜像，走兜底方案：
   - Radeon 520 作为 BIOS 显示卡，Vega 20 仅用于 OS；
   - 或串口/BMC console 管理 BIOS；
   - 或寻找其他支持 Vega 20 的 AArch64 GOP。

### 3.3 完全不能启动

说明启动链对 BIOS 区有签名/完整性校验，或重建/写入有误：

1. 用编程器恢复 `firmware/original/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22).bin`。
2. 若想进一步定位，可做一个“无功能改动”的重压缩镜像做金丝雀测试，区分：
   - 启动链校验（无功能改动也不启动）；
   - 补丁/驱动问题（无功能改动能启动）。

### 3.4 刷回原镜像

始终可直接写回：

```
"firmware/original/BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22).bin"
SHA-256 e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704
```

---

## 4. 这个镜像改了什么

- 只改 BIOS FV2 中的压缩 DXE FV：
  - 外层 FFS：绝对偏移 `0x983770`
  - GUIDed LZMA section：绝对偏移 `0x983788`
  - 内层 Arm64Gop PE：PE 相对偏移 `0x1DD90` 的 16 字节名字表项
- 未改前 8 MiB 的 bootloader/IMU、其他 FV、BIOS 版本区。
- 内层 FFS 头、外层 FFS 文件校验（0xAA sentinel）、FV header 校验均保持有效；
  LZMA 重新压缩后已解压回读验证。
- UEFIExtract 检查结果与原镜像一致：只有原镜像本来就有的两条告警
  （`file header parsing failed with invalid size`、`not a single Volume Top File`）。

---

## 5. 注意事项

- BIOS 芯片已可插拔，失败可恢复；但没有第二份 BIOS，**原镜像备份是关键**。
- 刷写前确认编程器电压/芯片型号，避免损坏芯片。
- 如果首选能启动但无显示，先试 unsigned 备用版，再考虑恢复原镜像。
- 最小补丁不会影响 Radeon 520 的 Polaris 区间；被覆盖的 `0x1304` 名字项
  仍可通过原区间检查兜底，`0x1305+` 不受影响。
- 显示名可能仍是 “AMD Radeon VegaM Graphics”，仅名字表复用，不影响功能。
