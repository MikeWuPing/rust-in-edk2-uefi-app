# Rust-in-EDK2 UEFI 应用开发技能

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Skill](https://img.shields.io/badge/WorkBuddy-Skill-blue.svg)](https://www.workbuddy.cn/docs/workbuddy/Overview)

> 用 Rust 写 UEFI 应用的**业务逻辑**，图形与固件交互继续留在 C 侧（EDK2 + LVGL）。
> 本技能记录这条路上**每一个真炸过的坑**——尤其是那些不报错、只是悄悄不对的。

[English](README_EN.md) | 简体中文

## 简介

Rust 写 UEFI 应用有两条路：

1. **纯 Rust 路线** — 用 `uefi` crate（rust-osdev/uefi-rs），cargo 直接产出 `.efi`，不需要 EDK2。
2. **混合路线（本技能）** — Rust 只出静态库，由 **EDK2 做顶层链接器**，图形走 LVGL（C）。

第二条路的价值在于**复用既有 EDK2 工程的全部约定**：DSC/INF 体系、第三方 C 包、串口版本断言通道、vendored OVMF。代价是你要同时伺候三套工具链（cargo、EDK2 build、QEMU），而它们的失败方式各有各的阴险。

本技能不做泛泛的教程，只记**具体可执行的对策**，每条都标注了为什么会炸。

### 这些内容是从一个跑通的项目里长出来的

不是纸上推演。技能的每一节都来自 [rustpaint](https://github.com/MikeWuPing/rustpaint) —— 一个跑在 UEFI Shell 下的画图应用（Rust 逻辑 + EDK2 链接 + LVGL 9.2.2 + 中文 UI），在 QEMU 里实机验证到 v0.1.0.24。当前它的 C/Rust ABI 边界是 **58 个函数 + 50 个常量**，全部一致。

## 特性

- **三条链接硬规矩** — `/NODEFAULTLIB` 让 `/DEFAULTLIB:` 失效、库名撞 `BASE_NAME`、`[Binaries]` 段不参与链接
- **构建环境修复** — INCLUDE 缺 UCRT 导致所有 C 文件死在 `<stddef.h>`；`GenFw` 裸名调用找不到
- **PowerShell 5.1 陷阱** — 注释编码吞行尾、原生 stderr 重定向、`Start-Process` 环境块重复崩溃
- **QEMU 启动矩阵** — 只有一种写法能同时满足「窗口在桌面可见」+「输出能落盘」
- **QMP 闭环** — `screendump` 抓帧（规避 SDL 窗口抓屏必黑）、指针注入；含 Windows 上 `os.kill` 的坑
- **LVGL 静默陷阱** — 888 像素是 **B,G,R**；中文字库覆盖必须解析 cmap；默认不裁剪子对象
- **ABI 漂移校验** — 附 `check_abi.py`，把「C 头与 Rust 声明要同步」这条纪律变成可执行检查

## 目录结构

```
rust-in-edk2-uefi-app/
├── LICENSE
├── README.md                              本文件
├── README_EN.md
└── Skills/
    └── rust-in-edk2-uefi-app/
        ├── SKILL.md                        技能正文（278 行，全部内容就这一个文件）
        ├── evals/
        │   └── evals.json                  10 条评测用例
        └── templates/
            └── check_abi.py                C 头 ↔ Rust extern 声明一致性校验
```

## 安装

### 方法一：直接复制

把 `SKILL.md` 放进技能目录即可：

```bash
# WorkBuddy
mkdir -p ~/.workbuddy/skills/rust-in-edk2-uefi-app
cp Skills/rust-in-edk2-uefi-app/SKILL.md ~/.workbuddy/skills/rust-in-edk2-uefi-app/

# Claude Code
mkdir -p ~/.claude/skills/rust-in-edk2-uefi-app
cp Skills/rust-in-edk2-uefi-app/SKILL.md ~/.claude/skills/rust-in-edk2-uefi-app/

# Windows (cmd)
mkdir "%USERPROFILE%\.workbuddy\skills\rust-in-edk2-uefi-app"
copy Skills\rust-in-edk2-uefi-app\SKILL.md "%USERPROFILE%\.workbuddy\skills\rust-in-edk2-uefi-app\"
```

需要配套脚本时，把 `templates/` 一起复制。

### 方法二：Git Clone

```bash
git clone https://github.com/MikeWuPing/rust-in-edk2-uefi-app.git

# Linux/macOS
cp -r rust-in-edk2-uefi-app/Skills/rust-in-edk2-uefi-app ~/.workbuddy/skills/

# Windows (cmd)
xcopy /E /I rust-in-edk2-uefi-app\Skills\rust-in-edk2-uefi-app "%USERPROFILE%\.workbuddy\skills\rust-in-edk2-uefi-app"
```

## 快速开始

安装后直接提问即可触发，例如：

```
我想用 Rust 写一个 UEFI Shell 应用，但图形部分想继续用 LVGL，怎么组织？
Rust 编的 staticlib 链进 EDK2，报一堆 LNK2001 未解析符号，怎么办？
QEMU 里跑我的 .efi，怎么用脚本自动截图并注入鼠标操作来验证？
LVGL 里我按 RGB 写像素，为什么颜色是反的？
界面中文全是方框，怎么确认字库覆盖了哪些字？
```

## 内容目录

| 章节 | 内容 |
|------|--------|
| 0 | UEFI Shell 与语言无关：只认 PE/COFF + `EFI_APPLICATION` |
| 1 | 架构：Rust 出静态库，EDK2 做链接器 |
| 1.1 | shim 边界要配校验脚本，光立纪律不够 |
| 2 | 三条链接硬规矩（`/NODEFAULTLIB`、库名撞 `BASE_NAME`、`[Binaries]`、Version.h 不触发重编） |
| 3 | 构建环境（INCLUDE 缺 UCRT、`GenFw` 裸名、QEMU 磁盘需可引导项） |
| 4 | PowerShell 5.1 的四个陷阱 |
| 5 | 从 PowerShell 启动 QEMU：只有一个写法是对的 |
| 6 | QMP 抓帧的三个坑 |
| 7 | 自动化交互的 token 设计 |
| 8 | LVGL 静默陷阱：B,G,R 字节序、cmap 覆盖、不裁剪子对象、右对齐纪律 |
| 9 | 验收清单（每条都要留证据） |
| 10 | 排错顺序 |
| 附 | 点击坐标可以直接算，不用试 |

## 触发条件

遇到下列任一情况就会加载本技能：

- 应用逻辑用 Rust 写、渲染/固件层留在 C（EDK2 + LVGL）
- 把 cargo 的 `staticlib` 链进 EDK2 模块
- Rust 的 `.efi` 要作为普通 `EFI_APPLICATION` 跑在经典 UEFI Shell 下
- 在 LVGL 上做中文界面（字库覆盖检查）
- 用 Windows PowerShell 驱动 QEMU（启动 + QMP 抓帧/指针注入）

**不适用**：纯 Rust UEFI 固件（用 `uefi` crate 直接出 `.efi`）；纯 C 的 EDK2 应用。

## 配套脚本：check_abi.py

手写 C ABI shim 时，头文件与 Rust 的 `extern` 声明是一对孪生声明，靠人同步一定会漂。**两类漂移后果不对等**：

| 漏改 | 后果 |
|------|------|
| 漏一个函数声明 | 链接期 `LNK2001`，会报错，好发现 |
| 漏/写错一个**常量** | **编译期、链接期都不报错**，运行期静默取到错的值 |

用法：

```bash
# 默认布局：脚本放 <repo>/tools/ 下，自动定位头与 ffi.rs
python check_abi.py

# 换项目时指定路径与前缀
python check_abi.py --header path/to/shim.h --ffi path/to/ffi.rs --prefix RP_

# 两侧常量同名时用空前缀
python check_abi.py --prefix ''

python check_abi.py --verbose     # 列出全部符号
```

退出码：`0` 一致，`1` 有漂移，`2` 文件找不到。建议挂在构建流程最前面（cargo 之前）；Python 不在 PATH 时应跳过而非中断构建。

> 写这类校验脚本时**必须自己注入一次假漂移验证它能抓到**——两边都解析出 0 个符号时脚本也会「通过」，那是假绿。

## 快速参考

| 任务 | 要点 |
|------|------|
| Rust 出静态库 | `crate-type = ["staticlib"]`、`no_std`、`panic = "abort"`，目标 `x86_64-unknown-uefi` |
| 链进 EDK2 | 库作**输入文件**，`/DEFAULTLIB:` 无效；库名 ≠ `BASE_NAME` |
| Rust 侧入口返回值 | 用 `UINT64` 承载 EFI_STATUS，压成 32 位会把错误码截成看似成功的 `0x00000002` |
| INCLUDE 修复 | 脚本自行枚举 MSVC/SDK 目录，用 `Test-Path <dir>\ucrt\stddef.h` 校验，在 `edksetup.bat` **之后**覆盖 |
| 启动 QEMU | `cmd /c "start /b qemu.exe ... > out.log 2>&1"` |
| 抓帧 | monitor `screendump`（SDL 窗口抓屏必黑），存下后嗅探魔数确认是 PPM |
| 指针注入 | 拖动只能走相对位移；绝对定位用于精确落点校验 |
| 像素写入 | 888 是 **B,G,R**；行跨距用 `stride`，不能按 `w*3` |
| 字库检查 | 解析 cmap；SPARSE 表的 `unicode_list` 是**相对偏移**，不是绝对码位 |

## 相关资源

- [rustpaint](https://github.com/MikeWuPing/rustpaint) — 本技能的来源项目（Rust + EDK2 + LVGL 的 UEFI 画图应用）
- [EDK2](https://github.com/tianocore/edk2) — UEFI 参考实现
- [uefi-rs](https://github.com/rust-osdev/uefi-rs) — 纯 Rust 路线的应用封装
- [Patina](https://github.com/OpenDevicePartnership/patina) — 微软的 Rust UEFI 固件框架
- [LVGL](https://github.com/lvgl/lvgl) — 本技能使用的图形库（9.2.2）
- [UEFI 规范](https://uefi.org/specifications)

## 贡献

欢迎提交 Issue 和 Pull Request。

尤其是**踩到新的坑**——本技能的价值全在「真炸过」这三个字上。提交时请附上：

1. 实际报错信息或现象（不报错的那种更要写清楚现象）
2. 根因
3. 可执行的对策

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 许可证

本项目采用 [MIT](LICENSE) 许可证。

---

**注意**：技能正文 `SKILL.md` 供 AI 编码助手（WorkBuddy / Claude Code 等）在会话中自动加载使用。
