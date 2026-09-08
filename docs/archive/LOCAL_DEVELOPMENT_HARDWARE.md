# CareerAct 本地开发硬件升级方案

> 状态：硬盘升级方案已确定，内存升级按实测决定  
> 记录日期：2026-09-07

## 1. 当前设备

- 机型：HP ZBook Power 16 inch G11 Mobile Workstation PC；
- 处理器：Intel Core Ultra 7 155H，16 核 22 线程；
- 显卡：NVIDIA RTX 2000 Ada Laptop GPU；
- 内存：32GB DDR5-5600，由两条三星 16GB SO-DIMM 组成，两个插槽均已占用；
- 存储：一块三星 1TB NVMe SSD；
- 官方扩展能力：两个 M.2 2280 PCIe 4.0 ×4 插槽，最高支持两块 4TB SSD；两个 SO-DIMM 插槽，官方最高支持 64GB DDR5-5600。

这台移动工作站的处理器和整体性能足以承担 CareerAct 开发。当前最明确的限制是现有硬盘空间，不购买额外低性能二手主机。

## 2. 最终硬盘方案

保留现有 1TB 系统盘，在空闲的第二个 M.2 插槽增加一块独立的 2TB SSD：

- 主选：Samsung 990 PRO 2TB；
- 准确型号：`MZ-V9P2T0BW`；
- 规格：无散热片版、M.2 2280、PCIe 4.0 ×4、TLC、2GB DRAM；
- 耐久度：1200 TBW；
- 质保：5 年。

不替换原系统盘，不组 RAID。原盘继续保存 Windows、应用和个人文件；新盘专门保存 Docker Desktop / WSL 虚拟磁盘、镜像、数据库、构建缓存和 CareerAct 开发数据。

备选型号为 WD_BLACK SN850X 2TB 无散热片版，准确型号 `WDS200T2X0E-00BCA0`。只有主选缺货或价格明显不合理时才采用备选。

## 3. 性能边界

新增 SSD 必须满足以下条件，确保不降低原有存储性能：

- 安装在第二个 PCIe 4.0 ×4 插槽并正确协商为 PCIe 4.0 ×4；
- 使用适配笔记本内部空间的无散热片版本和对应导热垫；
- 不改动原系统盘，不因扩容降低 CPU、内存或原硬盘性能；
- 新盘持续性能、随机性能和耐久度不低于现有 OEM SSD 的开发需求；
- 安装后不存在掉盘、过热降速、休眠唤醒异常或 SMART 报错。

第二块 SSD 会增加少量功耗和发热，但正确安装时不应造成可感知的整机性能下降。

## 4. 购买与安装

- 首选京东的三星存储京东自营旗舰店；
- 下单前核对型号必须为 `MZ-V9P2T0BW`，不购买散热片版、散片、拆机盘、工包盘或来源不明的企业渠道盘；
- 价格不高于 2000 元时可购买；超过 2000 元则等待自营活动，不购买 HP 贴牌高价盘；
- 通过 [HP 官方服务中心](https://support.hp.com/cn-zh/help/service-center) 查找授权网点；
- 安装前确认授权网点允许携带自购 SSD，并确认不会影响整机保修；
- 要求安装至第二个 M.2 插槽并使用合适的导热垫，不替换原盘、不组 RAID。

## 5. 安装验收

安装后当场完成以下检查：

1. Samsung Magician 正确识别型号、序列号、容量和正品状态，并升级至稳定版固件；
2. CrystalDiskInfo / HWiNFO 显示接口为 PCIe 4.0 ×4，SMART 健康度正常；
3. CrystalDiskMark 顺序读取应接近该平台 PCIe 4.0 的正常水平，目标约 7000MB/s；
4. 连续读写压力测试期间无掉盘、I/O 错误或异常温度降速；
5. Windows 重启、关机、睡眠和唤醒后硬盘均正常识别；
6. 验收通过后再迁移 Docker Desktop 和 WSL 数据，迁移前保留备份。

## 6. 内存升级决策

当前不立即升级内存。先使用 32GB 完成全套开发环境搭建和端到端联调；出现以下任一情况时，再升级为两条相同型号的 32GB DDR5-5600 SO-DIMM：

- 完整开发环境下内存长期超过 85%；
- WSL 或容器出现 OOM；
- 持续使用大量 Swap 并造成明显卡顿；
- Steel / Chromium、Docling 与其他服务无法同时稳定运行。

升级时必须使用 `2 × 32GB`、JEDEC DDR5-5600、CL46、1.1V、Non-ECC、Unbuffered 的同型号套装，保持双通道和 5600 MT/s，不购买依赖 XMP 才能达到标称频率的内存。现有两条 16GB 内存需要同时替换。

## 7. 官方依据

- [HP ZBook Power 16 G11 官方规格](https://www8.hp.com/h20195/V2/GetPDF.aspx/c08954703)
- [HP 官方服务中心](https://support.hp.com/cn-zh/help/service-center)
- [Samsung 990 PRO 2TB 官方产品页](https://www.samsung.com.cn/memory-storage/nvme-ssd/990-pro-2tb-nvme-pcie-gen-4-mz-v9p2t0bw/)
